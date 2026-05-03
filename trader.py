"""
Trading logic module for executing orders via Polymarket CLOB.

This module handles:
- CLOB client initialization with L1/L2 authentication
- Market order execution via FAK (Fill-And-Kill)
- Balance and position management
- Thread-safe order execution with cooldown
- Football mode: 3 markets (Team1, Draw, Team2)

Order Strategy:
- BUY: FAK with price=0.99 as slippage protection, spends ~$amount
- SELL: FAK with price=0.01, sells all held shares
- FAK fills what's available immediately, cancels unfilled remainder
"""

import logging
import math
import time
import traceback
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from threading import Lock

from py_clob_client_v2 import (
    ClobClient,
    MarketOrderArgs,
    OrderType,
    BalanceAllowanceParams,
    AssetType,
    PartialCreateOrderOptions,
)
from py_clob_client_v2.order_builder.constants import BUY, SELL

from market_info import MarketData
from fill_tracker import FillTracker

log = logging.getLogger(__name__)


class OrderSide(Enum):
    """Order side enumeration for buy/sell combinations."""
    # Standard YES/NO
    BUY_YES = "buy_yes"
    BUY_NO = "buy_no"
    SELL_YES = "sell_yes"
    SELL_NO = "sell_no"
    # Football mode
    BUY_TEAM1 = "buy_team1"
    BUY_DRAW = "buy_draw"
    BUY_TEAM2 = "buy_team2"
    SELL_TEAM1 = "sell_team1"
    SELL_DRAW = "sell_draw"
    SELL_TEAM2 = "sell_team2"


@dataclass
class FootballMarkets:
    """Container for 3 football markets (Team1, Draw, Team2)."""
    team1: MarketData
    draw: MarketData
    team2: MarketData

    def get_market(self, outcome: str) -> MarketData:
        """Get market by outcome name."""
        if outcome == "team1":
            return self.team1
        elif outcome == "draw":
            return self.draw
        elif outcome == "team2":
            return self.team2
        raise ValueError(f"Unknown outcome: {outcome}")


class Trader:
    """
    Main trading class for executing Polymarket orders.

    Thread-safe for use with hotkey callbacks. Uses FAK (Fill-And-Kill)
    orders with aggressive pricing to sweep the orderbook immediately.

    Supports two modes:
    - Standard: Single market with YES/NO outcomes
    - Football: Three markets (Team1 win, Draw, Team2 win)

    Order Execution Strategy:
    - BUY: FAK with price=0.99 as slippage protection, spends ~$amount
    - SELL: FAK with price=0.01, sells all held shares
    - FAK fills what's available immediately, cancels unfilled remainder

    Authentication:
    - L1: Private key signs orders (never sent to server)
    - L2: API credentials derived from private key for API auth
    """

    # Aggressive prices for market-like orders
    # These ensure orders fill completely at best available prices
    MAX_BUY_PRICE = 0.99   # Maximum price willing to pay (sweeps orderbook)
    MIN_SELL_PRICE = 0.01  # Minimum price willing to accept

    # Mapping: OrderSide -> (mode, market_key, clob_side)
    _SIDE_MAP = {
        OrderSide.BUY_TEAM1:  ("football", "team1", BUY),
        OrderSide.SELL_TEAM1: ("football", "team1", SELL),
        OrderSide.BUY_DRAW:   ("football", "draw",  BUY),
        OrderSide.SELL_DRAW:  ("football", "draw",  SELL),
        OrderSide.BUY_TEAM2:  ("football", "team2", BUY),
        OrderSide.SELL_TEAM2: ("football", "team2", SELL),
        OrderSide.BUY_YES:    ("standard", "yes",   BUY),
        OrderSide.SELL_YES:   ("standard", "yes",   SELL),
        OrderSide.BUY_NO:     ("standard", "no",    BUY),
        OrderSide.SELL_NO:    ("standard", "no",    SELL),
    }

    def __init__(
        self,
        host: str,
        private_key: str,
        funder_address: str,
        chain_id: int = 137,
        signature_type: int = 0,
        cooldown_seconds: float = 0.5,
        api_key: str = None,
        api_secret: str = None,
        api_passphrase: str = None
    ):
        """
        Initialize the Trader with CLOB client.

        Args:
            host: CLOB API endpoint (https://clob.polymarket.com)
            private_key: Wallet private key (0x...)
            funder_address: Address holding funds (same as wallet for EOA)
            chain_id: Polygon chain ID (137 for mainnet)
            signature_type: 0 for EOA/MetaMask, 1 for Magic wallet
            cooldown_seconds: Minimum time between orders (anti-double-click)
            api_key: Builder API key from Polymarket
            api_secret: Builder API secret from Polymarket
            api_passphrase: Builder API passphrase from Polymarket
        """
        self._lock = Lock()
        self._last_order_time = 0.0
        self._cooldown = cooldown_seconds

        # Standard mode: single market
        self._current_market: Optional[MarketData] = None

        # Football mode: three markets
        self._football_markets: Optional[FootballMarkets] = None
        self._mode = "standard"  # "standard" or "football"

        # First create a temporary client to derive API credentials
        temp_client = ClobClient(
            host,
            key=private_key,
            chain_id=chain_id
        )

        api_creds = temp_client.create_or_derive_api_key()

        self._client = ClobClient(
            host,
            key=private_key,
            chain_id=chain_id,
            creds=api_creds,
            signature_type=signature_type,
            funder=funder_address
        )

        self._fill_tracker = FillTracker(
            api_key=api_creds.api_key,
            api_secret=api_creds.api_secret,
            api_passphrase=api_creds.api_passphrase,
        )
        self._fill_tracker.start()

    def set_mode(self, mode: str) -> None:
        """Set trading mode ('standard' or 'football')."""
        self._mode = mode

    def get_mode(self) -> str:
        """Get current trading mode."""
        return self._mode

    def set_market(self, market: MarketData) -> None:
        """
        Set the current market for standard trading.

        Args:
            market: MarketData object from Gamma API
        """
        with self._lock:
            self._current_market = market
            self._mode = "standard"

    def set_football_markets(self, team1: MarketData, draw: MarketData, team2: MarketData) -> None:
        """
        Set the three markets for football trading.

        Args:
            team1: Market for Team 1 winning
            draw: Market for Draw
            team2: Market for Team 2 winning
        """
        with self._lock:
            self._football_markets = FootballMarkets(team1=team1, draw=draw, team2=team2)
            self._mode = "football"

    def get_current_market(self) -> Optional[MarketData]:
        """Get the currently selected market (standard mode)."""
        return self._current_market

    def get_football_markets(self) -> Optional[FootballMarkets]:
        """Get the football markets (football mode)."""
        return self._football_markets

    def get_wallet_info(self) -> tuple[float, float]:
        """
        Fetch balance and allowance in a single HTTP call.

        Returns:
            Tuple of (balance_usdc, allowance)
        """
        try:
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            response = self._client.get_balance_allowance(params=params)
            balance = float(response.get("balance", "0")) / 1e6
            allowance = float(response.get("allowance", "0"))
            return balance, allowance
        except Exception:
            return 0.0, 0.0

    def get_balance(self) -> float:
        """Get current USDC balance."""
        balance, _ = self.get_wallet_info()
        return balance

    def get_allowance(self) -> float:
        """
        Get current USDC allowance for the exchange contract.

        Returns:
            Allowance as float in USDC
        """
        _, allowance = self.get_wallet_info()
        return allowance

    def get_position(self, token_id: str) -> float:
        """
        Get the number of shares owned for a specific token.

        Args:
            token_id: The token to check

        Returns:
            Number of shares owned (0 if none)
        """
        try:
            params = BalanceAllowanceParams(
                asset_type=AssetType.CONDITIONAL,
                token_id=token_id
            )
            response = self._client.get_balance_allowance(params=params)
            balance_str = response.get("balance", "0")
            return float(balance_str) / 1e6
        except Exception:
            return 0.0

    def get_price(self, token_id: str, side: str = "BUY") -> float:
        """
        Get current price for a token.

        Args:
            token_id: The token to price
            side: "BUY" or "SELL"

        Returns:
            Price as float (0.00 to 1.00)
        """
        try:
            result = self._client.get_price(token_id, side=side)
            if isinstance(result, dict):
                price_str = result.get('price', '0')
                return float(price_str)
            return float(result) if result else 0.0
        except Exception:
            return 0.0

    def refresh_market_prices(self) -> None:
        """Refresh prices for current market(s) from CLOB."""
        if self._mode == "standard" and self._current_market:
            try:
                yes_price = self.get_price(self._current_market.yes_token_id, "BUY")
                no_price = self.get_price(self._current_market.no_token_id, "BUY")
                if yes_price > 0:
                    self._current_market.yes_price = yes_price
                if no_price > 0:
                    self._current_market.no_price = no_price
            except Exception:
                pass
        elif self._mode == "football" and self._football_markets:
            try:
                for market in [self._football_markets.team1,
                               self._football_markets.draw,
                               self._football_markets.team2]:
                    new_price = self.get_price(market.yes_token_id, "BUY")
                    if new_price > 0:
                        market.yes_price = new_price
            except Exception:
                pass

    def _get_cached_price(self, token_id: str, is_buy: bool) -> Optional[float]:
        """
        Get price from cached market data (updated every 2s by periodic refresh).

        Returns cached price or None if not available.
        """
        if self._mode == "football" and self._football_markets:
            for market in [self._football_markets.team1,
                           self._football_markets.draw,
                           self._football_markets.team2]:
                if market.yes_token_id == token_id:
                    return market.yes_price
                if market.no_token_id == token_id:
                    return market.no_price
        elif self._mode == "standard" and self._current_market:
            if self._current_market.yes_token_id == token_id:
                return self._current_market.yes_price
            if self._current_market.no_token_id == token_id:
                return self._current_market.no_price
        return None

    def _resolve_order_params(self, side: OrderSide) -> tuple[str, str, MarketData]:
        """
        Resolve order side to (token_id, clob_side, market).

        Returns the MarketData object so caller has access to
        tick_size, neg_risk, question, etc.

        Raises ValueError if market not configured.
        """
        mode, key, clob_side = self._SIDE_MAP[side]

        if mode == "football":
            if not self._football_markets:
                raise ValueError("Football markets not set")
            market = getattr(self._football_markets, key)  # team1, draw, team2
            token_id = market.yes_token_id
        else:
            if not self._current_market:
                raise ValueError("Market not set")
            market = self._current_market
            token_id = market.yes_token_id if key == "yes" else market.no_token_id

        return token_id, clob_side, market

    def _check_cooldown(self) -> tuple[bool, float]:
        """
        Check if cooldown period has elapsed.

        Returns:
            Tuple of (can_proceed, remaining_seconds)
        """
        current_time = time.time()
        elapsed = current_time - self._last_order_time
        remaining = self._cooldown - elapsed

        if remaining <= 0:
            return True, 0.0
        return False, remaining

    def execute_order(self, side: OrderSide, amount: float) -> bool:
        """
        Execute a market order via FAK with aggressive pricing.

        This is the main entry point called by hotkey handlers.

        Args:
            side: OrderSide enum
            amount: Amount in USDC to trade

        Returns:
            True if order was sent successfully, False otherwise
        """
        start_time = time.time()
        log.debug("execute_order called: side=%s, amount=%s", side, amount)

        with self._lock:
            # Check cooldown
            can_proceed, remaining = self._check_cooldown()
            if not can_proceed:
                log.debug("BLOCKED by cooldown (%.1fs remaining)", remaining)
                return False

            # Resolve token, side, and market from OrderSide
            try:
                token_id, clob_side, market = self._resolve_order_params(side)
            except ValueError as e:
                log.debug("ERROR resolving order params: %s", e)
                return False

            is_buy = clob_side == BUY

            try:
                if is_buy:
                    order_args = MarketOrderArgs(
                        token_id=token_id,
                        amount=amount,
                        price=self.MAX_BUY_PRICE,
                        side=clob_side,
                    )
                else:
                    # SELL: sell all held shares
                    shares = self.get_position(token_id)
                    if shares <= 0:
                        log.debug("SELL: no shares to sell")
                        return False

                    # Floor to 2 decimals (API requirement)
                    shares = math.floor(shares * 100) / 100

                    order_args = MarketOrderArgs(
                        token_id=token_id,
                        amount=shares,
                        price=self.MIN_SELL_PRICE,
                        side=clob_side,
                    )

                options = PartialCreateOrderOptions(
                    tick_size=market.tick_size,
                    neg_risk=market.neg_risk,
                )

                signed_order = self._client.create_market_order(order_args, options)
                response = self._client.post_order(signed_order, OrderType.FAK)
                t_post = time.time()

                self._last_order_time = t_post
                execution_time = (t_post - start_time) * 1000
                log.debug("Order SUCCESS in %.0fms: %s", execution_time, response)

                # Fill confirmation report
                status = response.get("status", "")
                label = f"{'BUY' if is_buy else 'SELL'} {side.name.split('_', 1)[1]}"

                if status == "matched":
                    self._fill_tracker.report_instant(
                        label=label,
                        making_amount=response.get("makingAmount", "0"),
                        taking_amount=response.get("takingAmount", "0"),
                        is_buy=is_buy,
                        t_keypress=start_time,
                        t_post=t_post,
                    )
                elif status == "delayed":
                    self._fill_tracker.register_delayed(
                        order_id=response.get("orderID", ""),
                        label=label,
                        t_keypress=start_time,
                        t_post=t_post,
                    )

                return True

            except Exception as e:
                log.debug("ORDER EXCEPTION: %s", e)
                log.debug("Full traceback:\n%s", traceback.format_exc())
                return False

    def shutdown(self) -> None:
        """Release resources."""
        self._fill_tracker.stop()

    def cancel_all_orders(self) -> bool:
        """
        Cancel all open orders.

        Returns:
            True if cancellation succeeded
        """
        try:
            self._client.cancel_all()
            return True
        except Exception as e:
            log.debug("Failed to cancel orders: %s", e)
            return False

