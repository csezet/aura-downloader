import os
import sys
import time
import shutil
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
    while os.path.exists(f"{base} ({counter}){ext}") and counter < 10000:
        counter += 1
    return f"{base} ({counter}){ext}"

def get_unique_base_for_group(save_dir: str, stem: str, primary_ext: str, sidecar_suffixes: list) -> str:
    """
    Finds a base filename stem such that both the primary media file
    '{stem}{primary_ext}' and all its sidecar files '{stem}{sidecar_suffix}'
    can be written without colliding with any existing file in save_dir.
    """
    candidate_stem = stem
    counter = 1
    def has_collision(test_stem):
        if os.path.exists(os.path.join(save_dir, f"{test_stem}{primary_ext}")):
            return True
        for s_suffix in sidecar_suffixes:
            if os.path.exists(os.path.join(save_dir, f"{test_stem}{s_suffix}")):
                return True
        return False

    while has_collision(candidate_stem) and counter < 10000:
        candidate_stem = f"{stem} ({counter})"
        counter += 1
    return candidate_stem

def get_ffmpeg_path() -> str:
    candidates = []
    # 1. Bundled PyInstaller _MEIPASS
    if hasattr(sys, '_MEIPASS'):
        candidates.append(os.path.join(sys._MEIPASS, "tools", "ffmpeg.exe"))
        candidates.append(os.path.join(sys._MEIPASS, "ffmpeg.exe"))
    # 2. Frozen executable directory (PyInstaller onedir)
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "tools", "ffmpeg.exe"))
        candidates.append(os.path.join(exe_dir, "ffmpeg.exe"))
    # 3. Development / source project tools directory
    proj_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(proj_dir, "tools", "ffmpeg.exe"))
    candidates.append(os.path.join(proj_dir, "ffmpeg.exe"))

    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)

    which_path = shutil.which("ffmpeg")
    return which_path if which_path else "ffmpeg"

def get_ffprobe_path() -> str:
    candidates = []
    if hasattr(sys, '_MEIPASS'):
        candidates.append(os.path.join(sys._MEIPASS, "tools", "ffprobe.exe"))
        candidates.append(os.path.join(sys._MEIPASS, "ffprobe.exe"))
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "tools", "ffprobe.exe"))
        candidates.append(os.path.join(exe_dir, "ffprobe.exe"))
    proj_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(proj_dir, "tools", "ffprobe.exe"))
    candidates.append(os.path.join(proj_dir, "ffprobe.exe"))

    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)

    which_path = shutil.which("ffprobe")
    return which_path if which_path else "ffprobe"

def check_ffmpeg_available() -> tuple:
    ffmpeg_exe = get_ffmpeg_path()
    ffprobe_exe = get_ffprobe_path()
    has_ffmpeg = (os.path.isabs(ffmpeg_exe) and os.path.isfile(ffmpeg_exe)) or bool(shutil.which(ffmpeg_exe))
    has_ffprobe = (os.path.isabs(ffprobe_exe) and os.path.isfile(ffprobe_exe)) or bool(shutil.which(ffprobe_exe))
    if not has_ffmpeg or not has_ffprobe:
        return False, "FFmpeg или FFprobe не найдены. Установите через winget (winget install Gyan.FFmpeg) или поместите в папку tools/"
    try:
        res = subprocess.run([ffmpeg_exe, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if res.returncode == 0:
            first_line = res.stdout.splitlines()[0] if res.stdout else "FFmpeg OK"
            return True, first_line
    except Exception as e:
        return False, f"Ошибка запуска FFmpeg: {e}"
    return False, "FFmpeg вернул ненулевой код завершения."

def run_ffmpeg_cancellable(cmd: list, temp_output: str = None, is_cancelled_cb=None) -> bool:
    if cmd and cmd[0] == "ffmpeg":
        cmd = [get_ffmpeg_path()] + list(cmd[1:])
    elif cmd and cmd[0] == "ffprobe":
        cmd = [get_ffprobe_path()] + list(cmd[1:])
    with tempfile.TemporaryFile(mode='w+b') as err_file:
        proc = subprocess.Popen(
            cmd,
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=err_file
        )
        while proc.poll() is None:
            if is_cancelled_cb and is_cancelled_cb():
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=2)
                    except Exception:
                        pass
                if temp_output and os.path.exists(temp_output):
                    try:
                        os.remove(temp_output)
                    except Exception:
                        pass
                return False
            time.sleep(0.1)

        if proc.returncode != 0:
            if temp_output and os.path.exists(temp_output):
                try:
                    os.remove(temp_output)
                except Exception:
                    pass
            err_file.seek(0)
            err_data = err_file.read()
            err_text = err_data[-2000:].decode(errors='replace').strip() if err_data else "Unknown error"
            raise Exception(f"FFmpeg error: {err_text}")
        return True

def probe_video_stream(file_path: str) -> bool:
    """Verifies that the file actually contains a valid, decodable video stream (not audio/HTML/corrupted)."""
    if not file_path or not os.path.exists(file_path):
        return False
    try:
        import json
        cmd = [
            get_ffprobe_path(), "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_type,codec_name,width,height",
            "-of", "json",
            file_path
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
            return False
        data = json.loads(res.stdout)
        streams = data.get("streams", [])
        if not streams:
            return False
        s = streams[0]
        if s.get("codec_type") != "video":
            return False
        w = int(s.get("width") or 0)
        h = int(s.get("height") or 0)
        return w > 0 and h > 0
    except Exception:
        return False

def get_video_dimensions(input_path: str) -> tuple:
    if not input_path or not os.path.exists(input_path):
        return None, None
    try:
        import json
        # Compatible query for width, height across all FFprobe versions
        cmd = [
            get_ffprobe_path(), "-v", "error",
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
                get_ffprobe_path(), "-v", "error",
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

def convert_to_gif(input_path: str, output_path: str = None, fps: int = 15, width: int = 480, is_cancelled_cb=None) -> str:
    if is_cancelled_cb and is_cancelled_cb():
        return None
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
        if not run_ffmpeg_cancellable(cmd, part_path, is_cancelled_cb):
            return None

        if not os.path.exists(part_path) or os.path.getsize(part_path) == 0:
            raise Exception("Файл GIF пуст или не был создан.")

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
        raise e

def get_video_duration(input_path: str):
    if not input_path or not os.path.exists(input_path):
        return None
    try:
        cmd = [
            get_ffprobe_path(), "-v", "error",
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

def compress_to_target_size(input_path: str, target_mb: float = 8.0, output_path: str = None, is_cancelled_cb=None) -> str:
    if is_cancelled_cb and is_cancelled_cb():
        return None
    if not input_path or not os.path.exists(input_path):
        raise FileNotFoundError(f"Файл для сжатия не найден: {input_path}")

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = get_unique_path(f"{base}_compressed_{int(target_mb)}MB{ext or '.mp4'}")

    part_path = f"{output_path}.tmp.mp4"
    max_bytes = int(target_mb * 1024 * 1024)

    try:
        duration = get_video_duration(input_path)
        if not duration or duration <= 0:
            duration = 60.0

        # Pass 1: Initial bitrate budget (target 88% of limit to leave headroom)
        effective_target_mb = max(0.8, target_mb * 0.88)
        target_total_bitrate = (effective_target_mb * 8192) / duration
        audio_bitrate = 48 if target_total_bitrate < 250 else (64 if target_total_bitrate < 400 else 96)
        video_bitrate = max(35, int(target_total_bitrate - audio_bitrate))

        # Resolution scaling for lower bitrates to maintain quality and avoid oversized output
        vf_args = []
        if video_bitrate < 300:
            vf_args = ["-vf", "scale=trunc(min(iw\\,640)/2)*2:trunc(min(ih\\,360)/2)*2"]
        elif video_bitrate < 500:
            vf_args = ["-vf", "scale=trunc(min(iw\\,854)/2)*2:trunc(min(ih\\,480)/2)*2"]
        elif video_bitrate < 900:
            vf_args = ["-vf", "scale=trunc(min(iw\\,1280)/2)*2:trunc(min(ih\\,720)/2)*2"]

        cmd = ["ffmpeg", "-y", "-i", input_path]
        if vf_args:
            cmd.extend(vf_args)
        cmd.extend([
            "-c:v", "libx264",
            "-b:v", f"{video_bitrate}k",
            "-maxrate", f"{int(video_bitrate * 1.2)}k",
            "-bufsize", f"{int(video_bitrate * 1.5)}k",
            "-preset", "faster",
            "-c:a", "aac",
            "-b:a", f"{audio_bitrate}k",
            part_path
        ])

        if not run_ffmpeg_cancellable(cmd, part_path, is_cancelled_cb):
            return None

        if not os.path.exists(part_path) or os.path.getsize(part_path) == 0:
            raise Exception("Сжатый файл пуст.")

        # Pass 2: Re-encode if size strictly exceeds limit
        if os.path.getsize(part_path) > max_bytes:
            actual_bytes = os.path.getsize(part_path)
            ratio = max_bytes / actual_bytes
            lower_bitrate = max(25, int(video_bitrate * ratio * 0.85))
            cmd_reencode = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", "scale=trunc(min(iw\\,640)/2)*2:trunc(min(ih\\,360)/2)*2",
                "-c:v", "libx264",
                "-b:v", f"{lower_bitrate}k",
                "-maxrate", f"{int(lower_bitrate * 1.15)}k",
                "-bufsize", f"{int(lower_bitrate * 1.4)}k",
                "-preset", "faster",
                "-c:a", "aac",
                "-b:a", "48k",
                part_path
            ]
            if not run_ffmpeg_cancellable(cmd_reencode, part_path, is_cancelled_cb):
                return None

        # Pass 3: Fallback pass if still oversized
        if os.path.exists(part_path) and os.path.getsize(part_path) > max_bytes:
            actual_bytes = os.path.getsize(part_path)
            ratio = max_bytes / actual_bytes
            aggressive_bitrate = max(20, int(lower_bitrate * ratio * 0.80))
            cmd_reencode3 = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", "scale=trunc(min(iw\\,480)/2)*2:trunc(min(ih\\,270)/2)*2",
                "-c:v", "libx264",
                "-b:v", f"{aggressive_bitrate}k",
                "-maxrate", f"{int(aggressive_bitrate * 1.1)}k",
                "-bufsize", f"{int(aggressive_bitrate * 1.2)}k",
                "-preset", "fast",
                "-c:a", "aac",
                "-b:a", "32k",
                part_path
            ]
            if not run_ffmpeg_cancellable(cmd_reencode3, part_path, is_cancelled_cb):
                return None

        # Final Strict Limit Check
        if not os.path.exists(part_path):
            raise Exception("Файл сжатия не сформирован.")

        final_sz = os.path.getsize(part_path)
        if final_sz > max_bytes:
            os.remove(part_path)
            raise Exception(f"Не удалось сжать видео до лимита {target_mb:.1f} МБ (размер {final_sz / (1024*1024):.2f} МБ). Уменьшите длительность ролика.")

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
        raise e

def get_crop_filter(input_path: str, crop_params: dict) -> str:
    if not input_path or not crop_params:
        return ""
    try:
        real_w, real_h = get_video_dimensions(input_path)
        if not real_w or not real_h:
            return ""

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

def crop_video(input_path: str, crop_params: dict, output_path: str = None, is_cancelled_cb=None) -> str:
    if is_cancelled_cb and is_cancelled_cb():
        return None
    if not input_path or not os.path.exists(input_path) or not crop_params:
        return input_path

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = get_unique_path(f"{base}_crop{ext or '.mp4'}")

    part_path = f"{output_path}.tmp.mp4"
    try:
        crop_filter = get_crop_filter(input_path, crop_params)
        if not crop_filter:
            raise Exception("Не удалось кадрировать видео: невозможно рассчитать параметры кадрирования.")

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

        if not run_ffmpeg_cancellable(cmd, part_path, is_cancelled_cb):
            return None

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
        raise e

def cleanup_aura_temp_files(max_age_hours: float = 24.0, extra_dirs: list = None) -> int:
    """
    Cleans up leftover aura temp files (proxies, thumbs, cropped previews)
    and orphaned .aura_staging_* directories older than max_age_hours.
    """
    now = time.time()
    cutoff = now - (max_age_hours * 3600)
    cleaned_count = 0

    scan_dirs = {tempfile.gettempdir()}
    try:
        from core.settings import settings
        dl_dir = settings.get("download_dir")
        if dl_dir and os.path.isdir(dl_dir):
            scan_dirs.add(dl_dir)
    except Exception:
        pass

    if extra_dirs:
        for d in extra_dirs:
            if d and os.path.isdir(d):
                scan_dirs.add(d)

    prefixes = ("aura_proxy_", "aura_thumb_", "aura_crop_", "sample_")
    for target_dir in scan_dirs:
        try:
            for entry in os.scandir(target_dir):
                try:
                    # Clean temporary proxy/thumb/crop files
                    if entry.is_file() and entry.name.startswith(prefixes) and (
                        entry.name.endswith(".mp4") or entry.name.endswith(".jpg") or entry.name.endswith(".png")
                    ):
                        mtime = entry.stat().st_mtime
                        if mtime < cutoff or max_age_hours <= 0:
                            os.remove(entry.path)
                            cleaned_count += 1
                    # Clean orphaned staging directories
                    elif entry.is_dir() and entry.name.startswith(".aura_staging_"):
                        mtime = entry.stat().st_mtime
                        if mtime < cutoff or max_age_hours <= 0:
                            shutil.rmtree(entry.path, ignore_errors=True)
                            cleaned_count += 1
                except Exception:
                    pass
        except Exception:
            pass

    return cleaned_count



def get_video_codec(input_path: str) -> str:
    if not input_path or not os.path.exists(input_path):
        return ""
    try:
        cmd = [
            get_ffprobe_path(), "-v", "error",
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
            get_ffmpeg_path(), "-y",
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
