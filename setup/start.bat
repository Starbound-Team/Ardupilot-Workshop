@echo off
rem Double-click to set up whatever is missing for the workshop and start the GCS (Windows).
powershell -NoProfile -ExecutionPolicy ByPass -File "%~dp0start.ps1" %*
pause
