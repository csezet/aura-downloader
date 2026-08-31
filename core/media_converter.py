import os
import subprocess
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000

def get_startupinfo():
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo

def get_video_dimensions(input_path: str) -> tuple:
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
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
        parts = res.stdout.strip().split('x')
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return 1920, 1080

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

def crop_video(input_path: str, crop_params: dict, output_path: str = None) -> str:
    if not input_path or not os.path.exists(input_path) or not crop_params:
        return input_path

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_crop{ext or '.mp4'}"

    try:
        real_w, real_h = get_video_dimensions(input_path)
        
        if 'x_norm' in crop_params:
            x_norm = max(0.0, min(1.0, float(crop_params.get('x_norm', 0.0))))
            y_norm = max(0.0, min(1.0, float(crop_params.get('y_norm', 0.0))))
            w_norm = max(0.05, min(1.0, float(crop_params.get('w_norm', 1.0))))
            h_norm = max(0.05, min(1.0, float(crop_params.get('h_norm', 1.0))))

            crop_w = int(real_w * w_norm)
            crop_h = int(real_h * h_norm)
            crop_x = int(real_w * x_norm)
            crop_y = int(real_h * y_norm)
        else:
            crop_w = int(crop_params.get('w', real_w))
            crop_h = int(crop_params.get('h', real_h))
            crop_x = int(crop_params.get('x', 0))
            crop_y = int(crop_params.get('y', 0))

        # Enforce even dimensions for H.264/H.265/VP9 codecs
        crop_w = max(2, crop_w - (crop_w % 2))
        crop_h = max(2, crop_h - (crop_h % 2))
        crop_x = crop_x - (crop_x % 2)
        crop_y = crop_y - (crop_y % 2)

        # Clamp within video boundaries
        if crop_x + crop_w > real_w:
            crop_w = max(2, real_w - crop_x - ((real_w - crop_x) % 2))
        if crop_y + crop_h > real_h:
            crop_h = max(2, real_h - crop_y - ((real_h - crop_y) % 2))

        crop_filter = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"
        
        is_gif = input_path.lower().endswith('.gif')
        if is_gif:
            filter_complex = f"[0:v] {crop_filter},split [a][b];[a] palettegen [p];[b][p] paletteuse"
            cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", filter_complex, output_path]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", crop_filter,
                "-c:v", "libx264",
                "-crf", "18",
                "-preset", "faster",
                "-c:a", "copy",
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
        print(f"Video crop error: {e}")
        return input_path


def get_video_codec(input_path: str) -> str:
    if not input_path or not os.path.exists(input_path):
        return ""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name",
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
        return res.stdout.strip().lower()
    except Exception:
        return ""


def get_or_create_preview_proxy(input_path: str) -> str:
    """
    Ensures the video is playable in Qt Multimedia without D3D11 hardware acceleration failures.
    If the video is already h264/avc1/mp4v, returns input_path.
    If it's av1, vp9, hevc, etc. or exotic format, creates a fast lightweight H.264 proxy.
    """
    if not input_path or not os.path.exists(input_path):
        return input_path

    codec = get_video_codec(input_path)
    if codec in ['h264', 'avc1', 'mp4v', 'mjpeg']:
        return input_path

    try:
        import tempfile
        import hashlib
        file_hash = hashlib.md5(input_path.encode('utf-8')).hexdigest()[:12]
        proxy_path = os.path.join(tempfile.gettempdir(), f"aura_proxy_{file_hash}.mp4")
        if os.path.exists(proxy_path) and os.path.getsize(proxy_path) > 0:
            return proxy_path

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "26",
            "-tune", "fastdecode",
            "-vf", "scale='min(1280,iw)':-2",
            "-c:a", "aac",
            "-b:a", "128k",
            proxy_path
        ]
        subprocess.run(
            cmd,
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        if os.path.exists(proxy_path) and os.path.getsize(proxy_path) > 0:
            return proxy_path
    except Exception as e:
        print(f"Proxy creation error: {e}")

    return input_path
