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
    """Profile devices with zero registry (skipped by list_displays) must appear
    in the snapshot as disabled so restore can explicitly turn them off again."""
    with patch('src.switcher.DisplayManager') as MockDM:
        MockDM.list_displays.return_value = [
            {'name': '\\\\.\\DISPLAY1', 'active': True, 'primary': True},
        ]
        MockDM.get_current_settings.return_value = {
            'width': 1920, 'height': 1080, 'refresh_rate': 60,
            'position_x': 0, 'position_y': 0,
        }
        from src.switcher import _snapshot
        # DISPLAY2 is in the profile but not returned by list_displays (zero registry)
        result = _snapshot(profile_devices={'\\\\.\\DISPLAY1', '\\\\.\\DISPLAY2'})

    devices = {e['device'] for e in result}
    assert '\\\\.\\DISPLAY2' in devices
    disabled = next(e for e in result if e['device'] == '\\\\.\\DISPLAY2')
    assert disabled['enabled'] is False


def test_snapshot_does_not_include_ghost_adapters_outside_profile():
    """Devices NOT in the profile (e.g. virtual RemoteFX adapters) must NOT
    appear in the snapshot even if they exist as system adapters."""
    with patch('src.switcher.DisplayManager') as MockDM:
        MockDM.list_displays.return_value = [
            {'name': '\\\\.\\DISPLAY1', 'active': True, 'primary': True},
        ]
        MockDM.get_current_settings.return_value = {
            'width': 1920, 'height': 1080, 'refresh_rate': 60,
            'position_x': 0, 'position_y': 0,
        }
        from src.switcher import _snapshot
        # Only DISPLAY1 is in the profile — DISPLAY2…20 should not appear
        result = _snapshot(profile_devices={'\\\\.\\DISPLAY1'})

    devices = {e['device'] for e in result}
    assert devices == {'\\\\.\\DISPLAY1'}


def test_restore_disables_previously_unseen_display():
    """After switching, restore must disable a display that was in the profile
    but had zero registry width when the pre-switch snapshot was taken."""
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
            {'name': '\\\\.\\DISPLAY1', 'active': True,  'monitor_id': None},
            {'name': '\\\\.\\DISPLAY2', 'active': False, 'monitor_id': None},
        ]
        assert detect_active_profile(_PROFILES) == 'Work'


def test_detect_active_profile_returns_none_when_no_match():
    with patch('src.switcher.DisplayManager') as MockDM:
        MockDM.list_displays.return_value = [
            {'name': '\\\\.\\DISPLAY1', 'active': True,  'monitor_id': None},
            {'name': '\\\\.\\DISPLAY2', 'active': True,  'monitor_id': None},
        ]
        assert detect_active_profile(_PROFILES) is None


def test_detect_active_profile_matches_by_monitor_id_after_renumber():
    """After Windows renumbers adapters, detection must fall back to hardware IDs."""
    profiles_with_ids = [
        {
            'name': 'Work',
            'monitors': {
                '\\\\.\\DISPLAY1': {'enabled': True,  'monitor_id': 'MONITOR\\DEL001'},
                '\\\\.\\DISPLAY2': {'enabled': False, 'monitor_id': 'MONITOR\\SAM002'},
            },
        },
    ]
    with patch('src.switcher.DisplayManager') as MockDM:
        # After reboot DISPLAY1 ↔ DISPLAY2 swapped, but monitor_ids are stable
        MockDM.list_displays.return_value = [
            {'name': '\\\\.\\DISPLAY2', 'active': True,  'monitor_id': 'MONITOR\\DEL001'},
            {'name': '\\\\.\\DISPLAY1', 'active': False, 'monitor_id': 'MONITOR\\SAM002'},
        ]
        assert detect_active_profile(profiles_with_ids) == 'Work'


def test_switch_remaps_adapter_after_renumber():
    """switch_to must use find_adapter_by_monitor_id to locate the physical monitor
    even when Windows has assigned it a different DISPLAY number after reboot."""
    profile_with_id = {
        'name': 'Work',
        'monitors': {
            '\\\\.\\DISPLAY1': {   # stored name — now wrong after reboot
                'enabled': True, 'width': 1920, 'height': 1080,
                'refresh_rate': 60, 'position_x': 0, 'position_y': 0,
                'monitor_id': 'MONITOR\\DEL001',
            },
            '\\\\.\\DISPLAY2': {'enabled': False},
        },
    }
    with patch('src.switcher.DisplayManager') as MockDM, \
         patch('src.switcher.WindowMigrator'), \
         patch('src.switcher.time.sleep'):
        MockDM.list_displays.return_value = []
        # Monitor is now on DISPLAY2 after renumber
        MockDM.find_adapter_by_monitor_id.return_value = '\\\\.\\DISPLAY2'
        _ok(MockDM)
        switch_to(profile_with_id)

    # Must enable DISPLAY2 (remapped), not DISPLAY1 (stored)
    MockDM.enable_display.assert_called_once_with(
        '\\\\.\\DISPLAY2',
        width=1920, height=1080, refresh_rate=60, position_x=0, position_y=0,
    )
