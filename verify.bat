@echo off
REM ============================================================
REM  One-click Phase 1 verification.
REM  Runs: Python tests, backend tests, frontend build.
REM  All output -> verification.log (share/readable by Claude).
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
set LOG=%~dp0verification.log

echo ==== VERIFICATION RUN %date% %time% ==== > "%LOG%"

echo ==== TOOL VERSIONS ==== >> "%LOG%"
call java -version >> "%LOG%" 2>&1
call mvn -version >> "%LOG%" 2>&1
call node -v >> "%LOG%" 2>&1
call npm -v >> "%LOG%" 2>&1
call python --version >> "%LOG%" 2>&1
call docker --version >> "%LOG%" 2>&1

echo [1/3] Python tests...
echo. >> "%LOG%"
echo ==== [1/3] PYTHON TESTS ==== >> "%LOG%"
cd market-data-service
if not exist .venv call python -m venv .venv >> "%LOG%" 2>&1
call .venv\Scripts\pip install --progress-bar off -r requirements-dev.txt >> "%LOG%" 2>&1
call .venv\Scripts\python -m pytest -v >> "%LOG%" 2>&1
echo PYTHON_EXIT_CODE: !errorlevel! >> "%LOG%"
cd /d "%~dp0"

echo [2/3] Backend tests (first run downloads dependencies - takes a while)...
echo. >> "%LOG%"
echo ==== [2/3] BACKEND TESTS ==== >> "%LOG%"
cd backend
call mvn -B -ntp test >> "%LOG%" 2>&1
echo MAVEN_EXIT_CODE: !errorlevel! >> "%LOG%"
cd /d "%~dp0"

echo [3/3] Frontend install + production build...
echo. >> "%LOG%"
echo ==== [3/3] FRONTEND BUILD ==== >> "%LOG%"
cd frontend
call npm install >> "%LOG%" 2>&1
echo NPM_INSTALL_EXIT_CODE: !errorlevel! >> "%LOG%"
call npm run build >> "%LOG%" 2>&1
echo NPM_BUILD_EXIT_CODE: !errorlevel! >> "%LOG%"
cd /d "%~dp0"

echo. >> "%LOG%"
echo ==== DONE ==== >> "%LOG%"
echo.
echo Finished. Results are in verification.log
echo Look for PYTHON_EXIT_CODE / MAVEN_EXIT_CODE / NPM_BUILD_EXIT_CODE (0 = pass).
pause
