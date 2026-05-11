import win32api
import win32con
import win32gui


class WindowMigrator:

    @staticmethod
    def _primary_work_rect() -> tuple[int, int, int, int]:
        for monitor, _, _ in win32api.EnumDisplayMonitors():
            info = win32api.GetMonitorInfo(monitor)
            if info.get('Flags') & 1:
                return info['Work']
        return (0, 0,
                win32api.GetSystemMetrics(win32con.SM_CXSCREEN),
                win32api.GetSystemMetrics(win32con.SM_CYSCREEN))

    @classmethod
    def migrate_all(cls) -> None:
        px, py, pr, pb = cls._primary_work_rect()
        pw, ph = pr - px, pb - py

        def _move(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd) or not win32gui.GetWindowText(hwnd):
                return True
            if win32gui.IsIconic(hwnd):
                return True
            try:
                monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONULL)
                if monitor is None:
                    return True
                if win32api.GetMonitorInfo(monitor).get('Flags') & 1:
                    return True  # already on primary
                was_max = win32gui.IsZoomed(hwnd)
                if was_max:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                r = win32gui.GetWindowRect(hwnd)
                w = min(r[2] - r[0], pw)
                h = min(r[3] - r[1], ph)
                win32gui.MoveWindow(hwnd, px + (pw - w) // 2, py + (ph - h) // 2, w, h, True)
                if was_max:
                    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            except Exception:
                pass
            return True

        win32gui.EnumWindows(_move, None)
