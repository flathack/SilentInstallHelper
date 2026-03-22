@echo off
setlocal
cd /d "%~dp0"
start "" py -3 "%~dp0run.py"
endlocal
