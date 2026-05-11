import json
import sys
from pathlib import Path

APP_NAME = "ScreenShift"
BASE_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULT_CONFIG = {
    "autostart": True,
    "profiles": [
        {
            "name": "Work",
            "hotkey": "ctrl+alt+1",
            "monitors": {
                "\\\\.\\DISPLAY1": {
                    "enabled": True,
                    "primary": True,
                    "width": 1920,
                    "height": 1080,
                    "refresh_rate": 60,
                    "position_x": 0,
                    "position_y": 0,
                },
                "\\\\.\\DISPLAY2": {"enabled": False},
            },
        },
        {
            "name": "Gaming",
            "hotkey": "ctrl+alt+2",
            "monitors": {
                "\\\\.\\DISPLAY1": {"enabled": False},
                "\\\\.\\DISPLAY2": {
                    "enabled": True,
                    "primary": True,
                    "width": 2560,
                    "height": 1440,
                    "refresh_rate": 144,
                    "position_x": 0,
                    "position_y": 0,
                },
            },
        },
    ],
}


class Config:
    def __init__(self, path: Path = None):
        self._path = path or CONFIG_PATH
        self.data = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            with open(self._path, encoding='utf-8') as f:
                return json.load(f)
        with open(self._path, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        return DEFAULT_CONFIG.copy()

    @property
    def profiles(self) -> list:
        return self.data.get('profiles', [])

    @property
    def autostart(self) -> bool:
        return self.data.get('autostart', False)
