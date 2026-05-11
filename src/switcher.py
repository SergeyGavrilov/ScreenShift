import threading
import time

from src.display import DisplayManager, DISP_CHANGE_SUCCESSFUL
from src.migrator import WindowMigrator

_lock = threading.Lock()


def switch_to(profile: dict, notify=None) -> None:
    if not _lock.acquire(blocking=False):
        return
    try:
        for device, cfg in profile.get('monitors', {}).items():
            if cfg.get('enabled'):
                DisplayManager.enable_display(
                    device,
                    width=cfg['width'],
                    height=cfg['height'],
                    refresh_rate=cfg.get('refresh_rate', 60),
                    position_x=cfg.get('position_x', 0),
                    position_y=cfg.get('position_y', 0),
                )
            else:
                DisplayManager.disable_display(device)

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
