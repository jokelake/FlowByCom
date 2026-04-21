@echo off
title Agent VID Studio - Launcher
cd /d "%~dp0"
echo [*] Checking for Patches...
git pull origin main
echo [*] Launching Studio...
set PYTHONPATH=.
venv\Scripts\python.exe vid_engine/bootstrapper.py
pause
