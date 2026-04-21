# Agent VID | Production Studio Launcher
# Windows PowerShell Script (Stable & Diagnostic)

Write-Host "============================" -ForegroundColor Cyan
Write-Host "Starting Agent VID Studio..." -ForegroundColor Cyan
Write-Host "============================" -ForegroundColor Cyan

# 1. Check Python
$pythonCheck = python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Python not found. Please install Python 3.10+." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit
}
Write-Host "Found $pythonCheck" -ForegroundColor Green

# 2. Setup Venv
if (-not (Test-Path "venv")) {
    Write-Host "Setting up private environment (first time)..."
    python -m venv venv
}

# 3. Install Dependencies
Write-Host "Verifying requirements..."
.\venv\Scripts\python.exe -m pip install -r requirements.txt --quiet

# 4. Playwright Check
Write-Host "Verifying rendering engine..."
.\venv\Scripts\playwright.exe install chromium

# 5. Launch
Write-Host "Launching Dashboard at http://localhost:8111..." -ForegroundColor Yellow
Start-Process "http://localhost:8111"
$env:PYTHONPATH = "."
.\venv\Scripts\python.exe vid_dashboard/main.py

Write-Host "Studio has closed."
Read-Host "Press Enter to close this window"
