import asyncio
import json
import os
import random
import re
import signal
import csv
from datetime import datetime
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from vid_engine.parser import DEFAULT_SCHEMA

# Initialize environment variables
load_dotenv()

class GhostEngine:
    def __init__(self, storyboard_path, session_file="sessions/user_data.json", watch_mode=False, worker_id="1"):
        self.storyboard_path = storyboard_path
        self.session_file = session_file
        self.watch_mode = watch_mode
        self.worker_id = worker_id
        self.series_title = "Unknown" # v12.0.4
        self.phase = "Startup" # v12.0.4
        self.output_dir = "output"
        self.worker_dir = os.path.join(self.output_dir, "previews", f"w{worker_id}") # Isolated previews
        self.state_file = f"engine_state_{worker_id}.json" # Isolated state
        
        # Ensure worker folders exist
        os.makedirs(self.worker_dir, exist_ok=True)
        
        # Initialize with Centralized Schema
        self.SCHEMA = DEFAULT_SCHEMA.copy()
        self.ref_image_path = None
        self.creation_mode = "REGULAR"
        self.surveillance_enabled = True # v10.4.2
        self.last_thumbnail = ""
        
        # [v11.2.3] Ledger Synchronization State
        self.run_id = None
        self.start_time = None
        self.flow_project_url = "Initializing..."
        
        # [v12.0.8] Runtime state (always defined)
        self.is_running = False
        self.total_scenes = 0
        self.current_scene = 0
        
    def load_config(self, config_path):
        """Loads mapping choices and extra schema from the dashboard."""
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Handle the new nested run_config format
            choices = data.get("choices", {})
            extra = data.get("extra_schema", {})
            
            # Incorporate learned synonyms from the dashboard
            for field, key in extra.items():
                if field in self.SCHEMA and key not in self.SCHEMA[field]:
                    self.SCHEMA[field].append(key)
            
            self.ref_image_path = data.get("ref_image_path")
            self.creation_mode = data.get("creation_mode", "REGULAR") # v10.2 Mode Support
            self.surveillance_enabled = data.get("surveillance_enabled", True) # v10.4.2
            return choices
        
    def load_storyboard(self):
        with open(self.storyboard_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_field(self, scene, field_type):
        """Intelligently resolves a field from the scene dict based on known synonyms."""
        keys = self.SCHEMA.get(field_type, [])
        for k in keys:
            if k in scene and scene[k]:
                return scene[k]
        return ""

    def update_state(self, message, status="RUNNING", progress=None):
        """Updates the centralized JSON state file for the dashboard."""
        state = {
            "series_title": self.series_title, # v12.0.4
            "phase": self.phase, # v12.0.4
            "message": message,
            "status": status,
            "progress": progress if progress is not None else 0,
            "last_thumbnail": getattr(self, 'last_thumbnail', "")
        }
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f)
        
        # Update Ledger if finishing
        if status in ["COMPLETE", "STOPPED", "ERROR"]:
            self._update_ledger(status)
            
        print(f"[GhostEngine] {status}: {message}")

    def _update_ledger(self, status):
        """Atomically records or updates production metrics in the CSV ledger (v11.2.3)."""
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        ledger_path = os.path.join(output_dir, "production_ledger.csv")
        
        headers = ["run_id", "timestamp", "json_file", "series_title", "episode", "images", "videos", "ref_image", "flow_project_url", "status"]
        
        # Unique ID assignment
        if not self.run_id:
            self.run_id = f"RUN_{datetime.now().strftime('%y%m%d%H%M%S')}"

        # Extract metadata
        try:
            with open(self.storyboard_path, 'r', encoding='utf-8') as f:
                sb_data = json.load(f)
                series = sb_data.get("series_title", "Unknown Series")
                episode = sb_data.get("episode_number", "0")
                scenes = sb_data.get("storyboard", [])
        except:
            series, episode, scenes = "Error Loading", "0", []

        row = {
            "run_id": self.run_id,
            "timestamp": self.start_time.strftime("%Y-%m-%d %H:%M:%S") if self.start_time else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "json_file": os.path.basename(self.storyboard_path),
            "series_title": series,
            "episode": episode,
            "images": len(scenes),
            "videos": len(scenes),
            "ref_image": os.path.basename(getattr(self, 'ref_image_path', "")) or "None",
            "flow_project_url": getattr(self, 'flow_project_url', "Initializing..."),
            "status": status
        }

        # Atomically Load, Update, and Write back (v11.2.3)
        history = []
        found = False
        if os.path.isfile(ledger_path):
            try:
                with open(ledger_path, 'r', encoding='utf-8-sig', newline='') as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        if r.get("run_id") == self.run_id:
                            history.append(row)
                            found = True
                        else:
                            history.append(r)
            except Exception as e:
                print(f"[GhostEngine] Ledger Read Error: {e}")

        if not found:
            # If new run, append to end
            history.append(row)

        try:
            with open(ledger_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(history)
        except Exception as e:
            print(f"[GhostEngine] Ledger Write Error: {e}")

    async def type_stealth(self, page, selector, text, scene_num=1):
        """Types text with cognitive pauses and Thumbnail Guard. Skips click if thumbnail detected."""
        element = page.locator(selector).first

        # Split into words to simulate 'thought' blocks
        words = text.split(' ')
        for i, word in enumerate(words):
            for char in word:
                await element.type(char, delay=random.randint(20, 50)) # Fast typing
            
            await element.type(' ') # Space
            
            # Shorter, less frequent cognitive pauses
            if i % 10 == 0 and i > 0:
                await asyncio.sleep(random.uniform(0.3, 0.7))
            elif random.random() > 0.95:
                await asyncio.sleep(random.uniform(0.1, 0.3))

    async def move_mouse_arc(self, page, target_x, target_y, steps=15):
        """Simulates a human-like mouse movement in a slight arc to target coordinates."""
        # Removed brittle _impl access. Humans usually start moving from a rested position.
        start_x, start_y = (0, 0) 
        
        # Calculate a control point for a quadratic Bezier curve (random jitter)
        mid_x = (start_x + target_x) / 2 + random.randint(-50, 50)
        mid_y = (start_y + target_y) / 2 + random.randint(-50, 50)
        
        for i in range(1, steps + 1):
            t = i / steps
            # Quadratic Bezier formula
            x = (1-t)**2 * start_x + 2*(1-t)*t * mid_x + t**2 * target_x
            y = (1-t)**2 * start_y + 2*(1-t)*t * mid_y + t**2 * target_y
            await page.mouse.move(x, y)
            if i % 5 == 0: await asyncio.sleep(0.01)

    async def click_stealth(self, page, selector, anchor="center"):
        """Performs raw hardware-level mouse click. Supports strings, Locators, or (x,y) tuples."""
        target_x, target_y = (0, 0)
        
        if isinstance(selector, tuple):
            target_x, target_y = selector
            # Skip scroll_into_view for raw coordinates
        else:
            if isinstance(selector, str):
                element = page.locator(selector).first
            else:
                element = selector 
                
            await element.scroll_into_view_if_needed()
            box = await element.bounding_box()
            if not box: return False
            
            target_x = box['x'] + (box['width'] / 2) + random.randint(-4, 4)
            target_y = box['y'] + (box['height'] / 2) + random.randint(-4, 4)
            
        # 1. MOVE in an arc
        await self.move_mouse_arc(page, target_x, target_y)
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        # 2. CLICK with hold time (Human cadence)
        await page.mouse.move(target_x, target_y)
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.15))
        await page.mouse.up()
        await asyncio.sleep(random.uniform(0.3, 0.6))
        return True

    async def check_for_bot_detection(self, page):
        """Monitors for the 'Unusual Activity' or policy block messages."""
        error_indicators = [
            "unusal activity", 
            "visit the help center", 
            "content policy", 
            "third-party content",
            "allow uploads of minors"
        ]
        for indicator in error_indicators:
            error_loc = page.locator(f'div:has-text("{indicator}"), span:has-text("{indicator}")').first
            if await error_loc.is_visible():
                return await error_loc.inner_text()
        return None



    async def wait_for_asset_ready(self, page, index=0, timeout_sec=300):
        """Polls the Nth asset with initial stabilization wait (v12.2.3)."""
        self.update_state(f"Monitoring Gallery Item {index} for Rendering Finish...", "ANCHORING")
        
        # --- STABILIZATION BUFFER ---
        await asyncio.sleep(2.0) # Let the UI catch up with the upload/refresh
        
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < timeout_sec:
            try:
                # Target the nth child (0-indexed) of the virtuoso list
                asset = page.locator(f'[data-testid="virtuoso-item-list"] > div').nth(index)
                if not await asset.is_visible():
                    await asyncio.sleep(2)
                    continue
                
                content = await asset.inner_text()
                
                # --- PHASE 1: PROGRESS DETECTION (v12.2.4) ---
                # Check for percentage text overlay (e.g. "50%", "100%")
                # If percentage is present, the asset is ACTIVELY rendering and is NOT a failure.
                percentage_match = re.search(r'\d+\s?%', content)
                
                if percentage_match:
                    self.update_state(f"Asset {index} Rendering: {percentage_match.group(0)}", "ANCHORING")
                    await asyncio.sleep(5) # Poll every 5 seconds
                    continue

                # --- PHASE 2: FAILURE DETECTION ---
                # Only check for errors if no progress percentage is visible.
                # Includes specific policy/upload violation signals (v12.2.6).
                error_signals = [
                    "something went wrong", "fail to", "failed to", "error", 
                    "unable to generation", "unusual activity", "noted some",
                    "violate", "policies", "harmful content", "different prompt",
                    "different image", "do not allow", "minors", "violation"
                ]
                if any(sig in content.lower() for sig in error_signals):
                    self.update_state(f"Error Detected: Rendering Failure on Asset {index}.", "WARNING")
                    return f"ERROR_MSG:{content}"
                
                # --- PHASE 3: COMPLETION ---
                self.update_state(f"Asset {index} is READY.", "ANCHORING")
                return "READY"
                
            except Exception as e:
                self.update_state(f"Polling Warning: {e}")
                await asyncio.sleep(2)

        return "TIMEOUT"

    async def set_flow_options(self, page, mode="IMAGE"):
        """Ensures the correct Mode, Ratio, and Quantity are selected."""
        try:
            self.update_state(f"Setting {mode} configuration...", "CONFIG")
            # The settings button is named by the current model
            trigger = page.locator('button[id^="radix-"]:has-text("Banana"), button[id^="radix-"]:has-text("Video"), button[id^="radix-"]:has-text("Veo")').first
            await trigger.click()
            await page.wait_for_timeout(1000)

            # 1. Select Mode (Image or Video)
            mode_btn = page.locator(f'button[id$="-trigger-{mode}"]')
            await mode_btn.click()
            await page.wait_for_timeout(500)

            # 3. Select Ratio (9:16)
            ratio_btn = page.locator('button:has-text("9:16"), [role="tab"]:has-text("9:16")').first
            await ratio_btn.click()

            # 4. Select Quantity (x1)
            # Use specific role="tab" to avoid conflict with the main trigger text
            qty_btn = page.locator('[role="tab"]:has-text("x1")').first
            await qty_btn.click()

            # 5. Hard Close menu (using Escape to ensure poppers vanish)
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(1000)
            
            # Final check: if trigger still has 'expanded' state, click it again
            if await trigger.get_attribute("aria-expanded") == "true":
                await trigger.click()
                await page.wait_for_timeout(500)
                
            return True
        except Exception as e:
            self.update_state(f"Warning: Failed to set options: {e}")
            return False

    async def perform_reference_upload(self, page, image_path, scene_num=1):
        """Unified Evolutionary Handshake (v9.23): Links Portrait (Scene 1) or Result (Scene 2+)."""
        try:
            # 1. SCENE 1 SPECIAL CASE: Upload from Phase 0
            if scene_num == 1:
                if not image_path:
                    self.update_state("No starting reference provided. Proceeding with fresh generation.")
                    return True

                self.update_state("Injecting Starting Reference Image...", "ANCHORING")
                # Hyper-resilient selector for the '+' button (v9.25)
                ref_btn_sel = 'div:has(> div[role="textbox"]) button:has(i:text-is("add_2")), button:has(i:text-is("add_2")), button[aria-label*="Add"]'
                await self.click_stealth(page, ref_btn_sel)
                await asyncio.sleep(1.0)
                
                async with page.expect_file_chooser() as fc_info:
                    await self.click_stealth(page, 'i:text-is("upload")')
                file_chooser = await fc_info.value
                await file_chooser.set_files(os.path.abspath(image_path))
                
                # --- ZERO-TOUCH AUTO-LINK (Scene 1 Only) ---
                self.update_state("Waiting for Auto-Link Stability (Asset 0)...", "ANCHORING")
                status = await self.wait_for_asset_ready(page, index=0)
                if status != "READY":
                    self.update_state(f"Scene 1 Sync Failed: {status}.", "WARNING")
                    return False
                
                self.update_state("Scene 1 Auto-Link Secured.", "ANCHORING")
                return True

            # 2. EVOLUTIONARY LINKING: Use 'Most Left' (Scene 2+)
            await page.keyboard.press("Escape")
            await asyncio.sleep(1.0)

            # --- THE HANDSHAKE PROTOCOL RESTORED (v9.30) ---
            # Re-open Asset Picker to perform the definitive link
            # Scoped to the prompt area to avoid sidebar conflicts
            # ref_btn_sel = 'div:has(> div[role="textbox"]) button:has(i:text-is("add_2")), button:has(i:text-is("add_2"))'
            # await self.click_stealth(page, ref_btn_sel)
            # await asyncio.sleep(1.5)

            self.update_state(f"Linking Scene {scene_num} Anchor (Most Left)...", "ANCHORING")
            
            # BULLSEYE TARGETING: Target the IMAGE directly
            asset_item = page.locator('[data-testid="virtuoso-item-list"] > div:first-child img').first
            await asset_item.wait_for(state="visible", timeout=20000)
            await asset_item.hover()
            await asset_item.click(button="right")
            await asyncio.sleep(1.0)
            
            # Select "+ Add to prompt"
            add_option_sel = 'div[role="menuitem"]:has-text("Add to prompt"), [role="menuitem"] >> text=/Add to prompt/i'
            await self.click_stealth(page, add_option_sel)
            
            # THE COMMIT: Lock the link and clear the picker
            await page.keyboard.press("Escape")
            await asyncio.sleep(1.0)
            
            self.update_state(f"Scene {scene_num} Anchor Secured.", "ANCHORING")
            return True
        except Exception as e:
            self.update_state(f"Warning: Handshake failed: {e}")
            return False

    async def perform_motion_bridge_handshake(self, page, start_index=0, end_index=1, is_last=False):
        """Phase 2: Motion Bridge Handshake (v9.32). Links Start Image and End Image."""
        try:
            self.update_state("Initiating Motion Bridge Handshake...", "ANCHORING")
            
            # --- 1. ENSURE VIDEO MODE ---
            await self.set_flow_options(page, mode="VIDEO")
            await asyncio.sleep(random.uniform(1.0, 2.0))
            

            # --- 2. LINK START SLOT (With Self-Healing Retry) ---
            for attempt in range(3):
                self.update_state(f"Linking Start Slot (Gallery Index {start_index}) - Attempt {attempt+1}...", "ANCHORING")
                start_slot = page.locator('div[type="button"]').nth(0)
                
                if await start_slot.is_visible():
                    await self.click_stealth(page, start_slot)
                    break 
                elif attempt < 2:
                    self.update_state(f"Start button not visible. Refreshing page (Attempt {attempt+1}/2)...", "WARNING")
                    await page.reload()
                    await self.set_flow_options(page, mode="VIDEO")
                    await asyncio.sleep(3.0)
                else:
                    self.update_state("Can't find 'Start button' after 2 retries.", "ERROR")
                    raise Exception("[GhostEngine] Error: Can't find 'Start button'")

            await asyncio.sleep(random.uniform(1.5, 2.5)) # COGNITIVE JITTER
            
            # Select the Start Image (Precision Scoped)
            
            picker_box = page.locator('div[data-radix-popper-content-wrapper]')
            asset_item = picker_box.locator(f'[data-testid="virtuoso-item-list"] > div').nth(start_index).locator('img').first
            await asset_item.click()
            await asyncio.sleep(1.0)

            # --- 3. LINK END SLOT (If not last) ---
            if not is_last:
                for attempt in range(3):
                    self.update_state(f"Linking End Slot (Gallery Index {end_index}) - Attempt {attempt+1}...", "ANCHORING")
                    end_slot = page.locator('div[type="button"]').nth(0)
                    
                    if await end_slot.is_visible():
                        await self.click_stealth(page, end_slot)
                        break
                    elif attempt < 2:
                        self.update_state(f"End button not visible. Refreshing page...", "WARNING")
                        await page.reload()
                        await self.set_flow_options(page, mode="VIDEO")
                        await asyncio.sleep(3.0)
                    else:
                        self.update_state("Can't find 'End button' after 2 retries.", "ERROR")
                        raise Exception("[GhostEngine] Error: Can't find 'End button'")

                await asyncio.sleep(random.uniform(1.2, 2.8)) # COGNITIVE JITTER
                
                # Select the End Image (Precision Scoped)
                picker_box = page.locator('div[data-radix-popper-content-wrapper]')
                asset_item = picker_box.locator(f'[data-testid="virtuoso-item-list"] > div').nth(end_index).locator('img').first
                await asset_item.click()
                await asyncio.sleep(1.0)
            
            # THE COMMIT ---
            # await page.keyboard.press("Escape")
            await asyncio.sleep(1.0)
            
            self.update_state("Motion Bridge Secured.", "ANCHORING")
            return True
        except Exception as e:
            self.update_state(f"Warning: Motion Bridge failed: {e}")
            return False

    async def run(self, mapping_choices=None):
        """Main production loop handling both Image and Video phases."""
        self.is_running = True
        self.current_scene = 0
        self.start_time = datetime.now()
        self.run_id = f"RUN_{self.start_time.strftime('%y%m%d%H%M%S')}"
        self.flow_project_url = "Initializing..."
        
        # Initial Clock-In
        self._update_ledger("IN_PROGRESS")
        storyboard_data = self.load_storyboard()
        scenes = storyboard_data.get("storyboard", [])
        self.total_scenes = len(scenes)
        self.phase = "Initialization"
        self.update_state("Launching Workspace (Syncing Canvas)...", progress=0)
        
        async with async_playwright() as p:
            # [v12.0.8 FIX] Use the worker-specific mirrored profile (set via --profile arg)
            # self.session_file is bot_profile_1 or bot_profile_2, NOT the master bot_profile
            profile_dir = os.path.abspath(self.session_file)
            if not os.path.exists(profile_dir):
                self.update_state(f"ERROR: Profile not found at {profile_dir}. Run Sync first.")
                return

            # Randomize resolution to break fingerprinting
            width = 1280 + random.randint(-40, 40)
            height = 800 + random.randint(-40, 40)
            
            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                channel="chrome",
                headless=not self.watch_mode,
                viewport={'width': width, 'height': height},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                ignore_default_args=["--enable-automation"],
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-infobars"]
            )
            # --- INITIALIZE CONFIG ---
            # mapping_choices already contains the mappings, and self.ref_image_path is set in load_config
            print(f"[GhostEngine] Run initiated with character anchor: {getattr(self, 'ref_image_path', 'None')}")
            
            page = context.pages[0] if context.pages else await context.new_page()
            
            # --- STARTUP & GALLERY ESCAPE ---
            # --- STEP 1: Main Gallery -> New Project ---
            await page.goto("https://labs.google/fx/tools/flow", wait_until="networkidle", timeout=60000)
            self.update_state("Entering Google Flow Workspace...", "STARTUP")
            
            # Dismiss Overlapping Banners/Modals (Human-like patient clicks)
            for _ in range(2):
                try:
                    close_btn = page.locator('button:has(i:text-is("close")), button[aria-label="Close"], button[aria-label="Dismiss"]').first
                    if await close_btn.is_visible():
                        await self.click_stealth(page, close_btn)
                        await page.wait_for_timeout(1000)
                except: break

            # Force Project Entry
            if "/project/" not in page.url:
                new_project_btn = page.locator('button:has-text("New project")').first
                await new_project_btn.wait_for(state="visible", timeout=30000)
                self.update_state("Creating New Project Canvas...", "STARTUP")
                await self.click_stealth(page, 'button:has-text("New project")')
                await page.wait_for_url("**/project/**", timeout=45000)
                self.flow_project_url = page.url # Capture deep-link
                await page.wait_for_timeout(5000) # Let canvas settle

            # 3. Handle 'Loading Project' Splash Screen
            self.update_state("Waiting for Production Canvas to initialize...", "STARTUP")
            await page.wait_for_timeout(5000) # Initial beat
            
            # Wait for any "Loading" or "Initializing" indicators to vanish
            for _ in range(20): # Parallel timeout of ~100s
                loading = page.locator('div:has-text("Loading"), div:has-text("Initializing")').first
                if await loading.is_visible():
                    self.update_state("Project is still loading... Please wait.", "STARTUP")
                    await asyncio.sleep(5)
                else:
                    break

            # 4. Final wait and Focus for the prompt textbox
            try:
                textbox = page.locator("div[role='textbox']").first
                await textbox.wait_for(state="visible", timeout=15000)
                # Click to focus the canvas
                await textbox.click()
                self.flow_project_url = page.url 
                self._update_ledger("IN_PROGRESS")
                self.update_state("Workspace Fully Initialized!", "STARTUP")
                
                # Milestone: Workspace Ready (v12.0.7 Relocated)
                self.phase = "Image Generation"
                self.update_state("Ready. Starting Image Marathon (Phase 1)...", progress=5)
            except Exception as e:
                self.update_state("CRITICAL: Textbox not found. Try refreshing the page.")
                return

            # --- OPTION 2 WORKPLACE PLACEHOLDER (v10.2) ---
            if getattr(self, 'creation_mode', 'REGULAR') == "FASTER_VIDEO":
                self.update_state("INITIALIZING WORKPLACE: Faster Video Version (Evolutionary)...", "PREPARING")
                self.update_state("Placeholder: Evolutionary logic bridge initialized. Production parked.", "INFO")
                await asyncio.sleep(5)
                self.is_running = False
                return

            # --- PHASE 1: IMAGE MARATHON ---
            await self.set_flow_options(page, mode="IMAGE")
            
            # [NEW] Step 0: Upload Reference Anchor if provided
            ref_path = getattr(self, 'ref_image_path', None)
            if ref_path:
                full_ref_path = os.path.abspath(ref_path)
                print(f"[GhostEngine] Checking for Starting Reference: {full_ref_path}")
                if os.path.exists(full_ref_path):
                    await self.perform_reference_upload(page, full_ref_path)
                else:
                    print(f"[GhostEngine] Warning: Reference image not found at {full_ref_path}")
            else:
                print("[GhostEngine] No starting reference provided. Proceeding with fresh generation.")
            
            self.update_state("Starting Phase 1: Image Marathon", "IMAGE_PHASE", 0)

            for i, scene in enumerate(scenes):
                if not self.is_running: break
                
                image_prompt = self.get_field(scene, "image_prompt")
                if not image_prompt:
                    self.update_state(f"Skipping Scene {i+1} (No image prompt)", "IMAGE_PHASE")
                    continue

                # --- GENERATION SHIELD: 3-ATTEMPT RETRY LOOP (v12.2.2) ---
                for attempt in range(1, 4):
                    if not self.is_running: break
                    
                    self.update_state(f"Generating Scene {i+1} (Attempt {attempt}/3)...", "IMAGE_PHASE", i+1)
                    
                    if attempt > 1:
                        self.update_state(f"Recovery Refresh (Attempt {attempt})...", "WARNING")
                        await page.reload()
                        await asyncio.sleep(5.0) # Requested 5s wait
                        await self.set_flow_options(page, mode="IMAGE")

                    # --- THE EVOLUTIONARY HANDSHAKE ---
                    success = await self.perform_reference_upload(page, mapping_choices.get('ref_image_path'), scene_num=i+1)
                    if not success:
                        self.update_state(f"Warning: Handshake failed for Scene {i+1}. Recovering...", "WARNING")
                        continue # Trigger Recovery Refresh (v12.2.3)
                    
                    # Pre-Seating safe focus
                    textbox_sel = "div[role='textbox']"
                    await self.click_stealth(page, (750, 900)) 
                    
                    # Type and Trigger
                    await self.type_stealth(page, textbox_sel, image_prompt, scene_num=i+1)
                    await page.keyboard.press("Enter")
                    
                    # Wait for generation (v12.2.2)
                    status = await self.wait_for_asset_ready(page, index=0)
                    
                    if status == "READY":
                        self.update_state(f"Scene {i+1} 100% CLEAR.", "IMAGE_PHASE", i+1)
                        if self.surveillance_enabled:
                            asyncio.create_task(self.capture_asset_preview(page, index=0, scene_num=i+1, phase="IMAGE"))
                        break # Success!
                    
                    # If we hit here, it failed or timed out
                    if attempt == 3:
                        # Granular Error Mapping (v12.2.7)
                        err_text = status.lower() if status.startswith("ERROR_MSG:") else ""
                        mapped_status = "ERROR"
                        if "violate" in err_text or "harmful" in err_text:
                            mapped_status = "VIOLATE ERROR"
                        elif "allow upload" in err_text or "minors" in err_text:
                            mapped_status = "MINORS ERROR"
                        
                        self.update_state(f"CRITICAL FAILURE: Scene {i+1} failed after 3 attempts.", mapped_status)
                        import sys
                        sys.exit(1) # Hard fail for Sentinel
                    
                    self.update_state(f"Scene {i+1} {status}. Retrying with Refresh...", "WARNING")
                    await asyncio.sleep(2.0)
                
                # --- STABILIZATION PAUSE ---
                self.update_state("Stabilizing Gallery...", "IMAGE_PHASE")
                await asyncio.sleep(8.0) 

            # =========================================================================
            # PHASE 2: MOTION MARATHON (Cinematic Bridging)
            # =========================================================================
            if self.is_running:
                self.update_state("Entering Phase 2: Motion Marathon...", "VIDEO_PHASE")
                total_images = len(scenes)
                
                for i, scene in enumerate(scenes):
                    if not self.is_running: break
                    
                    video_prompt = self.get_field(scene, "video_prompt")
                    if not video_prompt:
                        self.update_state(f"Skipping Video {i+1} (No prompt)", "VIDEO_PHASE")
                        continue

                    # --- UNIVERSAL RENDER SENTINEL: 3-ATTEMPT RETRY LOOP (v12.2.2) ---
                    for attempt in range(1, 4):
                        if not self.is_running: break
                        
                        self.update_state(f"Bridging Motion Clip {i+1}/{total_images} (Attempt {attempt}/3)...", "VIDEO_PHASE", i+1)
                        
                        if attempt > 1:
                            self.update_state(f"Recovery Refresh (Attempt {attempt})...", "WARNING")
                            await page.reload()
                            await asyncio.sleep(5.0) # Requested 5s wait
                            await self.set_flow_options(page, mode="VIDEO")

                        # Trigger Generation (Hover + Click asset)
                        try:
                            # Re-verify flow options for video mode
                            await self.set_flow_options(page, mode="VIDEO")
                            
                            # Hover the nth image to reveal the "Video" button
                            asset = page.locator('[data-testid="virtuoso-item-list"] > div').nth(0)
                            await asset.hover()
                            await page.wait_for_timeout(500)
                            
                            # Click the video trigger overlay
                            await self.click_stealth(page, '[data-testid="asset-video-trigger"]')
                            await page.wait_for_timeout(1000)
                            
                            # Type prompt and Bridge
                            await self.type_stealth(page, 'textarea[placeholder*="video"]', video_prompt, scene_num=i+1)
                            await page.keyboard.press("Enter")
                            
                            # Wait for Rendering
                            status = await self.wait_for_asset_ready(page, index=0)
                            if status == "READY":
                                self.update_state(f"Video {i+1} 100% RENDERED.", "VIDEO_PHASE", i+1)
                                if self.surveillance_enabled:
                                    asyncio.create_task(self.capture_asset_preview(page, index=0, scene_num=i+1, phase="VIDEO"))
                                break
                            
                            # If we hit here, the wait itself failed (status is FAILED or TIMEOUT)
                            if attempt == 3:
                                # Granular Error Mapping (v12.2.7)
                                err_text = status.lower() if status.startswith("ERROR_MSG:") else ""
                                mapped_status = "ERROR"
                                if "violate" in err_text or "harmful" in err_text:
                                    mapped_status = "VIOLATE ERROR"
                                elif "allow upload" in err_text or "minors" in err_text:
                                    mapped_status = "MINORS ERROR"

                                self.update_state(f"CRITICAL FAILURE: Video {i+1} failed after 3 attempts.", mapped_status)
                                import sys
                                sys.exit(1) # Hard fail for Sentinel

                            self.update_state(f"Video {i+1} {status}. Retrying with Refresh...", "WARNING")
                            continue # Explicitly continue to retry (v12.2.3)
                        except Exception as e:
                            self.update_state(f"Motion Bridge Error: {e}. Retrying...", "WARNING")
                            await asyncio.sleep(2.0)
                    
                    await asyncio.sleep(5.0) # Break between bridges
            await context.close()
            self.is_running = False
            self.update_state("Production Complete!", "COMPLETE", self.total_scenes)

    async def capture_asset_preview(self, page, index=0, scene_num=1, phase="IMAGE"):
        """Captures a background preview of the READY asset (v10.4.3)."""
        try:
            # Ensure output directory exists before writing
            os.makedirs(os.path.join("output", "previews"), exist_ok=True)
            
            # Stabilization beat for UI rendering
            await asyncio.sleep(2.0)

            # Find the item in the virtuoso list (Anchor to newest)
            item = page.locator('[data-testid="virtuoso-item-list"] > div').nth(index)
            if not await item.is_visible():
                print(f"[GhostEngine] Surveillance Warning: Item at index {index} not visible.")
                return

            # Right click to open menu
            await item.click(button="right")
            await asyncio.sleep(1.0) # Wait for menu

            # Define destination
            ext = "webp" if phase == "IMAGE" else "mp4"
            filename = f"preview_{phase.lower()}_scene_{scene_num}.{ext}"
            filepath = os.path.join(self.worker_dir, filename) # Isolated to worker folder

            capture_success = False
            final_filename = filename

            # Trigger Download
            try:
                async with page.expect_download(timeout=5000) as download_info:
                    # Look for "Download" in the context menu
                    download_btn = page.get_by_text("Download", exact=False).first
                    if await download_btn.is_visible():
                        await download_btn.click()
                        download = await download_info.value
                        await download.save_as(filepath)
                        capture_success = True
            except:
                # Fallback to simple screenshot if download fails or menu is missing
                # [FIX v10.4.4] Screenshot doesn't support .webp or .mp4, pivot to .png
                print(f"[GhostEngine][W{self.worker_id}] Surveillance: Falling back to .png screenshot for Scene {scene_num}")
                final_filename = f"preview_{phase.lower()}_scene_{scene_num}.png"
                filepath = os.path.join(self.worker_dir, final_filename)
                
                await item.screenshot(path=filepath)
                capture_success = True
            
            if capture_success:
                # Update State (Isolated path for dashboard)
                self.last_thumbnail = f"/output/previews/w{self.worker_id}/{final_filename}"
                self.update_state(f"Visual Feed Updated: Scene {scene_num}", phase + "_PHASE", scene_num)
            
            # Close context menu if stuck (click away globally)
            await page.mouse.click(10, 10)
        except Exception as e:
            print(f"[GhostEngine] Surveillance Error: {e}")

    def stop(self):
        self.is_running = False
        self.update_state("STOPPED by User", "STOPPED")

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Ghost Engine v12.0 - Marathon Edition")
    parser.add_argument("storyboard", help="Path to JSON storyboard")
    parser.add_argument("config", help="Path to run config JSON")
    parser.add_argument("--watch", action="store_true", help="Run in visible head mode")
    parser.add_argument("--worker_id", default="1", help="Worker ID for state isolation")
    parser.add_argument("--profile", help="Custom Chrome profile path")
    parser.add_argument("--series_title", default="Untitled", help="Series metadata for dashboard") # v12.0.4
    
    args = parser.parse_args()
    
    # Use custom profile if provided (for session mirroring)
    session_file = args.profile if args.profile else "sessions/bot_profile"
    
    engine = GhostEngine(args.storyboard, session_file=session_file, watch_mode=args.watch, worker_id=args.worker_id)
    engine.series_title = args.series_title # v12.0.4 injection
    mapping_choices = engine.load_config(args.config)
    await engine.run(mapping_choices)

if __name__ == "__main__":
    asyncio.run(main())
