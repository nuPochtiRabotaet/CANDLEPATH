@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m moex_intelligence.launcher start
if errorlevel 1 (
  echo.
  echo Startup failed. Check .runtime\app.log
  pause
  exit /b 1
)
