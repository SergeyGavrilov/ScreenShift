; Переключение мониторов
; Ctrl+Alt+1 — монитор 1, 34R83Q (работа)
; Ctrl+Alt+2 — монитор 2, Mi monitor (игры)
; Requires AutoHotkey v2.0 и PowerShell 7 (pwsh)

#Requires AutoHotkey v2.0
#SingleInstance Force

RunPS(psCmd) {
    cmd := 'pwsh.exe -ExecutionPolicy Bypass -Command "Import-Module DisplayConfig; ' psCmd '"'
    RunWait cmd, , "Hide"
}

; Ctrl+Alt+1 — работа (монитор 1)
^!1:: {
    RunPS('Enable-Display -DisplayId 1 -DisplayIdToDisable 2')
}

; Ctrl+Alt+2 — игры (монитор 2)
^!2:: {
    RunPS('Enable-Display -DisplayId 2 -DisplayIdToDisable 1')
}
