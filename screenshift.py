#!/usr/bin/env python3
"""ScreenShift — Monitor profile switcher for Windows 11"""

import ctypes
import json
import os
import sys
import threading
import time
import winreg
from pathlib import Path

import keyboard
import pystray
import win32api
import win32con
import win32gui
from PIL import Image, ImageDraw

APP_NAME = "ScreenShift"
BASE_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

# ── Win32 Constants ───────────────────────────────────────────────────────────

DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x00000001
DISPLAY_DEVICE_PRIMARY_DEVICE      = 0x00000004

CDS_UPDATEREGISTRY   = 0x00000001
CDS_NORESET          = 0x10000000
DISP_CHANGE_SUCCESSFUL = 0

DM_POSITION         = 0x00000020
DM_BITSPERPEL       = 0x00000004
DM_PELSWIDTH        = 0x00080000
DM_PELSHEIGHT       = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000

ENUM_CURRENT_SETTINGS = -1

# ── Win32 Structures ──────────────────────────────────────────────────────────

class DEVMODE(ctypes.Structure):
    _fields_ = [
        ('dmDeviceName',         ctypes.c_wchar * 32),
        ('dmSpecVersion',        ctypes.c_uint16),
        ('dmDriverVersion',      ctypes.c_uint16),
        ('dmSize',               ctypes.c_uint16),
        ('dmDriverExtra',        ctypes.c_uint16),
        ('dmFields',             ctypes.c_uint32),
        ('dmPositionX',          ctypes.c_int32),
        ('dmPositionY',          ctypes.c_int32),
        ('dmDisplayOrientation', ctypes.c_uint32),
        ('dmDisplayFixedOutput', ctypes.c_uint32),
        ('dmColor',              ctypes.c_int16),
        ('dmDuplex',             ctypes.c_int16),
        ('dmYResolution',        ctypes.c_int16),
        ('dmTTOption',           ctypes.c_int16),
        ('dmCollate',            ctypes.c_int16),
        ('dmFormName',           ctypes.c_wchar * 32),
        ('dmLogPixels',          ctypes.c_uint16),
        ('dmBitsPerPel',         ctypes.c_uint32),
        ('dmPelsWidth',          ctypes.c_uint32),
        ('dmPelsHeight',         ctypes.c_uint32),
        ('dmDisplayFlags',       ctypes.c_uint32),
        ('dmDisplayFrequency',   ctypes.c_uint32),
        ('dmICMMethod',          ctypes.c_uint32),
        ('dmICMIntent',          ctypes.c_uint32),
        ('dmMediaType',          ctypes.c_uint32),
        ('dmDitherType',         ctypes.c_uint32),
        ('dmReserved1',          ctypes.c_uint32),
        ('dmReserved2',          ctypes.c_uint32),
        ('dmPanningWidth',       ctypes.c_uint32),
        ('dmPanningHeight',      ctypes.c_uint32),
    ]


class DISPLAY_DEVICE(ctypes.Structure):
    _fields_ = [
        ('cb',           ctypes.c_uint32),
        ('DeviceName',   ctypes.c_wchar * 32),
        ('DeviceString', ctypes.c_wchar * 128),
        ('StateFlags',   ctypes.c_uint32),
        ('DeviceID',     ctypes.c_wchar * 128),
        ('DeviceKey',    ctypes.c_wchar * 128),
    ]


# ── Display Manager ───────────────────────────────────────────────────────────

class DisplayManager:

    @staticmethod
    def list_displays():
        result, i = [], 0
        while True:
            dd = DISPLAY_DEVICE()
            dd.cb = ctypes.sizeof(DISPLAY_DEVICE)
            if not ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                break
            if dd.DeviceName:
                result.append({
                    'name':        dd.DeviceName,
                    'description': dd.DeviceString,
                    'active':      bool(dd.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP),
                    'primary':     bool(dd.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE),
                })
            i += 1
        return result

    @staticmethod
    def enable_display(device, width, height, refresh_rate, position_x, position_y, bpp=32):
        dm = DEVMODE()
        dm.dmSize            = ctypes.sizeof(DEVMODE)
        dm.dmFields          = DM_PELSWIDTH | DM_PELSHEIGHT | DM_POSITION | DM_DISPLAYFREQUENCY | DM_BITSPERPEL
        dm.dmPelsWidth       = width
        dm.dmPelsHeight      = height
        dm.dmPositionX       = position_x
        dm.dmPositionY       = position_y
        dm.dmDisplayFrequency = refresh_rate
        dm.dmBitsPerPel      = bpp
        return ctypes.windll.user32.ChangeDisplaySettingsExW(
            device, ctypes.byref(dm), None, CDS_UPDATEREGISTRY | CDS_NORESET, None,
        )

    @staticmethod
    def disable_display(device):
        dm = DEVMODE()
        dm.dmSize       = ctypes.sizeof(DEVMODE)
        dm.dmFields     = DM_PELSWIDTH | DM_PELSHEIGHT | DM_POSITION
        dm.dmPelsWidth  = 0
        dm.dmPelsHeight = 0
        dm.dmPositionX  = 0
        dm.dmPositionY  = 0
        return ctypes.windll.user32.ChangeDisplaySettingsExW(
            device, ctypes.byref(dm), None, CDS_UPDATEREGISTRY | CDS_NORESET, None,
        )

    @staticmethod
    def apply_changes():
        return ctypes.windll.user32.ChangeDisplaySettingsExW(None, None, None, 0, None)


# ── Window Migrator ───────────────────────────────────────────────────────────

class WindowMigrator:

    @staticmethod
    def _primary_work_rect():
        for monitor, _, _ in win32api.EnumDisplayMonitors():
            info = win32api.GetMonitorInfo(monitor)
            if info.get('Flags') & 1:
                return info['Work']
        return (0, 0,
                win32api.GetSystemMetrics(win32con.SM_CXSCREEN),
                win32api.GetSystemMetrics(win32con.SM_CYSCREEN))

    @classmethod
    def migrate_all(cls):
        px, py, pr, pb = cls._primary_work_rect()
        pw, ph = pr - px, pb - py

        def _move(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
                return True
            if win32gui.IsIconic(hwnd):
                return True
            try:
                monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONULL)
                if monitor is None:
                    return True
                if win32api.GetMonitorInfo(monitor).get('Flags') & 1:
                    return True  # already on primary
                was_max = win32gui.IsZoomed(hwnd)
                if was_max:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                r = win32gui.GetWindowRect(hwnd)
                w = min(r[2] - r[0], pw)
                h = min(r[3] - r[1], ph)
                win32gui.MoveWindow(hwnd, px + (pw - w) // 2, py + (ph - h) // 2, w, h, True)
                if was_max:
                    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            except Exception:
                pass
            return True

        win32gui.EnumWindows(_move, None)


# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
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
                    "position_y": 0
                },
                "\\\\.\\DISPLAY2": {"enabled": False}
            }
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
                    "position_y": 0
                }
            }
        }
    ],
    "autostart": True
}


class Config:

    def __init__(self):
        self.data = self._load()

    def _load(self):
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, encoding='utf-8') as f:
                return json.load(f)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        return DEFAULT_CONFIG.copy()

    @property
    def profiles(self):
        return self.data.get('profiles', [])

    @property
    def autostart(self):
        return self.data.get('autostart', False)


# ── Autostart ─────────────────────────────────────────────────────────────────

_RUN_KEY = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Run'


def _exe_cmd():
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{Path(__file__).resolve()}"'


def autostart_enable():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _exe_cmd())


def autostart_disable():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, APP_NAME)
    except FileNotFoundError:
        pass


# ── Tray Icon ─────────────────────────────────────────────────────────────────

def _make_icon():
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


# ── Profile Switcher ──────────────────────────────────────────────────────────

_lock = threading.Lock()


def switch_to(profile, notify=None):
    if not _lock.acquire(blocking=False):
        return
    try:
        for device, cfg in profile.get('monitors', {}).items():
            if cfg.get('enabled'):
                DisplayManager.enable_display(
                    device,
                    width=cfg['width'],
                    height=cfg['height'],
                    refresh_rate=cfg.get('refresh_rate', 60),
                    position_x=cfg.get('position_x', 0),
                    position_y=cfg.get('position_y', 0),
                )
            else:
                DisplayManager.disable_display(device)

        result = DisplayManager.apply_changes()

        if result == DISP_CHANGE_SUCCESSFUL:
            time.sleep(1.5)
            WindowMigrator.migrate_all()
            if notify:
                notify(f"Switched to: {profile['name']}")
        else:
            if notify:
                notify(f"Display change failed (code {result})")
    finally:
        _lock.release()


# ── App ───────────────────────────────────────────────────────────────────────

class ScreenShiftApp:

    def __init__(self):
        self.cfg  = Config()
        self.icon = None
        if self.cfg.autostart:
            autostart_enable()
        self._register_hotkeys()

    def _register_hotkeys(self):
        for p in self.cfg.profiles:
            if p.get('hotkey'):
                keyboard.add_hotkey(
                    p['hotkey'],
                    lambda prof=p: threading.Thread(
                        target=switch_to, args=(prof, self._notify), daemon=True,
                    ).start(),
                )

    def _notify(self, msg):
        if self.icon:
            self.icon.notify(msg, APP_NAME)

    def _build_menu(self):
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
            pystray.MenuItem('List Monitors', lambda _: self._show_monitors()),
            pystray.MenuItem('Open Config',   lambda _: os.startfile(str(CONFIG_PATH))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit',          lambda _: self.icon.stop()),
        ]
        return pystray.Menu(*items)

    def _show_monitors(self):
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

    def run(self):
        self.icon = pystray.Icon(APP_NAME, _make_icon(), APP_NAME, self._build_menu())
        self.icon.run()


if __name__ == '__main__':
    app = ScreenShiftApp()
    app.run()
