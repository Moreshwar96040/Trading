@echo off
title Model Accuracy
cd /d "%~dp0"
where py >nul 2>&1 && (set PY=py) || (set PY=python)
%PY% -u accuracy.py
echo.
pause
