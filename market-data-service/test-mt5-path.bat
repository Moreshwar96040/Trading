@echo off
REM ============================================================
REM  Retries the MT5 bridge using the EXPLICIT terminal path
REM  (your install is in "MetaTrader 5 EXNESS", which the package's
REM  auto-discovery does not find -> IPC timeout -10005).
REM ============================================================
cd /d "%~dp0"
title test MT5 explicit path

call .venv\Scripts\python -c "import MetaTrader5 as m; p=r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe'; ok=m.initialize(path=p, timeout=120000); print('initialize(path=...):', ok); print('last_error()       :', m.last_error()); i=m.account_info() if ok else None; print('account            :', (str(i.login)+' @ '+i.server) if i else 'none'); print('currency/equity    :', (i.currency+' '+str(i.equity)) if i else '-'); print('open positions     :', len(m.positions_get() or ()) if ok else 0); m.shutdown() if ok else None"

echo.
echo If initialize() is True above, MT5_TERMINAL_PATH is already set in your
echo .env - just restart the market-data-service and open the Exness tab.
echo.
echo If it is still False with -10005, try in MetaTrader 5:
echo   Tools -^> Options -^> Expert Advisors -^> tick "Allow algorithmic trading"
echo then close any open dialog in the terminal and run this again.
pause
