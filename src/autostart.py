import os
import sys
import winreg
from pathlib import Path

from src.config import APP_NAME

_RUN_KEY = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Run'


def _exe_cmd(exe_path: str = None) -> str:
    if exe_path:
        return f'"{exe_path}"'
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{Path(__file__).resolve().parent.parent / "screenshift.py"}"'


def autostart_enable(exe_path: str = None) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _exe_cmd(exe_path))


def autostart_disable() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, APP_NAME)
    except FileNotFoundError:
        pass


def start_menu_shortcut(exe_path: str) -> None:
    """Create / update the Start Menu shortcut pointing to the installed exe."""
    if not getattr(sys, 'frozen', False):
        return
    try:
        import win32com.client
        shell    = win32com.client.Dispatch('WScript.Shell')
        programs = (
            Path(os.environ.get('APPDATA', ''))
            / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs'
        )
        lnk = shell.CreateShortcut(str(programs / f'{APP_NAME}.lnk'))
        lnk.TargetPath       = exe_path
        lnk.WorkingDirectory = str(Path(exe_path).parent)
        lnk.Description      = 'Switch monitor profiles instantly'
        lnk.save()
    except Exception:
        pass


def autostart_is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except FileNotFoundError:
        return False
