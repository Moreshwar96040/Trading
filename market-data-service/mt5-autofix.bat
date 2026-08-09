@echo off
REM ============================================================
REM  Unattended MT5 fix attempt. No prompts - writes everything
REM  to mt5-autofix.log so it can be read without a console.
REM ============================================================
cd /d "%~dp0"
set LOG=%~dp0mt5-autofix.log
> "%LOG%" echo ===== MT5 AUTOFIX %DATE% %TIME% =====

>> "%LOG%" echo.
>> "%LOG%" echo --- terminal build ---
powershell -NoProfile -Command "(Get-Item 'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe').VersionInfo.FileVersion" >> "%LOG%" 2>&1

>> "%LOG%" echo --- terminal process ---
powershell -NoProfile -Command "Get-Process terminal64 -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Path" >> "%LOG%" 2>&1

>> "%LOG%" echo.
>> "%LOG%" echo --- attempt 1: current package, explicit path ---
call .venv\Scripts\python -c "import MetaTrader5 as m; print('pkg', m.__version__); p=r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe'; ok=m.initialize(path=p, timeout=180000); print('init', ok, m.last_error()); i=m.account_info() if ok else None; print('acct', (str(i.login)+' @ '+i.server) if i else 'none'); m.shutdown() if ok else None" >> "%LOG%" 2>&1

>> "%LOG%" echo.
>> "%LOG%" echo --- attempt 2: no path, auto-discovery ---
call .venv\Scripts\python -c "import MetaTrader5 as m; ok=m.initialize(timeout=180000); print('init', ok, m.last_error()); m.shutdown() if ok else None" >> "%LOG%" 2>&1

>> "%LOG%" echo.
>> "%LOG%" echo --- attempt 3: downgrade to 5.0.4687 ---
call .venv\Scripts\pip install --progress-bar off --quiet "MetaTrader5==5.0.4687" >> "%LOG%" 2>&1
call .venv\Scripts\python -c "import MetaTrader5 as m; print('pkg', m.__version__); p=r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe'; ok=m.initialize(path=p, timeout=180000); print('init', ok, m.last_error()); i=m.account_info() if ok else None; print('acct', (str(i.login)+' @ '+i.server) if i else 'none'); print('pos', len(m.positions_get() or ()) if ok else 0); m.shutdown() if ok else None" >> "%LOG%" 2>&1

>> "%LOG%" echo.
>> "%LOG%" echo --- attempt 4: downgrade to 5.0.45 ---
call .venv\Scripts\pip install --progress-bar off --quiet "MetaTrader5==5.0.45" >> "%LOG%" 2>&1
call .venv\Scripts\python -c "import MetaTrader5 as m; print('pkg', m.__version__); p=r'C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe'; ok=m.initialize(path=p, timeout=180000); print('init', ok, m.last_error()); i=m.account_info() if ok else None; print('acct', (str(i.login)+' @ '+i.server) if i else 'none'); print('pos', len(m.positions_get() or ()) if ok else 0); m.shutdown() if ok else None" >> "%LOG%" 2>&1

>> "%LOG%" echo.
>> "%LOG%" echo ===== DONE =====
