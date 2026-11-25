import os
import time
import shutil
import threading
import zipfile
import tempfile
import subprocess
from pathlib import Path
import hashlib
import math
from fractions import Fraction
import requests
from core.http_utils import parse_content_length as _parse_content_length
from core.media_converter import (
    get_unique_path, run_ffmpeg_cancellable, get_video_duration,
    get_ffprobe_path, get_ffmpeg_path,  # noqa: F401
    remove_partial, probe_media_info
)
from core.process_utils import CREATE_NO_WINDOW, get_startupinfo
from core.temp_files import get_cache_dir

EXPECTED_RIFE_SHA256 = "d8e4d772d26cd8006ef0ad0bc82eb191b53c68677d1ae2f42506d74cbbbea606"
RIFE_DISK_SAFETY_MARGIN = 512 * 1024 * 1024  # 512 MiB headroom

_rife_cache_lock = threading.Lock()
_rife_cache = {"checked": False, "tools_dir": None, "available": False}


def invalidate_rife_cache():
    with _rife_cache_lock:
        _rife_cache["checked"] = False
        _rife_cache["tools_dir"] = None
        _rife_cache["available"] = False


def get_tools_dir(create: bool = True) -> str:
    # Standard user data location on Windows: %LOCALAPPDATA%\AuraDownloader\tools\rife
    local_app_data = os.environ.get('LOCALAPPDATA')
    if local_app_data:
        tools_dir = os.path.join(local_app_data, "AuraDownloader", "tools", "rife")
    else:
        tools_dir = os.path.join(str(Path.home()), ".aura_downloader", "tools", "rife")
    if create:
        os.makedirs(tools_dir, exist_ok=True)
    return tools_dir


def _find_rife_in_dir(base_dir: str):
    if not base_dir or not os.path.isdir(base_dir):
        return None
    direct = os.path.join(base_dir, "rife-ncnn-vulkan.exe")
    if os.path.isfile(direct):
        return direct
    try:
        for entry in os.scandir(base_dir):
            if entry.is_file() and entry.name.lower() == "rife-ncnn-vulkan.exe":
                return entry.path
            if entry.is_dir():
                nested = os.path.join(entry.path, "rife-ncnn-vulkan.exe")
                if os.path.isfile(nested):
                    return nested
    except OSError:
        pass
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.lower() == "rife-ncnn-vulkan.exe":
                return os.path.join(root, f)
    return None


def get_rife_executable() -> str:
    # 1. Check user tools dir in %LOCALAPPDATA%
    found = _find_rife_in_dir(get_tools_dir(create=False))
    if found:
        return found

    # 2. Check bundled tools dir in app dir (if deployed with tools)
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bundled_dir = os.path.join(base, "tools", "rife")
    return _find_rife_in_dir(bundled_dir)


def is_rife_available(force_refresh: bool = False) -> bool:
    tools_dir = get_tools_dir(create=False)
    with _rife_cache_lock:
        if not force_refresh and _rife_cache["checked"] and _rife_cache["tools_dir"] == tools_dir:
            return _rife_cache["available"]
    exe = get_rife_executable()
    available = bool(exe and os.path.isfile(exe) and get_rife_model_path(exe))
    with _rife_cache_lock:
        _rife_cache["checked"] = True
        _rife_cache["tools_dir"] = tools_dir
        _rife_cache["available"] = available
    return available


def download_rife_engine(progress_callback=None, is_cancelled_cb=None) -> bool:
    url = "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/rife-ncnn-vulkan-20221029-windows.zip"
    tools_dir = get_tools_dir()
    zip_part = os.path.join(tools_dir, "rife.zip.part")
    resp = None

    try:
        if is_cancelled_cb and is_cancelled_cb():
            return False
        if progress_callback:
            progress_callback("Загрузка AI модели RIFE (~25 МБ)...")

        resp = requests.get(url, stream=True, timeout=(5, 15))
        resp.raise_for_status()

        total_size = _parse_content_length(resp.headers)
        downloaded = 0
        hasher = hashlib.sha256()

        with open(zip_part, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if is_cancelled_cb and is_cancelled_cb():
                    raise InterruptedError("Загрузка RIFE отменена.")
                if chunk:
                    f.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        pct = min(100, int((downloaded / total_size) * 100))
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
                    if not Path(target_path).resolve().is_relative_to(Path(temp_extract_dir).resolve()):
                        raise Exception("Обнаружена попытка выхода за пределы каталога при распаковке архива (Zip Slip).")
                zip_ref.extractall(temp_extract_dir)

            # Move extracted files to tools_dir
            if is_cancelled_cb and is_cancelled_cb():
                raise InterruptedError("Загрузка RIFE отменена.")
            for item in os.listdir(temp_extract_dir):
                s = os.path.join(temp_extract_dir, item)
                d = os.path.join(tools_dir, item)
                if (Path(s).resolve().parent != Path(temp_extract_dir).resolve()
                        or Path(d).resolve().parent != Path(tools_dir).resolve()):
                    raise ValueError("Небезопасный путь установки RIFE.")
                if os.path.exists(d):
                    if os.path.isdir(d):
                        shutil.rmtree(d)
                    else:
                        os.remove(d)
                shutil.move(s, d)

        if os.path.exists(zip_part):
            os.remove(zip_part)

        invalidate_rife_cache()
        return is_rife_available(force_refresh=True)
    except InterruptedError:
        if os.path.exists(zip_part):
            try:
                os.remove(zip_part)
            except Exception:
                pass
        return False
    except Exception as e:
        err_msg = f"Ошибка загрузки RIFE: {e}"
        print(err_msg)
        if progress_callback:
            progress_callback(err_msg)
        if os.path.exists(zip_part):
            try:
                os.remove(zip_part)
            except Exception:
                pass
        return False
    finally:
        if resp is not None:
            resp.close()


def get_video_fps(input_path: str):
    return probe_media_info(input_path)["fps"]


def resolve_target_fps(input_path, target_fps):
    try:
        fps = float(target_fps)
    except (TypeError, ValueError):
        raise ValueError("Некорректная частота кадров.")
    if fps == 0:
        source_fps = get_video_fps(input_path)
        if not source_fps:
            raise ValueError("Не удалось определить исходный FPS для удвоения.")
        fps = source_fps * 2
    if not math.isfinite(fps) or not 0 < fps <= 480:
        raise ValueError("Частота кадров должна быть от 0 до 480 FPS; 0 означает удвоение.")
    return fps


def _fps_text(fps):
    rate = Fraction(fps).limit_denominator(100000)
    return f"{rate.numerator}/{rate.denominator}"


def get_rife_model_path(executable, model="rife-v4.6"):
    name = "rife-v4.6" if model in ("auto", "rife") else model
    if name not in ("rife-v4", "rife-v4.6"):
        return None
    root = Path(executable).parent
    for folder in (root / name, root / "models" / name):
        if folder.is_dir() and any(folder.glob("*.param")) and any(folder.glob("*.bin")):
            return str(folder)
    return None


def _interpolation_output(input_path, target_fps, output_path):
    if output_path:
        if Path(output_path).suffix.lower() != ".mp4":
            raise ValueError("Результат интерполяции необходимо сохранить в MP4.")
        return output_path
    base = os.path.splitext(input_path)[0]
    return get_unique_path(f"{base}_{target_fps:g}fps.mp4")


def _estimate_rife_disk_bytes(width, height, duration, source_fps, target_fps):
    """Conservative estimate of disk space required for input + output PNG frame sequences."""
    if not duration or duration <= 0:
        return None
    in_frames = max(2, int(math.ceil(duration * source_fps)))
    out_frames = max(2, int(round(duration * target_fps)))
    if width and height:
        bytes_per_frame = max(65536, int(width * height * 1.5))
    else:
        bytes_per_frame = 2 * 1024 * 1024
    return (in_frames + out_frames) * bytes_per_frame


def interpolate_with_ffmpeg(input_path: str, target_fps=60, output_path: str = None,
                            is_cancelled_cb=None, status_callback=None) -> str:
    fps = resolve_target_fps(input_path, target_fps)
    output_path = _interpolation_output(input_path, fps, output_path)
    part_path = f"{output_path}.tmp.mp4"
    duration = get_video_duration(input_path)
    # Extra terminal frames let minterpolate finish its lookahead without shortening the clip.
    filters = [f"tpad=stop_mode=clone:stop_duration=1,minterpolate=fps={_fps_text(fps)}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1",
               f"fps={_fps_text(fps)}"]
    first_error = None
    try:
        for index, video_filter in enumerate(filters):
            if is_cancelled_cb and is_cancelled_cb():
                return None
            if status_callback:
                status_callback(f"FFmpeg: интерполяция движения ({fps:g} FPS)..." if index == 0 else
                                "Интерполяция движения недоступна: резервный режим с повторением кадров.")
            cmd = ["ffmpeg", "-y", "-i", input_path, "-map", "0:v:0", "-map", "0:a:0?",
                   "-vf", video_filter, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                   "-crf", "18", "-preset", "faster", "-c:a", "aac", "-b:a", "192k"]
            if duration:
                cmd += ["-t", str(duration)]
            cmd += ["-movflags", "+faststart", part_path]
            try:
                if not run_ffmpeg_cancellable(cmd, part_path, is_cancelled_cb):
                    return None
                if not os.path.isfile(part_path) or not os.path.getsize(part_path):
                    raise ValueError("Файл интерполяции пуст.")
                if is_cancelled_cb and is_cancelled_cb():
                    return None
                os.rename(part_path, output_path)
                return output_path
            except Exception as error:
                if index == 1:
                    raise RuntimeError(f"Не удалось выполнить увеличение плавности видео: {first_error} (резервный режим: {error})") from error
                first_error = error
    finally:
        remove_partial(part_path)


def interpolate_with_rife(input_path: str, target_fps=60, output_path: str = None,
                          status_callback=None, is_cancelled_cb=None, model="rife-v4.6") -> str:
    fps = resolve_target_fps(input_path, target_fps)
    output_path = _interpolation_output(input_path, fps, output_path)
    rife_exe = get_rife_executable()
    model_path = get_rife_model_path(rife_exe, model) if rife_exe else None

    def fallback(reason):
        if is_cancelled_cb and is_cancelled_cb():
            return None
        if status_callback:
            status_callback(f"RIFE недоступен ({reason}); используется FFmpeg.")
        return interpolate_with_ffmpeg(input_path, fps, output_path,
                                       is_cancelled_cb=is_cancelled_cb, status_callback=status_callback)

    if not rife_exe or not model_path:
        return fallback("движок или модель не установлены")

    media_info = probe_media_info(input_path)
    source_fps = media_info["fps"] or get_video_fps(input_path)
    if not source_fps:
        return fallback("не удалось определить исходный FPS")
    if fps <= source_fps:
        return fallback("заданный FPS не превышает исходный")

    cache_dir = Path(get_cache_dir()).resolve()
    estimated_bytes = _estimate_rife_disk_bytes(
        media_info["width"], media_info["height"], media_info["duration"], source_fps, fps
    )
    if estimated_bytes is not None:
        try:
            free_bytes = shutil.disk_usage(cache_dir).free
            required_bytes = estimated_bytes + RIFE_DISK_SAFETY_MARGIN
            if free_bytes < required_bytes:
                need_gb = required_bytes / (1024 ** 3)
                free_gb = free_bytes / (1024 ** 3)
                return fallback(f"недостаточно места на диске для кадров (нужно ~{need_gb:.1f} ГБ, свободно {free_gb:.1f} ГБ)")
        except OSError:
            pass

    part_path = f"{output_path}.tmp.mp4"
    temp_dir = Path(tempfile.mkdtemp(prefix="aura_rife_", dir=cache_dir))
    frames_in, frames_out = temp_dir / "in", temp_dir / "out"
    frames_in.mkdir()
    frames_out.mkdir()
    fallback_reason = None
    try:
        if is_cancelled_cb and is_cancelled_cb():
            return None
        if status_callback:
            status_callback("Извлечение кадров для RIFE...")
        # Normalize variable frame rate before RIFE, whose directory input has no timestamps.
        extract = ["ffmpeg", "-y", "-i", input_path, "-map", "0:v:0", "-an",
                   "-vf", f"fps={_fps_text(source_fps)}", "-fps_mode", "passthrough",
                   str(frames_in / "frame_%08d.png")]
        if not run_ffmpeg_cancellable(extract, None, is_cancelled_cb):
            return None
        in_frame_files = list(frames_in.glob("frame_*.png"))
        frame_count = len(in_frame_files)
        if frame_count < 2:
            fallback_reason = "слишком мало кадров"
        else:
            duration = frame_count / source_fps
            target_count = max(2, int(round(duration * fps)))
            # Verify actual extracted frame size against remaining disk space before running RIFE.
            try:
                in_bytes = sum(p.stat().st_size for p in in_frame_files)
                needed_out_bytes = int(in_bytes * (target_count / max(1, frame_count)) * 1.2) + RIFE_DISK_SAFETY_MARGIN
                free_bytes = shutil.disk_usage(cache_dir).free
                if free_bytes < needed_out_bytes:
                    need_gb = needed_out_bytes / (1024 ** 3)
                    free_gb = free_bytes / (1024 ** 3)
                    raise RuntimeError(f"недостаточно места на диске (нужно ~{need_gb:.1f} ГБ, свободно {free_gb:.1f} ГБ)")
            except OSError:
                pass
            if status_callback:
                status_callback(f"RIFE {Path(model_path).name}: {frame_count} → {target_count} кадров ({fps:g} FPS)...")
            # -n is the total frame count, not FPS. Only v4 models support custom -n.
            command = [rife_exe, "-i", str(frames_in), "-o", str(frames_out),
                       "-m", model_path, "-n", str(target_count), "-f", "%08d.png"]
            with tempfile.TemporaryFile(mode="w+b") as err_file:
                proc = subprocess.Popen(command, cwd=str(Path(rife_exe).parent),
                                        startupinfo=get_startupinfo(), creationflags=CREATE_NO_WINDOW,
                                        stdout=subprocess.DEVNULL, stderr=err_file)
                while proc.poll() is None:
                    if is_cancelled_cb and is_cancelled_cb():
                        proc.terminate()
                        try:
                            proc.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=2)
                        return None
                    time.sleep(0.1)
                if proc.returncode:
                    err_file.seek(0, os.SEEK_END)
                    size = err_file.tell()
                    err_file.seek(max(0, size - 4096))
                    raise RuntimeError(err_file.read()[-1000:].decode(errors="replace").strip() or "ошибка движка")
            if is_cancelled_cb and is_cancelled_cb():
                return None
            if sum(1 for _ in frames_out.glob("*.png")) != target_count:
                raise RuntimeError("движок создал неполную последовательность кадров")
            if status_callback:
                status_callback(f"Сборка MP4 ({fps:g} FPS)...")
            # Optional audio comes straight from the original, including Opus and silent clips.
            merge = ["ffmpeg", "-y", "-framerate", _fps_text(fps), "-start_number", "1",
                     "-i", str(frames_out / "%08d.png"), "-i", input_path,
                     "-map", "0:v:0", "-map", "1:a:0?", "-c:a", "aac", "-b:a", "192k",
                     "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "faster",
                     "-t", str(duration), "-movflags", "+faststart", part_path]
            if not run_ffmpeg_cancellable(merge, part_path, is_cancelled_cb):
                return None
            if not os.path.isfile(part_path) or not os.path.getsize(part_path):
                raise RuntimeError("пустой результат сборки")
            if is_cancelled_cb and is_cancelled_cb():
                return None
            os.rename(part_path, output_path)
            return output_path
    except Exception as error:
        fallback_reason = str(error)
    finally:
        remove_partial(part_path)
        if temp_dir.resolve().parent == cache_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)

    if fallback_reason is not None:
        return fallback(fallback_reason)
    return None


def interpolate_video(input_path: str, target_fps=60, model: str = "auto", output_path: str = None,
                      status_callback=None, is_cancelled_cb=None) -> str:
    if not input_path or not os.path.isfile(input_path):
        raise FileNotFoundError("Исходное видео для интерполяции не найдено.")
    if is_cancelled_cb and is_cancelled_cb():
        return None
    fps = resolve_target_fps(input_path, target_fps)
    if model in ("auto", "rife", "rife-v4", "rife-v4.6"):
        return interpolate_with_rife(input_path, target_fps=fps, output_path=output_path,
                                     status_callback=status_callback, is_cancelled_cb=is_cancelled_cb, model=model)
    if model != "ffmpeg":
        raise ValueError(f"Неизвестная модель интерполяции: {model}")
    return interpolate_with_ffmpeg(input_path, target_fps=fps, output_path=output_path,
                                   is_cancelled_cb=is_cancelled_cb, status_callback=status_callback)
