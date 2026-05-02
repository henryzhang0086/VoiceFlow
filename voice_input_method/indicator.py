"""Recording indicator overlays — visual feedback while recording.

MacWaveformIndicator: macOS-native floating panel with real-time audio level
    bars. Shows a dark capsule at the bottom of the screen with a pulsing red
    dot and animated waveform bars driven by audio amplitude.

MacNativeIndicator: simpler red dot / ring indicator (legacy).

NullIndicator: no-op for CLI, headless, and unsupported platforms.
"""

from __future__ import annotations

import ctypes
import multiprocessing


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


# ---------------------------------------------------------------------------
# macOS waveform indicator (PyObjC + AppKit in a subprocess)
# ---------------------------------------------------------------------------

_NUM_BARS = 20
_LEVEL_HISTORY = 32  # ring buffer of recent levels for waveform effect


def _run_waveform_process(
    show_event: multiprocessing.synchronize.Event,
    hide_event: multiprocessing.synchronize.Event,
    quit_event: multiprocessing.synchronize.Event,
    level_array,  # multiprocessing.Array('f', _LEVEL_HISTORY)
    level_index,  # multiprocessing.Value('i') — write head
) -> None:
    """Subprocess entry: renders a dark capsule with animated audio bars."""
    try:
        import objc  # noqa: F401
        from AppKit import (
            NSApplication,
            NSBezierPath,
            NSColor,
            NSFloatingWindowLevel,
            NSFont,
            NSFontAttributeName,
            NSForegroundColorAttributeName,
            NSMakeRect,
            NSPanel,
            NSScreen,
            NSString,
            NSTimer,
            NSView,
            NSWindowStyleMaskBorderless,
            NSWindowStyleMaskNonactivatingPanel,
        )
        from Foundation import NSDictionary, NSObject
    except ImportError:
        return

    PANEL_W = 280
    PANEL_H = 44
    CORNER_R = 22
    BOTTOM_MARGIN = 60
    BAR_W = 3
    BAR_GAP = 2
    BAR_AREA_X = 50  # left offset for bars (after the red dot)
    BAR_MAX_H = 28
    BAR_MIN_H = 3
    DOT_R = 7

    # Module-level state for the subprocess (avoids PyObjC ivar issues)
    _panel_ref = [None]
    _view_ref = [None]
    _dot_alpha = [1.0]
    _dot_up = [False]
    _current_levels = [[0.0] * _NUM_BARS]

    class WaveformView(NSView):
        def drawRect_(self, rect):
            w = rect.size.width
            h = rect.size.height

            # Dark capsule background
            bg = NSColor.colorWithCalibratedRed_green_blue_alpha_(0.1, 0.1, 0.12, 0.92)
            bg.setFill()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(0, 0, w, h), CORNER_R, CORNER_R
            ).fill()

            # Pulsing red dot (left side)
            red = NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.95, 0.25, 0.25, _dot_alpha[0]
            )
            red.setFill()
            dot_x = 18
            dot_y = (h - DOT_R * 2) / 2
            NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(dot_x, dot_y, DOT_R * 2, DOT_R * 2)
            ).fill()

            # Audio level bars
            bar_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.4, 0.9, 0.5, 0.9
            )
            bar_color.setFill()

            for i, level in enumerate(_current_levels[0]):
                bar_h = max(BAR_MIN_H, level * BAR_MAX_H)
                x = BAR_AREA_X + i * (BAR_W + BAR_GAP)
                y = (h - bar_h) / 2
                NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    NSMakeRect(x, y, BAR_W, bar_h), 1.5, 1.5
                ).fill()

            # "录音中" text (right side)
            text_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.85, 0.85, 0.85, 0.9
            )
            font = NSFont.systemFontOfSize_(11)
            attrs = NSDictionary.dictionaryWithObjects_forKeys_(
                [font, text_color],
                [NSFontAttributeName, NSForegroundColorAttributeName],
            )
            text = NSString.stringWithString_("录音中")
            text_x = BAR_AREA_X + _NUM_BARS * (BAR_W + BAR_GAP) + 8
            text_y = (h - 14) / 2
            text.drawAtPoint_withAttributes_((text_x, text_y), attrs)

    class Delegate(NSObject):
        def applicationDidFinishLaunching_(self, notification):
            screen = NSScreen.mainScreen().frame()
            x = (screen.size.width - PANEL_W) / 2
            y = BOTTOM_MARGIN

            panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(x, y, PANEL_W, PANEL_H),
                NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
                2,  # NSBackingStoreBuffered
                False,
            )
            panel.setLevel_(NSFloatingWindowLevel)
            panel.setOpaque_(False)
            panel.setBackgroundColor_(NSColor.clearColor())
            panel.setHasShadow_(True)
            panel.setMovableByWindowBackground_(False)
            panel.setIgnoresMouseEvents_(True)
            panel.setCollectionBehavior_(1 << 0)  # canJoinAllSpaces

            waveform_view = WaveformView.alloc().initWithFrame_(
                NSMakeRect(0, 0, PANEL_W, PANEL_H)
            )
            panel.setContentView_(waveform_view)

            _panel_ref[0] = panel
            _view_ref[0] = waveform_view

            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.04, self, "tick:", None, True
            )

        def tick_(self, timer):
            if quit_event.is_set():
                NSApplication.sharedApplication().terminate_(None)
                return

            panel = _panel_ref[0]
            if panel is None:
                return

            if show_event.is_set():
                show_event.clear()
                screen = NSScreen.mainScreen().frame()
                x = (screen.size.width - PANEL_W) / 2
                panel.setFrameOrigin_((x, BOTTOM_MARGIN))
                panel.orderFront_(None)

            if hide_event.is_set():
                hide_event.clear()
                panel.orderOut_(None)

            if panel.isVisible():
                # Read level ring buffer and build bar heights
                idx = level_index.value
                levels = []
                for i in range(_NUM_BARS):
                    buf_idx = (idx - _NUM_BARS + i) % _LEVEL_HISTORY
                    levels.append(level_array[buf_idx])
                _current_levels[0] = levels

                # Pulse the red dot
                step = 0.04
                if _dot_up[0]:
                    _dot_alpha[0] = min(1.0, _dot_alpha[0] + step)
                    if _dot_alpha[0] >= 1.0:
                        _dot_up[0] = False
                else:
                    _dot_alpha[0] = max(0.4, _dot_alpha[0] - step)
                    if _dot_alpha[0] <= 0.4:
                        _dot_up[0] = True

                _view_ref[0].setNeedsDisplay_(True)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)  # Accessory
    delegate = Delegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


class MacWaveformIndicator:
    """macOS recording indicator with real-time audio waveform bars."""

    def __init__(self) -> None:
        ctx = multiprocessing.get_context("spawn")
        self._show_event = ctx.Event()
        self._hide_event = ctx.Event()
        self._quit_event = ctx.Event()
        self._level_array = ctx.Array(ctypes.c_float, _LEVEL_HISTORY)
        self._level_index = ctx.Value("i", 0)
        self._process = ctx.Process(
            target=_run_waveform_process,
            args=(
                self._show_event, self._hide_event, self._quit_event,
                self._level_array, self._level_index,
            ),
            daemon=True,
        )
        self._process.start()

    def show(self, style: str = "dot") -> None:
        if self._process.is_alive():
            self._show_event.set()

    def hide(self) -> None:
        if self._process.is_alive():
            self._hide_event.set()

    def update_level(self, level: float) -> None:
        """Write a new audio level sample into the ring buffer."""
        if self._process.is_alive():
            idx = self._level_index.value
            self._level_array[idx % _LEVEL_HISTORY] = min(1.0, max(0.0, level))
            self._level_index.value = idx + 1

    def shutdown(self) -> None:
        if self._process.is_alive():
            self._quit_event.set()
            self._process.join(timeout=2)
            if self._process.is_alive():
                self._process.terminate()


# ---------------------------------------------------------------------------
# Legacy: simple red dot indicator
# ---------------------------------------------------------------------------

def _run_indicator_process(
    show_event: multiprocessing.synchronize.Event,
    hide_event: multiprocessing.synchronize.Event,
    quit_event: multiprocessing.synchronize.Event,
    style_value,
) -> None:
    """Entry point for the legacy red dot indicator subprocess."""
    try:
        import objc  # noqa: F401
        from AppKit import (
            NSApplication,
            NSBezierPath,
            NSColor,
            NSFloatingWindowLevel,
            NSMakeRect,
            NSPanel,
            NSScreen,
            NSTimer,
            NSView,
            NSWindowStyleMaskBorderless,
            NSWindowStyleMaskNonactivatingPanel,
        )
        from Foundation import NSObject
    except ImportError:
        return

    DOT_SIZE = 20
    RING_SIZE = 36
    BOTTOM_MARGIN = 80

    class IndicatorView(NSView):
        _pulse_alpha = 1.0
        _style = 0

        def drawRect_(self, rect):
            w = rect.size.width
            h = rect.size.height

            if self._style == 1:
                white = NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    1.0, 1.0, 1.0, 0.35 * self._pulse_alpha
                )
                white.setFill()
                NSBezierPath.bezierPathWithOvalInRect_(
                    NSMakeRect(0, 0, w, h)
                ).fill()

            red = NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.95, 0.2, 0.2, self._pulse_alpha
            )
            red.setFill()
            inset = (w - DOT_SIZE) / 2
            NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(inset, inset, DOT_SIZE, DOT_SIZE)
            ).fill()

        def setPulseAlpha_(self, alpha):
            self._pulse_alpha = alpha
            self.setNeedsDisplay_(True)

        def setStyle_(self, style):
            self._style = style
            self.setNeedsDisplay_(True)

    class Delegate(NSObject):
        panel = objc.ivar()
        indicator_view = objc.ivar()
        _pulse_up = objc.ivar()
        _current_alpha = objc.ivar()

        def applicationDidFinishLaunching_(self, notification):
            self._pulse_up = False
            self._current_alpha = 1.0

            screen = NSScreen.mainScreen().frame()
            x = (screen.size.width - RING_SIZE) / 2
            y = BOTTOM_MARGIN

            panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(x, y, RING_SIZE, RING_SIZE),
                NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
                2,
                False,
            )
            panel.setLevel_(NSFloatingWindowLevel)
            panel.setOpaque_(False)
            panel.setBackgroundColor_(NSColor.clearColor())
            panel.setHasShadow_(True)
            panel.setMovableByWindowBackground_(False)
            panel.setIgnoresMouseEvents_(True)
            panel.setCollectionBehavior_(1 << 0)

            indicator_view = IndicatorView.alloc().initWithFrame_(
                NSMakeRect(0, 0, RING_SIZE, RING_SIZE)
            )
            panel.setContentView_(indicator_view)

            self.panel = panel
            self.indicator_view = indicator_view

            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.05, self, "pollEvents:", None, True
            )

        def pollEvents_(self, timer):
            if quit_event.is_set():
                NSApplication.sharedApplication().terminate_(None)
                return

            if show_event.is_set():
                show_event.clear()
                self.indicator_view.setStyle_(style_value.value)
                screen = NSScreen.mainScreen().frame()
                x = (screen.size.width - RING_SIZE) / 2
                y = BOTTOM_MARGIN
                self.panel.setFrameOrigin_((x, y))
                self.panel.orderFront_(None)
                NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    0.05, self, "pulseAnimation:", None, True
                )

            if hide_event.is_set():
                hide_event.clear()
                self.panel.orderOut_(None)

        def pulseAnimation_(self, timer):
            if not self.panel.isVisible():
                timer.invalidate()
                self._current_alpha = 1.0
                return

            step = 0.03
            if self._pulse_up:
                self._current_alpha = min(1.0, self._current_alpha + step)
                if self._current_alpha >= 1.0:
                    self._pulse_up = False
            else:
                self._current_alpha = max(0.5, self._current_alpha - step)
                if self._current_alpha <= 0.5:
                    self._pulse_up = True

            self.indicator_view.setPulseAlpha_(self._current_alpha)

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)
    delegate = Delegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


class MacNativeIndicator:
    """macOS-native recording indicator using AppKit in a subprocess (legacy dot)."""

    def __init__(self) -> None:
        ctx = multiprocessing.get_context("spawn")
        self._show_event = ctx.Event()
        self._hide_event = ctx.Event()
        self._quit_event = ctx.Event()
        self._style_value = ctx.Value("i", 0)
        self._process = ctx.Process(
            target=_run_indicator_process,
            args=(self._show_event, self._hide_event, self._quit_event, self._style_value),
            daemon=True,
        )
        self._process.start()

    def show(self, style: str = "dot") -> None:
        if self._process.is_alive():
            self._style_value.value = 1 if style == "ring" else 0
            self._show_event.set()

    def hide(self) -> None:
        if self._process.is_alive():
            self._hide_event.set()

    def update_level(self, level: float) -> None:
        pass

    def shutdown(self) -> None:
        if self._process.is_alive():
            self._quit_event.set()
            self._process.join(timeout=2)
            if self._process.is_alive():
                self._process.terminate()
