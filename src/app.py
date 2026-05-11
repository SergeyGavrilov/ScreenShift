import ctypes
import os
import threading

import keyboard
import pystray
from PIL import Image, ImageDraw

from src.autostart import autostart_enable
from src.config import APP_NAME, CONFIG_PATH, Config
from src.display import DisplayManager
from src.switcher import switch_to


def _make_icon() -> Image.Image:
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([2, 10, 62, 46], outline='white', width=3, fill='#0f1626')
    d.rectangle([26, 46, 38, 54], fill='white')
    d.rectangle([18, 54, 46, 58], fill='white')
    d.polygon(
        [(18, 28), (32, 14), (32, 22), (46, 22), (46, 34), (32, 34), (32, 42)],
        fill='#00ccff',
    )
    return img


class ScreenShiftApp:

    def __init__(self):
        self.cfg  = Config()
        self.icon = None
        if self.cfg.autostart:
            autostart_enable()
        self._register_hotkeys()

    def _register_hotkeys(self) -> None:
        for p in self.cfg.profiles:
            if p.get('hotkey'):
                keyboard.add_hotkey(
                    p['hotkey'],
                    lambda prof=p: threading.Thread(
                        target=switch_to, args=(prof, self._notify), daemon=True,
                    ).start(),
                )

    def _notify(self, msg: str) -> None:
        if self.icon:
            self.icon.notify(msg, APP_NAME)

    def _build_menu(self) -> pystray.Menu:
        items = []
        for p in self.cfg.profiles:
            hk    = p.get('hotkey', '')
            label = f"{p['name']}  [{hk}]" if hk else p['name']
            items.append(pystray.MenuItem(
                label,
                lambda _, prof=p: threading.Thread(
                    target=switch_to, args=(prof, self._notify), daemon=True,
                ).start(),
            ))
        items += [
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('List Monitors', lambda _: threading.Thread(
                target=self._show_monitors, daemon=True,
            ).start()),
            pystray.MenuItem('Open Config',   lambda _: os.startfile(str(CONFIG_PATH))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit',          lambda _: self.icon.stop()),
        ]
        return pystray.Menu(*items)

    def _show_monitors(self) -> None:
        lines = []
        for d in DisplayManager.list_displays():
            tags   = (['active'] if d['active'] else []) + (['primary'] if d['primary'] else [])
            status = ', '.join(tags) or 'inactive'
            lines.append(f"{d['name']}  —  {d['description']}  ({status})")
        ctypes.windll.user32.MessageBoxW(
            None,
            '\n'.join(lines) or 'No displays found.',
            f'{APP_NAME} — Monitors',
            0x40,
        )

    def run(self) -> None:
        self.icon = pystray.Icon(APP_NAME, _make_icon(), APP_NAME, self._build_menu())
        self.icon.run()
