import logging
import threading
import time
from typing import Optional

from src.display import DisplayManager, DISP_CHANGE_SUCCESSFUL
from src.migrator import WindowMigrator

_log = logging.getLogger('ScreenShift')

_lock            = threading.Lock()
_previous_state: Optional[list] = None   # snapshot taken before the last successful switch
_current_profile: Optional[str] = None   # name of the last successfully applied profile


# ── snapshot helpers ──────────────────────────────────────────────────────────

def _snapshot(profile_devices: set[str] | None = None) -> list[dict]:
    """Capture the current active/inactive state of known displays.

    profile_devices — device names from the profile about to be applied.
    Devices in this set that are currently inactive (registry width=0, so
    skipped by list_displays) are added as disabled, ensuring restore can
    explicitly turn them back off.  This avoids pulling in the dozens of
    virtual/ghost adapters that list_all_adapters() would return.
    """
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
    for name in (profile_devices or set()):
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
    name = profile.get('name', '?')
    if (not _bypass_guard
            and _current_profile is not None
            and _current_profile == name):
        msg = f"Already active: {name}"
        _log.info(msg)
        if notify:
            notify(msg)
        return
    if not _lock.acquire(blocking=False):
        _log.debug("Switch to '%s' dropped — another switch in progress", name)
        return
    try:
        _log.info("Switching to profile '%s'", name)
        monitors_cfg = profile.get('monitors', {})
        snapshot = _snapshot(profile_devices=set(monitors_cfg.keys()))
        ordered = sorted(monitors_cfg.items(), key=lambda kv: not kv[1].get('enabled', False))

        failed = []
        for device, cfg in ordered:
            # Resolve current adapter name via monitor hardware ID so the switch
            # still targets the right physical monitor even if Windows renumbered
            # DISPLAY1 ↔ DISPLAY2 after a reboot.
            monitor_id = cfg.get('monitor_id')
            if monitor_id:
                current = DisplayManager.find_adapter_by_monitor_id(monitor_id)
                if current and current != device:
                    _log.info(
                        "Remapped %s → %s (Windows renumbered after reboot)",
                        device.replace('\\\\.\\', ''),
                        current.replace('\\\\.\\', ''),
                    )
                    device = current

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

            short = device.replace('\\\\.\\', '')
            if ret != DISP_CHANGE_SUCCESSFUL:
                failed.append(f"{short} → code {ret}")
                _log.warning("Staging %s failed (code %d)", short, ret)
            else:
                action = 'enabled' if cfg.get('enabled') else 'disabled'
                _log.debug("Staged %s %s", short, action)

        if failed:
            msg = f"Staging failed: {', '.join(failed)}"
            _log.error(msg)
            if notify:
                notify(msg)
            return

        result = DisplayManager.apply_changes()

        if result == DISP_CHANGE_SUCCESSFUL:
            _previous_state  = snapshot
            _current_profile = name
            _log.info("Applied profile '%s' successfully", name)
            time.sleep(1.5)
            try:
                WindowMigrator.migrate_all()
            except Exception as exc:
                _log.warning("WindowMigrator raised: %s", exc)
            if notify:
                notify(f"Switched to: {name}")
        else:
            msg = f"Display change failed (code {result})"
            _log.error("%s for profile '%s'", msg, name)
            if notify:
                notify(msg)
    finally:
        _lock.release()


def detect_active_profile(profiles: list[dict]) -> Optional[str]:
    """Return the name of the profile whose enabled-monitor set matches current state.

    Matches first by adapter name (exact), then by monitor hardware ID so the
    correct profile is detected even after Windows renumbers adapters on reboot.
    """
    try:
        active_displays     = [d for d in DisplayManager.list_displays() if d['active']]
        current_active_names = {d['name'] for d in active_displays}
        current_active_ids   = {d['monitor_id'] for d in active_displays
                                 if d.get('monitor_id')}
    except Exception:
        return None
    for profile in profiles:
        monitors = profile.get('monitors', {})
        if not monitors:
            continue
        profile_active_names = {dev for dev, cfg in monitors.items() if cfg.get('enabled')}
        profile_active_ids   = {cfg['monitor_id'] for cfg in monitors.values()
                                 if cfg.get('enabled') and cfg.get('monitor_id')}
        if profile_active_names == current_active_names:
            return profile['name']
        if profile_active_ids and current_active_ids and profile_active_ids == current_active_ids:
            return profile['name']
    return None


def restore_previous(notify=None) -> None:
    """Re-apply the display state captured before the last successful switch."""
    if not _previous_state:
        msg = 'Nothing to restore'
        _log.info(msg)
        if notify:
            notify(msg)
        return
    _log.info("Restoring previous display state")
    profile = _snapshot_to_profile(_previous_state)
    # bypass the already-active guard — the state behind 'Previous' changes each time
    switch_to(profile, notify=notify, _bypass_guard=True)
