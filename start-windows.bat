@echo off
cd /d "%~dp0"
if not exist app.py (
  echo Cannot find app.py. Extract the full ZIP before running this file.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto :failed
)
.venv\Scripts\python.exe -m pip install Flask==3.1.3 Pillow==12.3.0
if errorlevel 1 goto :failed
echo.
echo Stock Studio is starting. Open http://localhost:5000 in Chrome.
echo Keep this window open while using the app. Press Ctrl+C to stop.
.venv\Scripts\python.exe -m flask --app app:create_app run --host 127.0.0.1 --port 5000
if errorlevel 1 goto :failed
exit /b 0
:failed
echo.
echo Startup failed. Install Python 3.12 or newer and check the error above.
pause
exit /b 1
