@echo off
setlocal
cd /d "%~dp0"
set "MFF_PYTHON=%~dp0..\..\work\mff-venv\Scripts\python.exe"
if not exist "%MFF_PYTHON%" (
  echo The MFF Auto Python environment is missing. This launcher is configured for this PC.
  pause
  exit /b 1
)
start "MFF Auto" "%~dp0MFF Auto.exe"
