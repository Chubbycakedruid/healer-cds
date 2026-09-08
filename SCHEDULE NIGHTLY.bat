@echo off
rem Registers a Windows scheduled task that runs the tool every night. Double-click once.
rem Change the time below (24h clock) if you want a different slot; raids usually end before 23:30.
set "WHEN=23:30"
schtasks /Create /F /SC DAILY /ST %WHEN% /TN "Healer Cooldown Planner" /TR "\"%~dp0RUN QUIET.bat\""
if errorlevel 1 (
  echo Could not create the scheduled task. Right-click this file and choose "Run as administrator", then try again.
) else (
  echo Done. The tool will now run every day at %WHEN% and refresh out\dashboard.html.
  echo To remove it later:  schtasks /Delete /TN "Healer Cooldown Planner" /F
)
pause
