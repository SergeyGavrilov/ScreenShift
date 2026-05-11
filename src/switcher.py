import threading
import time

from src.display import DisplayManager, DISP_CHANGE_SUCCESSFUL
from src.migrator import WindowMigrator

_lock = threading.Lock()


def switch_to(profile: dict, notify=None) -> None:
    if not _lock.acquire(blocking=False):
        return
    try:
        monitors_cfg = profile.get('monitors', {})

        # Enable monitors before disabling — ensures at least one display stays
        # active throughout the staging phase so Windows doesn't reject requests.
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
            time.sleep(1.5)
            WindowMigrator.migrate_all()
            if notify:
                notify(f"Switched to: {profile['name']}")
        else:
            if notify:
                notify(f"Display change failed (code {result})")
    finally:
        _lock.release()
