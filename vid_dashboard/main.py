from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import sys
import subprocess
import csv
import json
import shutil
import threading
import time
import logging

# --- LOG NOISE SUPPRESSION (v12.1.0) ---
class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return msg.find("/status") == -1 and msg.find("/queue") == -1

# Silence the frequent polling logs in uvicorn
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

# Ensure the root 'vid_studio' directory is in the path for engine imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vid_engine.parser import StoryboardParser
from vid_engine.mapper import StoryboardMapper

app = FastAPI()

# Mount System (v10.4.2)
UPLOAD_DIR = "uploads"
STORYBOARD_DIR = os.path.join(UPLOAD_DIR, "storyboards")
OUTPUT_DIR = "output"
PREVIEWS_DIR = os.path.join(OUTPUT_DIR, "previews")

for d in [UPLOAD_DIR, STORYBOARD_DIR, OUTPUT_DIR, PREVIEWS_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

# Startup Ledger Cleanup (v12.2.8)
# If the server was shut down abruptly, mark any stuck 'IN_PROGRESS' items as 'ERROR (Crashed)'.
ledger_path = os.path.join(OUTPUT_DIR, "production_ledger.csv")
if os.path.exists(ledger_path):
    try:
        rows = []
        with open(ledger_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            if headers:
                for row in reader:
                    st = row.get("status", "")
                    if "IN_PROGRESS" in st or st == "RUNNING":
                        row["status"] = "ERROR (Crashed)"
                    rows.append(row)
        with open(ledger_path, "w", encoding="utf-8-sig", newline="") as f:
            if headers:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)
    except Exception as e:
        print(f"[Backend] Startup ledger cleanup error: {e}")

MARATHON_QUEUE_FILE = "marathon_queue.json"
if not os.path.exists(MARATHON_QUEUE_FILE):
    with open(MARATHON_QUEUE_FILE, "w") as f:
        json.dump([], f)

queue_lock = threading.Lock() # Thread safety for JSON access

app.mount("/static", StaticFiles(directory="vid_dashboard/static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/output", StaticFiles(directory="output"), name="output")

@app.get("/")
async def read_index():
    return FileResponse('vid_dashboard/static/index.html')

# State (v12.0.4 Marathon Edition)
production_workers = {"1": None, "2": None}
worker_lane_locked = {"1": False, "2": False} # v12.0.4 Lane Control
MARATHON_QUEUE_FILE = "marathon_queue.json"
MARATHON_CONFIG_DIR = "run_configs"
os.makedirs(MARATHON_CONFIG_DIR, exist_ok=True)

if not os.path.exists(MARATHON_QUEUE_FILE):
    with open(MARATHON_QUEUE_FILE, "w") as f:
        json.dump([], f)

class MappingChoice(BaseModel):
    storyboard_path: str
    choices: dict # { "Mali": "Series Name" }
    watch_mode: bool = False

@app.get("/series")
def get_series():
    """Returns a list of all existing series from the ledger."""
    with open("vid_engine/casting_ledger.json", "r", encoding="utf-8") as f:
        ledger = json.load(f)
    return list(ledger["series"].keys())

@app.post("/upload-ref")
async def upload_reference_image(file: UploadFile = File(...)):
    """Uploads a starting reference image and returns the ABSOLUTE path."""
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        
    file_name = f"ref_{file.filename}"
    file_path = os.path.abspath(os.path.join(UPLOAD_DIR, file_name))
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    print(f"[Dashboard] Ref Image Saved to: {file_path}")
    return {"ref_image_path": file_path}

@app.post("/analyze")
async def analyze_storyboard(file: UploadFile = File(...)):
    """Uploads JSON, verifies compatibility, and suggests character mappings (v12.2.1)."""
    # Force persistent storage with timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = os.path.join(STORYBOARD_DIR, safe_filename)
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
    
    parser = StoryboardParser(file_path)
    report = parser.verify_compatibility()
    extracted_names = parser.extract_characters()
    
    mapper = StoryboardMapper()
    suggestions = mapper.get_suggestions(extracted_names)
    
    # Extract total scene count for progress bars
    with open(file_path, "r", encoding="utf-8") as f:
        sb_data = json.load(f)
        total_scenes = len(sb_data.get("storyboard", []))
        if total_scenes == 0:
            total_scenes = len(sb_data.get("scenes", []))

    return {
        "storyboard_path": file_path,
        "extracted_characters": extracted_names,
        "mapping_suggestions": suggestions,
        "compatibility_report": report,
        "total_scenes": total_scenes
    }

@app.get("/storyboard/{filename}")
def get_storyboard_content(filename: str):
    """Returns the JSON content for the fast-previewer (v12.2.1)."""
    file_path = os.path.join(STORYBOARD_DIR, filename)
    if not os.path.exists(file_path):
        return {"error": "File not found"}
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

class ProductionConfig(BaseModel):
    storyboard_path: str
    choices: dict
    watch_mode: bool = False
    extra_schema: dict = {}
    ref1_path: str = None
    ref2_path: str = None
    creation_mode: str = "REGULAR" 
    surveillance_enabled: bool = True # v10.4.2

@app.post("/start")
def start_production(config: ProductionConfig, worker_id: str = "1"):
    """Starts a specific worker manually (Internal use or direct trigger)."""
    global production_workers
    
    # Extract Series Title for telemetry (v12.0.4)
    series_title = "Untitled"
    try:
        with open(config.storyboard_path, 'r', encoding='utf-8') as f:
            sb = json.load(f)
            series_title = sb.get("series_title", "Untitled")
    except: pass

    # Save worker-specific config
    config_path = os.path.join(MARATHON_CONFIG_DIR, f"config_w{worker_id}.json")
    run_config = {
        "choices": config.choices,
        "extra_schema": config.extra_schema,
        "ref1_path": config.ref1_path,
        "ref2_path": config.ref2_path,
        "creation_mode": config.creation_mode,
        "surveillance_enabled": config.surveillance_enabled
    }
    with open(config_path, "w") as f:
        json.dump(run_config, f)
        
    # Handle Profile Isolation Mirroring (v12.0.4 Fix for WinError 32)
    master_profile = os.path.abspath(os.path.join("sessions", "bot_profile"))
    target_profile = os.path.abspath(os.path.join("sessions", f"bot_profile_{worker_id}"))
    
    print(f"[Backend] Worker {worker_id}: Preparing mirrored session for '{series_title}'...")
    
    # [v12.0.8] Robust file-by-file mirroring — skips individually locked files
    SKIP_PATTERNS = {'.lock', 'Singleton', '-journal', 'Cookies-journal', 'Safe Browsing'}
    errors = []
    try:
        os.makedirs(target_profile, exist_ok=True)
        for root, dirs, files in os.walk(master_profile):
            rel_root = os.path.relpath(root, master_profile)
            dest_root = os.path.join(target_profile, rel_root)
            os.makedirs(dest_root, exist_ok=True)
            for fname in files:
                if any(p in fname for p in SKIP_PATTERNS):
                    continue
                src = os.path.join(root, fname)
                dst = os.path.join(dest_root, fname)
                try:
                    shutil.copy2(src, dst)
                except Exception as e:
                    errors.append(fname)  # Log name only, skip silently
        if errors:
            print(f"[Backend] Mirroring: Skipped {len(errors)} locked file(s): {errors[:5]}")
        else:
            print(f"[Backend] Mirroring: Clean copy to {target_profile}")
    except Exception as e:
        print(f"[Backend] Mirroring Error: {e} (Continuing with existing profile)")

    cmd = [
        sys.executable, "vid_engine/ghost_engine.py", 
        config.storyboard_path, 
        config_path,
        "--worker_id", worker_id,
        "--profile", target_profile,
        "--series_title", series_title
    ]
    if config.watch_mode:
        cmd.append("--watch")
        
    production_workers[worker_id] = subprocess.Popen(cmd)
    return {"status": "Production Started", "worker": worker_id, "pid": production_workers[worker_id].pid}

@app.post("/worker/action")
def worker_action(worker_id: str, action: str):
    """Handles manual lane overrides (Stop/Resume/Terminate) (v12.0.9)."""
    global production_workers, worker_lane_locked
    
    if action == "stop":
        # Kill the task and LOCK the lane (worker waits for manual Resume)
        worker_lane_locked[worker_id] = True
        proc = production_workers.get(worker_id)
        if proc and proc.poll() is None:
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)])
                production_workers[worker_id] = None
            except: pass
        
        # Mark the job as PAUSED so it doesn't get picked up by another worker
        with queue_lock:
            with open(MARATHON_QUEUE_FILE, "r") as f:
                queue = json.load(f)
            for job in queue:
                if job["status"] == "PROCESSING" and job.get("worker") == worker_id:
                    job["status"] = "PAUSED"
                    # Keep job["worker"] = worker_id so it resumes on the same lane
                    break
            with open(MARATHON_QUEUE_FILE, "w") as f:
                json.dump(queue, f, indent=4)
                
        return {"status": "LOCKED", "worker": worker_id}

    elif action == "terminate":
        # Kill the task, mark job FAILED, unlock lane for next job
        proc = production_workers.get(worker_id)
        if proc and proc.poll() is None:
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)])
            except: pass
        production_workers[worker_id] = None
        worker_lane_locked[worker_id] = False  # Unlock immediately

        # Mark the job as FAILED in the queue
        failed_job_id = None
        with queue_lock:
            with open(MARATHON_QUEUE_FILE, "r") as f:
                queue = json.load(f)
            for job in queue:
                if job["status"] in ("PROCESSING", "PENDING") and job.get("worker") == worker_id:
                    job["status"] = "FAILED"
                    job["failed_at"] = time.strftime("%Y-%m-%d %H:%M")
                    failed_job_id = job.get("id")
                    break
            with open(MARATHON_QUEUE_FILE, "w") as f:
                json.dump(queue, f, indent=4)

        # Update ledger CSV: find matching run by storyboard filename and mark FAIL
        ledger_path = os.path.join(OUTPUT_DIR, "production_ledger.csv")
        if os.path.exists(ledger_path):
            try:
                rows = []
                with open(ledger_path, "r", encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    headers = reader.fieldnames
                    for row in reader:
                        if row.get("status") and ("IN_PROGRESS" in row.get("status") or row.get("status") == "RUNNING") and row not in rows:
                            row["status"] = "FAIL"
                        rows.append(row)
                with open(ledger_path, "w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    writer.writeheader()
                    writer.writerows(rows)
                print(f"[Backend] Worker {worker_id} TERMINATED. Ledger updated to FAIL.")
            except Exception as e:
                print(f"[Backend] Ledger update error on terminate: {e}")

        return {"status": "TERMINATED", "worker": worker_id}
        
    elif action == "resume":
        # Change the PAUSED job back to PENDING so the sentinel can pick it up
        with queue_lock:
            with open(MARATHON_QUEUE_FILE, "r") as f:
                queue = json.load(f)
            for job in queue:
                if job["status"] == "PAUSED" and job.get("worker") == worker_id:
                    job["status"] = "PENDING"
                    break
            with open(MARATHON_QUEUE_FILE, "w") as f:
                json.dump(queue, f, indent=4)
                
        worker_lane_locked[worker_id] = False
        return {"status": "ACTIVE", "worker": worker_id}

@app.post("/stop")
def stop_production():
    """Abort All workers globally."""
    for wid in ["1", "2"]:
        worker_action(wid, "stop")
    return {"status": "ALL_STOPPED"}

# --- QUEUE ENDPOINTS ---
@app.post("/queue/add")
def add_to_queue(config: ProductionConfig):
    """Stages a job in the Marathon Queue."""
    with queue_lock:
        with open(MARATHON_QUEUE_FILE, "r") as f:
            queue = json.load(f)
        
        job_id = f"JOB_{int(time.time())}"
        job = {
            "id": job_id,
            "config": config.dict(),
            "status": "PENDING",
            "added_at": time.ctime()
        }
        queue.append(job)
        
        with open(MARATHON_QUEUE_FILE, "w") as f:
            json.dump(queue, f, indent=4)
    
    return {"status": "STAGED", "job_id": job_id}

@app.post("/queue/remove")
def remove_from_queue(job_id: str):
    """Deletes a specific job from the queue (v12.0.9)."""
    with queue_lock:
        with open(MARATHON_QUEUE_FILE, "r") as f:
            queue = json.load(f)
        new_queue = [j for j in queue if j["id"] != job_id]
        with open(MARATHON_QUEUE_FILE, "w") as f:
            json.dump(new_queue, f, indent=4)
    return {"status": "REMOVED"}

@app.get("/queue")
def get_queue():
    with queue_lock:
        with open(MARATHON_QUEUE_FILE, "r") as f:
            return json.load(f)

@app.post("/queue/clear")
def clear_queue():
    """Wipes all PENDING jobs from the queue (v12.0.9)."""
    with queue_lock:
        with open(MARATHON_QUEUE_FILE, "r") as f:
            queue = json.load(f)
        new_queue = [j for j in queue if j["status"] != "PENDING"]
        with open(MARATHON_QUEUE_FILE, "w") as f:
            json.dump(new_queue, f, indent=4)
    return {"status": "PENDING_CLEARED"}

@app.post("/queue/clear-failed")
def clear_failed_jobs():
    """Wipes all FAILED jobs from the queue history (v12.0.9)."""
    with queue_lock:
        with open(MARATHON_QUEUE_FILE, "r") as f:
            queue = json.load(f)
        new_queue = [j for j in queue if j["status"] != "FAILED"]
        with open(MARATHON_QUEUE_FILE, "w") as f:
            json.dump(new_queue, f, indent=4)
    return {"status": "FAILED_CLEARED"}

@app.get("/status")
def get_status():
    """Aggregates all worker states for the dashboard monitor (v12.1.5)."""
    states = {}
    for wid in ["1", "2"]:
        state_file = f"engine_state_{wid}.json"
        is_active = production_workers.get(wid) is not None
        
        # If no process is running, force it to IDLE regardless of what the old file says
        if not is_active and not worker_lane_locked[wid]:
             states[wid] = {"status": "IDLE", "message": "Ready", "locked": False}
             # Also try to kill the file if it somehow survived
             if os.path.exists(state_file):
                 try: os.remove(state_file)
                 except: pass
        elif os.path.exists(state_file):
            with open(state_file, "r") as f:
                state = json.load(f)
                state["locked"] = worker_lane_locked[wid] # Inject lock state
                states[wid] = state
        else:
            states[wid] = {"status": "IDLE", "message": "Ready", "locked": worker_lane_locked[wid]}
    
    return {
        "workers": states,
        "queue_count": len(get_queue())
    }

# --- MARATHON SENTINEL (v12.0.4) ---
def queue_sentinel():
    """Background loop that feeds workers from the queue (v12.0.9)."""
    while True:
        try:
            with queue_lock:
                with open(MARATHON_QUEUE_FILE, "r") as f:
                    queue = json.load(f)
            
            if not queue:
                time.sleep(5)
                continue

            queue_dirty = False

            # --- CHECK FOR COMPLETED WORKERS ---
            for wid in ["1", "2"]:
                proc = production_workers.get(wid)
                if proc and proc.poll() is not None:
                    # Process finished — mark its job COMPLETE or FAILED
                    state_file = f"engine_state_{wid}.json"
                    final_status = "COMPLETE" if proc.returncode == 0 else "FAILED"
                    
                    # --- GRANULAR ERROR OVERRIDE (v12.2.7) ---
                    if proc.returncode != 0 and os.path.exists(state_file):
                        try:
                            with open(state_file, "r") as f:
                                last_state = json.load(f)
                                reported_status = last_state.get("status")
                                if "ERROR" in reported_status:
                                    final_status = reported_status
                        except: pass

                    for job in queue:
                        if job.get("status") == "PROCESSING" and job.get("worker") == wid:
                            job["status"] = final_status
                            if final_status == "COMPLETE":
                                job["completed_at"] = time.strftime("%Y-%m-%d %H:%M")
                            else:
                                job["failed_at"] = time.strftime("%Y-%m-%d %H:%M")
                            queue_dirty = True
                            print(f"[Sentinel] Worker {wid} finished (rc={proc.returncode}). Job → {final_status}")
                    production_workers[wid] = None  # Free the slot
                    
                    # Cleanup local state file so dashboard resets to IDLE UI (v12.1.2)
                    state_file = f"engine_state_{wid}.json"
                    if os.path.exists(state_file):
                        try: os.remove(state_file)
                        except: pass

            # --- ASSIGN PENDING JOBS TO FREE WORKERS ---
            for wid in ["1", "2"]:
                if worker_lane_locked[wid]:
                    continue

                if not production_workers[wid] or production_workers[wid].poll() is not None:
                    # Only pick up jobs with no worker assigned, or jobs specifically assigned to this worker (resumed jobs)
                    pending_idx = next((i for i, j in enumerate(queue) if j["status"] == "PENDING" and (not j.get("worker") or j.get("worker") == wid)), None)
                    
                    if pending_idx is not None:
                        job = queue[pending_idx]
                        print(f"[Sentinel] Worker {wid} picking up '{job['config'].get('storyboard_path')}'...")
                        job["status"] = "PROCESSING"
                        job["worker"] = wid
                        queue_dirty = True

                        config_data = ProductionConfig(**job["config"])
                        start_production(config_data, worker_id=wid)

            if queue_dirty:
                with queue_lock:
                    with open(MARATHON_QUEUE_FILE, "w") as f:
                        json.dump(queue, f, indent=4)
                        
        except Exception as e:
            print(f"[Sentinel] Error: {e}")
        
        time.sleep(5)

# Start Sentinel in background thread
threading.Thread(target=queue_sentinel, daemon=True).start()

@app.get("/ledger")
def get_ledger():
    """Retrieves the production history from the CSV ledger (v11.2)."""
    ledger_path = os.path.join(OUTPUT_DIR, "production_ledger.csv")
    if not os.path.exists(ledger_path):
        return []
        
    history = []
    try:
        with open(ledger_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                history.append(row)
    except Exception as e:
        print(f"[Backend] Ledger Error: {e}")
        return []
        
    # Return most recent first
    return history[::-1]

@app.post("/sync")
def sync_account():
    """Launches the visible session_sync.py so the user can log in manually."""
    # We use a visible browser here so the user can handle the login
    cmd = [sys.executable, "vid_engine/session_sync.py"]
    subprocess.Popen(cmd)
    return {"status": "SYNC_STARTED", "message": "Login window opened. Please log in and close it when done."}

@app.get("/sync-status")
def get_sync_status():
    """Checks if the session file exists, meaning the account is linked."""
    exists = os.path.exists("sessions/user_data.json")
    return {"connected": exists}

# Serve the frontend
# app.mount("/", StaticFiles(directory="vid_studio/vid_dashboard/static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8111)
