@echo off
REM ============================================================
REM  Run this AFTER logging into your Exness account in MT5.
REM  Restores the correct package version and verifies the bridge.
REM  Writes to mt5-verify.log (no prompts).
REM ============================================================
cd /d "%~dp0"
set LOG=%~dp0mt5-verify.log
> "%LOG%" echo ===== MT5 VERIFY %DATE% %TIME% =====

>> "%LOG%" echo --- restoring package to 5.0.6070 (matches terminal build 6061) ---
call .venv\Scripts\pip install --progress-bar off --quiet "MetaTrader5==5.0.6070" >> "%LOG%" 2>&1

>> "%LOG%" echo.
>> "%LOG%" echo --- connecting ---
call .venv\Scripts\python -c "import MetaTrader5 as m; print('pkg', m.__version__); p=r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe'; ok=m.initialize(path=p, timeout=120000); print('init', ok, m.last_error()); ti=m.terminal_info(); print('connected', getattr(ti,'connected',None) if ti else None); i=m.account_info() if ok else None; print('acct', (str(i.login)+' @ '+i.server) if i else 'none'); print('equity', (i.currency+' '+str(i.equity)) if i else '-'); ps=m.positions_get() if ok else (); print('positions', len(ps or ())); [print('  ', x.symbol, x.volume, x.price_open, '->', x.price_current, 'sl', x.sl, 'pnl', x.profit) for x in (ps or ())]; m.shutdown() if ok else None" >> "%LOG%" 2>&1

>> "%LOG%" echo ===== DONE =====
