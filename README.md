# 🎬 Agent VID Studio

> **"One-click cinematic story generation via Google Labs Flow."**

Agent VID Studio is an automated production suite designed to take JSON storyboards and turn them into high-quality cinematic videos using Gemini and Google Labs Flow.

---

## 🚀 Quick Start (Installation)

If you are setting this up on a new PC, follow these steps:

1.  **Run the Installer**: 
    Right-click `install_studio.ps1` and select **"Run with PowerShell"**.
    *(This will automatically install Python, Git, and all necessary dependencies.)*
2.  **Launch the Studio**:
    Double-click the **Agent VID Studio** icon on your Desktop or run `launcher.bat`.

---

## 🛠️ How to Use

### 1. Upload Storyboard
Navigate to the **Dashboard** (usually opens automatically at `http://localhost:8111`). Drag and drop your Gemini-generated JSON storyboard into the upload area.

### 2. Character Mapping
Once uploaded, the system will extract characters. Map them to your existing casting ledger or create new ones.

### 3. Start Production
Click **"Start Marathon"**. The studio will:
- Open a "Ghost Engine" (hidden browser).
- Log in to your Flow account.
- Automate the image and video generation for every scene.

---

## 🔄 The "Patch Engine" (Updating)

This project is built for easy updates. Every time you run `launcher.bat`, the program checks for **patches** from the main server (GitHub).

- **To update**: Simply close the program and run `launcher.bat` again. It will automatically `git pull` the latest features and bug fixes.
- **To contribute**: Push your changes to the `main` branch, and all other users will receive the update the next time they launch!

---

## 📂 Project Structure

- `vid_dashboard/`: FastAPI backend and React-based control room.
- `vid_engine/`: The "Ghost Engine" automation logic.
- `uploads/`: Temporary storage for uploaded storyboards.
- `output/`: Where your finished cinematic assets are saved.

---

## ⚖️ Technical Requirements

- **Python**: 3.11 or 3.12 (Recommended).
- **Git**: Required for the auto-patch engine.
- **Browser**: Playwright Chromium (Installed automatically).

---

*Built with ❤️ by Agent VID.*
