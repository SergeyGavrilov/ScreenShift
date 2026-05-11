"""
Tests for SetupWizard.build_config().

We skip the full Tk UI and test only the config-building logic by
constructing a wizard with mocked tkinter variables.
"""
import types
from unittest.mock import MagicMock, patch

import pytest


# ── Fake tk variables ─────────────────────────────────────────────────────────

class _BoolVar:
    def __init__(self, value=False): self._v = value
    def get(self): return self._v
    def set(self, v): self._v = v


class _StrVar:
    def __init__(self, value=''): self._v = value
    def get(self): return self._v
    def set(self, v): self._v = v


# ── Helpers ────────────────────────────────────────────────────────────────────

_MONITOR_A = {
    'name': '\\\\.\\DISPLAY1', 'description': 'Primary Monitor',
    'active': True, 'primary': True,
    'settings': {'width': 1920, 'height': 1080, 'refresh_rate': 60,
                 'position_x': 0, 'position_y': 0},
}
_MONITOR_B = {
    'name': '\\\\.\\DISPLAY2', 'description': 'Gaming Monitor',
    'active': True, 'primary': False,
    'settings': {'width': 2560, 'height': 1440, 'refresh_rate': 144,
                 'position_x': 1920, 'position_y': 0},
}
_MONITOR_C = {
    'name': '\\\\.\\DISPLAY3', 'description': 'Samsung TV',
    'active': False, 'primary': False,
    'settings': None,
}


def _make_wizard(monitors, profile_rows, autostart=True):
    """
    Build a minimal SetupWizard-like object with build_config() available,
    bypassing tkinter construction entirely.
    """
    # Import after conftest has mocked tkinter deps
    with patch('src.setup_wizard.DisplayManager'), \
         patch('tkinter.Tk'), \
         patch('tkinter.ttk.Style'):
        import importlib
        import src.setup_wizard as mod
        importlib.reload(mod)  # reload so patches take effect on module-level code

    wizard = object.__new__(mod.SetupWizard)
    wizard.monitors      = monitors
    wizard.profile_rows  = profile_rows
    wizard.autostart_var = _BoolVar(autostart)
    wizard.install_path  = _StrVar('C:/ScreenShift')
    # bind the unbound method
    import types
    wizard.build_config = types.MethodType(mod.SetupWizard.build_config, wizard)
    return wizard


def _row(enabled_flags: list[bool], name='Work', hotkey='ctrl+alt+1'):
    return {
        'name_var':    _StrVar(name),
        'hotkey_var':  _StrVar(hotkey),
        'monitor_vars': [_BoolVar(v) for v in enabled_flags],
    }


# ── build_config tests ────────────────────────────────────────────────────────

def test_enabled_monitor_has_correct_resolution():
    monitors = [_MONITOR_A, _MONITOR_B]
    rows = [
        _row([True, False], 'Work',   'ctrl+alt+1'),
        _row([False, True], 'Gaming', 'ctrl+alt+2'),
        _row([False, False],'Off',    'ctrl+alt+3'),
    ]
    w = _make_wizard(monitors, rows)
    cfg = w.build_config()

    work = cfg['profiles'][0]['monitors']['\\\\.\\DISPLAY1']
    assert work['enabled'] is True
    assert work['width']   == 1920
    assert work['height']  == 1080


def test_disabled_monitor_has_enabled_false():
    monitors = [_MONITOR_A, _MONITOR_B]
    rows = [
        _row([True, False], 'Work', 'ctrl+alt+1'),
        _row([False, True], 'Gaming', 'ctrl+alt+2'),
        _row([False, False], 'Off', 'ctrl+alt+3'),
    ]
    w = _make_wizard(monitors, rows)
    cfg = w.build_config()

    display2_in_work = cfg['profiles'][0]['monitors']['\\\\.\\DISPLAY2']
    assert display2_in_work == {'enabled': False}


def test_first_enabled_monitor_is_primary():
    monitors = [_MONITOR_A, _MONITOR_B]
    rows = [_row([True, True], 'Both', 'ctrl+alt+1'),
            _row([False, False], 'Off', ''),
            _row([False, False], 'Off2', '')]
    w = _make_wizard(monitors, rows)
    cfg = w.build_config()

    mons = cfg['profiles'][0]['monitors']
    assert mons['\\\\.\\DISPLAY1']['primary'] is True
    assert mons['\\\\.\\DISPLAY2']['primary'] is False


def test_position_reset_to_origin_for_active_monitor():
    monitors = [_MONITOR_B]  # DISPLAY2 normally at x=1920
    rows = [_row([True], 'Gaming', 'ctrl+alt+1'),
            _row([False], 'Off', ''),
            _row([False], 'Off2', '')]
    w = _make_wizard(monitors, rows)
    cfg = w.build_config()

    m = cfg['profiles'][0]['monitors']['\\\\.\\DISPLAY2']
    assert m['position_x'] == 0
    assert m['position_y'] == 0


def test_inactive_monitor_uses_default_resolution():
    monitors = [_MONITOR_C]  # TV, settings=None
    rows = [_row([True], 'TV', 'ctrl+alt+1'),
            _row([False], 'Off', ''),
            _row([False], 'Off2', '')]
    w = _make_wizard(monitors, rows)
    cfg = w.build_config()

    m = cfg['profiles'][0]['monitors']['\\\\.\\DISPLAY3']
    assert m['enabled'] is True
    assert m['width']   == 1920
    assert m['height']  == 1080


def test_profile_name_and_hotkey_preserved():
    monitors = [_MONITOR_A]
    rows = [_row([True],  'WorkStation', 'ctrl+shift+1'),
            _row([False], 'B', ''),
            _row([False], 'C', '')]
    w = _make_wizard(monitors, rows)
    cfg = w.build_config()

    p = cfg['profiles'][0]
    assert p['name']   == 'WorkStation'
    assert p['hotkey'] == 'ctrl+shift+1'


def test_empty_name_gets_fallback():
    monitors = [_MONITOR_A]
    rows = [_row([True], '', 'ctrl+alt+1'),
            _row([False], '', ''),
            _row([False], '', '')]
    w = _make_wizard(monitors, rows)
    cfg = w.build_config()

    assert cfg['profiles'][0]['name'] == 'Profile 1'


def test_autostart_flag_propagates():
    monitors = [_MONITOR_A]
    rows = [_row([False]), _row([False]), _row([False])]

    w_on  = _make_wizard(monitors, rows, autostart=True)
    w_off = _make_wizard(monitors, rows, autostart=False)

    assert w_on.build_config()['autostart']  is True
    assert w_off.build_config()['autostart'] is False


def test_three_profiles_always_present():
    monitors = [_MONITOR_A]
    rows = [_row([True], 'A', ''), _row([False], 'B', ''), _row([False], 'C', '')]
    w = _make_wizard(monitors, rows)
    cfg = w.build_config()

    assert len(cfg['profiles']) == 3


def test_all_monitors_appear_in_every_profile():
    monitors = [_MONITOR_A, _MONITOR_B]
    rows = [_row([True, False]), _row([False, True]), _row([False, False])]
    w = _make_wizard(monitors, rows)
    cfg = w.build_config()

    for profile in cfg['profiles']:
        assert '\\\\.\\DISPLAY1' in profile['monitors']
        assert '\\\\.\\DISPLAY2' in profile['monitors']
