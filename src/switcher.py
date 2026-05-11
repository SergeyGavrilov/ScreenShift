import threading
import time
from typing import Optional

from src.display import DisplayManager, DISP_CHANGE_SUCCESSFUL
from src.migrator import WindowMigrator

_lock            = threading.Lock()
_previous_state: Optional[list] = None   # snapshot taken before the last successful switch
_current_profile: Optional[str] = None   # name of the last successfully applied profile


# ── snapshot helpers ──────────────────────────────────────────────────────────

def _snapshot() -> list[dict]:
    """Capture the current active/inactive state of all known displays."""
    result = []
    for d in DisplayManager.list_displays():
        entry: dict = {'device': d['name'], 'enabled': d['active']}
        if d['active']:
            settings = DisplayManager.get_current_settings(d['name'])
            if settings:
                entry.update(settings)
        result.append(entry)
    return result


def _snapshot_to_profile(state: list[dict], name: str = 'Previous') -> dict:
    monitors = {}
    for entry in state:
        if entry['enabled']:
            monitors[entry['device']] = {
                'enabled':      True,
                'width':        entry.get('width',        1920),
                'height':       entry.get('height',       1080),
                'refresh_rate': entry.get('refresh_rate', 60),
                'position_x':   entry.get('position_x',  0),
                'position_y':   entry.get('position_y',  0),
            }
        else:
            monitors[entry['device']] = {'enabled': False}
    return {'name': name, 'monitors': monitors}


# ── public API ────────────────────────────────────────────────────────────────

def switch_to(profile: dict, notify=None) -> None:
    global _previous_state, _current_profile
    if _current_profile is not None and _current_profile == profile.get('name'):
        if notify:
            notify(f"Already active: {profile['name']}")
        return
    if not _lock.acquire(blocking=False):
        return
    try:
        snapshot = _snapshot()

        monitors_cfg = profile.get('monitors', {})
        ordered = sorted(monitors_cfg.items(), key=lambda kv: not kv[1].get('enabled', False))

        failed = []
        for device, cfg in ordered:
            if cfg.get('enabled'):
                ret = DisplayManager.enable_display(
                    device,
                    width=cfg['width'],
                    height=cfg['height'],
                    refresh_rate=cfg.get('refresh_rate', 60),
                    position_x=cfg.get('position_x', 0),
                    position_y=cfg.get('position_y', 0),
                )
            else:
                ret = DisplayManager.disable_display(device)

            if ret != DISP_CHANGE_SUCCESSFUL:
                failed.append(f"{device.replace('\\\\.\\', '')} → code {ret}")

        if failed:
            if notify:
                notify(f"Staging failed: {', '.join(failed)}")
            return

        result = DisplayManager.apply_changes()

        if result == DISP_CHANGE_SUCCESSFUL:
            _previous_state  = snapshot           # commit snapshot only on success
            _current_profile = profile.get('name')
            time.sleep(1.5)
            WindowMigrator.migrate_all()
            if notify:
                notify(f"Switched to: {profile['name']}")
        else:
            if notify:
                notify(f"Display change failed (code {result})")
    finally:
        _lock.release()


def restore_previous(notify=None) -> None:
    """Re-apply the display state captured before the last successful switch."""
    if not _previous_state:
        if notify:
            notify('Nothing to restore')
        return
    profile = _snapshot_to_profile(_previous_state)
    switch_to(profile, notify=notify)
