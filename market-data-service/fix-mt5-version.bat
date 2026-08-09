@echo off
REM ============================================================
REM  -10005 IPC timeout persists with the correct path and the
REM  Python API allowed. Prime suspect: the MetaTrader5 Python
REM  package build does not match the terminal build.
REM  This prints both, then tries a known-good older package.
REM ============================================================
cd /d "%~dp0"
title fix MT5 version mismatch

echo === Terminal build (file version of terminal64.exe) ===
powershell -NoProfile -Command "(Get-Item 'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe').VersionInfo | Select-Object FileVersion,ProductVersion | Format-List"

echo === Current Python package version ===
call .venv\Scripts\python -c "import MetaTrader5 as m; print('  package:', m.__version__)"

echo.
echo === Attempt A: is the Algo Trading toolbar button ON? ===
echo   In MetaTrader 5 the toolbar button must be GREEN, not a red square.
echo   If it is red, click it now, then press any key to continue.
pause

call .venv\Scripts\python -c "import MetaTrader5 as m; p=r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe'; ok=m.initialize(path=p, timeout=180000); print('  retry initialize:', ok, m.last_error()); m.shutdown() if ok else None"

echo.
echo === Attempt B: downgrade the package to a known-good build ===
echo   Press Ctrl+C to skip, or any key to downgrade and retest.
pause
call .venv\Scripts\pip install --progress-bar off "MetaTrader5==5.0.4687"
call .venv\Scripts\python -c "import MetaTrader5 as m; print('  package now:', m.__version__); p=r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe'; ok=m.initialize(path=p, timeout=180000); print('  initialize :', ok, m.last_error()); i=m.account_info() if ok else None; print('  account    :', (str(i.login)+' @ '+i.server) if i else 'none'); print('  positions  :', len(m.positions_get() or ()) if ok else 0); m.shutdown() if ok else None"

echo.
echo If Attempt B connected, keep this version - I will pin it in
echo requirements.txt. If BOTH failed, tell me the terminal build
echo printed at the top and we will try the matching package.
pause
