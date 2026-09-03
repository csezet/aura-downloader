import os
import sys
import shutil
import subprocess
from pathlib import Path

# Ensure UTF-8 output on Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

def build():
    project_dir = Path(__file__).resolve().parent
    icon_path = project_dir / "assets" / "app_logo.ico"
    if not icon_path.exists():
        icon_path = project_dir / "assets" / "icon.ico"

    print("=" * 60)
    print("STARTING AURA DOWNLOADER STANDALONE EXE BUILD")
    print("=" * 60)

    # PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=AuraDownloader",
        "--noconsole",
        "--windowed",
        f"--icon={str(icon_path)}",
        "--add-data=assets;assets",
        "--add-data=tools;tools",
        "--hidden-import=PySide6.QtSvg",
        "--hidden-import=PySide6.QtMultimedia",
        "--hidden-import=PySide6.QtMultimediaWidgets",
        "--hidden-import=yt_dlp",
        "--hidden-import=requests",
        "--hidden-import=pefile",
        "--clean",
        "--noconfirm",
        "main.py"
    ]

    # Check if user requested single file
    if "--onefile" in sys.argv:
        cmd.append("--onefile")
        print("Build Mode: Single .EXE (--onefile)")
    else:
        cmd.append("--onedir")
        print("Build Mode: Application Folder (--onedir, ultra-fast launch)")

    print(f"Executing:\n{' '.join(cmd)}\n")
    res = subprocess.run(cmd, cwd=str(project_dir))

    if res.returncode == 0:
        dist_dir = project_dir / "dist" / "AuraDownloader"
        print("\n" + "=" * 60)
        print("BUILD COMPLETED SUCCESSFULLY!")
        print(f"Output directory:\n{dist_dir}")
        print("=" * 60)
    else:
        print("\nBuild failed.")
        sys.exit(res.returncode)

if __name__ == "__main__":
    build()
