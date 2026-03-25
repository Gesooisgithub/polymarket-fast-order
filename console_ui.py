"""
Console UI module for status display and user interaction.

Uses colorama for cross-platform colored output.
Provides real-time feedback for trading operations.
Supports both standard (YES/NO) and football (Team1/Draw/Team2) modes.
"""

import os
import sys
from typing import Optional, List

from colorama import init, Fore, Style

from market_info import MarketData

# Initialize colorama for Windows support
init()


class ConsoleUI:
    """
    Console-based UI for displaying trading status.

    Provides:
    - Colored output for status visibility
    - Real-time order notifications
    - Market selection interface
    - Status bar with current state
    - Football mode support (3 markets)
    """

    def __init__(self):
        """Initialize the console UI."""
        self._last_order_info: Optional[str] = None

    def clear_screen(self) -> None:
        """Clear the console screen."""
        os.system('cls' if os.name == 'nt' else 'clear')

    def print_header(self, mode: str = "standard") -> None:
        """Print the application header."""
        print(f"\n{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}")
        if mode == "football":
            print(f"{Fore.CYAN}  POLYMARKET HOTKEY TRADER - FOOTBALL MODE{Style.RESET_ALL}")
        else:
            print(f"{Fore.CYAN}  POLYMARKET HOTKEY TRADER{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'=' * 60}{Style.RESET_ALL}\n")

    def print_wallet_info(self, address: str, balance: float) -> None:
        """
        Print wallet information.

        Args:
            address: Wallet address (will be truncated)
            balance: USDC balance
        """
        # Truncate address for display
        if len(address) > 12:
            display_addr = f"{address[:6]}...{address[-4:]}"
        else:
            display_addr = address

        print(f"{Fore.WHITE}Wallet:{Style.RESET_ALL} {display_addr}")
        print(f"{Fore.WHITE}Balance:{Style.RESET_ALL} ${balance:,.2f} USDC")
        print()

    def print_hotkey_guide_standard(self, current_amount: float) -> None:
        """
        Print the hotkey guide for standard YES/NO mode.

        Args:
            current_amount: Current trading amount
        """
        print(f"{Fore.YELLOW}Hotkeys:{Style.RESET_ALL}")
        print(f"  {Fore.WHITE}Current Amount: ${current_amount:.0f}{Style.RESET_ALL}")
        print()
        print(f"  {Fore.GREEN}CTRL+1{Style.RESET_ALL} - Buy YES")
        print(f"  {Fore.GREEN}CTRL+2{Style.RESET_ALL} - Buy NO")
        print(f"  {Fore.MAGENTA}CTRL+3{Style.RESET_ALL} - Sell YES")
        print(f"  {Fore.MAGENTA}CTRL+4{Style.RESET_ALL} - Sell NO")
        print()
        print(f"  {Fore.CYAN}CTRL+A{Style.RESET_ALL} - Set Amount")
        print(f"  {Fore.YELLOW}CTRL+M{Style.RESET_ALL} - Change Market")
        print(f"  {Fore.RED}CTRL+Q{Style.RESET_ALL} - Quit")
        print()

    def print_hotkey_guide_football(self, current_amount: float) -> None:
        """
        Print the hotkey guide for football mode (Team1/Draw/Team2).

        Args:
            current_amount: Current trading amount
        """
        print(f"{Fore.YELLOW}Hotkeys (Football Mode):{Style.RESET_ALL}")
        print(f"  {Fore.WHITE}Current Amount: ${current_amount:.0f}{Style.RESET_ALL}")
        print()
        print(f"  {Fore.CYAN}--- BUY ---{Style.RESET_ALL}")
        print(f"  {Fore.GREEN}CTRL+F1{Style.RESET_ALL} - Buy TEAM 1")
        print(f"  {Fore.GREEN}CTRL+F2{Style.RESET_ALL} - Buy DRAW")
        print(f"  {Fore.GREEN}CTRL+F3{Style.RESET_ALL} - Buy TEAM 2")
        print(f"  {Fore.CYAN}--- SELL ---{Style.RESET_ALL}")
        print(f"  {Fore.MAGENTA}CTRL+F4{Style.RESET_ALL} - Sell TEAM 1")
        print(f"  {Fore.MAGENTA}CTRL+F5{Style.RESET_ALL} - Sell DRAW")
        print(f"  {Fore.MAGENTA}CTRL+F6{Style.RESET_ALL} - Sell TEAM 2")
        print()
        print(f"  {Fore.CYAN}CTRL+A{Style.RESET_ALL} - Set Amount")
        print(f"  {Fore.YELLOW}CTRL+M{Style.RESET_ALL} - Change Markets")
        print(f"  {Fore.RED}CTRL+Q{Style.RESET_ALL} - Quit")
        print()

    def print_hotkey_guide(self, current_amount: float, mode: str = "standard") -> None:
        """
        Print the appropriate hotkey guide based on mode.

        Args:
            current_amount: Current trading amount
            mode: "standard" or "football"
        """
        if mode == "football":
            self.print_hotkey_guide_football(current_amount)
        else:
            self.print_hotkey_guide_standard(current_amount)

    def print_market_info(self, market: Optional[MarketData]) -> None:
        """
        Print current market information (standard mode).

        Args:
            market: Current market data or None
        """
        print(f"{Fore.CYAN}{'-' * 60}{Style.RESET_ALL}")

        if market:
            # Truncate long questions
            question = market.question
            if len(question) > 55:
                question = question[:52] + "..."

            print(f"{Fore.WHITE}Market:{Style.RESET_ALL} {question}")
            print(f"  {Fore.GREEN}YES:{Style.RESET_ALL} ${market.yes_price:.2f}  "
                  f"{Fore.RED}NO:{Style.RESET_ALL} ${market.no_price:.2f}")

            if not market.active or market.closed:
                print(f"  {Fore.RED}[MARKET CLOSED]{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}No market selected{Style.RESET_ALL}")

        print(f"{Fore.CYAN}{'-' * 60}{Style.RESET_ALL}\n")

    def print_football_markets_info(
        self,
        team1: Optional[MarketData],
        draw: Optional[MarketData],
        team2: Optional[MarketData],
        team1_name: str = "Team 1",
        team2_name: str = "Team 2"
    ) -> None:
        """
        Print football markets information (3 markets).

        Args:
            team1: Market for Team 1 win
            draw: Market for Draw
            team2: Market for Team 2 win
            team1_name: Display name for Team 1
            team2_name: Display name for Team 2
        """
        print(f"{Fore.CYAN}{'-' * 60}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Football Match:{Style.RESET_ALL} {team1_name} vs {team2_name}")
        print()

        # Team 1
        if team1:
            price = team1.yes_price
            print(f"  {Fore.BLUE}[1] {team1_name}:{Style.RESET_ALL} ${price:.2f}")
        else:
            print(f"  {Fore.RED}[1] {team1_name}: NOT SET{Style.RESET_ALL}")

        # Draw
        if draw:
            price = draw.yes_price
            print(f"  {Fore.YELLOW}[X] Draw:{Style.RESET_ALL}   ${price:.2f}")
        else:
            print(f"  {Fore.RED}[X] Draw: NOT SET{Style.RESET_ALL}")

        # Team 2
        if team2:
            price = team2.yes_price
            print(f"  {Fore.BLUE}[2] {team2_name}:{Style.RESET_ALL} ${price:.2f}")
        else:
            print(f"  {Fore.RED}[2] {team2_name}: NOT SET{Style.RESET_ALL}")

        print(f"{Fore.CYAN}{'-' * 60}{Style.RESET_ALL}\n")

    def print_status_ready(self) -> None:
        """Print ready status message."""
        print(f"{Fore.GREEN}Ready for trading. Press hotkeys to place orders.{Style.RESET_ALL}\n")

    def print_amount_changed(self, new_amount: float) -> None:
        """
        Print notification that amount was changed.

        Args:
            new_amount: The new trading amount
        """
        print(f"\n{Fore.CYAN}Amount changed to: ${new_amount:.0f}{Style.RESET_ALL}\n")

    def prompt_amount_input(self, current_amount: float) -> Optional[float]:
        """
        Prompt user for new trading amount.

        Args:
            current_amount: Current amount for display

        Returns:
            New amount or None if cancelled
        """
        print(f"\n{Fore.YELLOW}Set new trading amount:{Style.RESET_ALL}")
        print(f"  Current: ${current_amount:.0f}")
        print(f"  Enter new amount (or press Enter to cancel):")

        try:
            user_input = input(f"{Fore.CYAN}$ {Style.RESET_ALL}").strip()
            if not user_input:
                return None
            amount = float(user_input)
            if amount <= 0:
                self.print_error("Amount must be positive.")
                return None
            return amount
        except (ValueError, EOFError, KeyboardInterrupt):
            return None

    def prompt_market_input(self, label: str = "market") -> str:
        """
        Prompt user for market identifier.

        Args:
            label: Label to show (e.g., "market", "Team 1 market", "Draw market")

        Returns:
            User input (condition_id, slug, or search term)
        """
        print(f"\n{Fore.YELLOW}Enter {label} identifier:{Style.RESET_ALL}")
        print("  - Condition ID (starts with 0x...)")
        print("  - Market slug (from URL)")
        print("  - Search term to find markets")
        print()

        try:
            return input(f"{Fore.CYAN}> {Style.RESET_ALL}").strip()
        except (EOFError, KeyboardInterrupt):
            return ""

    def prompt_team_names(self) -> tuple[str, str]:
        """
        Prompt user for team names.

        Returns:
            Tuple of (team1_name, team2_name)
        """
        print(f"\n{Fore.YELLOW}Enter team names for display:{Style.RESET_ALL}")

        try:
            team1 = input(f"{Fore.CYAN}Team 1 name: {Style.RESET_ALL}").strip()
            team2 = input(f"{Fore.CYAN}Team 2 name: {Style.RESET_ALL}").strip()
            return (team1 or "Team 1", team2 or "Team 2")
        except (EOFError, KeyboardInterrupt):
            return ("Team 1", "Team 2")

    def display_market_selection(self, markets: List[MarketData]) -> Optional[int]:
        """
        Display market selection menu.

        Args:
            markets: List of MarketData objects

        Returns:
            Selected index (0-based) or None if cancelled
        """
        if not markets:
            self.print_error("No markets found.")
            return None

        print(f"\n{Fore.YELLOW}Select a market:{Style.RESET_ALL}")
        for i, market in enumerate(markets, 1):
            # Truncate long questions
            question = market.question
            if len(question) > 50:
                question = question[:47] + "..."

            status = ""
            if not market.active or market.closed:
                status = f" {Fore.RED}[CLOSED]{Style.RESET_ALL}"

            print(f"  {Fore.CYAN}{i}{Style.RESET_ALL}. {question}{status}")
            print(f"     YES: ${market.yes_price:.2f} | NO: ${market.no_price:.2f}")

        print(f"\n  {Fore.YELLOW}0{Style.RESET_ALL}. Cancel")

        try:
            choice_str = input(f"\n{Fore.CYAN}> {Style.RESET_ALL}").strip()
            choice = int(choice_str)

            if choice == 0:
                return None
            if 1 <= choice <= len(markets):
                return choice - 1
            return None
        except (ValueError, EOFError, KeyboardInterrupt):
            return None

    def print_error(self, message: str) -> None:
        """Print an error message."""
        print(f"{Fore.RED}Error: {message}{Style.RESET_ALL}")

    def print_success(self, message: str) -> None:
        """Print a success message."""
        print(f"{Fore.GREEN}{message}{Style.RESET_ALL}")

    def print_info(self, message: str) -> None:
        """Print an info message."""
        print(f"{Fore.YELLOW}{message}{Style.RESET_ALL}")

    def print_warning(self, message: str) -> None:
        """Print a warning message."""
        print(f"{Fore.YELLOW}Warning: {message}{Style.RESET_ALL}")

    def confirm_action(self, message: str) -> bool:
        """
        Ask user to confirm an action.

        Args:
            message: Confirmation message to display

        Returns:
            True if user confirms (y/yes), False otherwise
        """
        try:
            response = input(f"{Fore.YELLOW}{message} (y/n): {Style.RESET_ALL}").strip().lower()
            return response in ('y', 'yes')
        except (EOFError, KeyboardInterrupt):
            return False

    def print_goodbye(self) -> None:
        """Print goodbye message."""
        print(f"\n{Fore.CYAN}Goodbye! Happy trading.{Style.RESET_ALL}\n")

