"""
Hotkey management module using the keyboard library.

Handles:
- Global hotkey registration
- Thread-safe callbacks
- Hotkey lifecycle management
- Periodic refresh callback

IMPORTANT: On Windows, this requires Administrator privileges to capture
global hotkeys. Run the terminal/IDE as Administrator.
"""

import keyboard
from typing import Dict, Callable, Optional
from threading import Lock, Event, Thread
import time


class HotkeyManager:
    """
    Manages global hotkey registration and callbacks.

    The keyboard library runs callbacks in a separate thread automatically,
    so all callbacks provided should be thread-safe or handle their own
    synchronization.

    Usage:
        manager = HotkeyManager()
        manager.register_hotkey("buy_yes", "ctrl+1", lambda: print("Buy YES!"))
        manager.start()  # Blocks until stop() is called
    """

    def __init__(self):
        """Initialize the hotkey manager."""
        self._hotkeys: Dict[str, str] = {}  # action_name -> hotkey combo
        self._callbacks: Dict[str, Callable] = {}  # action_name -> callback
        self._lock = Lock()
        self._stop_event = Event()

        # Callback for UI feedback when hotkey is pressed
        self._on_hotkey_pressed: Optional[Callable[[str], None]] = None

        # Periodic refresh callback
        self._refresh_callback: Optional[Callable[[], None]] = None
        self._refresh_interval: float = 2.0  # seconds

    def register_hotkey(
        self,
        action_name: str,
        hotkey_combo: str,
        callback: Callable,
        suppress: bool = False
    ) -> bool:
        """
        Register a hotkey with its callback.

        Args:
            action_name: Descriptive name (e.g., "buy_yes_small")
            hotkey_combo: Key combination (e.g., "ctrl+1", "ctrl+shift+b")
            callback: Function to call when hotkey is pressed
            suppress: If True, prevent the key from being passed to other apps

        Returns:
            True if registration succeeded, False otherwise

        Example:
            manager.register_hotkey("buy_yes", "ctrl+1", lambda: trader.buy_yes(100))
        """
        with self._lock:
            try:
                # Store mapping
                self._hotkeys[action_name] = hotkey_combo
                self._callbacks[action_name] = callback

                # Create wrapper that notifies UI and handles errors
                def wrapped_callback():
                    try:
                        # Notify UI that hotkey was pressed
                        if self._on_hotkey_pressed:
                            self._on_hotkey_pressed(action_name)
                        # Execute the actual callback
                        callback()
                    except Exception as e:
                        print(f"Error in hotkey callback '{action_name}': {e}")

                # Register with keyboard library
                # Note: callback runs in separate thread automatically
                keyboard.add_hotkey(
                    hotkey_combo,
                    wrapped_callback,
                    suppress=suppress
                )

                return True

            except Exception as e:
                print(f"Failed to register hotkey '{action_name}': {e}")
                return False

    def unregister_hotkey(self, action_name: str) -> bool:
        """
        Remove a registered hotkey.

        Args:
            action_name: The name of the hotkey to remove

        Returns:
            True if unregistration succeeded
        """
        with self._lock:
            if action_name not in self._hotkeys:
                return False

            try:
                hotkey_combo = self._hotkeys[action_name]
                keyboard.remove_hotkey(hotkey_combo)

                del self._hotkeys[action_name]
                del self._callbacks[action_name]

                return True
            except Exception as e:
                print(f"Failed to unregister hotkey '{action_name}': {e}")
                return False

    def unregister_all(self) -> None:
        """Remove all registered hotkeys."""
        with self._lock:
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
            self._hotkeys.clear()
            self._callbacks.clear()

    def suspend_all(self) -> None:
        """Temporarily unhook all hotkeys without clearing the registry."""
        with self._lock:
            try:
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass

    def resume_all(self) -> None:
        """Re-register all hotkeys after a suspend."""
        with self._lock:
            for action_name, hotkey_combo in list(self._hotkeys.items()):
                callback = self._callbacks.get(action_name)
                if not callback:
                    continue

                on_pressed = self._on_hotkey_pressed

                def make_wrapper(cb, name, on_p):
                    def wrapped():
                        try:
                            if on_p:
                                on_p(name)
                            cb()
                        except Exception:
                            pass
                    return wrapped

                try:
                    keyboard.add_hotkey(
                        hotkey_combo,
                        make_wrapper(callback, action_name, on_pressed),
                        suppress=False
                    )
                except Exception:
                    pass

    def set_hotkey_pressed_callback(self, callback: Callable[[str], None]) -> None:
        """
        Set callback for when any hotkey is pressed (for UI feedback).

        Args:
            callback: Function receiving the action_name as argument
        """
        self._on_hotkey_pressed = callback

    def set_refresh_callback(self, callback: Callable[[], None], interval: float = 2.0) -> None:
        """
        Set a callback to be called periodically for refreshing data.

        Args:
            callback: Function to call periodically
            interval: Time between calls in seconds
        """
        self._refresh_callback = callback
        self._refresh_interval = interval

    def get_registered_hotkeys(self) -> Dict[str, str]:
        """
        Get all registered hotkeys.

        Returns:
            Dict mapping action_name to hotkey_combo
        """
        with self._lock:
            return dict(self._hotkeys)

    def start(self) -> None:
        """
        Start listening for hotkeys.

        This is a blocking call that keeps the main thread alive
        until stop() is called from a callback or another thread.
        Also runs periodic refresh if configured.
        """
        self._stop_event.clear()

        last_refresh = time.time()

        # Keep the thread alive while listening
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=0.1)

            # Periodic refresh
            if self._refresh_callback:
                now = time.time()
                if now - last_refresh >= self._refresh_interval:
                    try:
                        self._refresh_callback()
                    except Exception as e:
                        print(f"Error in refresh callback: {e}")
                    last_refresh = now

    def stop(self) -> None:
        """
        Stop the hotkey listener.

        Can be called from a hotkey callback to exit the main loop.
        """
        self._stop_event.set()
        self.unregister_all()

    def is_running(self) -> bool:
        """Check if the manager is currently running."""
        return not self._stop_event.is_set()


def format_hotkey_display(hotkey_combo: str) -> str:
    """
    Format a hotkey combo for display.

    Converts "ctrl+1" to "CTRL+1" for consistent display.

    Args:
        hotkey_combo: The hotkey combination string

    Returns:
        Formatted string for display
    """
    return hotkey_combo.upper().replace("+", " + ")