"""Browser cookies & Netscape cookies.txt helpers with Windows lock fallback."""
import os
from core.settings import settings

SUPPORTED_BROWSERS = [
    ("none", "Отключено (Без cookies)"),
    ("chrome", "Google Chrome"),
    ("edge", "Microsoft Edge"),
    ("firefox", "Mozilla Firefox"),
    ("brave", "Brave Browser"),
    ("opera", "Opera"),
    ("vivaldi", "Vivaldi"),
]


def get_cookies_config():
    browser = settings.get("browser_cookies", "none")
    if browser and browser != "none":
        return (browser,)
    return None


def get_cookies_file():
    path = settings.get("cookies_file", "")
    if isinstance(path, str) and path.strip() and os.path.isfile(path):
        return path
    return None


def get_ytdlp_cookies_opts(browser_cookies=None, cookies_file=None) -> dict:
    """Return yt-dlp cookie options, preferring an explicit cookies.txt file over browser DB."""
    if cookies_file:
        return {"cookiefile": cookies_file}
    if browser_cookies:
        return {"cookiesfrombrowser": browser_cookies}
    return {}


def strip_cookie_opts(opts: dict) -> dict:
    """Return a shallow copy of yt-dlp options without cookiesfrombrowser/cookiefile."""
    cleaned = dict(opts)
    cleaned.pop("cookiesfrombrowser", None)
    cleaned.pop("cookiefile", None)
    return cleaned


def is_cookie_db_error(error) -> bool:
    """Detect yt-dlp failures caused by locked/encrypted browser cookie databases on Windows."""
    msg = str(error or "").lower()
    if "cookie" not in msg and "dpapi" not in msg:
        return False
    return (
        ("could not copy" in msg and "cookie" in msg)
        or "failed to decrypt with dpapi" in msg
        or ("could not find" in msg and "cookie" in msg)
        or ("permission denied" in msg and "cookie" in msg)
        or ("app-bound" in msg and "cookie" in msg)
        or "chrome cookie database" in msg
    )


def format_cookie_auth_error(err_msg: str, cookie_db_failed: bool = False, has_proxy: bool = False) -> str:
    """Format user-friendly Russian guidance for auth / locked Chrome cookie errors."""
    text = str(err_msg or "")
    low = text.lower()
    needs_auth = any(k in low for k in ("sign in", "confirm you", "login", "not a bot"))

    if cookie_db_failed and needs_auth:
        return (
            "Браузер заблокировал базу cookies, а сайт требует вход. "
            "Закройте браузер, выберите Firefox или укажите файл cookies.txt в Настройках."
        )
    if is_cookie_db_error(text):
        return (
            "Браузер заблокировал базу cookies (обычно открытый Chrome). "
            "Закройте браузер, выберите Firefox или укажите файл cookies.txt в Настройках."
        )
    if needs_auth:
        if has_proxy:
            return (
                "Сайт запросил вход (проверка IP прокси). "
                "Укажите файл cookies.txt или Firefox в Настройках (для Chrome экспортируйте cookies.txt)."
            )
        return "Требуется авторизация (выберите Cookies браузера или файл cookies.txt в Настройках)."
    return text
