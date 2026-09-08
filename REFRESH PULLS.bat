@echo off
rem Quick mid-raid refresh: re-reads only OUR latest pulls (a few seconds), keeps the kill analysis and plan as they are.
cd /d "%~dp0"
set "PATH=%LOCALAPPDATA%\Programs\Python\Launcher;%PATH%"
py -3 run.py --pulls-only
if errorlevel 1 pause
