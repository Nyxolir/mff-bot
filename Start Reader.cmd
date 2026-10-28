@echo off
setlocal
cd /d "%~dp0"
set "MFF_PYTHON=%~dp0..\..\work\mff-venv\Scripts\python.exe"
if not exist "%MFF_PYTHON%" (
  echo The isolated Python environment is missing. This launcher is configured for this PC.
  pause
  exit /b 1
)
"%MFF_PYTHON%" reader_gui.py
if errorlevel 1 pause
