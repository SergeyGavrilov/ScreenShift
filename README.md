# ScreenShift

A lightweight Windows 11 system tray utility for instantly switching between monitor profiles.

## The Problem

If you use multiple monitors but not simultaneously — switching between them is tedious: you drag windows around, unused monitors stay powered on, and it takes too many clicks.

## The Solution

ScreenShift sits in your system tray and lets you switch between named display profiles in one click (or a hotkey). When you switch:

- The target monitor is activated
- Unused monitors are turned off
- All open windows are automatically moved to the active display

## Features

- System tray icon with profile menu
- JSON-based profile configuration
- Automatic window migration on profile switch
- Global hotkeys for hands-free switching
- Launches on Windows startup

## Tech Stack

- Python 3
- `pystray` — system tray
- `ctypes` — Windows Display API (`SetDisplayConfig`)
- `pywin32` — window enumeration and movement
- Distributed as a standalone `.exe` via PyInstaller

## Status

Work in progress.
