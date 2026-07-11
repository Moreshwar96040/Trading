@echo off
cd /d "%~dp0"
title market-data-service
if not exist .venv call python -m venv .venv
if not exist .venv\Scripts\uvicorn.exe call .venv\Scripts\pip install --progress-bar off -r requirements-dev.txt
call .venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
