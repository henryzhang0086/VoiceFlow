"""macOS backend: text input via a signed helper binary.

Uses a separate signed binary (paste_helper) with its own Accessibility
permission to type text via CGEventKeyboardSetUnicodeString.
"""

import subprocess
import time
from pathlib import Path

from .base import PlatformBackend

_TYPE_HELPER = str(Path.home() / "Applications/VoiceFlow.app/Contents/MacOS/paste_helper")


class MacOSBackend(PlatformBackend):
    def __init__(self):
        pass

    def paste_text(self, text: str):
        subprocess.Popen(
            [_TYPE_HELPER, text],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

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
