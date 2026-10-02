"""Build, verify and archive a self-contained Windows distribution."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from core.version import APP_VERSION

PROJECT = Path(__file__).resolve().parent


def clean_build_environment():
    environment = os.environ.copy()
    windows = Path(os.environ["SystemRoot"])
    environment["PATH"] = os.pathsep.join(str(path) for path in
                                          (Path(sys.prefix) / "Scripts", Path(sys.base_prefix), windows / "System32", windows))
    for name in ("PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        environment.pop(name, None)
    return environment


def verify_environment():
    if sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("Release builds require Windows x64.")
    if sys.version_info[:3] != (3, 12, 10):
        raise RuntimeError("Use CPython 3.12.10 to build the verified release.")
    packages = {}
    for line in (PROJECT / "requirements-lock.txt").read_text(encoding="utf-8").splitlines():
        requirement = line.split(";", 1)[0].strip()
        if not requirement or requirement.startswith("#"):
            continue
        name, version = requirement.split("==", 1)
        actual = importlib.metadata.version(name)
        if actual != version:
            raise RuntimeError(f"{name}: expected {version}, found {actual}. Install requirements-lock.txt.")
        packages[name] = actual
    return packages


def build_command(tools, deno, onefile=False):
    command = [sys.executable, "-m", "PyInstaller", "--name=AuraDownloader", "--windowed", "--noupx",
               "--icon=" + str(PROJECT / "assets" / "app_logo.ico"), "--clean", "--noconfirm",
               "--specpath=" + str(PROJECT / "build"), "--distpath=" + str(PROJECT / "dist"),
               "--workpath=" + str(PROJECT / "build" / "pyinstaller"),
               "--add-data=" + str(PROJECT / "assets") + ";assets",
               "--hidden-import=PySide6.QtSvg", "--hidden-import=PySide6.QtMultimedia",
               "--hidden-import=PySide6.QtMultimediaWidgets", "--collect-all=yt_dlp",
               "--collect-all=yt_dlp_ejs", "--collect-all=Cryptodome",
               "--recursive-copy-metadata=yt-dlp", "--copy-metadata=deno",
               "--copy-metadata=yt-dlp-ejs"]
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        executable = tools / name
        if not executable.is_file():
            raise FileNotFoundError(f"Missing {executable}; run build_exe.py --download-tools.")
        command.append("--add-binary=" + str(executable) + ";tools")
    command.append("--add-binary=" + str(deno) + ";tools")
    command.extend(["--onefile" if onefile else "--onedir", str(PROJECT / "main.py")])
    return command


def copy_notices(destination, tools, packages):
    destination.mkdir(parents=True, exist_ok=True)
    for name in packages:
        distribution = importlib.metadata.distribution(name)
        for entry in distribution.files or []:
            if any("license" in part.lower() or "copying" in part.lower() for part in entry.parts):
                source = Path(distribution.locate_file(entry))
                if source.is_file() and source.stat().st_size < 2 * 1024 * 1024:
                    folder = destination / name
                    folder.mkdir(exist_ok=True)
                    shutil.copy2(source, folder / (hashlib.sha256(str(entry).encode()).hexdigest()[:8] + "-" + source.name))
    for name in ("FFmpeg-LICENSE.txt", "FFmpeg-README.txt", "ffmpeg-source.json"):
        source = tools / name
        if not source.is_file():
            raise FileNotFoundError(f"Missing FFmpeg notice {source}; use --download-tools.")
        shutil.copy2(source, destination / name)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, destination / "Python-LICENSE.txt")


def archive_distribution(directory):
    import zipfile
    target = PROJECT / "dist" / f"AuraDownloader-v{APP_VERSION}-windows-x64.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                archive.write(path, str(Path("AuraDownloader") / path.relative_to(directory)))
    with target.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    target.with_suffix(target.suffix + ".sha256").write_text(f"{digest}  {target.name}\n", encoding="ascii")
    return target


def build(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--onefile", action="store_true", help="Single EXE; default is a portable application folder.")
    parser.add_argument("--download-tools", action="store_true", help="Download the pinned FFmpeg build and verify its SHA-256.")
    args = parser.parse_args(argv)
    packages = verify_environment()
    tools = PROJECT / "tools"
    if args.download_tools:
        from scripts.prepare_tools import prepare_tools
        tools = prepare_tools()
    tool_config = json.loads((PROJECT / "packaging" / "tools.json").read_text(encoding="utf-8"))
    for name, expected in tool_config["files"].items():
        with (tools / name).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError(f"Unexpected checksum for {name}; use the pinned tools.")
    from deno import find_deno_bin
    deno = Path(find_deno_bin()).resolve()
    command = build_command(tools, deno, args.onefile)
    # Check licenses before any costly build.
    notice_dir = PROJECT / "build" / "release-notices"
    copy_notices(notice_dir, tools, packages)
    subprocess.run(command, cwd=PROJECT, env=clean_build_environment(), check=True)
    distribution = PROJECT / "dist" / ("AuraDownloaderSingle" if args.onefile else "AuraDownloader")
    if args.onefile:
        distribution.mkdir(exist_ok=True)
        shutil.copy2(PROJECT / "dist" / "AuraDownloader.exe", distribution / "AuraDownloader.exe")
    else:
        if not (distribution / "AuraDownloader.exe").is_file():
            raise RuntimeError("PyInstaller did not produce the expected EXE.")
    shutil.copytree(notice_dir, distribution / "licenses", dirs_exist_ok=True)
    for name in ("LICENSE", "THIRD_PARTY.md", "README.md", "requirements-lock.txt"):
        shutil.copy2(PROJECT / name, distribution / name)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT, capture_output=True, text=True)
    changes = subprocess.run(["git", "status", "--porcelain"], cwd=PROJECT, capture_output=True, text=True)
    manifest = {"version": APP_VERSION, "python": platform.python_version(), "packages": packages,
                "git_revision": revision.stdout.strip(), "working_tree_dirty": bool(changes.stdout.strip()),
                "tool_sha256": tool_config["files"],
                "deno_sha256": hashlib.sha256(deno.read_bytes()).hexdigest()}
    (distribution / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    from scripts.check_packaged_app import check_packaged_app
    check_packaged_app(distribution / "AuraDownloader.exe", PROJECT / "dist" / "smoke-report.json")
    archive = archive_distribution(distribution)
    print(f"Verified distribution: {archive}", flush=True)
    return archive


if __name__ == "__main__":
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr:
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        build()
    except Exception as error:
        print(f"Build failed: {error}", file=sys.stderr)
        raise SystemExit(1)
