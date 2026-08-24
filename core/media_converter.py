import os
import subprocess
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000

def get_startupinfo():
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo

def convert_to_gif(input_path: str, output_path: str = None, fps: int = 15, width: int = 480) -> str:
    if not input_path or not os.path.exists(input_path):
        return input_path

    if not output_path:
        base, _ = os.path.splitext(input_path)
        output_path = f"{base}.gif"

    try:
        filter_complex = f"[0:v] fps={fps},scale={width}:-1:flags=lanczos,split [a][b];[a] palettegen [p];[b][p] paletteuse"
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", filter_complex,
            output_path
        ]
        subprocess.run(
            cmd,
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        return output_path
    except Exception as e:
        print(f"GIF conversion error: {e}")
        return input_path

def get_video_duration(input_path: str) -> float:
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            input_path
        ]
        res = subprocess.run(
            cmd,
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        val = res.stdout.strip()
        return float(val) if val else 60.0
    except Exception:
        return 60.0

def compress_to_target_size(input_path: str, target_mb: float = 8.0, output_path: str = None) -> str:
    if not input_path or not os.path.exists(input_path):
        return input_path

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_compressed_{int(target_mb)}MB{ext or '.mp4'}"

    try:
        duration = get_video_duration(input_path)
        if duration <= 0:
            duration = 60.0

        target_total_bitrate = (target_mb * 8192) / duration
        audio_bitrate = 96
        video_bitrate = max(40, int(target_total_bitrate - audio_bitrate))

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-c:v", "libx264",
            "-b:v", f"{video_bitrate}k",
            "-maxrate", f"{int(video_bitrate * 1.3)}k",
            "-bufsize", f"{int(video_bitrate * 2)}k",
            "-preset", "faster",
            "-c:a", "aac",
            "-b:a", f"{audio_bitrate}k",
            output_path
        ]
        subprocess.run(
            cmd,
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        return output_path
    except Exception as e:
        print(f"Video compression error: {e}")
        return input_path
