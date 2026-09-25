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
        "--hidden-import=PySide6.QtSvg",
        "--hidden-import=PySide6.QtMultimedia",
        "--hidden-import=PySide6.QtMultimediaWidgets",
        "--hidden-import=yt_dlp",
        "--hidden-import=requests",
        "--hidden-import=pefile",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--clean",
        "--noconfirm",
    ]

    if (project_dir / "assets").exists():
        cmd.append("--add-data=assets;assets")
    
    tools_dir = project_dir / "tools"
    has_bundled_ffmpeg = (tools_dir / "ffmpeg.exe").exists() and (tools_dir / "ffprobe.exe").exists()
    if has_bundled_ffmpeg:
        print("Bundled Tools: tools/ffmpeg.exe and tools/ffprobe.exe detected! Packaging into distribution.")
        cmd.append("--add-data=tools;tools")
    else:
        print("=" * 60)
        print("⚠️ ВНИМАНИЕ: tools/ffmpeg.exe или tools/ffprobe.exe не найдены.")
        print("Готовая сборка Aura Downloader потребует наличия FFmpeg в системном PATH")
        print("или ручного копирования ffmpeg.exe и ffprobe.exe в папку tools/.")
        print("=" * 60)
        if tools_dir.exists():
            cmd.append("--add-data=tools;tools")

    cmd.append("main.py")

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
