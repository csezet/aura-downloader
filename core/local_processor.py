import os
import subprocess
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from core.downloader import format_bytes, format_seconds
from core.media_converter import (
    convert_to_gif, compress_to_target_size,
    get_video_dimensions, get_video_duration, get_unique_path, run_ffmpeg_cancellable,
    get_ffmpeg_path, transform_video, extract_audio
)
from core.interpolator import interpolate_video, get_video_fps
from core.temp_files import get_cache_dir, OwnedDirectory, remove_owned_directory

CREATE_NO_WINDOW = 0x08000000

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.flv', '.wmv', '.m4v', '.ts'}

def get_startupinfo():
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo

def is_video_file(file_path: str) -> bool:
    if not file_path or not isinstance(file_path, str):
        return False
    clean = file_path.strip().strip('"').strip("'").strip()
    if not os.path.isfile(clean):
        return False
    ext = os.path.splitext(clean)[1].lower()
    return ext in VIDEO_EXTENSIONS

def get_local_media_info(file_path: str) -> dict:
    if not file_path:
        return None
    file_path = file_path.strip().strip('"').strip("'").strip()
    if not os.path.exists(file_path):
        return None

    try:
        duration = get_video_duration(file_path)
    except Exception:
        duration = None

    try:
        width, height = get_video_dimensions(file_path)
    except Exception:
        width, height = None, None

    try:
        fps = get_video_fps(file_path)
    except Exception:
        fps = None

    try:
        size = os.path.getsize(file_path)
    except Exception:
        size = 0

    thumb_path = None
    try:
        temp_dir = get_cache_dir()
        thumb_path = os.path.join(temp_dir, f"aura_thumb_{abs(hash(file_path))}.jpg")
        seek_sec = "00:00:00.5" if (duration and duration > 1) else "00:00:00"
        cmd = [
            get_ffmpeg_path(), "-y",
            "-ss", seek_sec,
            "-i", file_path,
            "-vframes", "1",
            "-q:v", "2",
            thumb_path
        ]
        subprocess.run(
            cmd,
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10
        )
        if not os.path.exists(thumb_path):
            thumb_path = None
    except Exception:
        thumb_path = None

    dims_str = f"{width}×{height}" if (width and height) else "Разрешение неизвестно"
    fps_str = f", {int(round(fps))} FPS" if fps else ""

    return {
        'url': file_path,
        'file_path': file_path,
        'is_local': True,
        'title': Path(file_path).name,
        'uploader': f"Локальное видео ({dims_str}{fps_str})",
        'duration': duration or 0,
        'duration_str': format_seconds(duration) if duration else "--:--",
        'thumbnail': thumb_path,
        'platform': 'Local Video',
        'available_res': ([f"{width}x{height}"] + [f"{p}p" for p in (2160, 1440, 1080, 720, 480, 360)
                          if p < height]) if (width and height) else [],
        'has_video': True,
        'width': width,
        'height': height,
        'fps': fps,
        'file_size': size,
        'file_size_str': format_bytes(size)
    }



def process_single_local_file(file_path: str, options: dict, save_dir: str, status_cb=None, progress_cb=None, is_cancelled_cb=None) -> dict:
    if not os.path.isfile(file_path):
        raise FileNotFoundError("Исходный файл не найден.")
    mode = options.get("mode", "best")
    if mode not in ("best", "custom", "video_only", "audio_only", "gif", "discord_8mb", "telegram_50mb"):
        raise ValueError(f"Неизвестный режим: {mode}")
    cancelled = is_cancelled_cb or (lambda: False)
    if cancelled():
        return None
    os.makedirs(save_dir, exist_ok=True)
    base_name = Path(file_path).stem
    session = OwnedDirectory(save_dir, ".aura_staging_", "staging")
    final_output = None

    def report(message, percent):
        if status_cb:
            status_cb(message)
        if progress_cb:
            progress_cb({"percent": percent, "speed_str": "ОБРАБОТКА", "eta_str": "--:--",
                         "downloaded_str": "", "total_str": "", "status": "processing"})

    try:
        report(f"Подготовка {base_name}...", 0)
        if mode == "audio_only":
            audio_fmt = str(options.get("audio_fmt", "mp3")).lower()
            report(f"Извлечение аудио [{audio_fmt.upper()}]...", 20)
            current = extract_audio(file_path, audio_fmt, options,
                                    str(session.path / f"{base_name}.{audio_fmt}"), cancelled)
        else:
            report("Обрезка, кадрирование и подготовка видео...", 20)
            current = transform_video(file_path, options,
                                      str(session.path / f"{base_name}_aura.mp4"), cancelled)
            if not current or cancelled():
                return None
            if options.get("smooth_enabled") and mode != "gif":
                report("Увеличение плавности...", 50)
                current = interpolate_video(current, target_fps=options.get("smooth_fps", 60),
                                            model=options.get("smooth_model", "auto"),
                                            status_callback=status_cb, is_cancelled_cb=cancelled)
            if not current or cancelled():
                return None
            if mode == "gif":
                report("Конвертация в GIF...", 75)
                current = convert_to_gif(current, output_path=str(session.path / f"{base_name}.gif"),
                                         is_cancelled_cb=cancelled)
            elif mode in ("discord_8mb", "telegram_50mb"):
                limit = 7.8 if mode == "discord_8mb" else 49.0
                report(f"Сжатие до {limit:g} МБ...", 75)
                current = compress_to_target_size(current, target_mb=limit,
                                                  output_path=str(session.path / f"{base_name}_compressed.mp4"),
                                                  is_cancelled_cb=cancelled)
        if not current or cancelled():
            return None
        report("Сохранение результата...", 95)
        # Windows rename refuses to overwrite a file that appeared after path selection.
        while True:
            destination = get_unique_path(os.path.join(save_dir, Path(current).name))
            try:
                os.rename(current, destination)
                final_output = destination
                break
            except FileExistsError:
                continue
        if cancelled():
            os.remove(final_output)
            final_output = None
            return None
        file_size = os.path.getsize(final_output)
        if progress_cb:
            progress_cb({"percent": 100.0, "speed_str": "ГОТОВО", "eta_str": "00:00",
                         "downloaded_str": format_bytes(file_size), "total_str": format_bytes(file_size),
                         "status": "finished"})
        return {"title": Path(final_output).stem, "url": file_path, "file_path": final_output,
                "file_size": file_size, "file_size_str": format_bytes(file_size),
                "thumbnail": None, "mode": f"Studio ({mode.upper()})"}
    finally:
        session.release()
        remove_owned_directory(session.path, save_dir, "staging")


class LocalProcessWorker(QThread):
    progress_updated = Signal(dict)
    download_completed = Signal(dict)
    download_error = Signal(str)
    status_message = Signal(str)

    def __init__(self, file_path: str, options: dict, save_dir: str):
        super().__init__()
        self.file_path = file_path.strip().strip('"').strip("'")
        self.options = options
        self.save_dir = save_dir
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        try:
            res = process_single_local_file(
                self.file_path,
                self.options,
                self.save_dir,
                status_cb=self.status_message.emit,
                progress_cb=self.progress_updated.emit,
                is_cancelled_cb=lambda: self.is_cancelled
            )
            if res and not self.is_cancelled:
                self.progress_updated.emit({
                    'percent': 100.0,
                    'speed_str': "SSD",
                    'eta_str': "00:00",
                    'downloaded_str': res.get('file_size_str', ''),
                    'total_str': res.get('file_size_str', ''),
                    'status': 'finished'
                })
                self.download_completed.emit(res)
        except Exception as e:
            if not self.is_cancelled:
                self.download_error.emit(str(e))


# UnifiedBatchWorker replaces the legacy local-only batch worker
from core.unified_batch_worker import UnifiedBatchWorker as LocalBatchProcessWorker
