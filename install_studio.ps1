# Agent VID Studio - Automated Installer (v1.0.0)
# This script prepares the environment for other PCs.

$ProjectRepo = "https://github.com/jokelake/FlowByCom.git"
$VenvFolder = "venv"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "   Agent VID Studio: One-Click Setup    " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Check for Git
Write-Host "[*] Checking for Git..."
if (!(Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "[!] Git not found. Installing Git via winget..." -ForegroundColor Yellow
    winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to install Git. Please install it manually from https://git-scm.com/" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit
    }
    # Refresh PATH for the current session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
Write-Host "[OK] Git is ready." -ForegroundColor Green

# 2. Check for Python
Write-Host "[*] Checking for Python 3.10+..."
$pythonVer = & python --version 2>&1
if ($LASTEXITCODE -ne 0 -or $pythonVer -notmatch "Python 3\.(1[0-9])") {
    Write-Host "[!] Python 3.10+ not found. Installing Python 3.12 via winget..." -ForegroundColor Yellow
    winget install --id Python.Python.3.12 -e --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to install Python. Please install it manually from https://python.org/" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit
    }
    # Refresh PATH for the current session
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
Write-Host "[OK] $pythonVer is ready." -ForegroundColor Green

# 3. Setup Virtual Environment
Write-Host "[*] Setting up Virtual Environment (venv)..."
if (!(Test-Path $VenvFolder)) {
    python -m venv $VenvFolder
}
Write-Host "[OK] Environment isolated." -ForegroundColor Green

# 4. Git Initialization
Write-Host "[*] Linking to GitHub Repository..."
if (!(Test-Path ".git")) {
    git init
    git remote add origin $ProjectRepo
    Write-Host "[*] Fetching latest patches from origin..."
    git fetch
    # Try to pull, but don't fail if repo is empty or branch missing
    git pull origin main --allow-unrelated-histories
}
Write-Host "[OK] Repository linked." -ForegroundColor Green

# 5. Install Dependencies
Write-Host "[*] Installing Python dependencies (this may take a minute)..."
& "$VenvFolder\Scripts\python.exe" -m pip install --upgrade pip --quiet
& "$VenvFolder\Scripts\python.exe" -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[ERROR] Pip failed to install dependencies." -ForegroundColor Red
    Write-Host "[TIP] You are using Python 3.13, which is very new. If build errors persist, please install Python 3.12 instead." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit
}
Write-Host "[OK] Dependencies installed." -ForegroundColor Green

# 6. Playwright Setup
Write-Host "[*] Preparing rendering engine (Chromium)..."
$PlaywrightPath = "$VenvFolder\Scripts\playwright.exe"
if (Test-Path $PlaywrightPath) {
    Write-Host "[*] Installing Chromium and system dependencies..."
    & "$VenvFolder\Scripts\python.exe" -m playwright install --with-deps chromium
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Playwright browser installation failed." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit
    }
    
    # Verification Check
    Write-Host "[*] Verifying Playwright integration..."
    & "$VenvFolder\Scripts\python.exe" -c "import playwright; print('Playwright Library: OK')"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Playwright library is installed but not working. This usually means a dependency is missing." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit
    }
} else {
    Write-Host "[ERROR] Playwright not found in venv. Dependencies probably didn't install correctly." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit
}
Write-Host "[OK] Rendering engine ready." -ForegroundColor Green

# 7. Create Launcher and Desktop Shortcut
Write-Host "[*] Creating Desktop Shortcut..."
$LauncherContent = @"
@echo off
title Agent VID Studio - Launcher
cd /d "%~dp0"
echo [*] Checking for Patches...
git pull origin main
echo [*] Launching Studio...
set PYTHONPATH=.
venv\Scripts\python.exe vid_engine/bootstrapper.py
pause
"@

$LauncherContent | Out-File -FilePath "launcher.bat" -Encoding ASCII

# Create Desktop Shortcut using COM
try {
    $WshShell = New-Object -ComObject WScript.Shell
    $ShortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "Agent VID Studio.lnk"
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = "$PWD\launcher.bat"
    $Shortcut.WorkingDirectory = "$PWD"
    $Shortcut.IconLocation = "powershell.exe" # Simple icon placeholder
    $Shortcut.Save()
    Write-Host "[OK] Shortcut created on Desktop." -ForegroundColor Green
} catch {
    Write-Host "[!] Could not create Desktop shortcut automatically." -ForegroundColor Yellow
}

Write-Host "`n==========================================" -ForegroundColor Cyan
Write-Host "   SETUP COMPLETE!                        " -ForegroundColor Cyan
Write-Host "   Use 'launcher.bat' or the Desktop icon " -ForegroundColor Cyan
Write-Host "   to start the studio.                   " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Read-Host "Press Enter to finish"
