import ctypes

# ── Constants ─────────────────────────────────────────────────────────────────

DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x00000001
DISPLAY_DEVICE_PRIMARY_DEVICE      = 0x00000004
DISPLAY_DEVICE_MIRRORING_DRIVER    = 0x00000008

CDS_UPDATEREGISTRY    = 0x00000001
CDS_NORESET           = 0x10000000
DISP_CHANGE_SUCCESSFUL = 0

DM_POSITION          = 0x00000020
DM_BITSPERPEL        = 0x00000004
DM_PELSWIDTH         = 0x00080000
DM_PELSHEIGHT        = 0x00100000
DM_DISPLAYFREQUENCY  = 0x00400000
ENUM_CURRENT_SETTINGS  = -1
ENUM_REGISTRY_SETTINGS = -2

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
    def get_monitor_id(adapter_name: str) -> str | None:
        """Return the hardware DeviceID of the monitor attached to adapter_name.

        The DeviceID (e.g. 'MONITOR\\DEL4062\\{...}\\0002') is derived from
        the monitor's EDID and stays constant across reboots even if Windows
        renumbers the adapter as DISPLAY1 ↔ DISPLAY2.  Returns None if no
        monitor is detected on this adapter (display is off or virtual).
        """
        dd = DISPLAY_DEVICE()
        dd.cb = ctypes.sizeof(DISPLAY_DEVICE)
        if ctypes.windll.user32.EnumDisplayDevicesW(adapter_name, 0, ctypes.byref(dd), 0):
            dev_id = dd.DeviceID.strip()
            return dev_id if dev_id else None
        return None

    @staticmethod
    def find_adapter_by_monitor_id(monitor_id: str) -> str | None:
        r"""Return the current \\.\DISPLAYx that has the given monitor hardware ID.

        Scans all non-mirror adapters (active and inactive) so it works even
        when Windows has renumbered adapters after a reboot.
        """
        i = 0
        while True:
            dd = DISPLAY_DEVICE()
            dd.cb = ctypes.sizeof(DISPLAY_DEVICE)
            if not ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                break
            i += 1
            if not dd.DeviceName or (dd.StateFlags & DISPLAY_DEVICE_MIRRORING_DRIVER):
                continue
            mid = DisplayManager.get_monitor_id(dd.DeviceName)
            if mid and mid == monitor_id:
                return dd.DeviceName
        return None

    @staticmethod
    def list_all_adapters() -> list[str]:
        """Names of all real (non-mirror) adapters — no ghost filtering.
        Used by the snapshot to include adapters we previously disabled
        (their registry width is 0, so list_displays() would skip them)."""
        result, i = [], 0
        while True:
            dd = DISPLAY_DEVICE()
            dd.cb = ctypes.sizeof(DISPLAY_DEVICE)
            if not ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                break
            i += 1
            if dd.DeviceName and not (dd.StateFlags & DISPLAY_DEVICE_MIRRORING_DRIVER):
                result.append(dd.DeviceName)
        return result

    @staticmethod
    def list_displays() -> list[dict]:
        result, i = [], 0
        while True:
            dd = DISPLAY_DEVICE()
            dd.cb = ctypes.sizeof(DISPLAY_DEVICE)
            if not ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                break
            i += 1
            if not dd.DeviceName:
                continue
            # Skip virtual mirror drivers (RDP, Hyper-V video, etc.)
            if dd.StateFlags & DISPLAY_DEVICE_MIRRORING_DRIVER:
                continue
            is_active  = bool(dd.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP)
            is_primary = bool(dd.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE)
            # For inactive adapters, skip those with no registry settings or
            # zero resolution — these are ghost/placeholder entries.
            if not is_active:
                dm = DEVMODE()
                dm.dmSize = ctypes.sizeof(DEVMODE)
                has_reg = ctypes.windll.user32.EnumDisplaySettingsW(
                    dd.DeviceName, ENUM_REGISTRY_SETTINGS, ctypes.byref(dm),
                )
                if not has_reg or dm.dmPelsWidth == 0:
                    continue
            result.append({
                'name':        dd.DeviceName,
                'description': dd.DeviceString,
                'active':      is_active,
                'primary':     is_primary,
                'monitor_id':  DisplayManager.get_monitor_id(dd.DeviceName),
            })
        return result

    @staticmethod
    def enable_display(device: str, width: int, height: int,
                       refresh_rate: int, position_x: int, position_y: int,
                       bpp: int = 32) -> int:
        dm = DEVMODE()
        dm.dmSize = ctypes.sizeof(DEVMODE)

        # Priority 1: registry-stored settings (valid after a previous enable).
        # disable_display() writes width=0 to registry, so zero means the
        # display was last disabled by us — fall through to the next option.
        has_reg = ctypes.windll.user32.EnumDisplaySettingsW(
            device, ENUM_REGISTRY_SETTINGS, ctypes.byref(dm),
        )
        if has_reg and dm.dmPelsWidth > 0:
            dm.dmPositionX  = position_x
            dm.dmPositionY  = position_y
            dm.dmFields    |= DM_POSITION
        else:
            # Priority 2: live current settings — Windows often auto-restores
            # disabled displays after reboot, giving us the correct native mode.
            cur = DEVMODE()
            cur.dmSize = ctypes.sizeof(DEVMODE)
            has_cur = ctypes.windll.user32.EnumDisplaySettingsW(
                device, ENUM_CURRENT_SETTINGS, ctypes.byref(cur),
            )
            if has_cur and cur.dmPelsWidth > 0:
                dm.dmFields           = DM_PELSWIDTH | DM_PELSHEIGHT | DM_POSITION | DM_DISPLAYFREQUENCY | DM_BITSPERPEL
                dm.dmPelsWidth        = cur.dmPelsWidth
                dm.dmPelsHeight       = cur.dmPelsHeight
                dm.dmDisplayFrequency = cur.dmDisplayFrequency
                dm.dmBitsPerPel       = cur.dmBitsPerPel if cur.dmBitsPerPel else bpp
                dm.dmPositionX        = position_x
                dm.dmPositionY        = position_y
            else:
                # Priority 3: config values as last resort.
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
