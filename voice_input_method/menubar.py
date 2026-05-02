"""VoiceFlow macOS menu bar application via rumps.

Thin shell over VoiceEngine — all business logic lives in engine.py.
Provides: menu bar icon + status + start/stop control.
"""

from __future__ import annotations

import threading
from pathlib import Path

import rumps

from .config import Config, load_config
from .factory import create_engine
from .hotkey import CombinedHotkeyListener


class VoiceFlowApp(rumps.App):
    def __init__(self, config: Config):
        super().__init__("VoiceFlow", quit_button=None)
        self._config = config
        self._engine = None
        self._hotkey = None
        self._loading = True

        self.icon = None
        self.title = "🎙"
        self.menu = [
            rumps.MenuItem("状态: 加载中...", callback=None),
            None,
            rumps.MenuItem("退出", callback=self._quit),
        ]

        threading.Thread(target=self._load_engine, daemon=True).start()

    def _load_engine(self) -> None:
        try:
            self._engine = create_engine(
                self._config,
                on_result=self._on_result,
                on_error=self._on_error,
            )
            self._engine.start()

            self._hotkey = CombinedHotkeyListener(
                hold_hotkey=self._config.hotkey,
                hold_on_press=self._start_recording,
                hold_on_release=self._stop_recording,
                toggle_hotkey=self._config.toggle_hotkey or None,
                toggle_on_start=self._start_recording,
                toggle_on_stop=self._stop_recording,
            )
            self._hotkey.start()

            self._loading = False
            self._update_status("空闲")
        except Exception as e:
            self._update_status(f"错误: {e}")

    def _start_recording(self) -> None:
        if self._engine and not self._loading:
            self._engine.start_recording()
            self._update_status("录音中...")
            self.title = "🔴"

    def _stop_recording(self) -> None:
        if self._engine and not self._loading:
            self._engine.stop_recording()
            self._update_status("转写中...")
            self.title = "⏳"

    def _on_result(self, text: str) -> None:
        self._update_status("空闲")
        self.title = "🎙"

    def _on_error(self, exc: Exception) -> None:
        self._update_status(f"错误: {exc}")
        self.title = "⚠️"

    def _update_status(self, status: str) -> None:
        if self.menu and "状态: 加载中..." in [item.title for item in self.menu.values()
                                              if hasattr(item, "title")]:
            pass
        try:
            self.menu.keys()
            first_key = list(self.menu.keys())[0]
            self.menu[first_key].title = f"状态: {status}"
        except (IndexError, KeyError):
            pass

    def _quit(self, _) -> None:
        if self._hotkey:
            self._hotkey.stop()
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
