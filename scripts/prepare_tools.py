"""Download a pinned FFmpeg build and extract only the required files."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile
import requests

PROJECT = Path(__file__).resolve().parents[1]


def extract_tools(archive, target):
    target = Path(target)
    wanted = {"ffmpeg.exe": "ffmpeg.exe", "ffprobe.exe": "ffprobe.exe",
              "LICENSE": "FFmpeg-LICENSE.txt", "README.txt": "FFmpeg-README.txt"}
    with zipfile.ZipFile(archive) as package:
        entries = {}
        for member in package.infolist():
            name = member.filename.replace("\\", "/").rsplit("/", 1)[-1]
            if name in wanted:
                if name in entries or member.file_size > 300 * 1024 * 1024:
                    raise ValueError("Invalid FFmpeg archive.")
                entries[name] = member
        if set(entries) != set(wanted):
            raise ValueError("Archive does not contain both tools and their notices.")
        target.mkdir(parents=True, exist_ok=True)
        # Never extract paths supplied by the archive.
        for name, member in entries.items():
            output = target / wanted[name]
            with package.open(member) as source, output.open("wb") as destination:
                shutil.copyfileobj(source, destination)


def prepare_tools():
    config = json.loads((PROJECT / "packaging" / "tools.json").read_text(encoding="utf-8"))
    target = PROJECT / "tools"
    marker = target / "ffmpeg-source.json"
    if marker.is_file() and all((target / name).is_file() for name in
                                ("ffmpeg.exe", "ffprobe.exe", "FFmpeg-LICENSE.txt", "FFmpeg-README.txt")):
        if json.loads(marker.read_text(encoding="utf-8")) == config:
            matches = True
            for name, expected in config["files"].items():
                with (target / name).open("rb") as stream:
                    matches = matches and hashlib.file_digest(stream, "sha256").hexdigest() == expected
            if matches:
                return target
    if any((target / name).exists() for name in ("ffmpeg.exe", "ffprobe.exe")) and not marker.exists():
        raise ValueError("tools/ contains user-provided binaries. Move them aside before downloading the pinned build.")
    with tempfile.TemporaryDirectory(prefix="aura_tools_") as temporary:
        archive = Path(temporary) / "ffmpeg.zip"
        digest = hashlib.sha256()
        print(f"Downloading FFmpeg {config['version']} with SHA-256 verification...", flush=True)
        with requests.get(config["url"], stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            size = 0
            with archive.open("wb") as stream:
                for chunk in response.iter_content(1024 * 1024):
                    size += len(chunk)
                    if size > 250 * 1024 * 1024:
                        raise ValueError("FFmpeg archive exceeded the expected size.")
                    digest.update(chunk)
                    stream.write(chunk)
        if digest.hexdigest() != config["sha256"]:
            raise ValueError("FFmpeg checksum mismatch; no binaries were installed.")
        staged = Path(temporary) / "extracted"
        extract_tools(archive, staged)
        for name, expected in config["files"].items():
            with (staged / name).open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise ValueError(f"Unexpected checksum for {name}; no binaries were installed.")
        target.mkdir(parents=True, exist_ok=True)
        for source in staged.iterdir():
            with tempfile.NamedTemporaryFile(dir=target, suffix=".part", delete=False) as stream:
                part = Path(stream.name)
                with source.open("rb") as incoming:
                    shutil.copyfileobj(incoming, stream)
            try:
                os.replace(part, target / source.name)
            finally:
                part.unlink(missing_ok=True)
        marker.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    print(prepare_tools())
