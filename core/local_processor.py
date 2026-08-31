import os
import sys
import tempfile
import subprocess
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from core.downloader import format_bytes, format_seconds, parse_time_str
from core.media_converter import convert_to_gif, compress_to_target_size, crop_video, get_video_dimensions, get_video_duration
from core.interpolator import interpolate_video, get_video_fps

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
        duration = get_video_duration(file_path) or 0
    except Exception:
        duration = 0

    try:
        width, height = get_video_dimensions(file_path)
    except Exception:
        width, height = 1920, 1080

    try:
        fps = get_video_fps(file_path) or 30.0
    except Exception:
        fps = 30.0

    try:
        size = os.path.getsize(file_path)
    except Exception:
        size = 0

    thumb_path = None
    try:
        temp_dir = tempfile.gettempdir()
        thumb_path = os.path.join(temp_dir, f"aura_thumb_{abs(hash(file_path))}.jpg")
        seek_sec = "00:00:00.5" if duration > 1 else "00:00:00"
        cmd = [
            "ffmpeg", "-y",
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
            stderr=subprocess.PIPE
        )
        if not os.path.exists(thumb_path):
            thumb_path = None
    except Exception:
        thumb_path = None

    return {
        'url': file_path,
        'file_path': file_path,
        'is_local': True,
        'title': Path(file_path).name,
        'uploader': f"Локальное видео ({width}×{height}, {int(round(fps))} FPS)",
        'duration': duration,
        'duration_str': format_seconds(duration) if duration else "--:--",
        'thumbnail': thumb_path,
        'platform': 'Local Video',
        'available_res': [f"{width}x{height}"],
        'has_video': True,
        'width': width,
        'height': height,
        'fps': fps,
        'file_size': size,
        'file_size_str': format_bytes(size)
    }


def process_single_local_file(file_path: str, options: dict, save_dir: str, status_cb=None, progress_cb=None, is_cancelled_cb=None) -> dict:
    if not os.path.exists(file_path):
        raise Exception("Исходный файл не найден.")

    os.makedirs(save_dir, exist_ok=True)
    mode = options.get('mode', 'best')
    audio_fmt = options.get('audio_fmt', 'mp3').lower()
    trim_enabled = options.get('trim_enabled', False)
    trim_start = options.get('trim_start', '')
    trim_end = options.get('trim_end', '')
    crop_enabled = options.get('crop_enabled', False)
    crop_params = options.get('crop_params')
    smooth_enabled = options.get('smooth_enabled', False)
    smooth_fps = options.get('smooth_fps', 60)
    smooth_model = options.get('smooth_model', 'auto')

    base_name = Path(file_path).stem
    current_path = file_path

    if status_cb:
        status_cb(f"Подготовка {base_name}...")

    # 1. Trimming
    if trim_enabled and (trim_start or trim_end):
        if is_cancelled_cb and is_cancelled_cb():
            return None
        if status_cb:
            status_cb(f"Обрезка фрагмента {base_name}...")
        start_sec = parse_time_str(trim_start) or 0
        end_sec = parse_time_str(trim_end)

        trimmed_path = os.path.join(save_dir, f"{base_name}_trim.mp4")
        cmd = ["ffmpeg", "-y"]
        if start_sec > 0:
            cmd.extend(["-ss", str(start_sec)])
        if end_sec is not None and end_sec > start_sec:
            cmd.extend(["-to", str(end_sec)])
        cmd.extend(["-i", current_path, "-c:v", "libx264", "-crf", "18", "-preset", "faster", "-c:a", "copy", trimmed_path])

        subprocess.run(
            cmd,
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        current_path = trimmed_path

    # 2. Cropping
    if crop_enabled and crop_params and mode != 'audio_only':
        if is_cancelled_cb and is_cancelled_cb():
            return None
        if status_cb:
            status_cb(f"Кадрирование {base_name} (Crop)...")
        cropped_path = crop_video(current_path, crop_params)
        if cropped_path != current_path:
            if current_path != file_path:
                try:
                    os.remove(current_path)
                except Exception:
                    pass
            current_path = cropped_path

    # 3. Smooth FPS
    if smooth_enabled and mode not in ['audio_only', 'gif']:
        if is_cancelled_cb and is_cancelled_cb():
            return None
        if status_cb:
            status_cb(f"AI Увеличение плавности {base_name} ({smooth_fps} FPS)...")
        smooth_path = interpolate_video(
            current_path,
            target_fps=smooth_fps,
            model=smooth_model,
            status_callback=lambda msg: status_cb(msg.upper()) if status_cb else None
        )
        if smooth_path != current_path:
            if current_path != file_path:
                try:
                    os.remove(current_path)
                except Exception:
                    pass
            current_path = smooth_path

    # 4. Mode formatting
    if mode == 'audio_only':
        if status_cb:
            status_cb(f"Извлечение аудио [{audio_fmt.upper()}] {base_name}...")
        out_audio = os.path.join(save_dir, f"{base_name}.{audio_fmt}")
        cmd = ["ffmpeg", "-y", "-i", current_path, "-vn"]
        if audio_fmt == 'mp3':
            cmd.extend(["-c:a", "libmp3lame", "-b:a", "320k"])
        elif audio_fmt == 'flac':
            cmd.extend(["-c:a", "flac"])
        elif audio_fmt == 'm4a':
            cmd.extend(["-c:a", "aac", "-b:a", "256k"])
        elif audio_fmt == 'wav':
            cmd.extend(["-c:a", "pcm_s16le"])
        else:
            cmd.extend(["-c:a", "copy"])
        cmd.append(out_audio)

        subprocess.run(cmd, startupinfo=get_startupinfo(), creationflags=CREATE_NO_WINDOW, check=True)
        final_output = out_audio

    elif mode == 'gif':
        if status_cb:
            status_cb(f"Конвертация {base_name} в GIF...")
        gif_path = convert_to_gif(current_path)
        final_output = gif_path

    elif mode == 'discord_8mb':
        if status_cb:
            status_cb(f"Сжатие {base_name} для Discord (< 8 МБ)...")
        comp_path = compress_to_target_size(current_path, target_mb=7.8)
        final_output = comp_path

    elif mode == 'video_only':
        if status_cb:
            status_cb(f"Удаление аудиодорожки {base_name}...")
        out_no_audio = os.path.join(save_dir, f"{base_name}_mute.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-i", current_path, "-c:v", "copy", "-an", out_no_audio],
            startupinfo=get_startupinfo(),
            creationflags=CREATE_NO_WINDOW,
            check=True
        )
        final_output = out_no_audio

    else:
        # Best / Standard
        if current_path == file_path:
            final_output = os.path.join(save_dir, f"{base_name}_aura.mp4")
            subprocess.run(
                ["ffmpeg", "-y", "-i", current_path, "-c", "copy", final_output],
                startupinfo=get_startupinfo(),
                creationflags=CREATE_NO_WINDOW,
                check=True
            )
        else:
            final_output = current_path

    # Clean intermediate
    if current_path != file_path and current_path != final_output:
        try:
            os.remove(current_path)
        except Exception:
            pass

    file_size = os.path.getsize(final_output) if os.path.exists(final_output) else 0

    return {
        'title': Path(final_output).stem,
        'url': file_path,
        'file_path': final_output,
        'file_size': file_size,
        'file_size_str': format_bytes(file_size),
        'thumbnail': None,
        'mode': f"Studio ({mode.upper()})"
    }


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


class LocalBatchProcessWorker(QThread):
    progress_updated = Signal(dict)
    item_completed = Signal(dict)
    batch_completed = Signal(list)
    download_error = Signal(str)
    status_message = Signal(str)

    def __init__(self, items: list, fallback_options: dict, save_dir: str):
        super().__init__()
        self.items = items
        self.fallback_options = fallback_options
        self.save_dir = save_dir
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        results = []
        total = len(self.items)
        try:
            for idx, item in enumerate(self.items):
                if self.is_cancelled:
                    break

                if isinstance(item, dict):
                    path = (item.get('url') or item.get('file_path', '')).strip().strip('"').strip("'")
                    opts = item.get('options') or self.fallback_options
                elif isinstance(item, tuple):
                    path = item[0].strip().strip('"').strip("'")
                    opts = item[1] or self.fallback_options
                else:
                    path = str(item).strip().strip('"').strip("'")
                    opts = self.fallback_options

                self.status_message.emit(f"[{idx+1}/{total}] ОБРАБОТКА: {Path(path).name}")
                base_pct = (idx / total) * 100.0
                self.progress_updated.emit({
                    'percent': base_pct,
                    'speed_str': f"{idx+1}/{total}",
                    'eta_str': "--:--",
                    'downloaded_str': f"{idx}/{total}",
                    'total_str': f"{total} файлов",
                    'status': 'processing'
                })

                res = process_single_local_file(
                    path,
                    opts,
                    self.save_dir,
                    status_cb=lambda msg: self.status_message.emit(f"[{idx+1}/{total}] {msg}"),
                    is_cancelled_cb=lambda: self.is_cancelled
                )
                if res:
                    results.append(res)
                    self.item_completed.emit(res)

            if not self.is_cancelled:
                self.progress_updated.emit({
                    'percent': 100.0,
                    'speed_str': "SSD",
                    'eta_str': "00:00",
                    'downloaded_str': f"{len(results)}/{total}",
                    'total_str': f"{total} файлов",
                    'status': 'finished'
                })
                self.batch_completed.emit(results)
        except Exception as e:
            if not self.is_cancelled:
                self.download_error.emit(str(e))
