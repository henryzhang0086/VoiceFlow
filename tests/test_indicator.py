"""Tests for the recording indicator module."""

from voice_input_method.indicator import MenuBarIndicator, NullIndicator
from voice_input_method.protocols import RecordingIndicator


class TestNullIndicator:
    """NullIndicator should be a silent no-op that satisfies the Protocol."""

    def test_satisfies_protocol(self):
        assert isinstance(NullIndicator(), RecordingIndicator)

    def test_show_is_noop(self):
        indicator = NullIndicator()
        indicator.show()

    def test_hide_is_noop(self):
        indicator = NullIndicator()
        indicator.hide()

    def test_shutdown_is_noop(self):
        indicator = NullIndicator()
        indicator.shutdown()

    def test_full_lifecycle(self):
        indicator = NullIndicator()
        indicator.show()
        indicator.update_level(0.5)
        indicator.hide()
        indicator.shutdown()


class TestMenuBarIndicator:
    def test_satisfies_protocol(self):
        assert isinstance(MenuBarIndicator(), RecordingIndicator)

    def test_inactive_returns_none(self):
        ind = MenuBarIndicator()
        assert ind.render_title() is None

    def test_active_returns_title(self):
        ind = MenuBarIndicator()
        ind.show()
        for i in range(8):
            ind.update_level(0.3 + i * 0.05)
        title = ind.render_title()
        assert title.startswith("🔴")
        assert len(title) == 9  # 🔴 + 8 bar chars

    def test_levels_reflected_in_bars(self):
        ind = MenuBarIndicator()
        ind.show()
        # Feed max levels
        for _ in range(8):
            ind.update_level(1.0)
        title = ind.render_title()
        assert "▇" in title

    def test_zero_levels(self):
        ind = MenuBarIndicator()
        ind.show()
        for _ in range(8):
            ind.update_level(0.0)
        title = ind.render_title()
        # All spaces (lowest bar)
        assert title == "🔴" + " " * 8

    def test_hide_stops(self):
        ind = MenuBarIndicator()
        ind.show()
        ind.update_level(0.5)
        ind.hide()
        assert ind.render_title() is None

    def test_update_when_inactive_ignored(self):
        ind = MenuBarIndicator()
        ind.update_level(0.9)
        assert ind.render_title() is None
