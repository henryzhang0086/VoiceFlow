"""macOS backend: clipboard + Cmd+V paste via pyobjc.

Requires Accessibility permissions in System Settings > Privacy & Security.
Uses NSPasteboard for clipboard and CGEvent for key simulation — no Qt dependency.
"""

import sys
import time

from AppKit import NSPasteboard, NSPasteboardTypeString
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    kCGEventFlagMaskCommand,
    kCGHIDEventTap,
)

from .base import PlatformBackend

_kVK_V = 0x09


class MacOSBackend(PlatformBackend):
    def __init__(self):
        self._pasteboard = NSPasteboard.generalPasteboard()

    def paste_text(self, text: str):
        old_contents = self._pasteboard.stringForType_(NSPasteboardTypeString)

        self._pasteboard.clearContents()
        self._pasteboard.setString_forType_(text, NSPasteboardTypeString)

        key_down = CGEventCreateKeyboardEvent(None, _kVK_V, True)
        key_up = CGEventCreateKeyboardEvent(None, _kVK_V, False)
        CGEventSetFlags(key_down, kCGEventFlagMaskCommand)
        CGEventSetFlags(key_up, kCGEventFlagMaskCommand)
        CGEventPost(kCGHIDEventTap, key_down)
        CGEventPost(kCGHIDEventTap, key_up)

        time.sleep(0.05)

        if old_contents:
            self._pasteboard.clearContents()
            self._pasteboard.setString_forType_(old_contents, NSPasteboardTypeString)

    def check_permissions(self) -> list[str]:
        """Check macOS Accessibility permissions."""
        missing = []
        if sys.platform != "darwin":
            return missing
        try:
            from ApplicationServices import AXIsProcessTrusted
            if not AXIsProcessTrusted():
                missing.append(
                    "Accessibility permission required: "
                    "System Settings > Privacy & Security > Accessibility"
                )
        except ImportError:
            # PyObjC not installed, can't check
            pass
        return missing
