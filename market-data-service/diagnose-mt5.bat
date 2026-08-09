@echo off
REM ============================================================
REM  Diagnoses why the MT5 bridge can't attach to the terminal.
REM  Reports the real error code, finds installed terminals, and
REM  retries against each path it finds.
REM ============================================================
cd /d "%~dp0"
title diagnose MT5 bridge

echo === 1. Is a MetaTrader 5 terminal actually running? ===
tasklist /FI "IMAGENAME eq terminal64.exe" 2>nul | find /I "terminal64.exe" >nul
if errorlevel 1 (
    echo   NO terminal64.exe process found.
    echo   ^-^> MetaTrader 5 is not running. Open it and log into Exness.
) else (
    echo   terminal64.exe IS running:
    powershell -NoProfile -Command "Get-Process terminal64 -ErrorAction SilentlyContinue | Select-Object Id,Path | Format-Table -AutoSize" 2>nul
)

echo.
echo === 2. Are you running elevated? (must match the terminal) ===
net session >nul 2>&1
if errorlevel 1 (echo   This window: NORMAL user) else (echo   This window: ADMINISTRATOR)
echo   If MT5 was started "as administrator" and this is not (or vice
echo   versa), Windows blocks the IPC channel between them.

echo.
echo === 3. Installed terminals found on disk ===
powershell -NoProfile -Command "$p=@(); foreach($r in @($env:ProgramFiles,${env:ProgramFiles(x86)},\"$env:APPDATA\")){ if($r){ $p += Get-ChildItem -Path $r -Filter terminal64.exe -Recurse -ErrorAction SilentlyContinue -Depth 4 | Select-Object -ExpandProperty FullName } }; if($p){$p | ForEach-Object {Write-Host '   ' $_}} else {Write-Host '    none found'}"

echo.
echo === 4. Bridge attempt with the real error code ===
call .venv\Scripts\python -c "import MetaTrader5 as m; ok=m.initialize(); print('   initialize():', ok); print('   last_error():', m.last_error()); i=m.account_info() if ok else None; print('   account    :', (str(i.login)+' @ '+i.server) if i else 'none'); m.shutdown() if ok else None"

echo.
echo === What the codes mean ===
echo   (-10003, 'IPC initialize failed')  terminal not found / not running,
echo                                      or an elevation mismatch (see step 2)
echo   (-10005, 'IPC timeout')            terminal busy or still starting
echo   (-6,     'Authorization failed')   terminal running but not logged in
echo   (1, 'Success') with account none   logged out account
echo.
echo If a path was listed in step 3 but initialize() failed, set it in .env:
echo   MT5_TERMINAL_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
echo (use the Exness one if several are listed), then re-run this script.
pause
