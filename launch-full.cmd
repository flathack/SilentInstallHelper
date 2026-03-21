@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  python ".\run.py" ".\config-template-full.jsonc"
  if errorlevel 1 pause
) else if exist ".\dist\SilentInstallHelper.exe" (
  ".\dist\SilentInstallHelper.exe" ".\config-template-full.jsonc"
  if errorlevel 1 pause
) else (
  echo Weder Python noch dist\SilentInstallHelper.exe wurden gefunden.
  pause
)
