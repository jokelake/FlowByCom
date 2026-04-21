import subprocess
import sys
import os

def clear_port(port):
    """Kills any process running on the specified port."""
    try:
        # Windows-specific command to find PID on port
        cmd = f'netstat -aon | findstr LISTENING | findstr :{port}'
        output = subprocess.check_output(cmd, shell=True).decode()
        for line in output.strip().split('\n'):
            pid = line.strip().split()[-1]
            print(f"[*] Closing old session on port {port} (PID: {pid})...")
            subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
    except Exception:
        pass # Port is likely already clear

def install_and_verify():
    """
    Agent VID Bootstrapper: 
    Ensures all dependencies are present before launching the studio.
    """
    required_packages = [
        "fastapi", 
        "uvicorn", 
        "playwright", 
        "pydantic", 
        "python-multipart", 
        "imageio-ffmpeg"
    ]
    
    print("==========================================")
    print("   Agent VID Production Studio: Setup   ")
    print("   [SYSTEM READY] v1.2.6 (Patch Active) ")
    print("==========================================")
    
    for package in required_packages:
        try:
            # Check if package is already installed
            __import__(package.replace("-", "_"))
            print(f"[OK] {package} is ready.")
        except ImportError:
            print(f"[*] Missing {package}. Installing now...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"[OK] {package} installed successfuly.")

    # Special check for Playwright browsers
    print("[*] Verifying rendering engine...")
    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
    
    print("\n[SUCCESS] Environment is ready. Launching Control Room...")

if __name__ == "__main__":
    try:
        # 1. Clear any old session stuck on Port 8111
        clear_port(8111)
        
        # 2. Verify dependencies
        install_and_verify()
        # After setup, launch the actual dashboard
        # Using subprocess.run to keep the window open for logs
        from vid_dashboard.main import app
        import uvicorn
        
        # Start the browser automatically
        import webbrowser
        webbrowser.open("http://localhost:8111")
        
        uvicorn.run(app, host="0.0.0.0", port=8111)
        
    except Exception as e:
        print(f"\n[CRITICAL ERROR] {e}")
        input("\nPress ENTER to close...")
