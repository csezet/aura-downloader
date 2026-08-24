import os
import sys
import subprocess
import ctypes
from pathlib import Path
import win32com.client

SHCNE_ASSOCCHANGED = 0x08000000
SHCNF_IDLIST = 0x0000
SHCNF_FLUSH = 0x1000

def refresh_windows_icon_cache():
    try:
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_FLUSH, 0, 0)
    except Exception as e:
        print(f"Icon cache notification error: {e}")

def create_shortcuts():
    project_dir = Path(__file__).resolve().parent
    main_script = project_dir / "main.pyw"
    icon_path = project_dir / "assets" / "app_logo.ico"

    python_dir = Path(sys.executable).parent
    pythonw_exe = python_dir / "pythonw.exe"
    if not pythonw_exe.exists():
        pythonw_exe = Path(sys.executable)

    # Detect user's real primary desktop
    desktop_dirs = []
    try:
        ps_cmd = "[Environment]::GetFolderPath('Desktop')"
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
        p = res.stdout.strip()
        if p and os.path.exists(p):
            desktop_dirs.append(Path(p))
    except Exception:
        pass

    user_home = Path(os.environ.get("USERPROFILE", "C:/Users/denis"))
    candidates = [
        user_home / "OneDrive" / "Рабочий стол",
        user_home / "OneDrive" / "Desktop",
        user_home / "Desktop",
    ]
    for c in candidates:
        if c.exists() and c not in desktop_dirs:
            desktop_dirs.append(c)

    shell = win32com.client.Dispatch("WScript.Shell")

    created = []
    # Primary desktop first
    for d in desktop_dirs[:1]:  # Only create in primary desktop to avoid duplicates
        try:
            shortcut_path = d / "Aura Downloader.lnk"
            if shortcut_path.exists():
                shortcut_path.unlink()

            shortcut = shell.CreateShortCut(str(shortcut_path))
            shortcut.TargetPath = str(pythonw_exe)
            shortcut.Arguments = f'"{str(main_script)}"'
            shortcut.WorkingDirectory = str(project_dir)
            shortcut.IconLocation = f"{str(icon_path)},0"
            shortcut.Description = "Aura Downloader - Liquid Glass Media Downloader"
            shortcut.WindowStyle = 1
            shortcut.save()
            created.append(str(shortcut_path))
            print(f"[OK] Shortcut created at: {shortcut_path}")
        except Exception as e:
            print(f"[Error] Failed for {d}: {e}")

    refresh_windows_icon_cache()
    return created

if __name__ == "__main__":
    create_shortcuts()
