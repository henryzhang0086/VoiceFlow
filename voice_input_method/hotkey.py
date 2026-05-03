"""Global hotkey listener — independent of any GUI framework.

Uses pynput for cross-platform keyboard monitoring. The module only
imports pynput when start() is called, so headless environments can
import this module without error.

Supports two concurrent hotkeys via a single pynput Listener:
  - Hold hotkey (press → start, release → stop)
  - Toggle hotkey (press once → start, press again → stop)
  - Lone-tap hotkey (modifier key tapped alone without combining other keys)
"""

from __future__ import annotations

import time
from typing import Callable

# Keys that only fire release events on macOS (need toggle workaround)
_RELEASE_ONLY_KEYS = {"fn"}

# Keys that need lone-tap detection (modifier keys used for typing)
_LONE_TAP_KEYS = {"shift", "shift_r", "ctrl", "ctrl_r", "alt", "alt_r"}


def _resolve_key(name: str):
    """Resolve a hotkey name to a pynput key object. Must be called after pynput import."""
    from pynput import keyboard

    if name == "fn":
        return keyboard.KeyCode.from_vk(63)
    if hasattr(keyboard.Key, name):
        return getattr(keyboard.Key, name)
    return keyboard.Key.f6


class HotkeyListener:
    """Hold mode: press → on_press, release → on_release.

    For keys that only fire release (e.g. fn), auto-falls back to toggle.
    """

    def __init__(self, hotkey: str, on_press: Callable, on_release: Callable):
        self._hotkey_name = hotkey
        self._on_press = on_press
        self._on_release = on_release
        self._listener = None
        self._pressed = False

    def start(self) -> None:
        from pynput import keyboard
        target = _resolve_key(self._hotkey_name)
        use_toggle = self._hotkey_name in _RELEASE_ONLY_KEYS

        if use_toggle:
            def on_press(key):
                pass
            def on_release(key):
                if key == target:
                    if not self._pressed:
                        self._pressed = True
                        self._on_press()
                    else:
                        self._pressed = False
                        self._on_release()
        else:
            def on_press(key):
                try:
                    if key == target and not self._pressed:
                        self._pressed = True
                        self._on_press()
                except AttributeError:
                    pass
            def on_release(key):
                if key == target and self._pressed:
                    self._pressed = False
                    self._on_release()

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    @property
    def is_pressed(self) -> bool:
        return self._pressed


class ToggleHotkeyListener:
    """Toggle mode: press once → on_start, press again → on_stop."""

    def __init__(self, hotkey: str, on_start: Callable, on_stop: Callable):
        self._hotkey_name = hotkey
        self._on_start = on_start
        self._on_stop = on_stop
        self._listener = None
        self._recording = False

    def start(self):
        from pynput import keyboard
        target = _resolve_key(self._hotkey_name)
        release_only = self._hotkey_name in _RELEASE_ONLY_KEYS

        if release_only:
            def on_press(key): pass
            def on_release(key):
                if key == target:
                    self._toggle()
        else:
            def on_press(key):
                try:
                    if key == target:
                        self._toggle()
                except AttributeError:
                    pass
            def on_release(key): pass

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def _toggle(self):
        if not self._recording:
            self._recording = True
            self._on_start()
        else:
            self._recording = False
            self._on_stop()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    @property
    def is_recording(self) -> bool:
        return self._recording


class CombinedHotkeyListener:
    """Runs two hotkeys (hold + toggle) in a single pynput Listener.

    pynput only supports one active Listener per process. This class
    merges both hotkey handlers into one Listener.
    """

    def __init__(
        self,
        hold_hotkey: str,
        hold_on_press: Callable,
        hold_on_release: Callable,
        toggle_hotkey: str | None = None,
        toggle_on_start: Callable | None = None,
        toggle_on_stop: Callable | None = None,
    ):
        self._hold_name = hold_hotkey
        self._hold_on_press = hold_on_press
        self._hold_on_release = hold_on_release
        self._hold_pressed = False

        self._toggle_name = toggle_hotkey
        self._toggle_on_start = toggle_on_start
        self._toggle_on_stop = toggle_on_stop
        self._toggle_recording = False

        self._listener = None

    def start(self):
        from pynput import keyboard

        hold_key = _resolve_key(self._hold_name)
        hold_release_only = self._hold_name in _RELEASE_ONLY_KEYS

        toggle_key = _resolve_key(self._toggle_name) if self._toggle_name else None
        toggle_release_only = self._toggle_name in _RELEASE_ONLY_KEYS if self._toggle_name else False

        def on_press(key):
            if not hold_release_only:
                try:
                    if key == hold_key and not self._hold_pressed and not self._toggle_recording:
                        self._hold_pressed = True
                        self._hold_on_press()
                except AttributeError:
                    pass
            if toggle_key and not toggle_release_only:
                try:
                    if key == toggle_key and not self._hold_pressed:
                        self._do_toggle()
                except AttributeError:
                    pass

        def on_release(key):
            if hold_release_only:
                if key == hold_key and not self._toggle_recording:
                    if not self._hold_pressed:
                        self._hold_pressed = True
                        self._hold_on_press()
                    else:
                        self._hold_pressed = False
                        self._hold_on_release()
            else:
                if key == hold_key and self._hold_pressed:
                    self._hold_pressed = False
                    self._hold_on_release()

            if toggle_key and toggle_release_only:
                if key == toggle_key and not self._hold_pressed:
                    self._do_toggle()

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def _do_toggle(self):
        if not self._toggle_recording:
            self._toggle_recording = True
            if self._toggle_on_start:
                self._toggle_on_start()
        else:
            self._toggle_recording = False
            if self._toggle_on_stop:
                self._toggle_on_stop()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    @property
    def hold_pressed(self) -> bool:
        return self._hold_pressed

    @property
    def toggle_recording(self) -> bool:
        return self._toggle_recording


class LoneTapToggleListener:
    """Toggle triggered by tapping a modifier key alone (no combo).

    Detects: key pressed → no other key pressed in between → key released within threshold.
    This avoids firing when shift is used for capitals (Shift+A) or ctrl for shortcuts.
    """

    def __init__(
        self,
        hotkey: str,
        on_start: Callable,
        on_stop: Callable,
        max_tap_duration: float = 0.4,
    ):
        self._hotkey_name = hotkey
        self._on_start = on_start
        self._on_stop = on_stop
        self._max_tap_duration = max_tap_duration
        self._listener = None
        self._recording = False
        self._target_pressed_at: float = 0
        self._other_key_pressed = False

    def start(self) -> None:
        from pynput import keyboard

        target = _resolve_key(self._hotkey_name)

        def on_press(key):
            if key == target:
                self._target_pressed_at = time.monotonic()
                self._other_key_pressed = False
            elif self._target_pressed_at > 0:
                self._other_key_pressed = True

        def on_release(key):
            if key == target and self._target_pressed_at > 0:
                elapsed = time.monotonic() - self._target_pressed_at
                self._target_pressed_at = 0
                if not self._other_key_pressed and elapsed <= self._max_tap_duration:
                    self._toggle()

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.start()

    def _toggle(self):
        if not self._recording:
            self._recording = True
            self._on_start()
        else:
            self._recording = False
            self._on_stop()

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None

    @property
    def is_recording(self) -> bool:
        return self._recording
