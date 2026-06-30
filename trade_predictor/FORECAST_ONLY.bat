@echo off
title NSE Forecast
cd /d "%~dp0"
where py >nul 2>&1 && (set PY=py) || (set PY=python)
echo Next-day forecast (using the last trained model)...
echo.
%PY% predict_next.py
echo.
pause
