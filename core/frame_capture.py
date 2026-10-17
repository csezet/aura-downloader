"""Extract original video frames using their presentation timestamps."""
import bisect
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid

from core.media_converter import get_ffmpeg_path, get_ffprobe_path, CREATE_NO_WINDOW, get_startupinfo
from core.temp_files import OwnedDirectory, cache_root, remove_owned_directory


class CaptureCancelled(Exception):
    pass


def run_command(command, cancelled, timeout=45):
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=output, stderr=errors,
                                   startupinfo=get_startupinfo(), creationflags=CREATE_NO_WINDOW)
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if cancelled():
                    raise CaptureCancelled()
                if time.monotonic() > deadline:
                    raise ValueError('Получение кадра заняло слишком много времени. Попробуйте ещё раз.')
                time.sleep(.03)
            if cancelled():
                raise CaptureCancelled()
            if process.returncode:
                errors.seek(0)
                detail = re.sub(r'https?://\S+', '[URL]', errors.read().decode('utf-8', 'replace')[-1500:])
                logging.getLogger('aura.frame').debug('Frame decoder: %s', detail)
                raise ValueError('Не удалось прочитать исходное видео. Проверьте доступность файла или ссылки.')
            output.seek(0)
            return output.read()
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


class FrameCaptureSession:
    def __init__(self, source):
        self.source = dict(source) if isinstance(source, dict) else {'url': source}
        self.media = None
        self.workspace = None
        self.timestamps = []
        self.window = None
        self.snapshots = {}

    def _prepare(self, cancelled, status):
        if cancelled():
            raise CaptureCancelled()
        if self.media:
            return
        source = self.source
        url = source.get('url') or ''
        if not url:
            raise ValueError('Не указан исходный ролик для сохранения кадра.')
        headers = dict(source.get('http_headers') or {})
        if not url.startswith(('http://', 'https://')):
            if not Path(url).is_file():
                raise ValueError('Исходный видеофайл удалён или перемещён.')
            media_url = str(Path(url).resolve())
        elif source.get('direct_media_url'):
            media_url = source['direct_media_url']
        elif Path(url.split('?', 1)[0]).suffix.lower() in ('.mp4', '.mkv', '.mov', '.webm', '.m3u8'):
            media_url = url
        else:
            status('Получение видеопотока в лучшем качестве…')
            import yt_dlp
            from core.downloader import DEFAULT_HTTP_HEADERS, DEFAULT_EXTRACTOR_ARGS
            from core.cookies_helper import get_cookies_config
            from core.js_runtime import javascript_options
            options = {**javascript_options(), 'quiet': True, 'no_warnings': True,
                       'noplaylist': True, 'format': 'bestvideo/best', 'skip_download': True,
                       'socket_timeout': 8, 'retries': 0, 'extractor_retries': 1,
                       'http_headers': DEFAULT_HTTP_HEADERS, 'extractor_args': DEFAULT_EXTRACTOR_ARGS}
            cookies = get_cookies_config()
            if cookies:
                options['cookiesfrombrowser'] = cookies
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(url, download=False)
                if not info or not info.get('url') or info.get('vcodec') == 'none':
                    raise ValueError('Сайт не предоставил видеопоток для сохранения кадра.')
                media_url = info['url']
                headers.update(info.get('http_headers') or {})
                cookie_header = downloader.cookiejar.get_cookie_header(media_url)
                if cookie_header:
                    headers['Cookie'] = cookie_header
        if cancelled():
            raise CaptureCancelled()
        network = media_url.startswith(('https://', 'http://'))
        arguments = []
        if network:
            arguments += ['-rw_timeout', '8000000']
            safe_headers = ''.join(f'{key}: {value}\r\n' for key, value in headers.items()
                                   if isinstance(key, str) and isinstance(value, str)
                                   and not any(c in key + value for c in '\r\n'))
            if safe_headers:
                arguments += ['-headers', safe_headers]
        status('Подготовка исходного видео…')
        raw = run_command([get_ffprobe_path(), '-v', 'error', *arguments, '-select_streams', 'v:0',
                           '-show_entries', 'stream=start_time,duration,color_transfer:format=duration,start_time',
                           '-of', 'json', media_url], cancelled)
        data = json.loads(raw)
        stream = (data.get('streams') or [{}])[0]
        if not data.get('streams'):
            raise ValueError('В источнике отсутствует видеодорожка.')
        container = data.get('format') or {}
        start = float(stream.get('start_time') or container.get('start_time') or 0)
        duration = float(stream.get('duration') or container.get('duration') or 0)
        self.workspace = OwnedDirectory(cache_root(), 'frames_', 'cache')
        self.media = {'url': media_url, 'arguments': arguments, 'start': start,
                      'duration': duration, 'transfer': stream.get('color_transfer')}

    def capture(self, position, direction=0, cancelled=lambda: False, status=lambda value: None):
        self._prepare(cancelled, status)
        if not math.isfinite(position) or position < 0 or direction not in (-1, 0, 1):
            raise ValueError('Некорректная позиция кадра.')
        media = self.media
        duration = media['duration']
        position = min(position, max(0, duration - .000001)) if duration > 0 else position
        times = self.timestamps
        index = bisect.bisect_right(times, position + .000002) - 1
        if not self.window or not (self.window[0] <= position <= self.window[1]) or index < 1 or index + 2 >= len(times):
            lower, upper = max(0, position - 1), position + 1
            interval = f'{media["start"] + lower:.9f}%{media["start"] + upper:.9f}'
            raw = run_command([get_ffprobe_path(), '-v', 'error', *media['arguments'],
                               '-select_streams', 'v:0', '-read_intervals', interval,
                               '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time',
                               '-of', 'json', media['url']], cancelled)
            values = (float(frame['best_effort_timestamp_time']) - media['start']
                      for frame in json.loads(raw).get('frames', []) if frame.get('best_effort_timestamp_time') is not None)
            times = sorted(set(max(0, value) for value in values if math.isfinite(value) and value >= -.00001))
            if not times:
                raise ValueError('Не удалось найти кадр в выбранной позиции.')
            self.timestamps, self.window = times, (lower, upper)
        index = max(0, bisect.bisect_right(times, position + .000002) - 1)
        index = max(0, min(len(times) - 1, index + direction))
        timestamp = times[index]
        key = round(timestamp, 6)
        if key not in self.snapshots:
            status('Извлечение кадра в исходном разрешении…')
            path = self.workspace.path / (uuid.uuid4().hex + '.png')
            filters = [f'select=gte(t\\,{max(0, timestamp - .000002):.9f})']
            if media['transfer'] in ('smpte2084', 'arib-std-b67'):
                filters += ['zscale=t=linear:npl=100', 'format=gbrpf32le', 'tonemap=hable:desat=0',
                            'zscale=p=bt709:t=iec61966-2-1:m=gbr:r=full', 'format=rgb24']
            command = [get_ffmpeg_path(), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                       '-ss', f'{max(0, timestamp - .25):.9f}', '-copyts', '-start_at_zero',
                       *media['arguments'], '-i', media['url'], '-map', '0:v:0', '-an', '-sn', '-dn',
                       '-vf', ','.join(filters), '-frames:v', '1', '-fps_mode', 'passthrough',
                       '-c:v', 'png', '-update', '1', str(path)]
            try:
                run_command(command, cancelled)
                if not path.is_file() or not path.stat().st_size:
                    raise ValueError('Декодер не вернул изображение выбранного кадра.')
                from PIL import Image
                with Image.open(path) as image:
                    width, height = image.size
                    image.verify()
                self.snapshots[key] = {'path': str(path), 'position': timestamp, 'width': width, 'height': height}
                while len(self.snapshots) > 4:
                    oldest = self.snapshots.pop(next(iter(self.snapshots)))
                    Path(oldest['path']).unlink(missing_ok=True)
            except Exception:
                path.unlink(missing_ok=True)
                raise
        return dict(self.snapshots[key])

    def close(self):
        if self.workspace:
            path = self.workspace.path
            self.workspace.release()
            remove_owned_directory(path, cache_root(), 'cache')
            self.workspace = None
        self.snapshots.clear()


def save_frame(frame, destination, cancelled=lambda: False):
    target = Path(destination)
    if target.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
        raise ValueError('Выберите формат PNG или JPG.')
    if Path(frame['path']).resolve() == target.resolve():
        raise ValueError('Выберите папку для сохранения фотографии.')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.aura_frame_', suffix=target.suffix, delete=False) as stream:
            temporary = Path(stream.name)
        if cancelled():
            raise CaptureCancelled()
        if target.suffix.lower() == '.png':
            shutil.copyfile(frame['path'], temporary)
        else:
            from PIL import Image
            with Image.open(frame['path']) as image:
                image.convert('RGB').save(temporary, 'JPEG', quality=95, subsampling=0)
        if cancelled():
            raise CaptureCancelled()
        os.replace(temporary, target)
        return str(target)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
