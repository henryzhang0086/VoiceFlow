"""Recording indicator — visual feedback while recording.

MenuBarIndicator: Updates the macOS menu bar title with unicode audio level
    bars. Zero dependencies beyond rumps (no AppKit windows needed).

NullIndicator: no-op for CLI, headless, and unsupported platforms.
"""

from __future__ import annotations

_BARS = " ▁▂▃▄▅▆▇"
_NUM_DISPLAY = 8  # number of bar characters to show


class NullIndicator:
    """No-op indicator for CLI / headless / unsupported platforms."""

    def show(self, style: str = "dot") -> None:
        pass

    def hide(self) -> None:
        pass

    def update_level(self, level: float) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def render_title(self) -> str | None:
        return None


class MenuBarIndicator:
    """Recording indicator that renders as unicode bars in the menu bar title.

    Usage:
        indicator.show()           # start showing
        indicator.update_level(x)  # feed audio levels (0.0–1.0)
        title = indicator.render_title()  # get current title string
        indicator.hide()           # stop
    """

    def __init__(self) -> None:
        self._active = False
        self._levels = [0.0] * _NUM_DISPLAY
        self._idx = 0

    def show(self, style: str = "dot") -> None:
        self._active = True
        self._levels = [0.0] * _NUM_DISPLAY
        self._idx = 0

    def hide(self) -> None:
        self._active = False

    def update_level(self, level: float) -> None:
        if self._active:
            self._levels[self._idx % _NUM_DISPLAY] = min(1.0, max(0.0, level))
            self._idx += 1

    def render_title(self) -> str | None:
        """Return the menu bar title string, or None if not active."""
        if not self._active:
            return None
        # Build bar string from recent levels (oldest to newest)
        bars = []
        for i in range(_NUM_DISPLAY):
            buf_idx = (self._idx - _NUM_DISPLAY + i) % _NUM_DISPLAY
            level = self._levels[buf_idx]
            char_idx = int(level * (len(_BARS) - 1))
            bars.append(_BARS[char_idx])
        return "🔴" + "".join(bars)

    def shutdown(self) -> None:
        self._active = False
