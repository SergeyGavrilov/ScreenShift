import sys
from unittest.mock import MagicMock, call, patch

import win32api
import win32con
import win32gui

from src.migrator import WindowMigrator

# ── helpers ───────────────────────────────────────────────────────────────────

PRIMARY_RECT   = (0, 0, 1920, 1080)
SECONDARY_RECT = (1920, 0, 4480, 1440)

_PRIMARY_MONITOR   = object()
_SECONDARY_MONITOR = object()


def _setup_primary(monkeypatch):
    monkeypatch.setattr(win32api, 'EnumDisplayMonitors', lambda: [
        (_PRIMARY_MONITOR, None, PRIMARY_RECT),
    ])
    monkeypatch.setattr(win32api, 'GetMonitorInfo', lambda m: {
        'Flags': 1, 'Work': PRIMARY_RECT, 'Monitor': PRIMARY_RECT,
    })


# ── _primary_work_rect ────────────────────────────────────────────────────────

def test_primary_work_rect_returns_primary(monkeypatch):
    monkeypatch.setattr(win32api, 'EnumDisplayMonitors', lambda: [
        (_PRIMARY_MONITOR,   None, PRIMARY_RECT),
        (_SECONDARY_MONITOR, None, SECONDARY_RECT),
    ])

    def mock_monitor_info(monitor):
        return {'Flags': 1 if monitor is _PRIMARY_MONITOR else 0, 'Work': PRIMARY_RECT}

    monkeypatch.setattr(win32api, 'GetMonitorInfo', mock_monitor_info)

    assert WindowMigrator._primary_work_rect() == PRIMARY_RECT


def test_primary_work_rect_fallback(monkeypatch):
    monkeypatch.setattr(win32api, 'EnumDisplayMonitors', lambda: [])
    monkeypatch.setattr(win32api, 'GetSystemMetrics', lambda metric: 1920 if metric == win32con.SM_CXSCREEN else 1080)

    result = WindowMigrator._primary_work_rect()

    assert result == (0, 0, 1920, 1080)


# ── migrate_all ───────────────────────────────────────────────────────────────

def _drive_migrate(monkeypatch, windows: list):
    """
    windows: list of dicts with keys:
      hwnd, visible, title, iconic, zoomed, monitor, on_primary, rect
    """
    _setup_primary(monkeypatch)

    def fake_enum_windows(callback, param):
        for w in windows:
            callback(w['hwnd'], param)

    monkeypatch.setattr(win32gui, 'EnumWindows',      fake_enum_windows)
    monkeypatch.setattr(win32gui, 'IsWindowVisible',  lambda h: next(w['visible'] for w in windows if w['hwnd'] == h))
    monkeypatch.setattr(win32gui, 'GetWindowText',    lambda h: next(w['title']   for w in windows if w['hwnd'] == h))
    monkeypatch.setattr(win32gui, 'IsIconic',         lambda h: next(w['iconic']  for w in windows if w['hwnd'] == h))
    monkeypatch.setattr(win32gui, 'IsZoomed',         lambda h: next(w['zoomed']  for w in windows if w['hwnd'] == h))
    monkeypatch.setattr(win32gui, 'GetWindowRect',    lambda h: next(w['rect']    for w in windows if w['hwnd'] == h))
    monkeypatch.setattr(win32gui, 'MoveWindow',       MagicMock())
    monkeypatch.setattr(win32gui, 'ShowWindow',       MagicMock())

    def fake_monitor_from_window(h, flag):
        return next(w['monitor'] for w in windows if w['hwnd'] == h)

    def fake_monitor_info(monitor):
        # _PRIMARY_MONITOR is always primary; anything else is secondary
        return {
            'Flags': 1 if monitor is _PRIMARY_MONITOR else 0,
            'Work': PRIMARY_RECT,
        }

    monkeypatch.setattr(win32api, 'MonitorFromWindow', fake_monitor_from_window)
    monkeypatch.setattr(win32api, 'GetMonitorInfo',    fake_monitor_info)


def test_migrate_skips_invisible_window(monkeypatch):
    _drive_migrate(monkeypatch, [
        dict(hwnd=1, visible=False, title='App', iconic=False, zoomed=False,
             monitor=_SECONDARY_MONITOR, on_primary=False, rect=(1920, 0, 2720, 600)),
    ])
    WindowMigrator.migrate_all()
    win32gui.MoveWindow.assert_not_called()


def test_migrate_skips_window_without_title(monkeypatch):
    _drive_migrate(monkeypatch, [
        dict(hwnd=1, visible=True, title='', iconic=False, zoomed=False,
             monitor=_SECONDARY_MONITOR, on_primary=False, rect=(1920, 0, 2720, 600)),
    ])
    WindowMigrator.migrate_all()
    win32gui.MoveWindow.assert_not_called()


def test_migrate_skips_minimized_window(monkeypatch):
    _drive_migrate(monkeypatch, [
        dict(hwnd=1, visible=True, title='App', iconic=True, zoomed=False,
             monitor=_SECONDARY_MONITOR, on_primary=False, rect=(1920, 0, 2720, 600)),
    ])
    WindowMigrator.migrate_all()
    win32gui.MoveWindow.assert_not_called()


def test_migrate_skips_window_already_on_primary(monkeypatch):
    _drive_migrate(monkeypatch, [
        dict(hwnd=1, visible=True, title='App', iconic=False, zoomed=False,
             monitor=_PRIMARY_MONITOR, on_primary=True, rect=(100, 100, 900, 700)),
    ])
    WindowMigrator.migrate_all()
    win32gui.MoveWindow.assert_not_called()


def test_migrate_moves_window_from_secondary_to_primary(monkeypatch):
    _drive_migrate(monkeypatch, [
        dict(hwnd=1, visible=True, title='App', iconic=False, zoomed=False,
             monitor=_SECONDARY_MONITOR, on_primary=False, rect=(1920, 0, 2720, 600)),
    ])
    WindowMigrator.migrate_all()
    win32gui.MoveWindow.assert_called_once()
    args = win32gui.MoveWindow.call_args[0]
    new_x, new_y = args[1], args[2]
    assert 0 <= new_x < 1920
    assert 0 <= new_y < 1080


def test_migrate_restores_and_re_maximizes(monkeypatch):
    _drive_migrate(monkeypatch, [
        dict(hwnd=1, visible=True, title='App', iconic=False, zoomed=True,
             monitor=_SECONDARY_MONITOR, on_primary=False, rect=(1920, 0, 4480, 1440)),
    ])
    WindowMigrator.migrate_all()
    show_calls = [c[0][1] for c in win32gui.ShowWindow.call_args_list]
    assert win32con.SW_RESTORE  in show_calls
    assert win32con.SW_MAXIMIZE in show_calls
