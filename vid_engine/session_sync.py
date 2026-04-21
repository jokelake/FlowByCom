import asyncio
import os
from playwright.async_api import async_playwright

# Configuration
SESSION_DIR = "sessions"
SESSION_FILE = os.path.join(SESSION_DIR, "user_data.json")

async def run_session_sync():
    """
    Opens a visible browser for the user to log into Google Labs Flow.
    Once the user is logged in and ready, they can close the browser or press Enter
    in the terminal to save the session.
    """
    if not os.path.exists(SESSION_DIR):
        os.makedirs(SESSION_DIR)

    async with async_playwright() as p:
        print("\n" + "="*50)
        print("ACTION REQUIRED:")
        print("1. A visible Chrome window will open.")
        print("2. Log in, handle 2FA, and reach the Flow Workspace.")
        print("3. RETURN HERE and press [ENTER] to lock in the profile.")
        print("="*50 + "\n")
        
        # Use Persistent Context (The folder is the "Brain")
        # Use absolute path to ensure Windows locks the correct directory
        profile_dir = os.path.abspath(os.path.join(SESSION_DIR, "bot_profile"))
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            channel="chrome", 
            headless=False,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Navigate to Flow
        await page.goto("https://labs.google/fx/tools/flow")
        
        # Block until user is ready
        await asyncio.to_thread(input, ">>> Press ENTER once you reach the Flow Dashboard...")
        
        print(f"\n[SUCCESS] IDENTITY PROFILE LOCKED in: {SESSION_DIR}/bot_profile")
        await context.close()

if __name__ == "__main__":
    asyncio.run(run_session_sync())
