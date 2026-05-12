import ctypes
import pytest
from unittest.mock import MagicMock

from src.display import (
    CDS_NORESET,
    CDS_UPDATEREGISTRY,
    DISP_CHANGE_SUCCESSFUL,
    DM_BITSPERPEL,
    DM_DISPLAYFREQUENCY,
    DM_PELSHEIGHT,
    DM_PELSWIDTH,
    DM_POSITION,
    DISPLAY_DEVICE_ATTACHED_TO_DESKTOP,
    DISPLAY_DEVICE_MIRRORING_DRIVER,
    DISPLAY_DEVICE_PRIMARY_DEVICE,
    DisplayManager,
)


@pytest.fixture(autouse=True)
def mock_windll(monkeypatch):
    """Replace ctypes.windll with a MagicMock for every test in this module."""
    m = MagicMock()
    monkeypatch.setattr(ctypes, 'windll', m)
    return m


# ── list_displays ─────────────────────────────────────────────────────────────

def test_list_displays_returns_empty_when_no_devices(mock_windll):
    mock_windll.user32.EnumDisplayDevicesW.return_value = 0

    assert DisplayManager.list_displays() == []


def test_list_displays_stops_after_first_failure(mock_windll):
    # First call succeeds but DeviceName stays empty → skipped; second call stops loop
    mock_windll.user32.EnumDisplayDevicesW.side_effect = [1, 0]

    assert DisplayManager.list_displays() == []


def test_list_displays_active_and_primary_flags(mock_windll):
    call_count = 0

    def fake_enum(name, index, dd_ptr, flags):
        nonlocal call_count
        if call_count > 0:
            return 0
        dd = dd_ptr._obj
        dd.DeviceName = '\\\\.\\DISPLAY1'
        dd.StateFlags = DISPLAY_DEVICE_ATTACHED_TO_DESKTOP | DISPLAY_DEVICE_PRIMARY_DEVICE
        call_count += 1
        return 1

    mock_windll.user32.EnumDisplayDevicesW.side_effect = fake_enum

    result = DisplayManager.list_displays()

    assert len(result) == 1
    assert result[0]['active']  is True
    assert result[0]['primary'] is True


def test_list_displays_inactive_with_registry_settings(mock_windll):
    # Inactive device that has real registry settings → should be included
    call_count = 0

    def fake_enum(name, index, dd_ptr, flags):
        nonlocal call_count
        if call_count > 0:
            return 0
        dd = dd_ptr._obj
        dd.DeviceName = '\\\\.\\DISPLAY2'
        dd.StateFlags = 0  # inactive, not mirroring
        call_count += 1
        return 1

    def fake_settings(device, mode, dm_ptr, *a):
        dm = dm_ptr._obj
        dm.dmPelsWidth  = 2560
        dm.dmPelsHeight = 1440
        return 1  # has registry entry

    mock_windll.user32.EnumDisplayDevicesW.side_effect = fake_enum
    mock_windll.user32.EnumDisplaySettingsW.side_effect = fake_settings

    result = DisplayManager.list_displays()

    assert len(result) == 1
    assert result[0]['active']  is False
    assert result[0]['primary'] is False


def test_list_displays_skips_ghost_inactive_device(mock_windll):
    # Inactive device with zero resolution in registry → ghost adapter, skip it
    call_count = 0

    def fake_enum(name, index, dd_ptr, flags):
        nonlocal call_count
        if call_count > 0:
            return 0
        dd = dd_ptr._obj
        dd.DeviceName = '\\\\.\\DISPLAY5'
        dd.StateFlags = 0
        call_count += 1
        return 1

    def fake_settings(device, mode, dm_ptr, *a):
        # dmPelsWidth stays 0 (ctypes default)
        return 1

    mock_windll.user32.EnumDisplayDevicesW.side_effect = fake_enum
    mock_windll.user32.EnumDisplaySettingsW.side_effect = fake_settings

    assert DisplayManager.list_displays() == []


def test_list_displays_skips_mirror_driver(mock_windll):
    call_count = 0

    def fake_enum(name, index, dd_ptr, flags):
        nonlocal call_count
        if call_count > 0:
            return 0
        dd = dd_ptr._obj
        dd.DeviceName = '\\\\.\\DISPLAY3'
        dd.StateFlags = DISPLAY_DEVICE_MIRRORING_DRIVER
        call_count += 1
        return 1

    mock_windll.user32.EnumDisplayDevicesW.side_effect = fake_enum

    assert DisplayManager.list_displays() == []


# ── enable_display ────────────────────────────────────────────────────────────

def test_enable_display_calls_api(mock_windll):
    mock_windll.user32.EnumDisplaySettingsW.return_value = 0  # no registry entry
    mock_windll.user32.ChangeDisplaySettingsExW.return_value = DISP_CHANGE_SUCCESSFUL

    result = DisplayManager.enable_display(
        '\\\\.\\DISPLAY1', width=1920, height=1080,
        refresh_rate=60, position_x=0, position_y=0,
    )

    assert mock_windll.user32.ChangeDisplaySettingsExW.called
    assert result == DISP_CHANGE_SUCCESSFUL


def test_enable_display_uses_config_when_no_registry(mock_windll):
    # Both registry and current settings return 0 → fall back to config values
    mock_windll.user32.EnumDisplaySettingsW.return_value = 0
    captured = {}

    def capture(device, dm_ptr, hwnd, flags, param):
        dm = dm_ptr._obj
        captured.update({
            'width':   dm.dmPelsWidth,
            'height':  dm.dmPelsHeight,
            'refresh': dm.dmDisplayFrequency,
            'x':       dm.dmPositionX,
            'y':       dm.dmPositionY,
            'fields':  dm.dmFields,
        })
        return DISP_CHANGE_SUCCESSFUL

    mock_windll.user32.ChangeDisplaySettingsExW.side_effect = capture

    DisplayManager.enable_display(
        '\\\\.\\DISPLAY1', width=2560, height=1440,
        refresh_rate=144, position_x=10, position_y=20,
    )

    assert captured['width']   == 2560
    assert captured['height']  == 1440
    assert captured['refresh'] == 144
    assert captured['x']       == 10
    assert captured['y']       == 20
    assert captured['fields']  == DM_PELSWIDTH | DM_PELSHEIGHT | DM_POSITION | DM_DISPLAYFREQUENCY | DM_BITSPERPEL


def test_enable_display_uses_registry_when_available(mock_windll):
    # EnumDisplaySettingsW succeeds with stored settings → use those, only override position
    def fake_settings(device, mode, dm_ptr, *a):
        dm = dm_ptr._obj
        dm.dmPelsWidth        = 2560
        dm.dmPelsHeight       = 1440
        dm.dmDisplayFrequency = 144
        dm.dmFields           = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY
        return 1

    mock_windll.user32.EnumDisplaySettingsW.side_effect = fake_settings
    captured = {}

    def capture_change(device, dm_ptr, hwnd, flags, param):
        dm = dm_ptr._obj
        captured['width']  = dm.dmPelsWidth
        captured['height'] = dm.dmPelsHeight
        captured['x']      = dm.dmPositionX
        captured['y']      = dm.dmPositionY
        return DISP_CHANGE_SUCCESSFUL

    mock_windll.user32.ChangeDisplaySettingsExW.side_effect = capture_change

    DisplayManager.enable_display(
        '\\\\.\\DISPLAY1', width=1920, height=1080,   # config values — should be ignored
        refresh_rate=60, position_x=5, position_y=10,
    )

    # Registry values preserved, only position overridden
    assert captured['width']  == 2560
    assert captured['height'] == 1440
    assert captured['x']      == 5
    assert captured['y']      == 10


def test_enable_display_falls_back_to_current_when_registry_zero(mock_windll):
    # Registry entry exists but width=0 (display was disabled by us) → use current live settings.
    # This covers the post-reboot case where Windows auto-restores the display.
    call_count = [0]

    def fake_settings(device, mode, dm_ptr, *a):
        call_count[0] += 1
        dm = dm_ptr._obj
        if call_count[0] == 1:              # ENUM_REGISTRY_SETTINGS → disabled (zero)
            dm.dmPelsWidth  = 0
            dm.dmPelsHeight = 0
        else:                               # ENUM_CURRENT_SETTINGS → Windows-restored mode
            dm.dmPelsWidth        = 2560
            dm.dmPelsHeight       = 1440
            dm.dmDisplayFrequency = 144
            dm.dmBitsPerPel       = 32
        return 1

    mock_windll.user32.EnumDisplaySettingsW.side_effect = fake_settings
    captured = {}

    def capture_change(device, dm_ptr, hwnd, flags, param):
        dm = dm_ptr._obj
        captured['width']   = dm.dmPelsWidth
        captured['height']  = dm.dmPelsHeight
        captured['refresh'] = dm.dmDisplayFrequency
        return DISP_CHANGE_SUCCESSFUL

    mock_windll.user32.ChangeDisplaySettingsExW.side_effect = capture_change

    DisplayManager.enable_display(
        '\\\\.\\DISPLAY1', width=1920, height=1080,   # config values — should be ignored
        refresh_rate=60, position_x=0, position_y=0,
    )

    assert captured['width']   == 2560   # from current settings, not config
    assert captured['height']  == 1440
    assert captured['refresh'] == 144


# ── disable_display ───────────────────────────────────────────────────────────

def test_disable_display_sets_zero_resolution(mock_windll):
    captured = {}

    def capture(device, dm_ptr, hwnd, flags, param):
        dm = dm_ptr._obj
        captured['width']  = dm.dmPelsWidth
        captured['height'] = dm.dmPelsHeight
        return DISP_CHANGE_SUCCESSFUL

    mock_windll.user32.ChangeDisplaySettingsExW.side_effect = capture

    DisplayManager.disable_display('\\\\.\\DISPLAY2')

    assert captured['width']  == 0
    assert captured['height'] == 0


def test_disable_display_uses_registry_flags(mock_windll):
    captured = {}

    def capture(device, dm_ptr, hwnd, flags, param):
        captured['flags'] = flags
        return DISP_CHANGE_SUCCESSFUL

    mock_windll.user32.ChangeDisplaySettingsExW.side_effect = capture

    DisplayManager.disable_display('\\\\.\\DISPLAY2')

    assert captured['flags'] == CDS_UPDATEREGISTRY | CDS_NORESET


# ── apply_changes ─────────────────────────────────────────────────────────────

# ── list_all_adapters ─────────────────────────────────────────────────────────

def test_list_all_adapters_includes_zero_width_inactive(mock_windll):
    # Adapter that list_displays() would skip (inactive + zero registry width)
    # must still be returned by list_all_adapters().
    call_count = 0

    def fake_enum(name, index, dd_ptr, flags):
        nonlocal call_count
        if call_count > 0:
            return 0
        dd = dd_ptr._obj
        dd.DeviceName = '\\\\.\\DISPLAY1'
        dd.StateFlags = 0   # inactive, zero registry → filtered by list_displays
        call_count += 1
        return 1

    mock_windll.user32.EnumDisplayDevicesW.side_effect = fake_enum

    result = DisplayManager.list_all_adapters()
    assert result == ['\\\\.\\DISPLAY1']


def test_list_all_adapters_skips_mirror_driver(mock_windll):
    call_count = 0

    def fake_enum(name, index, dd_ptr, flags):
        nonlocal call_count
        if call_count > 0:
            return 0
        dd = dd_ptr._obj
        dd.DeviceName = '\\\\.\\DISPLAY9'
        dd.StateFlags = DISPLAY_DEVICE_MIRRORING_DRIVER
        call_count += 1
        return 1

    mock_windll.user32.EnumDisplayDevicesW.side_effect = fake_enum

    assert DisplayManager.list_all_adapters() == []


# ── apply_changes ─────────────────────────────────────────────────────────────

def test_apply_changes_calls_api_with_nulls(mock_windll):
    mock_windll.user32.ChangeDisplaySettingsExW.return_value = DISP_CHANGE_SUCCESSFUL

    result = DisplayManager.apply_changes()

    mock_windll.user32.ChangeDisplaySettingsExW.assert_called_with(None, None, None, 0, None)
    assert result == DISP_CHANGE_SUCCESSFUL
