@echo off
REM ============================================================
REM  One-click startup: DB -> backend -> python -> data -> UI.
REM  Each service opens in its own window; close windows to stop.
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist .env copy .env.example .env >nul

echo [1/6] Checking Docker...
docker info >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker Desktop is not running. Start it, then run this again.
    pause
    exit /b 1
)

echo [2/6] Starting PostgreSQL...
docker compose up -d
set /a tries=0
:waitdb
set /a tries+=1
if %tries% gtr 30 (echo ERROR: PostgreSQL did not become ready. & pause & exit /b 1)
timeout /t 2 /nobreak >nul
docker compose exec -T postgres pg_isready -U trading -d trading >nul 2>&1 || goto waitdb
echo     PostgreSQL is ready.

echo [3/6] Starting backend and Python service (separate windows)...
start "trading-backend" cmd /k backend\run.bat
start "market-data-service" cmd /k market-data-service\run.bat

echo [4/6] Waiting for backend on :8080 (first start compiles - can take 1-2 min)...
set /a tries=0
:waitapi
set /a tries+=1
if %tries% gtr 60 (echo ERROR: Backend did not start - check the trading-backend window. & pause & exit /b 1)
timeout /t 3 /nobreak >nul
curl -s -f -o nul http://localhost:8080/api/v1/symbols || goto waitapi
echo     Backend is up.

echo     Waiting for Python service on :8000...
set /a tries=0
:waitpy
set /a tries+=1
if %tries% gtr 60 (echo ERROR: Python service did not start - check its window. & pause & exit /b 1)
timeout /t 3 /nobreak >nul
curl -s -f -o nul http://localhost:8000/health || goto waitpy
echo     Python service is up.

echo [5/6] Loading NSE dataset (idempotent - safe every run)...
curl -s -X POST http://localhost:8080/api/v1/sync/csv-import
echo.

echo [6/6] Starting UI (new window; first start runs npm install)...
start "trading-ui" cmd /k frontend\run.bat
set /a tries=0
:waitui
set /a tries+=1
if %tries% gtr 100 (echo NOTE: UI still compiling - it will open at http://localhost:4200 when done. & goto end)
timeout /t 3 /nobreak >nul
curl -s -o nul http://localhost:4200 || goto waitui
start http://localhost:4200

:end
echo.
echo All services launched. Search RELIANCE at http://localhost:4200
pause
