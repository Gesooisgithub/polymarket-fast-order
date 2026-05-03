"""
Portfolio display module — prints portfolio status after each fill.

Data sources:
- fill_price:   passed from FillTracker (calculated from makingAmount/takingAmount)
- fill_shares:  passed from FillTracker (takingAmount for buy, makingAmount for sell)
- is_buy:       passed from FillTracker
- current prices: fresh HTTP call via clob_client.get_price() in _do_print
- last buy price: tracked locally in _last_buy_price (per outcome)
"""

import logging
import threading

from colorama import Fore, Style

log = logging.getLogger(__name__)


class PortfolioDisplay:
    """Displays portfolio status after fill confirmations."""

    def __init__(self, clob_client):
        """
        Args:
            clob_client: CLOB client used to fetch fresh prices.
        """
        self._clob_client = clob_client
        # Tracks last buy fill price per outcome — used for sell P/L calculation
        self._last_buy_price: dict[str, float] = {}  # outcome -> price

    def show(
        self,
        label: str,
        football_markets,
        team1_name: str,
        team2_name: str,
        fill_price: float,
        fill_shares: float,
        is_buy: bool,
    ) -> None:
        """Run portfolio display in a background daemon thread."""
        log.debug("Portfolio display triggered after fill: %s", label)
        threading.Thread(
            target=self._print,
            args=(label, football_markets, team1_name, team2_name,
                  fill_price, fill_shares, is_buy),
            daemon=True,
        ).start()

    def _print(self, label, football_markets, team1_name, team2_name,
               fill_price, fill_shares, is_buy) -> None:
        try:
            self._do_print(label, football_markets, team1_name, team2_name,
                           fill_price, fill_shares, is_buy)
        except Exception:
            log.debug("Portfolio display error", exc_info=True)

    def _do_print(self, label, football_markets, team1_name, team2_name,
                  fill_price, fill_shares, is_buy) -> None:
        if football_markets is None:
            return

        # Fetch fresh prices via HTTP (fallback to cached on error)
        fresh_prices = {}
        for market in (football_markets.team1, football_markets.draw, football_markets.team2):
            try:
                result = self._clob_client.get_price(market.yes_token_id, side="BUY")
                if isinstance(result, dict):
                    fresh_prices[market.yes_token_id] = float(result.get('price', '0'))
                else:
                    fresh_prices[market.yes_token_id] = float(result) if result else market.yes_price
            except Exception:
                fresh_prices[market.yes_token_id] = market.yes_price

        # Extract outcome from label e.g. "BUY TEAM1" -> "TEAM1"
        outcome = label.split(" ", 1)[1] if " " in label else ""

        # Update buy price cache before rendering
        if is_buy:
            self._last_buy_price[outcome] = fill_price

        markets_info = [
            (f"[1] {team1_name}:", football_markets.team1, Fore.BLUE),
            ("[X] Draw:",          football_markets.draw,  Fore.YELLOW),
            (f"[2] {team2_name}:", football_markets.team2, Fore.BLUE),
        ]

        sep = "=" * 60
        lines = [
            "",
            f"{Fore.CYAN}{sep}{Style.RESET_ALL}",
            f"{Fore.CYAN}  PORTFOLIO STATUS{Style.RESET_ALL}",
            f"{Fore.CYAN}{sep}{Style.RESET_ALL}",
            "",
            f"  {Fore.WHITE}Current Prices:{Style.RESET_ALL}",
        ]

        for lbl, market, color in markets_info:
            price = fresh_prices.get(market.yes_token_id, market.yes_price)
            lines.append(f"    {color}{lbl:<16}{Style.RESET_ALL}${price:.4f}")

        # Fill detail for the filled outcome only
        outcome_map = {"TEAM1": markets_info[0], "DRAW": markets_info[1], "TEAM2": markets_info[2]}
        filled = outcome_map.get(outcome)

        if filled:
            fill_lbl, fill_market, fill_color = filled
            lines.append("")
            lines.append(f"  {Fore.WHITE}Positions:{Style.RESET_ALL}")
            lines.append(f"    {fill_color}{fill_lbl}{Style.RESET_ALL}")
            lines.append(f"        {Fore.WHITE}Shares:{Style.RESET_ALL}     {fill_shares:.4f}")

            if is_buy:
                current_price = fresh_prices.get(fill_market.yes_token_id, fill_market.yes_price)
                pnl_cash = (current_price - fill_price) * fill_shares
                pnl_pct = ((current_price - fill_price) / fill_price * 100) if fill_price > 0 else 0.0
                pnl_color = Fore.GREEN if pnl_cash >= 0 else Fore.RED

                lines.append(f"        {Fore.WHITE}Bought at:{Style.RESET_ALL}  ${fill_price:.4f}")
                lines.append(f"        {Fore.WHITE}Current:{Style.RESET_ALL}    ${current_price:.4f}")
                lines.append(
                    f"        {Fore.WHITE}P/L:{Style.RESET_ALL}        "
                    f"{pnl_color}${pnl_cash:+.4f} ({pnl_pct:+.1f}%){Style.RESET_ALL}"
                )
            else:
                bought_at = self._last_buy_price.get(outcome)

                if bought_at is not None:
                    lines.append(f"        {Fore.WHITE}Bought at:{Style.RESET_ALL}  ${bought_at:.4f}")
                    lines.append(f"        {Fore.WHITE}Sold at:{Style.RESET_ALL}    ${fill_price:.4f}")

                    pnl_cash = (fill_price - bought_at) * fill_shares
                    pnl_pct = ((fill_price - bought_at) / bought_at * 100) if bought_at > 0 else 0.0
                    pnl_color = Fore.GREEN if pnl_cash >= 0 else Fore.RED

                    lines.append(
                        f"        {Fore.WHITE}P/L:{Style.RESET_ALL}        "
                        f"{pnl_color}${pnl_cash:+.4f} ({pnl_pct:+.1f}%){Style.RESET_ALL}"
                    )
                else:
                    lines.append(f"        {Fore.WHITE}Sold at:{Style.RESET_ALL}    ${fill_price:.4f}")

        lines.append("")
        lines.append(f"{Fore.CYAN}{sep}{Style.RESET_ALL}")

        print("\n".join(lines))
