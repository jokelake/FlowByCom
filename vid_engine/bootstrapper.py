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
    Reads directly from requirements.txt for total parity.
    """
    print("==========================================")
    print("   Agent VID Production Studio: Setup   ")
    print("   [SYSTEM READY] v1.2.7 (Dynamic Sync) ")
    print("==========================================")
    
    req_file = "requirements.txt"
    if os.path.exists(req_file):
        with open(req_file, "r") as f:
            packages = [line.split(">")[0].split("=")[0].strip() for line in f if line.strip() and not line.startswith("#")]
        
        for package in packages:
            try:
                # Map requirement names to import names if necessary
                import_name = package.replace("-", "_")
                if package == "python-dotenv": import_name = "dotenv"
                
                __import__(import_name)
                print(f"[OK] {package} is ready.")
            except ImportError:
                print(f"[*] Missing {package}. Installing now...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                print(f"[OK] {package} installed successfuly.")
    else:
        print("[WARNING] requirements.txt not found. Skipping deep verify.")

    # Special check for Playwright browsers
    print("[*] Verifying rendering engine...")
    try:
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"])
    except Exception as e:
        print(f"[WARNING] Playwright browser setup failed: {e}")
        print("[!] Trying fallback: Manual playwright install...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
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
