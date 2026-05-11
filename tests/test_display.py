import ctypes
from unittest.mock import MagicMock, call, patch

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
    DISPLAY_DEVICE_PRIMARY_DEVICE,
    DEVMODE,
    DisplayManager,
)


# ── list_displays ─────────────────────────────────────────────────────────────

def test_list_displays_returns_empty_when_no_devices():
    ctypes.windll.user32.EnumDisplayDevicesW.return_value = 0

    result = DisplayManager.list_displays()

    assert result == []


def test_list_displays_stops_at_first_failure():
    ctypes.windll.user32.EnumDisplayDevicesW.side_effect = [1, 0]

    # Even if the first call "succeeds", the device name is empty (MagicMock default)
    # so the device is skipped, then the second call returns 0 and the loop ends
    result = DisplayManager.list_displays()

    assert isinstance(result, list)


def test_list_displays_active_and_primary_flags():
    call_count = 0

    def fake_enum(name, index, dd_ptr, flags):
        nonlocal call_count
        if call_count > 0:
            return 0
        from src.display import DISPLAY_DEVICE
        dd = ctypes.cast(dd_ptr, ctypes.POINTER(DISPLAY_DEVICE)).contents
        dd.DeviceName = '\\\\.\\DISPLAY1'
        dd.StateFlags = DISPLAY_DEVICE_ATTACHED_TO_DESKTOP | DISPLAY_DEVICE_PRIMARY_DEVICE
        call_count += 1
        return 1

    ctypes.windll.user32.EnumDisplayDevicesW.side_effect = fake_enum

    result = DisplayManager.list_displays()

    assert len(result) == 1
    assert result[0]['active'] is True
    assert result[0]['primary'] is True


def test_list_displays_inactive_device():
    call_count = 0

    def fake_enum(name, index, dd_ptr, flags):
        nonlocal call_count
        if call_count > 0:
            return 0
        from src.display import DISPLAY_DEVICE
        dd = ctypes.cast(dd_ptr, ctypes.POINTER(DISPLAY_DEVICE)).contents
        dd.DeviceName = '\\\\.\\DISPLAY2'
        dd.StateFlags = 0  # not attached
        call_count += 1
        return 1

    ctypes.windll.user32.EnumDisplayDevicesW.side_effect = fake_enum

    result = DisplayManager.list_displays()

    assert result[0]['active'] is False
    assert result[0]['primary'] is False


# ── enable_display ────────────────────────────────────────────────────────────

def test_enable_display_calls_api():
    ctypes.windll.user32.ChangeDisplaySettingsExW.return_value = DISP_CHANGE_SUCCESSFUL

    result = DisplayManager.enable_display(
        '\\\\.\\DISPLAY1', width=1920, height=1080,
        refresh_rate=60, position_x=0, position_y=0,
    )

    assert ctypes.windll.user32.ChangeDisplaySettingsExW.called
    assert result == DISP_CHANGE_SUCCESSFUL


def test_enable_display_devmode_fields():
    captured = {}

    def capture(device, dm_ptr, hwnd, flags, param):
        dm = dm_ptr._obj  # ctypes byref object
        captured['width']   = dm.dmPelsWidth
        captured['height']  = dm.dmPelsHeight
        captured['refresh'] = dm.dmDisplayFrequency
        captured['x']       = dm.dmPositionX
        captured['y']       = dm.dmPositionY
        captured['fields']  = dm.dmFields
        return DISP_CHANGE_SUCCESSFUL

    ctypes.windll.user32.ChangeDisplaySettingsExW.side_effect = capture

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


# ── disable_display ───────────────────────────────────────────────────────────

def test_disable_display_sets_zero_resolution():
    captured = {}

    def capture(device, dm_ptr, hwnd, flags, param):
        dm = dm_ptr._obj
        captured['width']  = dm.dmPelsWidth
        captured['height'] = dm.dmPelsHeight
        return DISP_CHANGE_SUCCESSFUL

    ctypes.windll.user32.ChangeDisplaySettingsExW.side_effect = capture

    DisplayManager.disable_display('\\\\.\\DISPLAY2')

    assert captured['width']  == 0
    assert captured['height'] == 0


def test_disable_display_uses_registry_flags():
    captured_flags = {}

    def capture(device, dm_ptr, hwnd, flags, param):
        captured_flags['flags'] = flags
        return DISP_CHANGE_SUCCESSFUL

    ctypes.windll.user32.ChangeDisplaySettingsExW.side_effect = capture

    DisplayManager.disable_display('\\\\.\\DISPLAY2')

    assert captured_flags['flags'] == CDS_UPDATEREGISTRY | CDS_NORESET


# ── apply_changes ─────────────────────────────────────────────────────────────

def test_apply_changes_calls_api_with_nulls():
    ctypes.windll.user32.ChangeDisplaySettingsExW.return_value = DISP_CHANGE_SUCCESSFUL

    result = DisplayManager.apply_changes()

    ctypes.windll.user32.ChangeDisplaySettingsExW.assert_called_with(None, None, None, 0, None)
    assert result == DISP_CHANGE_SUCCESSFUL
