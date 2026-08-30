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
    clean = file_path.strip().strip('"').strip("'")
    if not os.path.isfile(clean):
        return False
    ext = os.path.splitext(clean)[1].lower()
    return ext in VIDEO_EXTENSIONS

def get_local_media_info(file_path: str) -> dict:
    file_path = file_path.strip().strip('"').strip("'")
    if not os.path.exists(file_path):
        return None

    try:
        duration = get_video_duration(file_path)
        width, height = get_video_dimensions(file_path)
        fps = get_video_fps(file_path)
        size = os.path.getsize(file_path)

        # Generate thumbnail frame
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

        return {
            'url': file_path,
            'file_path': file_path,
            'is_local': True,
            'title': Path(file_path).name,
            'uploader': f"Локальное видео ({width}×{height}, {int(round(fps))} FPS)",
            'duration': int(duration),
            'duration_str': format_seconds(duration) if duration else "--:--",
            'thumbnail': thumb_path if os.path.exists(thumb_path) else None,
            'platform': 'Local Video',
            'available_res': [f"{width}x{height}"],
            'has_video': True,
            'width': width,
            'height': height,
            'fps': fps,
            'file_size': size,
            'file_size_str': format_bytes(size)
        }
    except Exception as e:
        print(f"Error getting local media info: {e}")
        return None


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
            if not os.path.exists(self.file_path):
                raise Exception("Исходный файл не найден.")

            os.makedirs(self.save_dir, exist_ok=True)
            mode = self.options.get('mode', 'best')
            audio_fmt = self.options.get('audio_fmt', 'mp3').lower()
            trim_enabled = self.options.get('trim_enabled', False)
            trim_start = self.options.get('trim_start', '')
            trim_end = self.options.get('trim_end', '')
            crop_enabled = self.options.get('crop_enabled', False)
            crop_params = self.options.get('crop_params')
            smooth_enabled = self.options.get('smooth_enabled', False)
            smooth_fps = self.options.get('smooth_fps', 60)
            smooth_model = self.options.get('smooth_model', 'auto')

            base_name = Path(self.file_path).stem
            current_path = self.file_path

            self.status_message.emit("Подготовка видео к обработке...")
            self.progress_updated.emit({
                'percent': 10.0,
                'speed_str': "SSD",
                'eta_str': "00:05",
                'downloaded_str': "0 MB",
                'total_str': format_bytes(os.path.getsize(self.file_path)),
                'status': 'processing'
            })

            # 1. Trimming if enabled
            if trim_enabled and (trim_start or trim_end):
                self.status_message.emit("Обрезка фрагмента по таймкодам...")
                start_sec = parse_time_str(trim_start) or 0
                end_sec = parse_time_str(trim_end)

                trimmed_path = os.path.join(self.save_dir, f"{base_name}_trim.mp4")
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

            self.progress_updated.emit({'percent': 35.0, 'status': 'processing'})

            # 2. Cropping if enabled
            if crop_enabled and crop_params and mode != 'audio_only':
                self.status_message.emit("Кадрирование области кадра (Crop)...")
                cropped_path = crop_video(current_path, crop_params)
                if cropped_path != current_path:
                    if current_path != self.file_path:
                        try:
                            os.remove(current_path)
                        except Exception:
                            pass
                    current_path = cropped_path

            self.progress_updated.emit({'percent': 60.0, 'status': 'processing'})

            # 3. Smooth FPS if enabled
            if smooth_enabled and mode not in ['audio_only', 'gif']:
                self.status_message.emit(f"AI Увеличение плавности ({smooth_fps} FPS)...")
                smooth_path = interpolate_video(
                    current_path,
                    target_fps=smooth_fps,
                    model=smooth_model,
                    status_callback=lambda msg: self.status_message.emit(msg.upper())
                )
                if smooth_path != current_path:
                    if current_path != self.file_path:
                        try:
                            os.remove(current_path)
                        except Exception:
                            pass
                    current_path = smooth_path

            self.progress_updated.emit({'percent': 85.0, 'status': 'processing'})

            # 4. Mode formatting
            out_file = os.path.join(self.save_dir, f"{base_name}_studio_{mode}.mp4")

            if mode == 'audio_only':
                self.status_message.emit(f"Извлечение аудио [{audio_fmt.upper()}]...")
                out_audio = os.path.join(self.save_dir, f"{base_name}.{audio_fmt}")
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
                self.status_message.emit("Конвертация в GIF...")
                gif_path = convert_to_gif(current_path)
                final_output = gif_path

            elif mode == 'discord_8mb':
                self.status_message.emit("Сжатие под лимит Discord (< 8 МБ)...")
                comp_path = compress_to_target_size(current_path, target_mb=7.8)
                final_output = comp_path

            elif mode == 'video_only':
                self.status_message.emit("Удаление аудиодорожки...")
                out_no_audio = os.path.join(self.save_dir, f"{base_name}_mute.mp4")
                subprocess.run(
                    ["ffmpeg", "-y", "-i", current_path, "-c:v", "copy", "-an", out_no_audio],
                    startupinfo=get_startupinfo(),
                    creationflags=CREATE_NO_WINDOW,
                    check=True
                )
                final_output = out_no_audio

            else:
                # Best / Standard
                if current_path == self.file_path:
                    # Make a copy or export to save_dir
                    final_output = os.path.join(self.save_dir, f"{base_name}_aura.mp4")
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", current_path, "-c", "copy", final_output],
                        startupinfo=get_startupinfo(),
                        creationflags=CREATE_NO_WINDOW,
                        check=True
                    )
                else:
                    final_output = current_path

            # Clean temporary intermediates
            if current_path != self.file_path and current_path != final_output:
                try:
                    os.remove(current_path)
                except Exception:
                    pass

            file_size = os.path.getsize(final_output) if os.path.exists(final_output) else 0

            self.progress_updated.emit({
                'percent': 100.0,
                'speed_str': "SSD",
                'eta_str': "00:00",
                'downloaded_str': format_bytes(file_size),
                'total_str': format_bytes(file_size),
                'status': 'finished'
            })

            self.download_completed.emit({
                'title': Path(final_output).stem,
                'url': self.file_path,
                'file_path': final_output,
                'file_size': file_size,
                'file_size_str': format_bytes(file_size),
                'thumbnail': None,
                'mode': f"Studio ({mode.upper()})"
            })

        except Exception as e:
            if not self.is_cancelled:
                self.download_error.emit(str(e))
