@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="
py -3.12 -c "import sys; assert sys.version_info[:2] == (3,12)" >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3.12"
if not defined PYTHON_CMD (
  py -3.13 -c "import sys; assert sys.version_info[:2] == (3,13)" >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=py -3.13"
)
if not defined PYTHON_CMD (
  echo ERROR: Install Python 3.12 or 3.13 (64-bit) from python.org.
  echo During installation, enable the Python launcher.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -c "import sys; assert (3,12) <= sys.version_info[:2] < (3,14)"
if errorlevel 1 (
  echo ERROR: Existing .venv uses an unsupported Python. Delete .venv and run setup.bat again.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install --require-hashes -r requirements.txt
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -c "import numpy, pandas, streamlit, mcp, websockets; print('Dependencies are ready.')"
if errorlevel 1 goto :error

echo.
echo Setup complete. Run start.bat.
pause
exit /b 0

:error
echo.
echo Setup failed. Check the error above and see the project documentation.
pause
exit /b 1
