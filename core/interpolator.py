import os
import sys
import shutil
import zipfile
import tempfile
import subprocess
from pathlib import Path
import hashlib
import requests
from core.media_converter import get_unique_path

CREATE_NO_WINDOW = 0x08000000

EXPECTED_RIFE_SHA256 = "d8e4d772d26cd8006ef0ad0bc82eb191b53c68677d1ae2f42506d74cbbbea606"

def get_startupinfo():
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo

def get_tools_dir() -> str:
    # Standard user data location on Windows: %LOCALAPPDATA%\AuraDownloader\tools\rife
    local_app_data = os.environ.get('LOCALAPPDATA')
    if local_app_data:
        tools_dir = os.path.join(local_app_data, "AuraDownloader", "tools", "rife")
    else:
        tools_dir = os.path.join(str(Path.home()), ".aura_downloader", "tools", "rife")
    os.makedirs(tools_dir, exist_ok=True)
    return tools_dir

def get_rife_executable() -> str:
    # 1. Check user tools dir in %LOCALAPPDATA%
    tools_dir = get_tools_dir()
    if os.path.exists(tools_dir):
        for root, _, files in os.walk(tools_dir):
            for f in files:
                if f.lower() == "rife-ncnn-vulkan.exe":
                    return os.path.join(root, f)

    # 2. Check bundled tools dir in app dir (if deployed with tools)
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bundled_dir = os.path.join(base, "tools", "rife")
    if os.path.exists(bundled_dir):
        for root, _, files in os.walk(bundled_dir):
            for f in files:
                if f.lower() == "rife-ncnn-vulkan.exe":
                    return os.path.join(root, f)

    return None

def is_rife_available() -> bool:
    exe = get_rife_executable()
    return exe is not None and os.path.exists(exe)

def download_rife_engine(progress_callback=None) -> bool:
    url = "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-windows.zip"
    tools_dir = get_tools_dir()
    zip_part = os.path.join(tools_dir, "rife.zip.part")

    try:
        if progress_callback:
            progress_callback("Загрузка AI модели RIFE (~25 МБ)...")

        resp = requests.get(url, stream=True, timeout=40)
        resp.raise_for_status()

        total_size = int(resp.headers.get('content-length', 0))
        downloaded = 0
        hasher = hashlib.sha256()

        with open(zip_part, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        pct = int((downloaded / total_size) * 100)
                        progress_callback(f"Загрузка AI модели RIFE: {pct}%...")

        # Verify SHA-256
        actual_sha256 = hasher.hexdigest().lower()
        if actual_sha256 != EXPECTED_RIFE_SHA256:
            if os.path.exists(zip_part):
                os.remove(zip_part)
            err_msg = f"Неверная контрольная сумма архива RIFE. Ожидалось {EXPECTED_RIFE_SHA256[:8]}, получено {actual_sha256[:8]}."
            if progress_callback:
                progress_callback(err_msg)
            print(err_msg)
            return False

        if progress_callback:
            progress_callback("Проверка и распаковка AI модели...")

        # Safe extraction into temporary directory with Zip Slip protection
        with tempfile.TemporaryDirectory() as temp_extract_dir:
            with zipfile.ZipFile(zip_part, 'r') as zip_ref:
                for member in zip_ref.infolist():
                    target_path = os.path.abspath(os.path.join(temp_extract_dir, member.filename))
                    if not target_path.startswith(os.path.abspath(temp_extract_dir)):
                        raise Exception("Обнаружена попытка выхода за пределы каталога при распаковке архива (Zip Slip).")
                zip_ref.extractall(temp_extract_dir)

            # Move extracted files to tools_dir
            for item in os.listdir(temp_extract_dir):
                s = os.path.join(temp_extract_dir, item)
                d = os.path.join(tools_dir, item)
                if os.path.exists(d):
                    if os.path.isdir(d):
                        shutil.rmtree(d)
                    else:
                        os.remove(d)
                shutil.move(s, d)

        if os.path.exists(zip_part):
            os.remove(zip_part)

        return is_rife_available()
    except Exception as e:
        print(f"Error downloading RIFE engine: {e}")
        if os.path.exists(zip_part):
            try:
                os.remove(zip_part)
            except Exception:
                pass
        return False

def get_video_fps(input_path: str):
    if not input_path or not os.path.exists(input_path):
        return None
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
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
            if '/' in val:
                num, den = val.split('/')
                den_f = float(den)
                if den_f > 0:
                    return float(num) / den_f
            elif val:
                fps = float(val)
                if fps > 0:
                    return fps
    except Exception:
        pass
    return None

def interpolate_with_ffmpeg(input_path: str, target_fps: int = 60, output_path: str = None) -> str:
    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = get_unique_path(f"{base}_{target_fps}fps{ext or '.mp4'}")

    part_path = f"{output_path}.tmp.mp4"
    try:
        # High quality motion-compensated interpolation
        filter_str = f"minterpolate=fps={target_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", filter_str,
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
        print(f"FFmpeg interpolation error: {e}")
        # Fallback to simple fps filter if MCI fails
        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vf", f"fps=fps={target_fps}",
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
            if os.path.exists(output_path):
                os.remove(output_path)
            os.rename(part_path, output_path)
            return output_path
        except Exception:
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except Exception:
                    pass
            return input_path

def interpolate_with_rife(input_path: str, target_fps: int = 60, output_path: str = None, status_callback=None) -> str:
    rife_exe = get_rife_executable()
    if not rife_exe or not os.path.exists(rife_exe):
        return interpolate_with_ffmpeg(input_path, target_fps, output_path)

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = get_unique_path(f"{base}_{target_fps}fps{ext or '.mp4'}")

    part_path = f"{output_path}.tmp.mp4"
    orig_fps = get_video_fps(input_path) or 30.0
    multiplier = max(2, int(round(target_fps / max(1.0, orig_fps))))

    temp_dir = tempfile.mkdtemp(prefix="aura_rife_")
    frames_in = os.path.join(temp_dir, "in")
    frames_out = os.path.join(temp_dir, "out")
    audio_path = os.path.join(temp_dir, "audio.aac")

    os.makedirs(frames_in, exist_ok=True)
    os.makedirs(frames_out, exist_ok=True)

    try:
        # 1. Extract audio
        if status_callback:
            status_callback("Извлечение аудио...")
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-vn", "-c:a", "copy", audio_path],
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        has_audio = os.path.exists(audio_path) and os.path.getsize(audio_path) > 0

        # 2. Extract frames
        if status_callback:
            status_callback("Извлечение кадров видео...")
        extract_pattern = os.path.join(frames_in, "frame_%08d.png")
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-qscale:v", "1", extract_pattern],
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )

        # 3. Run RIFE NCNN Vulkan
        if status_callback:
            status_callback(f"Нейросетевая интерполяция кадров (RIFE {multiplier}x)...")

        rife_dir = os.path.dirname(rife_exe)
        cmd_rife = [
            rife_exe,
            "-i", frames_in,
            "-o", frames_out,
            "-n", str(int(multiplier * orig_fps))
        ]

        subprocess.run(
            cmd_rife,
            cwd=rife_dir,
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )

        # 4. Assemble video back
        if status_callback:
            status_callback(f"Сборка видео ({target_fps} FPS)...")

        out_pattern = os.path.join(frames_out, "%08d.png")
        if not os.path.exists(os.path.join(frames_out, "00000001.png")):
            # Check naming
            out_pattern = os.path.join(frames_out, "frame_%08d.png")

        actual_fps = multiplier * orig_fps
        cmd_merge = [
            "ffmpeg", "-y",
            "-framerate", str(actual_fps),
            "-i", out_pattern,
        ]
        if has_audio:
            cmd_merge.extend(["-i", audio_path, "-c:a", "aac", "-b:a", "192k"])
        cmd_merge.extend([
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "18",
            "-preset", "faster",
            part_path
        ])

        subprocess.run(
            cmd_merge,
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
        print(f"RIFE error: {e}. Falling back to FFmpeg MCI.")
        return interpolate_with_ffmpeg(input_path, target_fps, output_path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def interpolate_video(input_path: str, target_fps: int = 60, model: str = 'auto', output_path: str = None, status_callback=None) -> str:
    if not input_path or not os.path.exists(input_path):
        return input_path

    if model == 'rife' or (model == 'auto' and is_rife_available()):
        return interpolate_with_rife(input_path, target_fps=target_fps, output_path=output_path, status_callback=status_callback)
    else:
        if status_callback:
            status_callback(f"Аппаратное увеличение плавности ({target_fps} FPS)...")
        return interpolate_with_ffmpeg(input_path, target_fps=target_fps, output_path=output_path)
