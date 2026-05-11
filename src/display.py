import ctypes

# ── Constants ─────────────────────────────────────────────────────────────────

DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x00000001
DISPLAY_DEVICE_PRIMARY_DEVICE      = 0x00000004

CDS_UPDATEREGISTRY    = 0x00000001
CDS_NORESET           = 0x10000000
DISP_CHANGE_SUCCESSFUL = 0

DM_POSITION          = 0x00000020
DM_BITSPERPEL        = 0x00000004
DM_PELSWIDTH         = 0x00080000
DM_PELSHEIGHT        = 0x00100000
DM_DISPLAYFREQUENCY  = 0x00400000
ENUM_CURRENT_SETTINGS = -1

# ── Structures ────────────────────────────────────────────────────────────────

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


# ── Manager ───────────────────────────────────────────────────────────────────

class DisplayManager:

    @staticmethod
    def list_displays() -> list[dict]:
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
    def enable_display(device: str, width: int, height: int,
                       refresh_rate: int, position_x: int, position_y: int,
                       bpp: int = 32) -> int:
        dm = DEVMODE()
        dm.dmSize             = ctypes.sizeof(DEVMODE)
        dm.dmFields           = DM_PELSWIDTH | DM_PELSHEIGHT | DM_POSITION | DM_DISPLAYFREQUENCY | DM_BITSPERPEL
        dm.dmPelsWidth        = width
        dm.dmPelsHeight       = height
        dm.dmPositionX        = position_x
        dm.dmPositionY        = position_y
        dm.dmDisplayFrequency = refresh_rate
        dm.dmBitsPerPel       = bpp
        return ctypes.windll.user32.ChangeDisplaySettingsExW(
            device, ctypes.byref(dm), None, CDS_UPDATEREGISTRY | CDS_NORESET, None,
        )

    @staticmethod
    def disable_display(device: str) -> int:
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
    def apply_changes() -> int:
        return ctypes.windll.user32.ChangeDisplaySettingsExW(None, None, None, 0, None)

    @staticmethod
    def get_current_settings(device_name: str) -> dict | None:
        dm = DEVMODE()
        dm.dmSize = ctypes.sizeof(DEVMODE)
        if ctypes.windll.user32.EnumDisplaySettingsW(device_name, ENUM_CURRENT_SETTINGS, ctypes.byref(dm)):
            return {
                'width':        dm.dmPelsWidth,
                'height':       dm.dmPelsHeight,
                'refresh_rate': dm.dmDisplayFrequency,
                'position_x':   dm.dmPositionX,
                'position_y':   dm.dmPositionY,
            }
        return None
