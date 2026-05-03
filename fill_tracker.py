"""
Fill confirmation tracker — shows real fill data after each order.

Two paths:
- INSTANT (non-sports): fill data from REST response (makingAmount/takingAmount)
- DELAYED (football/sports): fill data from WebSocket MATCHED event (up to 4s wait)

WebSocket connects to Polymarket user channel for real-time trade events.
"""

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

import websocket
from colorama import Fore, Style

log = logging.getLogger(__name__)

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
PING_INTERVAL = 10  # seconds
PENDING_TIMEOUT = 4  # seconds — max wait for MATCHED on sports markets


@dataclass
class _PendingOrder:
    order_id: str
    label: str
    t_keypress: float
    t_post: float


class FillTracker:
    """Tracks order fills and prints confirmation reports to terminal."""

    def __init__(self, api_key: str, api_secret: str, api_passphrase: str):
        self._api_key = api_key
        self._api_secret = api_secret
        self._api_passphrase = api_passphrase

        self._pending: dict[str, _PendingOrder] = {}
        self._pending_lock = threading.Lock()

        self._ws: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._ping_thread: Optional[threading.Thread] = None
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._portfolio_display = None
        self._football_context = None  # (football_markets, team1_name, team2_name)

    def set_football_context(self, football_markets, team1_name: str, team2_name: str) -> None:
        """Update the football market context for portfolio display."""
        self._football_context = (football_markets, team1_name, team2_name)

    # ── public API ──────────────────────────────────────────────

    def start(self) -> None:
        """Start WebSocket connection and background threads."""
        self._stop_event.clear()

        self._ws = websocket.WebSocketApp(
            WS_URL,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

        self._ws_thread = threading.Thread(
            target=self._ws.run_forever,
            daemon=True,
            name="fill-ws",
        )
        self._ws_thread.start()

        self._ping_thread = threading.Thread(
            target=self._ping_loop,
            daemon=True,
            name="fill-ping",
        )
        self._ping_thread.start()

        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="fill-cleanup",
        )
        self._cleanup_thread.start()

        log.debug("FillTracker started")

    def stop(self) -> None:
        """Stop WebSocket and background threads."""
        self._stop_event.set()
        if self._ws:
            self._ws.close()
        log.debug("FillTracker stopped")

    def report_instant(
        self,
        label: str,
        making_amount: str,
        taking_amount: str,
        is_buy: bool,
        t_keypress: float,
        t_post: float,
    ) -> None:
        """PATH A — immediate fill report from REST response data."""
        making = float(making_amount)
        taking = float(taking_amount)

        if making == 0 or taking == 0:
            return

        if is_buy:
            # making = USDC spent, taking = shares received
            price = making / taking
            fill_usd = making
            fill_shares = taking
        else:
            # making = shares sold, taking = USDC received
            price = taking / making
            fill_usd = taking
            fill_shares = making

        self._print_report(
            path="INSTANT",
            label=label,
            price=price,
            fill_usd=fill_usd,
            fill_shares=fill_shares,
            is_buy=is_buy,
            t_keypress=t_keypress,
            t_post=t_post,
            t_matched=None,
        )

    def register_delayed(
        self,
        order_id: str,
        label: str,
        t_keypress: float,
        t_post: float,
    ) -> None:
        """PATH B — register pending order, wait for WS MATCHED event."""
        if not order_id:
            return
        with self._pending_lock:
            self._pending[order_id] = _PendingOrder(
                order_id=order_id,
                label=label,
                t_keypress=t_keypress,
                t_post=t_post,
            )
        log.debug("Registered delayed order %s", order_id)

    # ── WebSocket callbacks ─────────────────────────────────────

    def _on_open(self, ws):
        auth_msg = json.dumps({
            "type": "user",
            "auth": {
                "apiKey": self._api_key,
                "secret": self._api_secret,
                "passphrase": self._api_passphrase,
            },
            "markets": [],
        })
        ws.send(auth_msg)
        log.debug("FillTracker WS authenticated")

    def _on_message(self, ws, raw):
        if raw == "PONG":
            return

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        # Only care about MATCHED trade events
        if data.get("event_type") != "trade" or data.get("status") != "MATCHED":
            return

        order_id = data.get("taker_order_id", "")
        if not order_id:
            return

        with self._pending_lock:
            pending = self._pending.pop(order_id, None)

        if pending is None:
            return

        t_matched = time.time()
        price = float(data.get("price", 0))
        size = float(data.get("size", 0))
        fill_usd = price * size

        is_buy = pending.label.startswith("BUY")
        fill_shares = size

        self._print_report(
            path="DELAYED",
            label=pending.label,
            price=price,
            fill_usd=fill_usd,
            fill_shares=fill_shares,
            is_buy=is_buy,
            t_keypress=pending.t_keypress,
            t_post=pending.t_post,
            t_matched=t_matched,
        )

    def _on_error(self, ws, error):
        log.debug("FillTracker WS error: %s", error)

    def _on_close(self, ws, close_status, close_msg):
        log.debug("FillTracker WS closed: %s %s", close_status, close_msg)

    # ── background loops ────────────────────────────────────────

    def _ping_loop(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(PING_INTERVAL)
            if self._stop_event.is_set():
                break
            try:
                if self._ws and self._ws.sock and self._ws.sock.connected:
                    self._ws.send("PING")
            except Exception:
                pass

    def _cleanup_loop(self):
        while not self._stop_event.is_set():
            self._stop_event.wait(2)
            if self._stop_event.is_set():
                break
            now = time.time()
            with self._pending_lock:
                expired = [
                    oid for oid, p in self._pending.items()
                    if now - p.t_post > PENDING_TIMEOUT
                ]
                for oid in expired:
                    p = self._pending.pop(oid)
                    log.debug(
                        "Pending order %s timed out after %.1fs (label=%s)",
                        oid, now - p.t_post, p.label,
                    )

    # ── output ──────────────────────────────────────────────────

    def _print_report(
        self,
        path: str,
        label: str,
        price: float,
        fill_usd: float,
        fill_shares: float,
        is_buy: bool,
        t_keypress: float,
        t_post: float,
        t_matched: Optional[float],
    ) -> None:
        send_ms = (t_post - t_keypress) * 1000

        label_color = Fore.GREEN if is_buy else Fore.RED

        # "TEAM1" -> "TEAM 1", "TEAM2" -> "TEAM 2"
        display_label = label.replace("TEAM", "TEAM ")

        t_end = t_matched if t_matched is not None else t_post
        total_ms = (t_end - t_keypress) * 1000

        lines = [
            f"{Fore.CYAN}FILL CONFIRMED ({path}){Style.RESET_ALL}",
            f"  {label_color}{display_label} ${fill_usd:.2f}{Style.RESET_ALL}",
            f"  Fill price: ${price:.4f}/share",
            f"  Send:   {send_ms:.0f}ms",
        ]

        if t_matched is not None:
            delay_ms = (t_matched - t_post) * 1000
            lines.append(f"  Delay:  {delay_ms:.0f}ms")

        lines.append(
            f"  {Fore.CYAN}Total:  {total_ms:.0f}ms (keypress -> fill){Style.RESET_ALL}"
        )

        print("\n".join(lines))

        if self._portfolio_display and self._football_context:
            fm, t1, t2 = self._football_context
            threading.Timer(3.0, self._portfolio_display.show, kwargs={
                "label": label,
                "football_markets": fm,
                "team1_name": t1,
                "team2_name": t2,
                "fill_price": price,
                "fill_shares": fill_shares,
                "is_buy": is_buy,
            }).start()
