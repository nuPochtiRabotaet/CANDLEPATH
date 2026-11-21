@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Run setup.bat first.
  pause
  exit /b 0
)
".venv\Scripts\python.exe" -m moex_intelligence.launcher stop
if errorlevel 1 pause
