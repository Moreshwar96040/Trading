@echo off
cd /d "%~dp0"
title trading-ui
if not exist node_modules call npm install
call npm start
pause
