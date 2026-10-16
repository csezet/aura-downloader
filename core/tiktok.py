"""Resolve TikTok share links and photo posts using TikTok's own page data."""
import re
from urllib.parse import urlsplit

import yt_dlp
from yt_dlp.extractor.tiktok import TikTokIE
from yt_dlp.networking import HEADRequest

SHARE_URL = re.compile(r'https?://(?:(?:www|m|vm|vt)\.)?tiktok\.com/[^\s<>"\]]+', re.I)
POST_PATH = re.compile(r'/@(?P<author>[^/]+)/(?P<kind>photo|video)/(?P<id>\d+)/?$', re.I)


def find_tiktok_url(text):
    match = SHARE_URL.search(str(text))
    return match.group(0).rstrip('.,;!?)）。，') if match else None


def is_tiktok_url(url):
    try:
        host = (urlsplit(url).hostname or '').lower()
    except ValueError:
        return False
    return host in ('tiktok.com', 'www.tiktok.com', 'm.tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com')


def gallery_from_post(post, url):
    """Keep image order and original CDN URLs, including their signed query."""
    images = (post.get('imagePost') or {}).get('images') or []
    author = post.get('author') or {}
    uploader = author.get('uniqueId') or author.get('nickname') or 'TikTok'
    items = []
    for index, image in enumerate(images, 1):
        urls = (image.get('imageURL') or {}).get('urlList') or []
        media = next((value for value in urls if isinstance(value, str)
                      and urlsplit(value).scheme in ('https', 'http')), None)
        if not media:
            raise ValueError(f'TikTok не предоставил файл фотографии №{index}. Повторите получение публикации.')
        items.append({'id': f"{post.get('id', '')}_{index:02d}", 'index': index,
                      'url': media, 'best_image': media, 'direct_media_url': media,
                      'source_url': url, 'thumbnail': media,
                      'title': f'TikTok_{uploader}_{post.get("id", "")}_{index:02d}',
                      'uploader': uploader, 'platform': 'TikTok',
                      'is_photo': True, 'is_video': False, 'has_video': False, 'media_type': 'photo',
                      'width': image.get('imageWidth'), 'height': image.get('imageHeight'),
                      'http_headers': {'Referer': 'https://www.tiktok.com/'}})
    if not items:
        raise ValueError('В публикации TikTok не найдены фотографии. Возможно, она удалена или требует входа.')
    return {'title': f'Фото от @{uploader}', 'uploader': uploader, 'platform': 'TikTok',
            'url': url, 'items': items}


def resolve_tiktok_post(url, is_cancelled_cb=lambda: False):
    """Return a canonical URL and, for photo posts, a selectable gallery."""
    if not is_tiktok_url(url) or is_cancelled_cb():
        return url, None
    parsed = urlsplit(url)
    match = POST_PATH.fullmatch(parsed.path)
    if match and match['kind'].lower() == 'video':
        return f'https://www.tiktok.com{parsed.path.rstrip("/")}', None
    if not match and TikTokIE.suitable(url):
        return url, None
    from core.cookies_helper import get_cookies_config
    from core.js_runtime import javascript_options
    options = {**javascript_options(), 'quiet': True, 'no_warnings': True,
               'socket_timeout': 8, 'retries': 0, 'extractor_retries': 1, 'noplaylist': True}
    cookies = get_cookies_config()
    if cookies:
        options['cookiesfrombrowser'] = cookies
    with yt_dlp.YoutubeDL(options) as downloader:
        if not match:
            response = downloader.urlopen(HEADRequest(url, headers={'User-Agent': 'facebookexternalhit/1.1'}))
            try:
                url = response.url
            finally:
                response.close()
            if is_cancelled_cb():
                return url, None
            if not is_tiktok_url(url):
                raise ValueError('Короткая ссылка TikTok ведёт на другой сайт.')
            parsed = urlsplit(url)
            match = POST_PATH.fullmatch(parsed.path)
        if not match:
            raise ValueError('Вставьте ссылку на конкретное видео или фото TikTok.')
        canonical = f'https://www.tiktok.com{parsed.path.rstrip("/")}'
        if match['kind'].lower() != 'photo' or is_cancelled_cb():
            return canonical, None
        # The photo route only renders an application shell. The video route for
        # the same public post includes the original imagePost data in its SSR.
        webpage = f'https://www.tiktok.com/@{match["author"]}/video/{match["id"]}'
        post, status = TikTokIE(downloader)._extract_web_data_and_status(webpage, match['id'])
        if is_cancelled_cb():
            return canonical, None
        if status in (10216, 10222):
            raise ValueError('Фото TikTok доступны только после входа. Выберите Cookies браузера в настройках.')
        if status == 10204:
            raise ValueError('TikTok ограничил доступ с этого подключения. Попробуйте позже.')
        if status != 0 or not post:
            raise ValueError('Не удалось получить фотографии TikTok. Проверьте доступность публикации в браузере.')
        return canonical, gallery_from_post(post, canonical)
