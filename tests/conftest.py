"""
Mock Windows-specific modules so tests run on any platform.
This file is loaded by pytest before any test module is imported.
"""
import ctypes
import sys
from unittest.mock import MagicMock

for _mod in ('win32api', 'win32gui', 'win32con', 'pystray', 'keyboard', 'winreg'):
    sys.modules.setdefault(_mod, MagicMock())

if not hasattr(ctypes, 'windll'):
    ctypes.windll = MagicMock()
