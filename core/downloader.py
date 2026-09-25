import os
import re
import time
import subprocess
import shutil
import requests
from pathlib import Path
from PySide6.QtCore import QThread, Signal
import yt_dlp
from yt_dlp.extractor.instagram import InstagramIE
from core.settings import settings
from core.cookies_helper import get_cookies_config
import tempfile
from core.media_converter import (
    convert_to_gif, compress_to_target_size, crop_video, get_unique_path,
    get_unique_base_for_group, get_video_duration, probe_video_stream, get_ffmpeg_path
)
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
    'instagram': {
        'include_reels': True,
    }
}


class MetadataWorker(QThread):
    info_ready = Signal(dict)
    playlist_ready = Signal(dict)
    gallery_ready = Signal(dict)
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

        # Specialized Instagram carousel & photo extraction
        if 'instagram.com' in self.url.lower():
            clean_ig_url = re.sub(r'\?.*$', '', self.url)
            urls_to_try = [self.url]
            if clean_ig_url != self.url:
                urls_to_try.append(clean_ig_url)

            for try_url in urls_to_try:
                for with_cookies in [True, False]:
                    try:
                        cur_opts = dict(ydl_opts)
                        if not with_cookies and 'cookiesfrombrowser' in cur_opts:
                            del cur_opts['cookiesfrombrowser']
                        with yt_dlp.YoutubeDL(cur_opts) as ydl_inst:
                            ie = InstagramIE(ydl_inst)
                            info = ie.extract(try_url)
                            if not info:
                                continue

                            entries = list(info.get('entries') or [])
                            # 1. Multi-item Carousel (2+ photos/videos)
                            if len(entries) > 1:
                                items = []
                                for idx, e in enumerate(entries):
                                    is_vid = bool(e.get('formats'))
                                    thumbs = e.get('thumbnails', [])
                                    best_img = thumbs[-1]['url'] if thumbs else None
                                    preview_thumb = thumbs[0]['url'] if thumbs else best_img
                                    vid_url = e.get('formats', [])[-1].get('url') if is_vid else None
                                    items.append({
                                        'id': e.get('id', f'item_{idx+1}'),
                                        'index': idx + 1,
                                        'is_video': is_vid,
                                        'media_type': 'video' if is_vid else 'photo',
                                        'url': vid_url if is_vid else best_img,
                                        'best_image': best_img,
                                        'thumbnail': preview_thumb,
                                        'title': e.get('title') or f"Instagram Фото #{idx+1}",
                                        'uploader': info.get('uploader') or info.get('channel') or 'Instagram',
                                    })
                                if not self.is_cancelled:
                                    self.gallery_ready.emit({
                                        'title': info.get('title', 'Галерея Instagram'),
                                        'uploader': info.get('uploader') or info.get('channel') or 'Instagram',
                                        'items': items
                                    })
                                    return

                            # 2. Single photo item (or single item inside entries)
                            target_entry = entries[0] if entries else info
                            is_vid = bool(target_entry.get('formats'))
                            thumbs = target_entry.get('thumbnails', [])
                            if not is_vid and thumbs:
                                best_img = thumbs[-1]['url']
                                uploader = info.get('uploader') or target_entry.get('uploader') or 'Instagram'
                                title = target_entry.get('title') or info.get('title') or f"Фото от @{uploader}"
                                if not self.is_cancelled:
                                    self.info_ready.emit({
                                        'title': title,
                                        'uploader': uploader,
                                        'duration': 0,
                                        'duration_str': "ФОТО",
                                        'thumbnail': best_img,
                                        'url': self.url,
                                        'direct_media_url': best_img,
                                        'is_photo': True,
                                        'platform': 'Instagram',
                                        'available_resolutions': ['Оригинал (JPG)']
                                    })
                                    return
                    except Exception:
                        continue

        info = None
        extract_error = None
        for attempt_no, try_opts in enumerate([ydl_opts, {**ydl_opts, 'proxy': ''}]):
            if self.is_cancelled:
                return
            try:
                with yt_dlp.YoutubeDL(try_opts) as ydl:
                    info = ydl.extract_info(self.url, download=False)
                    if info:
                        break
            except Exception as e:
                extract_error = e
                err_str = str(e).lower()
                if attempt_no == 0 and any(keyword in err_str for keyword in ['ssl', 'proxy', 'tunnel', 'connection refused', 'timed out']):
                    continue
                break

        if not info:
            if self.is_cancelled:
                return
            err_msg = str(extract_error) if extract_error else "Не удалось получить информацию о видео."
            if "Unsupported URL" in err_msg:
                err_msg = "Неподдерживаемая ссылка или ресурс недоступен."
            elif "Private video" in err_msg:
                err_msg = "Приватное видео (включите Cookies браузера в настройках)."
            elif "Sign in" in err_msg or "login" in err_msg.lower():
                err_msg = "Требуется авторизация (включите Cookies браузера в настройках)."
            elif "rate-limit" in err_msg.lower() or "429" in err_msg:
                err_msg = "Ограничение частоты запросов. Попробуйте через минуту или включите Cookies."
            self.info_error.emit(err_msg)
            return

        try:
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
        staging_dir = None
        download_succeeded = False
        try:
            mode = self.options.get('mode', 'best')
            audio_fmt = self.options.get('audio_fmt', 'mp3').lower()
            audio_q = self.options.get('audio_q', '320')
            target_res = self.options.get('res')
            trim_enabled = self.options.get('trim_enabled', False)
            trim_start = self.options.get('trim_start', '')
            trim_end = self.options.get('trim_end', '')

            os.makedirs(self.save_dir, exist_ok=True)

            # Direct Image / Instagram Photo or Direct Video Download
            direct_media_url = self.options.get('direct_media_url')
            target_url = direct_media_url or self.url or ""
            target_clean = target_url.lower().split('?')[0]

            is_explicit_video = bool(self.options.get('is_video') or (self.options.get('media_type') == 'video'))
            is_explicit_photo = bool(self.options.get('is_photo') or (self.options.get('media_type') == 'photo'))

            is_page_url = any(marker in target_clean for marker in [
                '/reel/', '/reels/', '/p/', '/tv/', '/stories/',
                'youtube.com', 'youtu.be', 'tiktok.com', 'twitter.com', 'x.com', 'vk.com'
            ])

            # A file is downloaded via direct HTTP only if it has an explicit direct media URL
            # or is clearly a media file CDN and NOT a web page
            is_photo = (is_explicit_photo or any(target_clean.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp'])) and not is_explicit_video and (direct_media_url or not is_page_url)
            is_direct_video = is_explicit_video and (direct_media_url or not is_page_url) and (
                'cdninstagram.com' in target_url or 'fbcdn.net' in target_url or any(target_clean.endswith(ext) for ext in ['.mp4', '.mkv', '.webm'])
            )

            if is_photo or is_direct_video:
                download_target = direct_media_url or target_url
                media_kind = "видео" if is_direct_video else "фотографию"
                media_ext = "mp4" if is_direct_video else "jpg"
                self.status_message.emit(f"Скачивание {media_kind}...")
                headers = {
                    'User-Agent': DEFAULT_HTTP_HEADERS['User-Agent'],
                    'Referer': 'https://www.instagram.com/'
                }
                resp = requests.get(download_target, headers=headers, stream=True, timeout=25)
                resp.raise_for_status()
                total_bytes = int(resp.headers.get('content-length', 0))
                downloaded_bytes = 0
                t0 = time.time()

                title = self.options.get('title') or ("Instagram_Video" if is_direct_video else "Instagram_Photo")
                clean_title = re.sub(r'[^\w\-]', '_', title)
                file_path = get_unique_path(os.path.join(self.save_dir, f"{clean_title}.{media_ext}"))
                part_path = f"{file_path}.part"

                try:
                    with open(part_path, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if self.is_cancelled:
                                raise Exception("Загрузка отменена.")
                            f.write(chunk)
                            downloaded_bytes += len(chunk)
                            dt = time.time() - t0
                            speed = downloaded_bytes / dt if dt > 0 else 0
                            speed_str = f"{speed / (1024 * 1024):.1f} MB/s" if speed > 0 else "-- MB/s"
                            pct = (downloaded_bytes / total_bytes * 100.0) if total_bytes > 0 else 100.0
                            self.progress_updated.emit({
                                'percent': pct,
                                'speed_str': speed_str,
                                'eta_str': "--:--",
                                'downloaded_str': format_bytes(downloaded_bytes),
                                'total_str': format_bytes(total_bytes),
                                'status': 'downloading'
                            })

                    if self.is_cancelled:
                        raise Exception("Загрузка отменена.")

                    # Validate downloaded file content
                    if is_direct_video:
                        if not probe_video_stream(part_path):
                            raise Exception("Скачанный файл не содержит валидного видеопотока (возможно CDN вернул ошибку или аудио/HTML).")
                    else:
                        try:
                            from PIL import Image
                            with Image.open(part_path) as img:
                                img.verify()
                        except Exception:
                            raise Exception("Скачанный файл не является корректным изображением.")

                    if os.path.exists(file_path):
                        os.remove(file_path)
                    os.rename(part_path, file_path)
                except Exception as ex:
                    if os.path.exists(part_path):
                        try:
                            os.remove(part_path)
                        except Exception:
                            pass
                    raise ex

                file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                self.download_completed.emit({
                    'title': title,
                    'url': self.url,
                    'file_path': file_path,
                    'file_size': file_size,
                    'file_size_str': format_bytes(file_size),
                    'thumbnail': file_path if not is_direct_video else None,
                    'mode': 'MP4' if is_direct_video else 'JPG'
                })
                return

            # Network video download via yt-dlp using isolated staging folder to prevent collision
            staging_dir = tempfile.mkdtemp(prefix=".aura_staging_", dir=self.save_dir)
            out_template = os.path.join(staging_dir, '%(title)s [%(id)s].%(ext)s')

            ydl_opts = {
                'outtmpl': out_template,
                'progress_hooks': [self._progress_hook],
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': False,
                'windowsfilenames': True,
                'overwrites': False,
                'nooverwrites': True,
                'geo_bypass': True,
                'http_headers': DEFAULT_HTTP_HEADERS,
                'extractor_args': DEFAULT_EXTRACTOR_ARGS,
            }

            cookies = get_cookies_config()
            if cookies:
                ydl_opts['cookiesfrombrowser'] = cookies

            ffmpeg_exe = get_ffmpeg_path()
            if ffmpeg_exe and (shutil.which(ffmpeg_exe) or os.path.isfile(ffmpeg_exe)):
                ydl_opts['ffmpeg_location'] = ffmpeg_exe

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
                    ydl_opts['format'] = f'bestvideo[height<={h}]/bestvideo'
                else:
                    ydl_opts['format'] = 'bestvideo/best'
            elif mode == 'custom' and target_res:
                height_match = re.search(r'(\d+)p', target_res)
                h = height_match.group(1) if height_match else '1080'
                ydl_opts.update({
                    'format': f'bestvideo[height<={h}]+bestaudio/best[height<={h}]/best',
                    'merge_output_format': 'mp4',
                    'postprocessors': [{'key': 'FFmpegMetadata', 'add_metadata': True}]
                })
            elif mode == 'gif':
                ydl_opts.update({
                    'format': 'bestvideo[height<=720]/best',
                    'merge_output_format': 'mp4',
                })
            elif mode == 'discord_8mb' or mode == 'telegram_50mb':
                ydl_opts.update({
                    'format': 'bestvideo+bestaudio/best',
                    'merge_output_format': 'mp4',
                    'postprocessors': [{'key': 'FFmpegMetadata', 'add_metadata': True}]
                })
            else:
                ydl_opts.update({
                    'format': 'bestvideo+bestaudio/best',
                    'merge_output_format': 'mp4',
                    'postprocessors': [{'key': 'FFmpegMetadata', 'add_metadata': True}]
                })

            self.status_message.emit("Запуск загрузки...")

            info = None
            dl_err = None
            used_opts = ydl_opts
            for attempt_no, cur_opts in enumerate([ydl_opts, {**ydl_opts, 'proxy': ''}]):
                if self.is_cancelled:
                    return
                try:
                    with yt_dlp.YoutubeDL(cur_opts) as ydl:
                        info = ydl.extract_info(self.url, download=True)
                        if info:
                            used_opts = cur_opts
                            break
                except Exception as e:
                    dl_err = e
                    err_str = str(e).lower()
                    if attempt_no == 0 and any(keyword in err_str for keyword in ['ssl', 'proxy', 'tunnel', 'connection refused', 'timed out']):
                        continue
                    raise e

            if not info:
                raise dl_err or Exception("Не удалось скачать видео.")

            with yt_dlp.YoutubeDL(used_opts) as ydl:
                final_path = ydl.prepare_filename(info)

            if mode == 'audio_only':
                base, _ = os.path.splitext(final_path)
                final_path = f"{base}.{audio_fmt}"
            elif mode != 'video_only' and ydl_opts.get('merge_output_format'):
                base, _ = os.path.splitext(final_path)
                final_path = f"{base}.{ydl_opts['merge_output_format']}"

            if not os.path.exists(final_path) and self._last_filename and os.path.exists(self._last_filename):
                final_path = self._last_filename

            if not os.path.exists(final_path) and staging_dir and os.path.exists(staging_dir):
                for f in os.listdir(staging_dir):
                    candidate = os.path.join(staging_dir, f)
                    if os.path.isfile(candidate) and not candidate.endswith('.part') and not any(candidate.endswith(ext) for ext in ['.srt', '.vtt', '.lrc', '.ass']):
                        final_path = candidate
                        break

            # Record initial stem of the downloaded media file before any crop/compress/interpolate
            raw_downloaded_stem = Path(final_path).stem if final_path else ""

            if self.is_cancelled:
                return

            # GIF post processing
            if mode == 'gif' and os.path.exists(final_path):
                self.status_message.emit("Конвертация в GIF...")
                gif_path = convert_to_gif(final_path, is_cancelled_cb=lambda: self.is_cancelled)
                if not gif_path or self.is_cancelled:
                    return
                if gif_path != final_path:
                    try:
                        os.remove(final_path)
                    except Exception:
                        pass
                final_path = gif_path

            # Discord compression post processing
            elif mode == 'discord_8mb' and os.path.exists(final_path):
                self.status_message.emit("Сжатие для Discord (< 8 МБ)...")
                comp_path = compress_to_target_size(final_path, target_mb=7.8, is_cancelled_cb=lambda: self.is_cancelled)
                if not comp_path or self.is_cancelled:
                    return
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
                cropped_path = crop_video(final_path, crop_params, is_cancelled_cb=lambda: self.is_cancelled)
                if not cropped_path or self.is_cancelled:
                    return
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
                    status_callback=lambda msg: self.status_message.emit(msg.upper()),
                    is_cancelled_cb=lambda: self.is_cancelled
                )
                if not smooth_path or self.is_cancelled:
                    return
                if smooth_path != final_path:
                    try:
                        os.remove(final_path)
                    except Exception:
                        pass
                final_path = smooth_path

            if self.is_cancelled:
                return

            if not os.path.exists(final_path):
                # Search inside staging_dir for any matching media file if name changed
                for f in os.listdir(staging_dir):
                    candidate = os.path.join(staging_dir, f)
                    if os.path.isfile(candidate) and not candidate.endswith('.part') and not any(candidate.endswith(ext) for ext in ['.srt', '.vtt', '.lrc', '.ass']):
                        final_path = candidate
                        break

            if not os.path.exists(final_path):
                raise Exception("Файл не был сохранен или был удален.")

            final_ext = Path(final_path).suffix
            final_media_stem = Path(final_path).stem

            # Collect all sidecar files in staging_dir (subtitles .srt/.vtt, etc.)
            sidecar_files = []
            if os.path.exists(staging_dir):
                for f in sorted(os.listdir(staging_dir)):
                    full_p = os.path.join(staging_dir, f)
                    if not os.path.isfile(full_p) or full_p.endswith('.part') or full_p == final_path:
                        continue
                    if raw_downloaded_stem and f.startswith(raw_downloaded_stem):
                        sub_suffix = f[len(raw_downloaded_stem):]
                    elif f.startswith(final_media_stem):
                        sub_suffix = f[len(final_media_stem):]
                    else:
                        sub_suffix = f".{f}"
                    sidecar_files.append((full_p, sub_suffix))

            # Compute a shared collision-free base stem for both final video and all its sidecars
            sidecar_suffixes = [s[1] for s in sidecar_files]
            unique_stem = get_unique_base_for_group(self.save_dir, final_media_stem, final_ext, sidecar_suffixes)
            final_dest = os.path.join(self.save_dir, f"{unique_stem}{final_ext}")

            # Prepare plan of all files to move
            moves_plan = [(final_path, final_dest)]
            for src_p, sub_suffix in sidecar_files:
                dest_p = os.path.join(self.save_dir, f"{unique_stem}{sub_suffix}")
                moves_plan.append((src_p, dest_p))

            # Execute moves as an atomic batch. If any move fails, raise exception!
            for src_p, dest_p in moves_plan:
                shutil.move(src_p, dest_p)

            final_path = final_dest
            download_succeeded = True

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
        finally:
            if staging_dir and os.path.exists(staging_dir):
                if download_succeeded:
                    try:
                        shutil.rmtree(staging_dir, ignore_errors=True)
                    except Exception:
                        pass


class GalleryDownloadWorker(QThread):
    progress_updated = Signal(float, str, str, str, str)  # percent, speed, eta, downloaded, total
    item_completed = Signal(dict)
    batch_completed = Signal(list)
    download_error = Signal(str)
    status_message = Signal(str)

    def __init__(self, items: list, save_dir: str):
        super().__init__()
        self.items = items
        self.save_dir = save_dir
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        os.makedirs(self.save_dir, exist_ok=True)
        total_items = len(self.items)
        if total_items == 0:
            return

        results = []
        errors = []
        headers = {
            'User-Agent': DEFAULT_HTTP_HEADERS['User-Agent'],
            'Referer': 'https://www.instagram.com/'
        }

        for i, item in enumerate(self.items):
            if self.is_cancelled:
                break

            media_type = item.get('media_type', 'photo')
            is_video = bool(item.get('is_video', False) or media_type == 'video')
            uploader = item.get('uploader', 'Instagram')
            item_id = item.get('id', str(i + 1))
            ext = 'mp4' if is_video else 'jpg'

            clean_uploader = re.sub(r'[^\w\-]', '_', uploader)
            clean_id = re.sub(r'[^\w\-]', '_', str(item_id))
            filename = f"Instagram_{clean_uploader}_{clean_id}.{ext}"
            file_path = get_unique_path(os.path.join(self.save_dir, filename))

            self.status_message.emit(f"Скачивание {i + 1}/{total_items}: {filename}")
            if is_video:
                download_url = item.get('url') or item.get('best_image')
            else:
                download_url = item.get('best_image') or item.get('url')

            part_path = f"{file_path}.part"

            try:
                resp = requests.get(download_url, headers=headers, stream=True, timeout=25)
                resp.raise_for_status()
                total_bytes = int(resp.headers.get('content-length', 0))
                downloaded_bytes = 0
                t0 = time.time()

                with open(part_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if self.is_cancelled:
                            break
                        f.write(chunk)
                        downloaded_bytes += len(chunk)
                        dt = time.time() - t0
                        speed = downloaded_bytes / dt if dt > 0 else 0
                        speed_str = f"{speed / (1024 * 1024):.1f} MB/s" if speed > 0 else "-- MB/s"

                        item_pct = (downloaded_bytes / total_bytes) if total_bytes > 0 else 1.0
                        overall_pct = ((i + item_pct) / total_items) * 100.0
                        self.progress_updated.emit(
                            overall_pct,
                            speed_str,
                            "--:--",
                            format_bytes(downloaded_bytes),
                            format_bytes(total_bytes) if total_bytes > 0 else "--"
                        )

                if self.is_cancelled:
                    if os.path.exists(part_path):
                        try:
                            os.remove(part_path)
                        except Exception:
                            pass
                    break

                if not os.path.exists(part_path) or os.path.getsize(part_path) == 0:
                    raise Exception(f"Файл {filename} пуст или не был скачан.")

                # Content verification
                if is_video:
                    if not probe_video_stream(part_path):
                        raise Exception(f"Файл {filename} не содержит валидного видеопотока.")
                else:
                    try:
                        from PIL import Image
                        with Image.open(part_path) as img:
                            img.verify()
                    except Exception:
                        raise Exception(f"Файл {filename} не является корректным изображением.")

                file_path = get_unique_path(file_path)
                if os.path.exists(file_path):
                    os.remove(file_path)
                os.rename(part_path, file_path)

                file_size = os.path.getsize(file_path)
                default_title = f"Instagram {'Видео' if is_video else 'Фото'} #{i + 1}"
                result_item = {
                    'title': item.get('title') or default_title,
                    'url': download_url,
                    'file_path': file_path,
                    'file_size': file_size,
                    'file_size_str': format_bytes(file_size),
                    'mode': 'MP4' if is_video else 'JPG',
                    'thumbnail': file_path if not is_video else None
                }
                results.append(result_item)
                self.item_completed.emit(result_item)

            except Exception as e:
                if os.path.exists(part_path):
                    try:
                        os.remove(part_path)
                    except Exception:
                        pass
                err_msg = f"{filename}: {e}"
                errors.append(err_msg)
                self.download_error.emit(f"Ошибка при скачивании: {err_msg}")

        self.results = results
        self.errors = errors

        if not self.is_cancelled:
            if results:
                total_sz = sum(r['file_size'] for r in results)
                pct = 100.0 if not errors else ((len(results) / total_items) * 100.0)
                speed_txt = "0 MB/s" if not errors else f"ЧАСТИЧНО ({len(results)}/{total_items})"
                self.progress_updated.emit(pct, speed_txt, "00:00", format_bytes(total_sz), format_bytes(total_sz))
                self.batch_completed.emit(results)
            elif errors:
                self.download_error.emit("\n".join(errors))

