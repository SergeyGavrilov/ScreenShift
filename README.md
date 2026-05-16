# Monitor Switcher

A utility for quickly switching between monitors on Windows.

---

## Project Status

> **The Python version (ScreenShift) does not work reliably and its development has been discontinued.**
>
> Use `SwitchMonitor.ahk` instead — it solves the same problem in ~20 lines and works reliably.

---

## SwitchMonitor.ahk

### How It Works

The script registers two global hotkeys:

| Shortcut | Action |
|----------|--------|
| `Ctrl+Alt+1` | Enable monitor 1, disable monitor 2 |
| `Ctrl+Alt+2` | Enable monitor 2, disable monitor 1 |

On keypress, the script launches PowerShell 7 (`pwsh.exe`) and calls the `Enable-Display` cmdlet from the **DisplayConfig** module. The cmdlet talks directly to the Windows Display API to switch the active monitor without any extra clicks.

### Dependencies

- **AutoHotkey v2.0** — runtime for the script. Download: https://www.autohotkey.com/
- **PowerShell 7** (`pwsh.exe`) — used to invoke the display-switching commands. Download: https://github.com/PowerShell/PowerShell/releases
- **DisplayConfig** (PowerShell module) — provides the `Enable-Display` cmdlet.

### Installation

1. Install AutoHotkey v2.0.
2. Install PowerShell 7.
3. Install the DisplayConfig module in PowerShell 7:
   ```powershell
   Install-Module -Name DisplayConfig -Scope CurrentUser
   ```
4. Place `SwitchMonitor.ahk` anywhere you like and double-click it to run.

To have the script start with Windows, create a shortcut to `SwitchMonitor.ahk` and place it in the Startup folder:

```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
```

### Configuration

Open `SwitchMonitor.ahk` in any text editor.

**Change hotkeys** — edit the lines with `^!1::` and `^!2::`:

```ahk
; ^ = Ctrl, ! = Alt, # = Win, + = Shift
^!1::  ; Ctrl+Alt+1
^!2::  ; Ctrl+Alt+2
```

**Change monitor IDs** — edit the `-DisplayId` and `-DisplayIdToDisable` values:

```ahk
RunPS('Enable-Display -DisplayId 1 -DisplayIdToDisable 2')
```

To find out which `DisplayId` corresponds to your monitor, run in PowerShell 7:

```powershell
Import-Module DisplayConfig
Get-DisplayConfig
```

---

## Python Version (Archive)

<details>
<summary>Original ScreenShift documentation (unsupported)</summary>

ScreenShift was a system tray applet written in Python for switching monitor profiles.

**Stack:** Python 3, `pystray`, `ctypes` (Windows Display API), `pywin32`, PyInstaller.

```bash
pip install -r requirements.txt
python screenshift.py
```

Build a standalone `.exe`:
```bash
build.bat
```

Development was discontinued due to unreliable behavior with the Windows Display API.

</details>
