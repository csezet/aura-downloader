import os
import subprocess
from pathlib import Path

# Windows flag to suppress any console window popup
CREATE_NO_WINDOW = 0x08000000

def get_startupinfo():
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo

def convert_to_gif(input_path: str, output_path: str = None, fps: int = 15, width: int = 480) -> str:
    if not output_path:
        base, _ = os.path.splitext(input_path)
        output_path = f"{base}.gif"

    # High quality GIF palette filter
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
        return float(res.stdout.strip())
    except Exception:
        return 0.0

def compress_to_target_size(input_path: str, target_mb: float = 8.0, output_path: str = None) -> str:
    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_compressed_{int(target_mb)}MB{ext or '.mp4'}"

    duration = get_video_duration(input_path)
    if duration <= 0:
        duration = 60.0  # Fallback assumption

    # Calculate total target bitrate in kbps (subtracting 96k for audio)
    target_total_bitrate = (target_mb * 8192) / duration  # in kbps
    audio_bitrate = 96
    video_bitrate = max(50, int(target_total_bitrate - audio_bitrate))

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
