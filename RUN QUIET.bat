@echo off
rem Quiet runner for the scheduled task: no pause, no browser, output logged to out\last-run.log
cd /d "%~dp0"
set "PATH=%LOCALAPPDATA%\Programs\Python\Launcher;%PATH%"
if not exist out mkdir out
py -3 run.py -v > "out\last-run.log" 2>&1
