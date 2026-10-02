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
    vbs_script = project_dir / "run.vbs"
    icon_path = project_dir / "assets" / "app_logo.ico"
    if not icon_path.exists():
        icon_path = project_dir / "assets" / "icon.ico"

    # Use pythonw.exe directly so Windows executes GUI application with NO console window
    venv_pythonw = project_dir / "venv" / "Scripts" / "pythonw.exe"
    if venv_pythonw.exists():
        target_exe = str(venv_pythonw)
    else:
        py_dir = Path(sys.executable).parent
        if (py_dir / "pythonw.exe").exists():
            target_exe = str(py_dir / "pythonw.exe")
        elif (py_dir / "Scripts" / "pythonw.exe").exists():
            target_exe = str(py_dir / "Scripts" / "pythonw.exe")
        else:
            target_exe = "pythonw.exe"

    main_script = project_dir / "main.pyw"
    args = f'"{str(main_script)}"'

    # Detect user's real desktop directories (including OneDrive Desktop / Рабочий стол)
    desktop_dirs = []
    user_home = Path(os.environ.get("USERPROFILE", str(Path.home())))
    candidates = [
        user_home / "Desktop",
        user_home / "OneDrive" / "Desktop",
        user_home / "OneDrive" / "Рабочий стол",
    ]
    for c in candidates:
        if c.exists() and c not in desktop_dirs:
            desktop_dirs.append(c)

    shell = win32com.client.Dispatch("WScript.Shell")

    created = []
    for d in desktop_dirs:
        try:
            shortcut_path = d / "Aura Downloader.lnk"
            if shortcut_path.exists():
                try:
                    shortcut_path.unlink()
                except Exception:
                    pass

            shortcut = shell.CreateShortCut(str(shortcut_path))
            shortcut.TargetPath = target_exe
            shortcut.Arguments = args
            shortcut.WorkingDirectory = str(project_dir)
            shortcut.IconLocation = f"{str(icon_path)},0"
            shortcut.Description = "Aura Downloader - Media Downloader"
            shortcut.WindowStyle = 1  # 1 = Normal Window (NOT Minimized!)
            shortcut.save()

            # Set AppUserModelID on shortcut so Windows Taskbar pins and groups under this icon
            try:
                from win32com.propsys import propsys, pscon
                store = propsys.SHGetPropertyStoreFromParsingName(
                    str(shortcut_path), None, 2, propsys.IID_IPropertyStore
                )
                store.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType('aura.media.downloader.pro.v1'))
                store.Commit()
                del store
            except Exception as pe:
                print(f"[Warning] Could not set AppUserModelID on shortcut {shortcut_path}: {pe}")

            created.append(str(shortcut_path))
            print(f"[OK] Shortcut created at: {shortcut_path}")
        except Exception as e:
            print(f"[Error] Failed for {d}: {e}")

    refresh_windows_icon_cache()
    return created

if __name__ == "__main__":
    create_shortcuts()
