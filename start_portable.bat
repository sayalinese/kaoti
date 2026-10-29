@echo off
cd /d "%~dp0"
"%~dp0python_runtime\python.exe" launcher.py %*
if errorlevel 1 pause
