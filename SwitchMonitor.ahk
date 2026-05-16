; Monitor Switcher
; Requires: AutoHotkey v2.0  https://www.autohotkey.com/
;           PowerShell 7      https://github.com/PowerShell/PowerShell/releases
;           DisplayConfig module — install once in PowerShell 7:
;               Install-Module -Name DisplayConfig -Scope CurrentUser
;
; To find your monitor IDs, run in PowerShell 7:
;   Import-Module DisplayConfig
;   Get-DisplayConfig
; Use the DisplayId values shown there in the hotkey bindings below.

#Requires AutoHotkey v2.0
#SingleInstance Force  ; only one instance of this script can run at a time

; Launches a PowerShell 7 command and waits for it to finish.
; The window is hidden so nothing flashes on screen.
RunPS(psCmd) {
    cmd := 'pwsh.exe -ExecutionPolicy Bypass -Command "Import-Module DisplayConfig; ' psCmd '"'
    RunWait cmd, , "Hide"
}

; --- Hotkey modifier symbols ---
; ^  = Ctrl
; !  = Alt
; #  = Win
; +  = Shift
; Example: ^+!1 means Ctrl+Shift+Alt+1

; Ctrl+Alt+1 — enable monitor 1 (work), disable monitor 2 (gaming)
; To change the hotkey, replace ^!1 with any combination from the table above.
; To change which monitor turns on/off, adjust -DisplayId and -DisplayIdToDisable.
^!1:: {
    RunPS('Enable-Display -DisplayId 1 -DisplayIdToDisable 2')
}

; Ctrl+Alt+2 — enable monitor 2 (gaming), disable monitor 1 (work)
^!2:: {
    RunPS('Enable-Display -DisplayId 2 -DisplayIdToDisable 1')
}
