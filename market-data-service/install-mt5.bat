@echo off
REM ============================================================
REM  Installs the MetaTrader 5 Python bridge into THIS service's
REM  venv (not global Python) and verifies it can be imported.
REM  Needed for the Exness FX & crypto tab. Windows only.
REM ============================================================
cd /d "%~dp0"
title install MetaTrader5 bridge

if not exist .venv (
    echo No .venv found. Run run.bat once to create it, then run this again.
    pause
    exit /b 1
)

echo Installing MetaTrader5 into .venv ...
call .venv\Scripts\pip install --progress-bar off MetaTrader5
if errorlevel 1 (
    echo.
    echo FAILED. Most common cause: the venv Python is 32-bit or not 3.9-3.12.
    echo Check with: .venv\Scripts\python --version
    pause
    exit /b 1
)

echo.
echo Verifying the bridge can talk to your terminal...
call .venv\Scripts\python -c "import MetaTrader5 as m; ok=m.initialize(); i=m.account_info() if ok else None; print('package      : OK', m.__version__); print('terminal     :', 'attached' if ok else 'NOT reachable -> open MT5 and log in'); print('account      :', (str(i.login)+' @ '+i.server) if i else 'not logged in'); print('positions    :', len(m.positions_get() or ()) if ok else 0); m.shutdown() if ok else None"

echo.
echo Done. If the account line shows your Exness login, restart the service
echo (close the market-data-service window, run run.bat) and open
echo Portfolio -^> FX ^& Crypto - Exness.
pause
