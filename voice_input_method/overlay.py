"""Floating waveform overlay — NSPanel at screen bottom center.

Uses NSPanel with nonactivatingPanel style mask so it displays from a
menu bar (Accessory policy) app without stealing focus. Audio levels are
fed from the PortAudio thread; drawing is driven by an NSTimer on the
main run loop.
"""

from __future__ import annotations

from AppKit import (
    NSApp,
    NSColor,
    NSFloatingWindowLevel,
    NSPanel,
    NSRunLoop,
    NSScreen,
    NSTimer,
    NSView,
)
from Foundation import NSMakeRect, NSObject, NSRunLoopCommonModes
from Quartz import CGColorCreateGenericRGB

_NUM_BARS = 18
_BAR_WIDTH = 4
_BAR_GAP = 2
_PANEL_HEIGHT = 32
_PANEL_PADDING = 10
_PANEL_WIDTH = _NUM_BARS * (_BAR_WIDTH + _BAR_GAP) - _BAR_GAP + _PANEL_PADDING * 2
_CORNER_RADIUS = 8
_MAX_BAR_HEIGHT = _PANEL_HEIGHT - 10

_state = {
    "panel": None,
    "content": None,
    "bars": [],
    "levels": [0.0] * _NUM_BARS,
    "idx": 0,
    "active": False,
    "timer": None,
    "ticker": None,
}


class _Ticker(NSObject):
    """Minimal ObjC object — timer target + main-thread dispatcher."""

    def tick_(self, timer):
        _refresh()

    def doShow_(self, _):
        _do_show()

    def doHide_(self, _):
        _do_hide()


def _get_ticker():
    if _state["ticker"] is None:
        _state["ticker"] = _Ticker.alloc().init()
    return _state["ticker"]


def _ensure_panel():
    if _state["panel"] is not None:
        return

    screen = NSScreen.mainScreen()
    sf = screen.frame()
    x = (sf.size.width - _PANEL_WIDTH) / 2
    y = 80

    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(x, y, _PANEL_WIDTH, _PANEL_HEIGHT),
        128,  # NSNonactivatingPanelMask
        2,  # NSBackingStoreBuffered
        False,
    )
    panel.setLevel_(NSFloatingWindowLevel)
    panel.setHidesOnDeactivate_(False)
    panel.setIgnoresMouseEvents_(True)
    panel.setOpaque_(False)
    panel.setBackgroundColor_(NSColor.clearColor())
    panel.setHasShadow_(True)
    panel.setCollectionBehavior_(1 | (1 << 4))

    content = NSView.alloc().initWithFrame_(
        NSMakeRect(0, 0, _PANEL_WIDTH, _PANEL_HEIGHT)
    )
    content.setWantsLayer_(True)
    content.layer().setBackgroundColor_(CGColorCreateGenericRGB(0.1, 0.1, 0.1, 0.85))
    content.layer().setCornerRadius_(_CORNER_RADIUS)
    panel.setContentView_(content)

    bars = []
    for i in range(_NUM_BARS):
        bx = _PANEL_PADDING + i * (_BAR_WIDTH + _BAR_GAP)
        bar = NSView.alloc().initWithFrame_(
            NSMakeRect(bx, _PANEL_HEIGHT / 2 - 1, _BAR_WIDTH, 2)
        )
        bar.setWantsLayer_(True)
        bar.layer().setCornerRadius_(1.5)
        bar.layer().setBackgroundColor_(CGColorCreateGenericRGB(0.1, 0.6, 0.2, 0.7))
        content.addSubview_(bar)
        bars.append(bar)

    _state["panel"] = panel
    _state["content"] = content
    _state["bars"] = bars


def _refresh():
    """Timer callback (main thread) — update bar heights from level buffer."""
    if not _state["active"]:
        return
    bars = _state["bars"]
    levels = _state["levels"]
    idx = _state["idx"]
    for i in range(_NUM_BARS):
        buf_idx = (idx - _NUM_BARS + i) % _NUM_BARS
        level = levels[buf_idx]
        h = max(2.0, level * _MAX_BAR_HEIGHT)
        bar = bars[i]
        bx = _PANEL_PADDING + i * (_BAR_WIDTH + _BAR_GAP)
        y = (_PANEL_HEIGHT - h) / 2
        bar.setFrame_(NSMakeRect(bx, y, _BAR_WIDTH, h))
        green_val = 0.4 + level * 0.6
        alpha = 0.5 + level * 0.5
        bar.layer().setBackgroundColor_(
            CGColorCreateGenericRGB(0.1 * level, green_val, 0.2, alpha)
        )


def _do_show():
    """Must run on main thread."""
    _ensure_panel()
    _state["panel"].orderFrontRegardless()
    NSApp.setActivationPolicy_(1)
    _start_timer()


def _do_hide():
    """Must run on main thread."""
    _stop_timer()
    if _state["panel"]:
        _state["panel"].orderOut_(None)


def _start_timer():
    if _state["timer"] is not None:
        return
    ticker = _get_ticker()
    timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
        0.05, ticker, b"tick:", None, True
    )
    NSRunLoop.mainRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)
    _state["timer"] = timer


def _stop_timer():
    if _state["timer"]:
        _state["timer"].invalidate()
        _state["timer"] = None


# --- Public API (thread-safe) ---


def init_on_main_thread():
    """Pre-create the panel. MUST be called from main thread (e.g. app init)."""
    _ensure_panel()


def show():
    """Show the overlay. Safe to call from any thread."""
    _state["active"] = True
    _state["levels"] = [0.0] * _NUM_BARS
    _state["idx"] = 0
    ticker = _get_ticker()
    ticker.performSelectorOnMainThread_withObject_waitUntilDone_(
        b"doShow:", None, False
    )


def hide():
    """Hide the overlay. Safe to call from any thread."""
    _state["active"] = False
    ticker = _get_ticker()
    ticker.performSelectorOnMainThread_withObject_waitUntilDone_(
        b"doHide:", None, False
    )


def update_level(level: float):
    """Feed an audio level (0.0–1.0). Called from audio thread."""
    if _state["active"]:
        _state["levels"][_state["idx"] % _NUM_BARS] = min(1.0, max(0.0, level))
        _state["idx"] += 1


def shutdown():
    """Tear down overlay completely."""
    _state["active"] = False
    ticker = _get_ticker()
    ticker.performSelectorOnMainThread_withObject_waitUntilDone_(
        b"doHide:", None, True
    )
    if _state["panel"]:
        _state["panel"] = None
    _state["bars"] = []
