"""
Main entry point for Polymarket Hotkey Trader.

Supports two modes:
- Standard: Single market with YES/NO outcomes
- Football: Three markets (Team1 win, Draw, Team2 win)

Features:
- Single customizable amount for all trades
- Change amount on the fly with CTRL+A

Usage:
    python main.py

Requirements:
    - .env file with POLYMARKET_PRIVATE_KEY and POLYMARKET_FUNDER_ADDRESS
    - config.json with hotkey bindings
    - Administrator privileges on Windows for global hotkeys
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from colorama import Fore, Style
from dotenv import load_dotenv

from trader import Trader, OrderSide
from hotkey_manager import HotkeyManager
from market_info import GammaClient, MarketData, GammaAPIError
from console_ui import ConsoleUI
from event_fetcher import fetch_football_markets_from_url
from portfolio_display import PortfolioDisplay

log = logging.getLogger(__name__)


def load_config(config_path: str = "config.json") -> dict:
    """
    Load configuration from JSON file.

    Falls back to sensible defaults if file doesn't exist.

    Args:
        config_path: Path to config file

    Returns:
        Configuration dictionary
    """
    default_config = {
        "mode": "football",
        "hotkeys": {
            "buy_team1": "ctrl+1",
            "buy_draw": "ctrl+2",
            "buy_team2": "ctrl+3",
            "sell_team1": "ctrl+4",
            "sell_draw": "ctrl+5",
            "sell_team2": "ctrl+6",
            "set_amount": "ctrl+a",
            "change_markets": "ctrl+m",
            "quit": "ctrl+q"
        },
        "default_amount": 100.0,
        "cooldown_seconds": 0.5,
        "clob_host": "https://clob.polymarket.com",
        "gamma_host": "https://gamma-api.polymarket.com",
        "chain_id": 137,
        "signature_type": 0,
    }

    config_file = Path(config_path)
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)

            # Merge with defaults (user config overrides)
            for key, value in user_config.items():
                if isinstance(value, dict) and key in default_config and isinstance(default_config[key], dict):
                    default_config[key].update(value)
                else:
                    default_config[key] = value
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load config.json: {e}")
            print("Using default configuration.")

    return default_config


def load_credentials() -> dict:
    """
    Load credentials from .env file.

    Returns:
        Dictionary with private_key, funder_address, and optional API keys

    Raises:
        ValueError if required credentials not found
    """
    load_dotenv()

    private_key = os.getenv("POLYMARKET_PRIVATE_KEY")
    funder_address = os.getenv("POLYMARKET_FUNDER_ADDRESS")

    if not private_key:
        raise ValueError(
            "POLYMARKET_PRIVATE_KEY not found in .env file.\n"
            "Please copy .env.example to .env and add your private key."
        )

    if not funder_address:
        raise ValueError(
            "POLYMARKET_FUNDER_ADDRESS not found in .env file.\n"
            "Please add your wallet address to .env."
        )

    # Basic validation
    if not private_key.startswith("0x"):
        raise ValueError("POLYMARKET_PRIVATE_KEY must start with 0x")

    if not funder_address.startswith("0x"):
        raise ValueError("POLYMARKET_FUNDER_ADDRESS must start with 0x")

    # Optional Builder API Keys (recommended)
    api_key = os.getenv("POLYMARKET_API_KEY")
    api_secret = os.getenv("POLYMARKET_API_SECRET")
    api_passphrase = os.getenv("POLYMARKET_PASSPHRASE")

    return {
        "private_key": private_key,
        "funder_address": funder_address,
        "api_key": api_key,
        "api_secret": api_secret,
        "api_passphrase": api_passphrase
    }


class PolymarketHotkeyApp:
    """
    Main application class that orchestrates all components.

    Supports:
    - Standard mode: Single YES/NO market
    - Football mode: Three markets (Team1, Draw, Team2)
    - Single customizable amount for all trades
    """

    def __init__(self):
        """Initialize the application components."""
        self.config = load_config()
        creds = load_credentials()
        self.private_key = creds["private_key"]
        self.funder_address = creds["funder_address"]
        api_key = creds["api_key"]
        api_secret = creds["api_secret"]
        api_passphrase = creds["api_passphrase"]

        # Determine mode
        self.mode = self.config.get("mode", "football")

        # Current trading amount (single amount for all trades)
        self.current_amount = self.config.get("default_amount", 100.0)

        # Team names for display (football mode)
        self.team1_name = "Team 1"
        self.team2_name = "Team 2"

        # Initialize UI first for error display
        self.ui = ConsoleUI()

        # Initialize market client (uses CLOB API for condition_id, Gamma for search)
        self.gamma_client = GammaClient(
            clob_host=self.config["clob_host"],
            gamma_host=self.config["gamma_host"]
        )

        # Initialize hotkey manager
        self.hotkey_manager = HotkeyManager()

        # Initialize trader (connects to CLOB)
        self.ui.print_info("Connecting to Polymarket CLOB...")
        self.trader = Trader(
            host=self.config["clob_host"],
            private_key=self.private_key,
            funder_address=self.funder_address,
            chain_id=self.config["chain_id"],
            signature_type=self.config["signature_type"],
            cooldown_seconds=self.config["cooldown_seconds"],
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase
        )

        # Portfolio display — injected into FillTracker
        self._portfolio_display = PortfolioDisplay(
            clob_client=self.trader._client,
        )
        self.trader._fill_tracker._portfolio_display = self._portfolio_display

        self._running = False

    def _select_single_market(self, label: str = "market") -> MarketData | None:
        """
        Prompt user to select a single market.

        Args:
            label: Label for the prompt

        Returns:
            MarketData or None if cancelled
        """
        while True:
            user_input = self.ui.prompt_market_input(label)

            if not user_input:
                return None

            market = None

            try:
                # Try as condition_id (starts with 0x)
                if user_input.startswith("0x"):
                    self.ui.print_info("Looking up market by condition ID...")
                    market = self.gamma_client.get_market_by_condition_id(user_input)

                # Try as slug (contains dash, no spaces)
                elif "-" in user_input and " " not in user_input:
                    self.ui.print_info("Looking up market by slug...")
                    market = self.gamma_client.get_market_by_slug(user_input)

                # Search by keyword
                else:
                    self.ui.print_info(f"Searching for markets matching '{user_input}'...")
                    markets = self.gamma_client.search_markets(user_input, limit=5)

                    if not markets:
                        self.ui.print_error("No markets found matching your search.")
                        continue

                    selected_idx = self.ui.display_market_selection(markets)
                    if selected_idx is not None:
                        market = markets[selected_idx]
                    else:
                        continue

            except GammaAPIError as e:
                self.ui.print_error(f"API error: {e}")
                continue

            if market:
                return market
            else:
                self.ui.print_error("Market not found. Please try again.")

    def _select_football_markets(self) -> bool:
        """
        Prompt user to select all three football markets.

        Returns:
            True if all markets selected, False if cancelled
        """
        # Get team names
        self.team1_name, self.team2_name = self.ui.prompt_team_names()

        self.ui.print_info(f"\nSetting up markets for: {self.team1_name} vs {self.team2_name}\n")

        # Select Team 1 win market
        self.ui.print_info(f"Select market for '{self.team1_name}' WIN:")
        team1_market = self._select_single_market(f"{self.team1_name} win")
        if not team1_market:
            return False

        # Select Draw market
        self.ui.print_info(f"\nSelect market for DRAW:")
        draw_market = self._select_single_market("Draw")
        if not draw_market:
            return False

        # Select Team 2 win market
        self.ui.print_info(f"\nSelect market for '{self.team2_name}' WIN:")
        team2_market = self._select_single_market(f"{self.team2_name} win")
        if not team2_market:
            return False

        # Set all markets
        self.trader.set_football_markets(team1_market, draw_market, team2_market)

        self.ui.print_success("\nAll three markets configured successfully!")
        return True

    def _set_amount(self) -> None:
        """Handle set amount hotkey (CTRL+A)."""
        self.hotkey_manager.suspend_all()
        try:
            new_amount = self.ui.prompt_amount_input(self.current_amount)
            if new_amount is not None:
                self.current_amount = new_amount
                self.ui.print_amount_changed(new_amount)
        finally:
            self.hotkey_manager.resume_all()

    def _check_balance(self) -> None:
        """Handle check balance hotkey (CTRL+B)."""
        balance, _ = self.trader.get_wallet_info()
        print(f"\n{Fore.CYAN}Balance: ${balance:.2f} USDC{Style.RESET_ALL}\n")

    def _change_markets(self) -> None:
        """Handle market change hotkey (CTRL+M)."""
        self.hotkey_manager.suspend_all()
        try:
            self.ui.print_info("\n--- Changing Markets ---")

            if self.mode == "football":
                try:
                    url = input(f"\n{Fore.CYAN}New event URL: {Style.RESET_ALL}").strip()
                    if not url:
                        self.ui.print_info("Market change cancelled.")
                    else:
                        self.ui.print_info("Fetching event data...")
                        team1_m, draw_m, team2_m, name1, name2 = fetch_football_markets_from_url(
                            url, self.gamma_client, self.config["gamma_host"]
                        )
                        self.trader.set_football_markets(team1_m, draw_m, team2_m)
                        self.team1_name = name1
                        self.team2_name = name2
                        self.trader._fill_tracker.set_football_context(
                            self.trader.get_football_markets(), name1, name2,
                        )
                        self.ui.print_success(f"{name1} vs {name2} - markets loaded!")
                        self._refresh_display()
                except (ValueError, GammaAPIError) as e:
                    self.ui.print_error(str(e))
                except (EOFError, KeyboardInterrupt):
                    self.ui.print_info("Market change cancelled.")
            else:
                market = self._select_single_market()
                if market:
                    self.trader.set_market(market)
                    self._refresh_display()
                else:
                    self.ui.print_info("Market change cancelled.")
        finally:
            self.hotkey_manager.resume_all()

    def _quit(self) -> None:
        """Handle quit hotkey (CTRL+Q)."""
        self.ui.print_info("\nShutting down...")
        self._running = False
        self.hotkey_manager.stop()

    def _refresh_display(self) -> None:
        """Refresh the main display with current state."""
        self.ui.clear_screen()
        self.ui.print_header(self.mode)

        # Wallet info (single HTTP call)
        balance, _ = self.trader.get_wallet_info()
        self.ui.print_wallet_info(self.funder_address, balance)

        # Hotkey guide (with current amount)
        self.ui.print_hotkey_guide(self.current_amount, self.mode)

        # Market info
        if self.mode == "football":
            markets = self.trader.get_football_markets()
            if markets:
                self.trader.refresh_market_prices()
                self.ui.print_football_markets_info(
                    markets.team1,
                    markets.draw,
                    markets.team2,
                    self.team1_name,
                    self.team2_name
                )
            else:
                self.ui.print_football_markets_info(None, None, None)
        else:
            market = self.trader.get_current_market()
            if market:
                self.trader.refresh_market_prices()
            self.ui.print_market_info(market)

        # Ready status
        self.ui.print_status_ready()

    def _periodic_refresh(self) -> None:
        """Periodic callback to refresh prices (called every 2 seconds)."""
        try:
            self.trader.refresh_market_prices()
        except Exception:
            pass  # Silently ignore refresh errors

    def _execute_buy_team1(self) -> None:
        log.debug("HOTKEY: _execute_buy_team1 triggered, amount=%s", self.current_amount)
        self.trader.execute_order(OrderSide.BUY_TEAM1, self.current_amount)

    def _execute_buy_draw(self) -> None:
        log.debug("HOTKEY: _execute_buy_draw triggered, amount=%s", self.current_amount)
        self.trader.execute_order(OrderSide.BUY_DRAW, self.current_amount)

    def _execute_buy_team2(self) -> None:
        log.debug("HOTKEY: _execute_buy_team2 triggered, amount=%s", self.current_amount)
        self.trader.execute_order(OrderSide.BUY_TEAM2, self.current_amount)

    def _execute_sell_team1(self) -> None:
        log.debug("HOTKEY: _execute_sell_team1 triggered, amount=%s", self.current_amount)
        self.trader.execute_order(OrderSide.SELL_TEAM1, self.current_amount)

    def _execute_sell_draw(self) -> None:
        log.debug("HOTKEY: _execute_sell_draw triggered, amount=%s", self.current_amount)
        self.trader.execute_order(OrderSide.SELL_DRAW, self.current_amount)

    def _execute_sell_team2(self) -> None:
        log.debug("HOTKEY: _execute_sell_team2 triggered, amount=%s", self.current_amount)
        self.trader.execute_order(OrderSide.SELL_TEAM2, self.current_amount)

    def _register_hotkeys_football(self) -> None:
        """Register all football mode hotkeys."""
        hotkeys = self.config["hotkeys"]

        # BUY hotkeys - using bound methods instead of lambdas
        self.hotkey_manager.register_hotkey(
            "buy_team1",
            hotkeys["buy_team1"],
            self._execute_buy_team1
        )
        self.hotkey_manager.register_hotkey(
            "buy_draw",
            hotkeys["buy_draw"],
            self._execute_buy_draw
        )
        self.hotkey_manager.register_hotkey(
            "buy_team2",
            hotkeys["buy_team2"],
            self._execute_buy_team2
        )

        # SELL hotkeys - using bound methods instead of lambdas
        self.hotkey_manager.register_hotkey(
            "sell_team1",
            hotkeys["sell_team1"],
            self._execute_sell_team1
        )
        self.hotkey_manager.register_hotkey(
            "sell_draw",
            hotkeys["sell_draw"],
            self._execute_sell_draw
        )
        self.hotkey_manager.register_hotkey(
            "sell_team2",
            hotkeys["sell_team2"],
            self._execute_sell_team2
        )

        # Control hotkeys
        self.hotkey_manager.register_hotkey(
            "set_amount",
            hotkeys["set_amount"],
            self._set_amount
        )
        self.hotkey_manager.register_hotkey(
            "check_balance",
            hotkeys["check_balance"],
            self._check_balance
        )
        self.hotkey_manager.register_hotkey(
            "change_markets",
            hotkeys["change_markets"],
            self._change_markets
        )
        self.hotkey_manager.register_hotkey(
            "quit",
            hotkeys["quit"],
            self._quit
        )

    def _register_hotkeys_standard(self) -> None:
        """Register all standard mode hotkeys."""
        hotkeys = self.config["hotkeys"]

        # BUY hotkeys
        self.hotkey_manager.register_hotkey(
            "buy_yes",
            hotkeys.get("buy_yes", "ctrl+1"),
            lambda: (log.debug("HOTKEY: buy_yes triggered, amount=%s", self.current_amount), self.trader.execute_order(OrderSide.BUY_YES, self.current_amount))
        )
        self.hotkey_manager.register_hotkey(
            "buy_no",
            hotkeys.get("buy_no", "ctrl+2"),
            lambda: (log.debug("HOTKEY: buy_no triggered, amount=%s", self.current_amount), self.trader.execute_order(OrderSide.BUY_NO, self.current_amount))
        )

        # SELL hotkeys
        self.hotkey_manager.register_hotkey(
            "sell_yes",
            hotkeys.get("sell_yes", "ctrl+3"),
            lambda: (log.debug("HOTKEY: sell_yes triggered, amount=%s", self.current_amount), self.trader.execute_order(OrderSide.SELL_YES, self.current_amount))
        )
        self.hotkey_manager.register_hotkey(
            "sell_no",
            hotkeys.get("sell_no", "ctrl+4"),
            lambda: (log.debug("HOTKEY: sell_no triggered, amount=%s", self.current_amount), self.trader.execute_order(OrderSide.SELL_NO, self.current_amount))
        )

        # Control hotkeys
        self.hotkey_manager.register_hotkey(
            "set_amount",
            hotkeys.get("set_amount", "ctrl+a"),
            self._set_amount
        )
        self.hotkey_manager.register_hotkey(
            "check_balance",
            hotkeys.get("check_balance", "ctrl+b"),
            self._check_balance
        )
        self.hotkey_manager.register_hotkey(
            "change_market",
            hotkeys.get("change_market", "ctrl+m"),
            self._change_markets
        )
        self.hotkey_manager.register_hotkey(
            "quit",
            hotkeys.get("quit", "ctrl+q"),
            self._quit
        )

    def run(self) -> None:
        """
        Main application loop.

        Flow:
        1. Display header
        2. Show wallet info
        3. Select markets (1 or 3 depending on mode)
        4. Register hotkeys
        5. Enter trading loop
        6. Cleanup on exit
        """
        try:
            # Initial display
            self.ui.clear_screen()
            self.ui.print_header(self.mode)

            # Get and display balance (single HTTP call)
            balance, _ = self.trader.get_wallet_info()
            self.ui.print_wallet_info(self.funder_address, balance)

            # Select markets based on mode
            if self.mode == "football":
                self.ui.print_info("FOOTBALL MODE: Paste a Polymarket event URL to auto-detect markets\n")
                while True:
                    try:
                        url = input(f"{Fore.CYAN}Event URL: {Style.RESET_ALL}").strip()
                        if not url:
                            continue
                        self.ui.print_info("Fetching event data...")
                        team1_m, draw_m, team2_m, name1, name2 = fetch_football_markets_from_url(
                            url, self.gamma_client, self.config["gamma_host"]
                        )
                        self.trader.set_football_markets(team1_m, draw_m, team2_m)
                        self.team1_name = name1
                        self.team2_name = name2
                        self.trader._fill_tracker.set_football_context(
                            self.trader.get_football_markets(), name1, name2,
                        )
                        self.ui.print_success(f"\n  {name1} vs {name2} - 3 markets loaded!")
                        self.ui.print_info(f"  [1] {name1}: ${team1_m.yes_price:.2f}")
                        self.ui.print_info(f"  [X] Draw: ${draw_m.yes_price:.2f}")
                        self.ui.print_info(f"  [2] {name2}: ${team2_m.yes_price:.2f}\n")
                        break
                    except (ValueError, GammaAPIError) as e:
                        self.ui.print_error(str(e))
                        self.ui.print_info("Try again.\n")
                    except (EOFError, KeyboardInterrupt):
                        self.ui.print_info("\nCancelled.")
                        return
            else:
                self.ui.print_info("Please select a market to start trading:\n")
                while True:
                    market = self._select_single_market()
                    if market:
                        self.trader.set_market(market)
                        break
                    self.ui.print_error("You must select a market to continue.")

            # Register hotkeys based on mode
            if self.mode == "football":
                self._register_hotkeys_football()
            else:
                self._register_hotkeys_standard()

            # Show full display
            self._refresh_display()

            # Set up periodic price refresh (every 2 seconds)
            self.hotkey_manager.set_refresh_callback(self._periodic_refresh, interval=2.0)

            # Main loop
            self._running = True
            self.hotkey_manager.start()

        except KeyboardInterrupt:
            pass
        except Exception as e:
            self.ui.print_error(f"Unexpected error: {e}")
        finally:
            self.trader.shutdown()
            self.hotkey_manager.unregister_all()
            self.gamma_client.close()
            self.ui.print_goodbye()


def main():
    """Application entry point."""
    # Configure logging — change to DEBUG for troubleshooting
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("hpack").setLevel(logging.WARNING)

    # Check Python version
    if sys.version_info < (3, 9):
        print("Error: Python 3.9 or higher is required.")
        sys.exit(1)

    # Check for admin on Windows (needed for global hotkeys)
    if os.name == 'nt':
        try:
            import ctypes
            if not ctypes.windll.shell32.IsUserAnAdmin():
                print("Warning: Running without Administrator privileges.")
                print("Global hotkeys may not work. Consider running as Administrator.")
                print()
        except Exception:
            pass

    try:
        app = PolymarketHotkeyApp()
        app.run()
    except ValueError as e:
        print(f"\nConfiguration error: {e}")
        sys.exit(1)
    except ImportError as e:
        print(f"\nMissing dependency: {e}")
        print("Run: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()