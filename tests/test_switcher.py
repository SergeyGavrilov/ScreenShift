import threading
import time
from unittest.mock import MagicMock, patch, call

import src.switcher as switcher_module
from src.display import DISP_CHANGE_SUCCESSFUL
from src.switcher import switch_to, _lock


_PROFILE = {
    'name': 'Work',
    'monitors': {
        '\\\\.\\DISPLAY1': {
            'enabled': True, 'width': 1920, 'height': 1080,
            'refresh_rate': 60, 'position_x': 0, 'position_y': 0,
        },
        '\\\\.\\DISPLAY2': {'enabled': False},
    },
}


# ── display calls ─────────────────────────────────────────────────────────────

def test_enables_correct_monitor():
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.apply_changes.return_value = DISP_CHANGE_SUCCESSFUL
        switch_to(_PROFILE)
        MockDM.enable_display.assert_called_once_with(
            '\\\\.\\DISPLAY1',
            width=1920, height=1080, refresh_rate=60, position_x=0, position_y=0,
        )


def test_disables_correct_monitor():
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.apply_changes.return_value = DISP_CHANGE_SUCCESSFUL
        switch_to(_PROFILE)
        MockDM.disable_display.assert_called_once_with('\\\\.\\DISPLAY2')


def test_calls_apply_changes():
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.apply_changes.return_value = DISP_CHANGE_SUCCESSFUL
        switch_to(_PROFILE)
        MockDM.apply_changes.assert_called_once()


# ── post-switch actions ───────────────────────────────────────────────────────

def test_migrates_windows_on_success():
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator') as MockWM, \
         patch('src.switcher.time.sleep'):
        MockDM.apply_changes.return_value = DISP_CHANGE_SUCCESSFUL
        switch_to(_PROFILE)
        MockWM.migrate_all.assert_called_once()


def test_does_not_migrate_on_failure():
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator') as MockWM, \
         patch('src.switcher.time.sleep'):
        MockDM.apply_changes.return_value = -1
        switch_to(_PROFILE)
        MockWM.migrate_all.assert_not_called()


def test_notifies_on_success():
    notify = MagicMock()
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.apply_changes.return_value = DISP_CHANGE_SUCCESSFUL
        switch_to(_PROFILE, notify=notify)
        notify.assert_called_once()
        assert 'Work' in notify.call_args[0][0]


def test_notifies_on_failure():
    notify = MagicMock()
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.apply_changes.return_value = -1
        switch_to(_PROFILE, notify=notify)
        notify.assert_called_once()
        assert 'failed' in notify.call_args[0][0].lower()


def test_notify_is_optional():
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.apply_changes.return_value = DISP_CHANGE_SUCCESSFUL
        switch_to(_PROFILE, notify=None)  # must not raise


# ── concurrency lock ──────────────────────────────────────────────────────────

def test_concurrent_call_is_dropped():
    results = []

    def slow_switch():
        with patch('src.switcher.DisplayManager') as MockDM, \
             patch('src.switcher.WindowMigrator'), \
             patch('src.switcher.time.sleep'):
            MockDM.apply_changes.return_value = DISP_CHANGE_SUCCESSFUL
            switch_to(_PROFILE, notify=lambda msg: results.append(msg))

    # Acquire the lock manually to simulate a switch already in progress
    acquired = _lock.acquire(blocking=False)
    assert acquired, "lock should be free at start of test"
    try:
        switch_to(_PROFILE, notify=lambda msg: results.append(msg))
        assert results == [], "second call should be silently dropped while lock is held"
    finally:
        _lock.release()
