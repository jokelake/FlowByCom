REM Agent VID Minimal Launcher
REM No-echo, no-nonsense debugging
CD /D "%~dp0"
ECHO Current Directory: %CD%
PYTHON --version
IF %ERRORLEVEL% NEQ 0 (
    ECHO Python not found in Path. Trying full path...
)
PYTHON vid_dashboard/main.py
PAUSE
