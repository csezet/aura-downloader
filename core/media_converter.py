import os
import time
import tempfile
import subprocess
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000

def get_startupinfo():
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo

def get_unique_path(target_path: str) -> str:
    if not os.path.exists(target_path):
        return target_path
    base, ext = os.path.splitext(target_path)
    counter = 1
    while os.path.exists(f"{base} ({counter}){ext}"):
        counter += 1
    return f"{base} ({counter}){ext}"

def check_ffmpeg_available() -> tuple:
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        return False, "FFmpeg или FFprobe не найдены в системном PATH."
    try:
        res = subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if res.returncode == 0:
            first_line = res.stdout.splitlines()[0] if res.stdout else "FFmpeg OK"
            return True, first_line
    except Exception as e:
        return False, f"Ошибка запуска FFmpeg: {e}"
    return False, "FFmpeg вернул ненулевой код завершения."

def get_video_dimensions(input_path: str) -> tuple:
    if not input_path or not os.path.exists(input_path):
        return None, None
    try:
        import json
        # Compatible query for width, height across all FFprobe versions
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            input_path
        ]
        res = subprocess.run(
            cmd,
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        if res.returncode != 0:
            return None, None

        data = json.loads(res.stdout)
        streams = data.get("streams", [])
        if not streams:
            return None, None

        s = streams[0]
        w = int(s["width"]) if "width" in s else None
        h = int(s["height"]) if "height" in s else None
        if not w or not h:
            return None, None

        # Safe rotation detection (only if supported, without breaking width/height)
        rotate = 0
        try:
            cmd_rot = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream_tags=rotate:stream_side_data=rotation",
                "-of", "json",
                input_path
            ]
            res_rot = subprocess.run(
                cmd_rot,
                startupinfo=get_startupinfo(),
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5
            )
            if res_rot.returncode == 0:
                data_rot = json.loads(res_rot.stdout)
                streams_rot = data_rot.get("streams", [])
                if streams_rot:
                    s_rot = streams_rot[0]
                    tags = s_rot.get("tags", {})
                    if "rotate" in tags:
                        rotate = int(float(tags["rotate"]))
                    for sd in s_rot.get("side_data_list", []):
                        if "rotation" in sd:
                            rotate = int(float(sd["rotation"]))
        except Exception:
            pass

        if abs(rotate) in [90, 270]:
            w, h = h, w

        return w, h
    except Exception:
        pass
    return None, None

def convert_to_gif(input_path: str, output_path: str = None, fps: int = 15, width: int = 480) -> str:
    if not input_path or not os.path.exists(input_path):
        return input_path

    if not output_path:
        base, _ = os.path.splitext(input_path)
        output_path = get_unique_path(f"{base}.gif")

    part_path = f"{output_path}.tmp.gif"
    try:
        filter_complex = f"[0:v] fps={fps},scale={width}:-1:flags=lanczos,split [a][b];[a] palettegen [p];[b][p] paletteuse"
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", filter_complex,
            part_path
        ]
        subprocess.run(
            cmd,
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(part_path, output_path)
        return output_path
    except Exception as e:
        if os.path.exists(part_path):
            try:
                os.remove(part_path)
            except Exception:
                pass
        print(f"GIF conversion error: {e}")
        return input_path

def get_video_duration(input_path: str):
    if not input_path or not os.path.exists(input_path):
        return None
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
            timeout=10
        )
        if res.returncode == 0:
            val = res.stdout.strip()
            if val:
                dur = float(val)
                if dur > 0:
                    return dur
    except Exception:
        pass
    return None

def compress_to_target_size(input_path: str, target_mb: float = 8.0, output_path: str = None) -> str:
    if not input_path or not os.path.exists(input_path):
        return input_path

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = get_unique_path(f"{base}_compressed_{int(target_mb)}MB{ext or '.mp4'}")

    part_path = f"{output_path}.tmp.mp4"
    try:
        duration = get_video_duration(input_path)
        if not duration or duration <= 0:
            duration = 60.0

        # Budget bitrate targeting ~7.4MB to ensure it reliably stays under target_mb
        effective_target_mb = max(1.0, target_mb - 0.6)
        target_total_bitrate = (effective_target_mb * 8192) / duration
        audio_bitrate = 64 if target_total_bitrate < 300 else 96
        video_bitrate = max(40, int(target_total_bitrate - audio_bitrate))

        # Resolution scaling for lower bitrates to maintain picture quality and avoid bloated macroblocks
        vf_args = []
        if video_bitrate < 350:
            vf_args = ["-vf", "scale=trunc(min(iw\\,854)/2)*2:trunc(min(ih\\,480)/2)*2"]
        elif video_bitrate < 800:
            vf_args = ["-vf", "scale=trunc(min(iw\\,1280)/2)*2:trunc(min(ih\\,720)/2)*2"]

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
        ]
        if vf_args:
            cmd.extend(vf_args)
        cmd.extend([
            "-c:v", "libx264",
            "-b:v", f"{video_bitrate}k",
            "-maxrate", f"{int(video_bitrate * 1.25)}k",
            "-bufsize", f"{int(video_bitrate * 2)}k",
            "-preset", "faster",
            "-c:a", "aac",
            "-b:a", f"{audio_bitrate}k",
            part_path
        ])
        subprocess.run(
            cmd,
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )

        if not os.path.exists(part_path) or os.path.getsize(part_path) == 0:
            raise Exception("Сжатый файл пуст.")

        # Verify actual file size on disk; if exceeded target_mb, re-encode with lower bitrate
        actual_mb = os.path.getsize(part_path) / (1024 * 1024)
        if actual_mb > target_mb:
            lower_bitrate = max(30, int(video_bitrate * (target_mb * 0.88 / actual_mb)))
            cmd_reencode = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", "scale=trunc(min(iw\\,854)/2)*2:trunc(min(ih\\,480)/2)*2",
                "-c:v", "libx264",
                "-b:v", f"{lower_bitrate}k",
                "-maxrate", f"{int(lower_bitrate * 1.15)}k",
                "-bufsize", f"{int(lower_bitrate * 1.5)}k",
                "-preset", "faster",
                "-c:a", "aac",
                "-b:a", f"{min(64, audio_bitrate)}k",
                part_path
            ]
            subprocess.run(
                cmd_reencode,
                startupinfo=get_startupinfo(),
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(part_path, output_path)
        return output_path
    except Exception as e:
        if os.path.exists(part_path):
            try:
                os.remove(part_path)
            except Exception:
                pass
        print(f"Video compression error: {e}")
        return input_path

def get_crop_filter(input_path: str, crop_params: dict) -> str:
    if not input_path or not crop_params:
        return ""
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

        # Enforce even dimensions for video codecs
        crop_w = max(2, crop_w - (crop_w % 2))
        crop_h = max(2, crop_h - (crop_h % 2))
        crop_x = crop_x - (crop_x % 2)
        crop_y = crop_y - (crop_y % 2)

        # Clamp within video boundaries
        if crop_x + crop_w > real_w:
            crop_w = max(2, real_w - crop_x - ((real_w - crop_x) % 2))
        if crop_y + crop_h > real_h:
            crop_h = max(2, real_h - crop_y - ((real_h - crop_y) % 2))

        return f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"
    except Exception as e:
        print(f"Error calculating crop filter: {e}")
        return ""

def crop_video(input_path: str, crop_params: dict, output_path: str = None) -> str:
    if not input_path or not os.path.exists(input_path) or not crop_params:
        return input_path

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = get_unique_path(f"{base}_crop{ext or '.mp4'}")

    part_path = f"{output_path}.tmp.mp4"
    try:
        crop_filter = get_crop_filter(input_path, crop_params)
        if not crop_filter:
            return input_path

        is_gif = input_path.lower().endswith('.gif')
        if is_gif:
            filter_complex = f"[0:v] {crop_filter},split [a][b];[a] palettegen [p];[b][p] paletteuse"
            cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", filter_complex, part_path]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", crop_filter,
                "-c:v", "libx264",
                "-crf", "18",
                "-preset", "faster",
                "-c:a", "copy",
                part_path
            ]

        subprocess.run(
            cmd,
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )

        if not os.path.exists(part_path) or os.path.getsize(part_path) == 0:
            raise Exception("Кадрированный файл пуст.")

        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(part_path, output_path)
        return output_path
    except Exception as e:
        if os.path.exists(part_path):
            try:
                os.remove(part_path)
            except Exception:
                pass
        print(f"Video crop error: {e}")
        return input_path

def cleanup_aura_temp_files(max_age_hours: float = 24.0) -> int:
    """Cleans up leftover aura temp files (proxies, thumbs, cropped previews) older than max_age_hours."""
    temp_dir = tempfile.gettempdir()
    now = time.time()
    cutoff = now - (max_age_hours * 3600)
    cleaned_count = 0

    prefixes = ("aura_proxy_", "aura_thumb_", "aura_crop_", "sample_")
    try:
        for entry in os.scandir(temp_dir):
            try:
                if entry.name.startswith(prefixes) and (entry.name.endswith(".mp4") or entry.name.endswith(".jpg") or entry.name.endswith(".png")):
                    mtime = entry.stat().st_mtime
                    if mtime < cutoff or max_age_hours <= 0:
                        os.remove(entry.path)
                        cleaned_count += 1
            except Exception:
                pass
    except Exception as e:
        print(f"Error during temp cleanup: {e}")
    return cleaned_count


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
