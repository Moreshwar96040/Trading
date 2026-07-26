@echo off
cd /d "%~dp0"
title trading-backend

REM ---- load ..\.env into this process's environment ----
REM Spring Boot reads OS environment variables, not .env files (that's a Python
REM convention) — so every KEY=VALUE line is exported here before launch.
REM Lines starting with # are comments; blank lines are skipped automatically.
if exist "..\.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in ("..\.env") do (
        if not "%%a"=="" set "%%a=%%b"
    )
    echo Loaded environment from ..\.env
) else (
    echo WARNING: ..\.env not found - using defaults only
)

mvn spring-boot:run
pause
