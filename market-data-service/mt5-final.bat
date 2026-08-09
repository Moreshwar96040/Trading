@echo off
REM ============================================================
REM  -6 Authorization failed means IPC works but the instance the
REM  package started is not logged in. Attaching WITHOUT a path
REM  reuses the running, logged-in terminal instead.
REM ============================================================
cd /d "%~dp0"
set LOG=%~dp0mt5-final.log
> "%LOG%" echo ===== MT5 FINAL %DATE% %TIME% =====

>> "%LOG%" echo --- A: attach to the RUNNING terminal (no path) ---
call .venv\Scripts\python -c "import MetaTrader5 as m; ok=m.initialize(); print('init', ok, m.last_error()); ti=m.terminal_info(); print('connected', getattr(ti,'connected',None) if ti else None); i=m.account_info(); print('acct', (str(i.login)+' @ '+i.server) if i else 'none'); print('equity', (i.currency+' '+str(i.equity)+' bal '+str(i.balance)+' margin_level '+str(i.margin_level)) if i else '-'); ps=m.positions_get(); print('positions', len(ps or ())); [print('  POS', x.symbol, 'type', x.type, 'vol', x.volume, 'open', x.price_open, 'now', x.price_current, 'sl', x.sl, 'tp', x.tp, 'profit', x.profit, 'swap', x.swap) for x in (ps or ())]; m.shutdown()" >> "%LOG%" 2>&1

>> "%LOG%" echo.
>> "%LOG%" echo --- B: portable flag with path (fallback) ---
call .venv\Scripts\python -c "import MetaTrader5 as m; p=r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe'; ok=m.initialize(path=p, portable=False); print('init', ok, m.last_error()); i=m.account_info(); print('acct', (str(i.login)+' @ '+i.server) if i else 'none'); m.shutdown() if ok else None" >> "%LOG%" 2>&1

>> "%LOG%" echo ===== DONE =====
