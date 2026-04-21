@echo off
title "Agent VID - Production Studio"

REM 1. Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found.
    pause
    exit /b
)

REM 2. Run the Studio (Bootstrapper handles everything)
set PYTHONPATH=.
python vid_engine/bootstrapper.py

if %errorlevel% neq 0 (
    echo [ERROR] Application crashed.
    pause
)
