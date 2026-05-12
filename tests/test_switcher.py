import threading
import time
from unittest.mock import MagicMock, patch, call

import src.switcher as switcher_module
from src.display import DISP_CHANGE_SUCCESSFUL
from src.switcher import switch_to, restore_previous, detect_active_profile, _lock

# reset module-level state before every test
import pytest

@pytest.fixture(autouse=True)
def _reset_switcher_state():
    switcher_module._previous_state  = None
    switcher_module._current_profile = None
    yield
    switcher_module._previous_state  = None
    switcher_module._current_profile = None


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
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.list_displays.return_value = []
        _ok(MockDM)
        MockDM.apply_changes.return_value = -1
        switch_to(_PROFILE)
    assert switcher_module._previous_state is None


def test_restore_previous_notifies_nothing_to_restore():
    notify = MagicMock()
    restore_previous(notify=notify)
    notify.assert_called_once_with('Nothing to restore')


def test_restore_previous_calls_switch_to():
    switcher_module._previous_state = [   # set directly — fixture resets after test
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
    switcher_module._previous_state = [   # set directly — fixture resets after test
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


# ── already-active guard ──────────────────────────────────────────────────────

def test_already_active_profile_is_skipped():
    switcher_module._current_profile = 'Work'
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        switch_to(_PROFILE)
        MockDM.apply_changes.assert_not_called()


def test_already_active_notifies_user():
    switcher_module._current_profile = 'Work'
    notify = MagicMock()
    switch_to(_PROFILE, notify=notify)
    notify.assert_called_once()
    assert 'already' in notify.call_args[0][0].lower()


def test_current_profile_set_on_success():
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.list_displays.return_value = []
        _ok(MockDM)
        switch_to(_PROFILE)
    assert switcher_module._current_profile == 'Work'


def test_current_profile_not_set_on_failure():
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.list_displays.return_value = []
        _ok(MockDM)
        MockDM.apply_changes.return_value = -1
        switch_to(_PROFILE)
    assert switcher_module._current_profile is None


def test_restore_previous_works_repeatedly():
    """Restore must not be blocked by the already-active guard on repeated presses."""
    switcher_module._previous_state = [
        {
            'device': '\\\\.\\DISPLAY1', 'enabled': True,
            'width': 1920, 'height': 1080, 'refresh_rate': 60,
            'position_x': 0, 'position_y': 0,
        },
    ]
    switcher_module._current_profile = 'Previous'   # simulate state after first restore

    calls = []
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.list_displays.return_value = []
        _ok(MockDM)
        restore_previous(notify=lambda m: calls.append(m))

    # should have switched, not returned "Already active"
    assert MockDM.apply_changes.called
    assert not any('already' in m.lower() for m in calls)


# ── snapshot completeness ─────────────────────────────────────────────────────

def test_snapshot_includes_zero_width_adapters():
    """Adapters disabled by us (registry width=0) must appear in the snapshot
    so that restore can explicitly disable them again."""
    with patch('src.switcher.DisplayManager') as MockDM:
        MockDM.list_displays.return_value = [
            {'name': '\\\\.\\DISPLAY1', 'active': True, 'primary': True},
        ]
        MockDM.get_current_settings.return_value = {
            'width': 1920, 'height': 1080, 'refresh_rate': 60,
            'position_x': 0, 'position_y': 0,
        }
        MockDM.list_all_adapters.return_value = [
            '\\\\.\\DISPLAY1',
            '\\\\.\\DISPLAY2',   # disabled by us → not returned by list_displays
        ]
        from src.switcher import _snapshot
        result = _snapshot()

    devices = {e['device'] for e in result}
    assert '\\\\.\\DISPLAY2' in devices
    disabled = next(e for e in result if e['device'] == '\\\\.\\DISPLAY2')
    assert disabled['enabled'] is False


def test_restore_disables_previously_unseen_display():
    """After switching, restore must disable a display that wasn't in the snapshot
    because it had zero registry width when the snapshot was taken."""
    # Snapshot captured only DISPLAY1 as active; DISPLAY2 was zero-width (our disable).
    # After the switch to Profile2, DISPLAY2 is now active.
    # Restore must disable DISPLAY2 again.
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
        MockDM.list_all_adapters.return_value = []
        _ok(MockDM)
        restore_previous()

    MockDM.disable_display.assert_called_with('\\\\.\\DISPLAY2')


# ── detect_active_profile ─────────────────────────────────────────────────────

_PROFILES = [
    {
        'name': 'Work',
        'monitors': {
            '\\\\.\\DISPLAY1': {'enabled': True},
            '\\\\.\\DISPLAY2': {'enabled': False},
        },
    },
    {
        'name': 'Gaming',
        'monitors': {
            '\\\\.\\DISPLAY1': {'enabled': False},
            '\\\\.\\DISPLAY2': {'enabled': True},
        },
    },
]


def test_detect_active_profile_matches_correctly():
    with patch('src.switcher.DisplayManager') as MockDM:
        MockDM.list_displays.return_value = [
            {'name': '\\\\.\\DISPLAY1', 'active': True},
            {'name': '\\\\.\\DISPLAY2', 'active': False},
        ]
        assert detect_active_profile(_PROFILES) == 'Work'


def test_detect_active_profile_returns_none_when_no_match():
    with patch('src.switcher.DisplayManager') as MockDM:
        MockDM.list_displays.return_value = [
            {'name': '\\\\.\\DISPLAY1', 'active': True},
            {'name': '\\\\.\\DISPLAY2', 'active': True},
        ]
        assert detect_active_profile(_PROFILES) is None
