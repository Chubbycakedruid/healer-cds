@echo off
setlocal
cd /d "%~dp0"
title Healer Cooldown Planner

set "PATH=%LOCALAPPDATA%\Programs\Python\Launcher;%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"

py -3 --version >nul 2>&1
if errorlevel 1 (
  echo Python is not installed yet. Installing it now, this takes a minute or two...
  echo (If Windows asks for permission, click Yes.)
  winget install -e --id Python.Python.3.12 --scope user --silent --accept-source-agreements --accept-package-agreements
  set "PATH=%LOCALAPPDATA%\Programs\Python\Launcher;%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
  py -3 --version >nul 2>&1
  if errorlevel 1 (
    echo.
    echo Could not install Python automatically. Please close this window, install it from
    echo https://www.python.org/downloads/  (tick "Add python.exe to PATH"^), then run this file again.
    pause
    exit /b 1
  )
)

echo Checking dependencies...
py -3 -m pip install -q -r requirements.txt

echo.
echo Pulling logs from Warcraft Logs and analysing. This takes a minute or two the first time.
echo.
py -3 run.py -v
if errorlevel 1 (
  echo.
  echo Something went wrong. Copy the text above and send it to Claude.
  pause
  exit /b 1
)

echo.
echo Done. Opening the dashboard...
start "" "out\dashboard.html"
pause
