import sys
from src.config import CONFIG_PATH

if __name__ == '__main__':
    if not CONFIG_PATH.exists():
        from src.setup_wizard import run_setup
        run_setup()
    else:
        from src.app import ScreenShiftApp
        ScreenShiftApp().run()
