"""Use the packaged Deno executable without relying on a user's PATH."""
import shutil
import sys
from pathlib import Path


def get_deno_path():
    candidates = []
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "tools" / "deno.exe")
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / "tools" / "deno.exe")
    candidates.append(Path(__file__).resolve().parents[1] / "tools" / "deno.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    try:
        from deno import find_deno_bin
        return str(find_deno_bin())
    except (ImportError, RuntimeError, FileNotFoundError):
        return shutil.which("deno")


def javascript_options():
    executable = get_deno_path()
    return {"js_runtimes": {"deno": {"path": executable}}} if executable else {}
