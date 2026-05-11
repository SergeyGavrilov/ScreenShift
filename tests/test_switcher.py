import threading
import time
from unittest.mock import MagicMock, patch, call

import src.switcher as switcher_module
from src.display import DISP_CHANGE_SUCCESSFUL
from src.switcher import switch_to, restore_previous, _lock


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

def _ok(MockDM):
    MockDM.enable_display.return_value  = DISP_CHANGE_SUCCESSFUL
    MockDM.disable_display.return_value = DISP_CHANGE_SUCCESSFUL
    MockDM.apply_changes.return_value   = DISP_CHANGE_SUCCESSFUL


def test_enables_correct_monitor():
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        _ok(MockDM)
        switch_to(_PROFILE)
        MockDM.enable_display.assert_called_once_with(
            '\\\\.\\DISPLAY1',
            width=1920, height=1080, refresh_rate=60, position_x=0, position_y=0,
        )


def test_disables_correct_monitor():
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        _ok(MockDM)
        switch_to(_PROFILE)
        MockDM.disable_display.assert_called_once_with('\\\\.\\DISPLAY2')


def test_calls_apply_changes():
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        _ok(MockDM)
        switch_to(_PROFILE)
        MockDM.apply_changes.assert_called_once()


# ── post-switch actions ───────────────────────────────────────────────────────

def test_migrates_windows_on_success():
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator') as MockWM, \
         patch('src.switcher.time.sleep'):
        _ok(MockDM)
        switch_to(_PROFILE)
        MockWM.migrate_all.assert_called_once()


def test_does_not_migrate_on_failure():
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator') as MockWM, \
         patch('src.switcher.time.sleep'):
        _ok(MockDM)
        MockDM.apply_changes.return_value = -1
        switch_to(_PROFILE)
        MockWM.migrate_all.assert_not_called()


def test_notifies_on_success():
    notify = MagicMock()
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        _ok(MockDM)
        switch_to(_PROFILE, notify=notify)
        notify.assert_called_once()
        assert 'Work' in notify.call_args[0][0]


def test_notifies_on_apply_failure():
    notify = MagicMock()
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.enable_display.return_value  = 0
        MockDM.disable_display.return_value = 0
        MockDM.apply_changes.return_value   = -1
        switch_to(_PROFILE, notify=notify)
        notify.assert_called_once()
        assert 'failed' in notify.call_args[0][0].lower()


def test_notifies_on_staging_failure():
    notify = MagicMock()
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.enable_display.return_value  = -2  # DISP_CHANGE_BADMODE
        MockDM.disable_display.return_value = 0
        switch_to(_PROFILE, notify=notify)
        notify.assert_called_once()
        assert 'staging' in notify.call_args[0][0].lower()


def test_does_not_apply_when_staging_fails():
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.enable_display.return_value = -2
        switch_to(_PROFILE)
        MockDM.apply_changes.assert_not_called()


def test_enables_before_disables():
    order = []
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.enable_display.side_effect  = lambda *a, **kw: order.append('enable')  or 0
        MockDM.disable_display.side_effect = lambda *a, **kw: order.append('disable') or 0
        MockDM.apply_changes.return_value  = 0
        switch_to(_PROFILE)
    assert order.index('enable') < order.index('disable')


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


# ── snapshot / restore_previous ───────────────────────────────────────────────

def _display(name, active, **kw):
    d = {'name': name, 'active': active, 'primary': active}
    d.update(kw)
    return d


def test_previous_state_saved_on_success():
    switcher_module._previous_state = None
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.list_displays.return_value = [_display('\\\\.\\DISPLAY1', True)]
        MockDM.get_current_settings.return_value = {
            'width': 1920, 'height': 1080, 'refresh_rate': 60,
            'position_x': 0, 'position_y': 0,
        }
        _ok(MockDM)
        switch_to(_PROFILE)
    assert switcher_module._previous_state is not None


def test_previous_state_not_saved_on_failure():
    switcher_module._previous_state = None
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.list_displays.return_value = []
        _ok(MockDM)
        MockDM.apply_changes.return_value = -1
        switch_to(_PROFILE)
    assert switcher_module._previous_state is None


def test_restore_previous_notifies_nothing_to_restore():
    switcher_module._previous_state = None
    notify = MagicMock()
    restore_previous(notify=notify)
    notify.assert_called_once_with('Nothing to restore')


def test_restore_previous_calls_switch_to():
    switcher_module._previous_state = [
        {
            'device': '\\\\.\\DISPLAY1', 'enabled': True,
            'width': 1920, 'height': 1080, 'refresh_rate': 60,
            'position_x': 0, 'position_y': 0,
        },
        {'device': '\\\\.\\DISPLAY2', 'enabled': False},
    ]
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.list_displays.return_value = []
        _ok(MockDM)
        restore_previous()
    MockDM.apply_changes.assert_called_once()


def test_restore_re_enables_previously_active_monitors():
    switcher_module._previous_state = [
        {
            'device': '\\\\.\\DISPLAY1', 'enabled': True,
            'width': 2560, 'height': 1440, 'refresh_rate': 144,
            'position_x': 0, 'position_y': 0,
        },
    ]
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.list_displays.return_value = []
        _ok(MockDM)
        restore_previous()
    MockDM.enable_display.assert_called_once_with(
        '\\\\.\\DISPLAY1',
        width=2560, height=1440, refresh_rate=144, position_x=0, position_y=0,
    )
