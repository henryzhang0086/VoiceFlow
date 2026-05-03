"""VoiceFlow macOS menu bar application via rumps.

Thin shell over VoiceEngine — all business logic lives in engine.py.
Provides: menu bar icon + status + hotkey selection + start/stop control.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import rumps

from .config import Config, load_config
from .factory import create_engine
from .hotkey import CombinedHotkeyListener, LoneTapToggleListener, _LONE_TAP_KEYS
from .indicator import MenuBarIndicator
from . import overlay

_HOTKEY_OPTIONS = [
    ("Shift（单击）", "shift"),
    ("右 Shift（单击）", "shift_r"),
    ("Control（单击）", "ctrl"),
    ("右 Control（单击）", "ctrl_r"),
    ("Option/Alt（单击）", "alt"),
    ("Fn（按住）", "fn"),
    ("F5（按住）", "f5"),
    ("F6（按住）", "f6"),
]


class VoiceFlowApp(rumps.App):
    def __init__(self, config: Config):
        super().__init__("VoiceF", quit_button=None)
        self._config = config
        self._engine = None
        self._indicator = MenuBarIndicator()
        self._hotkey_listener = None
        self._loading = True
        self._recording = False
        self._current_hotkey = config.toggle_hotkey or config.hotkey

        self.icon = None
        self.title = "🎙️"
        icon_dir = Path(__file__).parent / "icons"
        self._ripple_frames = [str(icon_dir / f"ripple_{i}.png") for i in range(4)]
        self._ripple_idx = 0
        self._last_ripple = 0.0

        hotkey_menu = rumps.MenuItem("快捷键")
        for label, key in _HOTKEY_OPTIONS:
            item = rumps.MenuItem(
                f"{'✓ ' if key == self._current_hotkey else '  '}{label}",
                callback=self._make_hotkey_callback(key),
            )
            hotkey_menu.add(item)

        self.menu = [
            rumps.MenuItem("状态: 加载中...", callback=None),
            None,
            hotkey_menu,
            None,
            rumps.MenuItem("退出", callback=self._quit),
        ]

        threading.Thread(target=self._load_engine, daemon=True).start()

    def _make_hotkey_callback(self, key: str):
        def callback(_):
            self._switch_hotkey(key)
        return callback

    def _switch_hotkey(self, new_key: str) -> None:
        if new_key == self._current_hotkey:
            return

        if self._hotkey_listener:
            self._hotkey_listener.stop()

        self._current_hotkey = new_key
        self._start_hotkey_listener(new_key)
        self._save_hotkey(new_key)

        hotkey_menu = self.menu["快捷键"]
        for label, key in _HOTKEY_OPTIONS:
            prefix = "✓ " if key == new_key else "  "
            menu_label_old_checked = f"✓ {label}"
            menu_label_old_unchecked = f"  {label}"
            if menu_label_old_checked in hotkey_menu:
                hotkey_menu[menu_label_old_checked].title = f"{prefix}{label}"
            elif menu_label_old_unchecked in hotkey_menu:
                hotkey_menu[menu_label_old_unchecked].title = f"{prefix}{label}"

    def _start_hotkey_listener(self, hotkey_name: str) -> None:
        if hotkey_name in _LONE_TAP_KEYS:
            self._hotkey_listener = LoneTapToggleListener(
                hotkey=hotkey_name,
                on_start=self._start_recording,
                on_stop=self._stop_recording,
            )
        else:
            self._hotkey_listener = CombinedHotkeyListener(
                hold_hotkey=hotkey_name,
                hold_on_press=self._start_recording,
                hold_on_release=self._stop_recording,
            )
        self._hotkey_listener.start()

    def _save_hotkey(self, key: str) -> None:
        """Persist hotkey choice to config.yaml."""
        config_path = Path.cwd() / "config.yaml"
        if not config_path.exists():
            config_path = Path(__file__).parent.parent / "config.yaml"
        if not config_path.exists():
            return

        lines = config_path.read_text(encoding="utf-8").splitlines()
        new_lines = []
        for line in lines:
            if line.startswith("hotkey:"):
                new_lines.append(f"hotkey: {key}")
            elif line.startswith("toggle_hotkey:"):
                new_lines.append(f"toggle_hotkey: {key}")
            else:
                new_lines.append(line)
        config_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    def _load_engine(self) -> None:
        try:
            self._engine = create_engine(
                self._config,
                on_result=self._on_result,
                on_error=self._on_error,
            )
            self._engine.recorder._on_level = self._on_audio_level

            self._engine.start()

            self._start_hotkey_listener(self._current_hotkey)

            self._loading = False
            self._update_status("空闲")
        except Exception as e:
            self._update_status(f"错误: {e}")

    def _start_recording(self) -> None:
        if self._engine and not self._loading:
            self._engine.start_recording()
            self._indicator.show()
            overlay.show()
            self._recording = True
            self._ripple_idx = 0
            self._last_ripple = 0.0
            self.title = ""
            self.icon = self._ripple_frames[0]
            self.template = True
            self._update_status("录音中...")

    def _stop_recording(self) -> None:
        if self._engine and not self._loading:
            self._recording = False
            self._indicator.hide()
            self.icon = None
            self.title = "🎙️"
            self._engine.stop_recording()
            self._update_status("转写中...")

    def _on_audio_level(self, level: float) -> None:
        self._indicator.update_level(level)
        overlay.update_level(level)
        if self._recording:
            now = time.monotonic()
            if now - self._last_ripple > 0.6:
                self._last_ripple = now
                self._ripple_idx = (self._ripple_idx + 1) % 4
                self.icon = self._ripple_frames[self._ripple_idx]
                self.template = True

    def _on_result(self, text: str) -> None:
        overlay.hide()
        self.icon = None
        self.title = "🎙️"
        self._update_status("空闲")

    def _on_error(self, exc: Exception) -> None:
        overlay.hide()
        self.icon = None
        self.title = "🎙️"
        self._update_status(f"错误: {exc}")

    def _update_status(self, status: str) -> None:
        try:
            first_key = list(self.menu.keys())[0]
            self.menu[first_key].title = f"状态: {status}"
        except (IndexError, KeyError):
            pass

    def _quit(self, _) -> None:
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        overlay.shutdown()
        if self._engine:
            self._engine.shutdown()
        rumps.quit_application()


def main():
    config_path = Path.cwd() / "config.yaml"
    if not config_path.exists():
        config_path = Path(__file__).parent.parent / "config.yaml"

    config = load_config(str(config_path) if config_path.exists() else None)

    if not config.sensevoice_model_path:
        model_dir = Path.home() / "quantflow/voiceflow/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
        if model_dir.exists():
            config.sensevoice_model_path = str(model_dir / "model.onnx")
            config.sensevoice_tokens_path = str(model_dir / "tokens.txt")

    app = VoiceFlowApp(config)
    app.run()


if __name__ == "__main__":
    main()
