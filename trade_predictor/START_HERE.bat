@echo off
title NSE Trade Predictor
cd /d "%~dp0"
echo ============================================================
echo   NSE SELF-LEARNING TRADE PREDICTOR
echo ============================================================
echo.

REM --- find Python ---
where py >nul 2>&1 && (set PY=py) || (set PY=python)
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python is not installed or not on PATH.
  echo Install Python 3.10+ from https://www.python.org/downloads/
  echo and tick "Add Python to PATH", then run this again.
  echo.
  pause
  exit /b 1
)
%PY% --version

echo.
echo [1/3] Installing libraries. The FIRST run downloads LightGBM/SciPy
echo       (about 50-100 MB) and can take 5-10 minutes. Progress shows below.
echo       (Later runs skip this instantly.)
echo ------------------------------------------------------------
%PY% -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 (
  echo.
  echo [WARN] Full install failed. Installing minimal set so it still runs...
  %PY% -m pip install -r requirements-minimal.txt --disable-pip-version-check
)
echo ------------------------------------------------------------
echo Libraries ready.
echo.

echo [2/3] Training + backtest. Live progress prints below...
%PY% -u trade_model.py --trials 12
echo.

echo [3/3] Next-day forecast:
%PY% -u predict_next.py
echo.
echo ============================================================
echo   DONE.  Accuracy table saved in:  artifacts\metrics.csv
echo ============================================================
pause
