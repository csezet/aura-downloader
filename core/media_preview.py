"""Choose a small video stream without downloading the full video for the editor."""
from urllib.parse import urlsplit


def choose_preview_format(formats):
    candidates = [f for f in formats if f.get('url') and f.get('vcodec') != 'none'
                  and (f.get('height') or f.get('vcodec'))
                  and f.get('ext') not in ('mhtml', 'jpg', 'jpeg', 'png')]
    if not candidates:
        return None

    def score(fmt):
        codec = fmt.get('vcodec') or ''
        height = fmt.get('height') or 0
        progressive = fmt.get('protocol') in (None, 'http', 'https')
        compatible = fmt.get('ext') == 'mp4' and codec.startswith(('avc', 'h264'))
        return (progressive, compatible, fmt.get('acodec') not in (None, 'none'),
                0 < height <= 480, height if height <= 480 else -height)

    return max(candidates, key=score)


def resolve_preview(url, is_cancelled_cb):
    import yt_dlp
    from core.cookies_helper import (
        get_cookies_config,
        get_cookies_file,
        get_ytdlp_cookies_opts,
        is_cookie_db_error,
        strip_cookie_opts,
    )
    from core.downloader import DEFAULT_HTTP_HEADERS, DEFAULT_EXTRACTOR_ARGS
    from core.http_utils import get_ytdlp_proxy_opts
    from core.js_runtime import javascript_options

    if is_cancelled_cb():
        return None
    proxy_opts = get_ytdlp_proxy_opts()
    options = {**javascript_options(), 'quiet': True, 'no_warnings': True,
               'noplaylist': True, 'skip_download': True,
               'socket_timeout': 15 if proxy_opts else 8,
               'extractor_retries': 1, 'retries': 0,
               'http_headers': DEFAULT_HTTP_HEADERS, 'extractor_args': DEFAULT_EXTRACTOR_ARGS,
               **proxy_opts}
    cookie_opts = get_ytdlp_cookies_opts(get_cookies_config(), get_cookies_file())
    if cookie_opts:
        options.update(cookie_opts)

    def _extract_preview(opts):
        with yt_dlp.YoutubeDL(opts) as downloader:
            data = downloader.extract_info(url, download=False, process=False)
            if data and data.get('_type') in ('url', 'url_transparent'):
                data = downloader.process_ie_result(data, download=False)
            return data

    try:
        info = _extract_preview(options)
    except Exception as exc:
        if is_cookie_db_error(exc) and 'cookiesfrombrowser' in options:
            info = _extract_preview(strip_cookie_opts(options))
        else:
            raise
    if is_cancelled_cb():
        return None
    if not info:
        raise ValueError('Не удалось получить видеопоток.')
    fmt = choose_preview_format(info.get('formats') or [])
    playable = fmt.get('url') if fmt else info.get('url')
    if not playable or urlsplit(playable).scheme not in ('http', 'https'):
        raise ValueError('Сайт не предоставил поток для предпросмотра.')
    return {'url': playable, 'duration': info.get('duration') or 0}
