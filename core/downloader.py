import os
import re
import time
import subprocess
from pathlib import Path
from PySide6.QtCore import QThread, Signal
import yt_dlp
from core.settings import settings
from core.cookies_helper import get_cookies_config
from core.media_converter import convert_to_gif, compress_to_target_size, crop_video
from core.interpolator import interpolate_video

def format_bytes(bytes_val):
    if bytes_val is None or bytes_val <= 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} TB"

def format_seconds(seconds_val):
    if seconds_val is None or seconds_val < 0:
        return "--:--"
    m, s = divmod(int(seconds_val), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def parse_time_str(time_str):
    if not time_str:
        return None
    time_str = time_str.strip()
    parts = time_str.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except Exception:
        return None
    return None

def detect_platform(url):
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "YouTube"
    elif "tiktok.com" in url_lower:
        return "TikTok"
    elif "instagram.com" in url_lower:
        return "Instagram"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "X / Twitter"
    elif "vk.com" in url_lower or "vkvideo.ru" in url_lower:
        return "VK Video"
    elif "twitch.tv" in url_lower:
        return "Twitch"
    elif "reddit.com" in url_lower:
        return "Reddit"
    elif "pinterest.com" in url_lower:
        return "Pinterest"
    return "Web Video"


DEFAULT_HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8',
    'Sec-Fetch-Mode': 'navigate',
}

DEFAULT_EXTRACTOR_ARGS = {
    'youtube': {
        'player_client': ['android', 'web', 'ios'],
    },
    'instagram': {
        'include_reels': True,
    }
}


class MetadataWorker(QThread):
    info_ready = Signal(dict)
    playlist_ready = Signal(dict)
    info_error = Signal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url.strip()
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        is_playlist_url = 'list=' in self.url or '/playlist' in self.url
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist' if is_playlist_url else False,
            'skip_download': True,
            'ignoreerrors': False,
            'geo_bypass': True,
            'http_headers': DEFAULT_HTTP_HEADERS,
            'extractor_args': DEFAULT_EXTRACTOR_ARGS,
        }
        cookies = get_cookies_config()
        if cookies:
            ydl_opts['cookiesfrombrowser'] = cookies

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if not info:
                    self.info_error.emit("Не удалось получить информацию о видео.")
                    return

                # Detect playlist with multiple entries
                if is_playlist_url and 'entries' in info and len(info['entries']) > 1:
                    entries = []
                    for e in info.get('entries', []):
                        if e:
                            vid = e.get('id')
                            v_url = e.get('url') or (f"https://www.youtube.com/watch?v={vid}" if vid else None)
                            entries.append({
                                'url': v_url,
                                'title': e.get('title', 'Без названия'),
                                'duration': e.get('duration', 0),
                                'duration_str': format_seconds(e.get('duration', 0)),
                                'thumbnail': e.get('thumbnail') or (f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else None),
                                'uploader': e.get('uploader') or e.get('channel') or info.get('uploader') or 'Автор'
                            })
                    valid_entries = [e for e in entries if e['url']]
                    if valid_entries and not self.is_cancelled:
                        self.playlist_ready.emit({
                            'title': info.get('title', 'Плейлист YouTube'),
                            'entries': valid_entries
                        })
                        return

                if 'entries' in info and info['entries']:
                    info = info['entries'][0]

                title = info.get('title', 'Без названия')
                uploader = info.get('uploader') or info.get('channel') or info.get('creator') or 'Неизвестный автор'
                duration = info.get('duration', 0)
                thumbnail = info.get('thumbnail')
                
                formats = info.get('formats', [])
                resolutions = set()
                has_video = False
                for f in formats:
                    if f.get('vcodec') != 'none' and f.get('height'):
                        has_video = True
                        h = f.get('height')
                        if h >= 2160:
                            resolutions.add('4K (2160p)')
                        elif h >= 1440:
                            resolutions.add('2K (1440p)')
                        elif h >= 1080:
                            resolutions.add('1080p Full HD')
                        elif h >= 720:
                            resolutions.add('720p HD')
                        elif h >= 480:
                            resolutions.add('480p')
                        elif h >= 360:
                            resolutions.add('360p')

                res_order = ['4K (2160p)', '2K (1440p)', '1080p Full HD', '720p HD', '480p', '360p']
                available_res = [r for r in res_order if r in resolutions]

                platform = detect_platform(self.url)

                width = info.get('width')
                height = info.get('height')
                if not width or not height:
                    for f in reversed(formats):
                        if f.get('width') and f.get('height'):
                            width = f.get('width')
                            height = f.get('height')
                            break

                # Extract playable direct stream URL for instant in-app player preview
                direct_url = info.get('url')
                if not direct_url and formats:
                    for f in reversed(formats):
                        if f.get('url') and f.get('ext') == 'mp4' and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                            direct_url = f.get('url')
                            break
                    if not direct_url:
                        for f in reversed(formats):
                            if f.get('url') and f.get('ext') == 'mp4' and f.get('vcodec') != 'none':
                                direct_url = f.get('url')
                                break
                    if not direct_url and formats:
                        direct_url = formats[-1].get('url')

                result = {
                    'url': self.url,
                    'direct_url': direct_url,
                    'playable_url': direct_url or self.url,
                    'title': title,
                    'uploader': uploader,
                    'duration': duration,
                    'duration_str': format_seconds(duration) if duration else "--:--",
                    'thumbnail': thumbnail,
                    'platform': platform,
                    'available_res': available_res,
                    'has_video': has_video,
                    'width': width or 1920,
                    'height': height or 1080
                }
                if not self.is_cancelled:
                    self.info_ready.emit(result)
        except Exception as e:
            if self.is_cancelled:
                return
            err_msg = str(e)
            if "Unsupported URL" in err_msg:
                err_msg = "Неподдерживаемая ссылка или ресурс недоступен."
            elif "Private video" in err_msg:
                err_msg = "Приватное видео (включите Cookies браузера в настройках)."
            elif "Sign in" in err_msg or "login" in err_msg.lower():
                err_msg = "Требуется авторизация (включите Cookies браузера в настройках)."
            elif "rate-limit" in err_msg.lower() or "429" in err_msg:
                err_msg = "Ограничение частоты запросов. Попробуйте через минуту или включите Cookies."
            self.info_error.emit(err_msg)


class DownloadWorker(QThread):
    progress_updated = Signal(dict)
    download_completed = Signal(dict)
    download_error = Signal(str)
    status_message = Signal(str)

    def __init__(self, url, options, save_dir):
        super().__init__()
        self.url = url
        self.options = options
        self.save_dir = save_dir
        self.is_cancelled = False
        self._last_filename = None
        self._downloaded_size = 0
        self._total_size = 0

    def cancel(self):
        self.is_cancelled = True

    def _progress_hook(self, d):
        if self.is_cancelled:
            raise Exception("Загрузка отменена пользователем.")

        status = d.get('status')
        if status == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            speed = d.get('speed') or 0
            eta = d.get('eta') or 0

            percent = 0.0
            if total > 0:
                percent = (downloaded / total) * 100.0

            self._downloaded_size = downloaded
            self._total_size = total

            self.progress_updated.emit({
                'percent': percent,
                'speed_str': f"{format_bytes(speed)}/s" if speed else "-- KB/s",
                'eta_str': format_seconds(eta),
                'downloaded_str': format_bytes(downloaded),
                'total_str': format_bytes(total) if total > 0 else "...",
                'status': 'downloading'
            })
            if d.get('filename'):
                self._last_filename = d.get('filename')

        elif status == 'finished':
            self.progress_updated.emit({
                'percent': 100.0,
                'speed_str': "0 KB/s",
                'eta_str': "00:00",
                'downloaded_str': format_bytes(self._total_size or self._downloaded_size),
                'total_str': format_bytes(self._total_size or self._downloaded_size),
                'status': 'processing'
            })
            self.status_message.emit("Обработка и объединение потоков (FFmpeg)...")
            if d.get('filename'):
                self._last_filename = d.get('filename')

    def run(self):
        try:
            mode = self.options.get('mode', 'best')
            audio_fmt = self.options.get('audio_fmt', 'mp3').lower()
            audio_q = self.options.get('audio_q', '320')
            target_res = self.options.get('res')
            trim_enabled = self.options.get('trim_enabled', False)
            trim_start = self.options.get('trim_start', '')
            trim_end = self.options.get('trim_end', '')

            os.makedirs(self.save_dir, exist_ok=True)
            out_template = os.path.join(self.save_dir, '%(title)s [%(id)s].%(ext)s')

            ydl_opts = {
                'outtmpl': out_template,
                'progress_hooks': [self._progress_hook],
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': False,
                'windowsfilenames': True,
                'overwrites': True,
                'geo_bypass': True,
                'http_headers': DEFAULT_HTTP_HEADERS,
                'extractor_args': DEFAULT_EXTRACTOR_ARGS,
            }

            cookies = get_cookies_config()
            if cookies:
                ydl_opts['cookiesfrombrowser'] = cookies

            # Trimmer section
            if trim_enabled and (trim_start or trim_end):
                start_sec = parse_time_str(trim_start) or 0
                end_sec = parse_time_str(trim_end)
                if end_sec is not None and end_sec > start_sec:
                    ydl_opts['download_ranges'] = yt_dlp.utils.download_range_func(None, [(start_sec, end_sec)])
                elif start_sec > 0:
                    ydl_opts['download_ranges'] = yt_dlp.utils.download_range_func(None, [(start_sec, float('inf'))])

            # Subtitle support
            download_subs = self.options.get('download_subs', settings.get('download_subtitles', False))
            if download_subs:
                ydl_opts.update({
                    'writesubtitles': True,
                    'writeautomaticsub': True,
                    'subtitleslangs': settings.get('subtitles_langs', ['ru', 'en']),
                    'subtitlesformat': 'srt/best',
                })

            if mode == 'audio_only':
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [
                        {
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': audio_fmt,
                            'preferredquality': audio_q,
                        },
                        {
                            'key': 'FFmpegMetadata',
                            'add_metadata': True,
                        }
                    ],
                })
            elif mode == 'video_only':
                if target_res:
                    height_match = re.search(r'(\d+)p', target_res)
                    h = height_match.group(1) if height_match else '1080'
                    ydl_opts['format'] = f'bestvideo[height<={h}][vcodec^=avc1]/bestvideo[height<={h}][ext=mp4]/bestvideo[height<={h}]/bestvideo'
                else:
                    ydl_opts['format'] = 'bestvideo[vcodec^=avc1]/bestvideo[ext=mp4]/bestvideo'
            elif mode == 'custom' and target_res:
                height_match = re.search(r'(\d+)p', target_res)
                h = height_match.group(1) if height_match else '1080'
                ydl_opts.update({
                    'format': f'bestvideo[height<={h}][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={h}]+bestaudio/best[height<={h}]/best',
                    'merge_output_format': 'mp4',
                    'postprocessors': [{'key': 'FFmpegMetadata', 'add_metadata': True}]
                })
            elif mode == 'gif':
                ydl_opts.update({
                    'format': 'bestvideo[height<=720][vcodec^=avc1]/bestvideo[height<=720]/best',
                    'merge_output_format': 'mp4',
                })
            elif mode == 'discord_8mb' or mode == 'telegram_50mb':
                ydl_opts.update({
                    'format': 'bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
                    'merge_output_format': 'mp4',
                    'postprocessors': [{'key': 'FFmpegMetadata', 'add_metadata': True}]
                })
            else:
                # Default "Best" MP4 with H.264 priority for universal compatibility
                ydl_opts.update({
                    'format': 'bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[vcodec^=avc]+bestaudio/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
                    'merge_output_format': 'mp4',
                    'postprocessors': [{'key': 'FFmpegMetadata', 'add_metadata': True}]
                })

            self.status_message.emit("Запуск загрузки...")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=True)
                if not info:
                    raise Exception("Не удалось скачать видео.")

                final_path = ydl.prepare_filename(info)
                if mode == 'audio_only':
                    base, _ = os.path.splitext(final_path)
                    final_path = f"{base}.{audio_fmt}"
                elif mode != 'video_only' and ydl_opts.get('merge_output_format'):
                    base, _ = os.path.splitext(final_path)
                    final_path = f"{base}.{ydl_opts['merge_output_format']}"

                if not os.path.exists(final_path) and self._last_filename and os.path.exists(self._last_filename):
                    final_path = self._last_filename

                # GIF post processing
                if mode == 'gif' and os.path.exists(final_path):
                    self.status_message.emit("Конвертация в GIF...")
                    gif_path = convert_to_gif(final_path)
                    if gif_path != final_path:
                        try:
                            os.remove(final_path)
                        except Exception:
                            pass
                    final_path = gif_path

                # Discord compression post processing
                elif mode == 'discord_8mb' and os.path.exists(final_path):
                    self.status_message.emit("Сжатие для Discord (< 8 МБ)...")
                    comp_path = compress_to_target_size(final_path, target_mb=7.8)
                    if comp_path != final_path:
                        try:
                            os.remove(final_path)
                        except Exception:
                            pass
                    final_path = comp_path

                # Crop post processing
                crop_enabled = self.options.get('crop_enabled', False)
                crop_params = self.options.get('crop_params')
                if crop_enabled and crop_params and mode != 'audio_only' and os.path.exists(final_path):
                    self.status_message.emit("Кадрирование видео (FFmpeg Crop)...")
                    cropped_path = crop_video(final_path, crop_params)
                    if cropped_path != final_path:
                        try:
                            os.remove(final_path)
                        except Exception:
                            pass
                    final_path = cropped_path

                # Smooth FPS post processing
                smooth_enabled = self.options.get('smooth_enabled', False)
                smooth_fps = self.options.get('smooth_fps', 60)
                smooth_model = self.options.get('smooth_model', 'auto')
                if smooth_enabled and mode not in ['audio_only', 'gif'] and os.path.exists(final_path):
                    self.status_message.emit(f"AI Увеличение плавности ({smooth_fps} FPS)...")
                    smooth_path = interpolate_video(
                        final_path,
                        target_fps=smooth_fps,
                        model=smooth_model,
                        status_callback=lambda msg: self.status_message.emit(msg.upper())
                    )
                    if smooth_path != final_path:
                        try:
                            os.remove(final_path)
                        except Exception:
                            pass
                    final_path = smooth_path

                file_size = os.path.getsize(final_path) if os.path.exists(final_path) else 0
                title = info.get('title', Path(final_path).stem if final_path else 'Скачанный файл')
                thumbnail = info.get('thumbnail')

                self.download_completed.emit({
                    'title': title,
                    'url': self.url,
                    'file_path': final_path,
                    'file_size': file_size,
                    'file_size_str': format_bytes(file_size),
                    'thumbnail': thumbnail,
                    'mode': mode
                })

        except Exception as e:
            if not self.is_cancelled:
                self.download_error.emit(str(e))
