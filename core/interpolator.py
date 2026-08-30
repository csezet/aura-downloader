import os
import sys
import shutil
import zipfile
import tempfile
import subprocess
from pathlib import Path
import requests

CREATE_NO_WINDOW = 0x08000000

def get_startupinfo():
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo

def get_tools_dir() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tools_dir = os.path.join(base, "tools", "rife")
    os.makedirs(tools_dir, exist_ok=True)
    return tools_dir

def get_rife_executable() -> str:
    tools_dir = get_tools_dir()
    for root, _, files in os.walk(tools_dir):
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
    zip_path = os.path.join(tools_dir, "rife.zip")

    try:
        if progress_callback:
            progress_callback("Загрузка AI модели RIFE (~25 МБ)...")

        resp = requests.get(url, stream=True, timeout=30)
        resp.raise_for_status()

        total_size = int(resp.headers.get('content-length', 0))
        downloaded = 0

        with open(zip_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        pct = int((downloaded / total_size) * 100)
                        progress_callback(f"Загрузка AI модели RIFE: {pct}%...")

        if progress_callback:
            progress_callback("Распаковка AI модели...")

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(tools_dir)

        if os.path.exists(zip_path):
            os.remove(zip_path)

        return is_rife_available()
    except Exception as e:
        print(f"Error downloading RIFE engine: {e}")
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except Exception:
                pass
        return False

def get_video_fps(input_path: str) -> float:
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
            check=True
        )
        val = res.stdout.strip()
        if '/' in val:
            num, den = val.split('/')
            return float(num) / max(1.0, float(den))
        return float(val) if val else 30.0
    except Exception:
        return 30.0

def interpolate_with_ffmpeg(input_path: str, target_fps: int = 60, output_path: str = None) -> str:
    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_{target_fps}fps{ext or '.mp4'}"

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
        except Exception:
            return input_path

def interpolate_with_rife(input_path: str, target_fps: int = 60, output_path: str = None, status_callback=None) -> str:
    rife_exe = get_rife_executable()
    if not rife_exe or not os.path.exists(rife_exe):
        return interpolate_with_ffmpeg(input_path, target_fps, output_path)

    if not output_path:
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_{target_fps}fps{ext or '.mp4'}"

    orig_fps = get_video_fps(input_path)
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
            output_path
        ])

        subprocess.run(
            cmd_merge,
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )

        return output_path

    except Exception as e:
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
