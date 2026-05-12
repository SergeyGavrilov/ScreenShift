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
    seen: set[str] = set()
    for d in DisplayManager.list_displays():
        seen.add(d['name'])
        entry: dict = {'device': d['name'], 'enabled': d['active']}
        if d['active']:
            settings = DisplayManager.get_current_settings(d['name'])
            if settings:
                entry.update(settings)
        result.append(entry)
    # list_displays() skips adapters that were disabled by us (registry width=0).
    # Include them explicitly as disabled so restore will turn them back off.
    for name in DisplayManager.list_all_adapters():
        if name not in seen:
            result.append({'device': name, 'enabled': False})
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

def switch_to(profile: dict, notify=None, _bypass_guard: bool = False) -> None:
    global _previous_state, _current_profile
    if (not _bypass_guard
            and _current_profile is not None
            and _current_profile == profile.get('name')):
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
            _previous_state  = snapshot
            _current_profile = profile.get('name')
            time.sleep(1.5)
            try:
                WindowMigrator.migrate_all()
            except Exception:
                pass   # window migration is best-effort
            if notify:
                notify(f"Switched to: {profile['name']}")
        else:
            if notify:
                notify(f"Display change failed (code {result})")
    finally:
        _lock.release()


def detect_active_profile(profiles: list[dict]) -> Optional[str]:
    """Return the name of the profile whose enabled-monitor set matches current state.
    Used on startup so the menu checkmark and already-active guard are correct."""
    try:
        current_active = {d['name'] for d in DisplayManager.list_displays() if d['active']}
    except Exception:
        return None
    for profile in profiles:
        monitors = profile.get('monitors', {})
        if not monitors:
            continue
        profile_active = {dev for dev, cfg in monitors.items() if cfg.get('enabled')}
        if profile_active == current_active:
            return profile['name']
    return None


def restore_previous(notify=None) -> None:
    """Re-apply the display state captured before the last successful switch."""
    if not _previous_state:
        if notify:
            notify('Nothing to restore')
        return
    profile = _snapshot_to_profile(_previous_state)
    # bypass the already-active guard — the state behind 'Previous' changes each time
    switch_to(profile, notify=notify, _bypass_guard=True)
