"""Shared HTTP response and proxy helpers with size guards and safe header parsing."""
from urllib.parse import urlsplit
import requests

MAX_THUMBNAIL_BYTES = 10 * 1024 * 1024  # 10 MiB limit for preview/thumbnail downloads
ALLOWED_PROXY_SCHEMES = ("http", "https", "socks4", "socks4a", "socks5", "socks5h")
SOCKS_PROXY_SCHEMES = ("socks4", "socks4a", "socks5", "socks5h")


class _ManagedResponse:
    """Ensure responses without __enter__/__exit__ (e.g. curl_cffi) work as context managers."""

    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self._response

    def __exit__(self, exc_type, exc, tb):
        self._response.close()
        return False

    def __getattr__(self, name):
        return getattr(self._response, name)


def validate_proxy_url(value: str) -> str:
    """Strip and validate a proxy URL; empty string disables explicit proxy."""
    if not isinstance(value, str):
        raise ValueError("Адрес прокси должен быть строкой.")
    cleaned = value.strip()
    if not cleaned:
        return ""
    if any(ch in cleaned for ch in "\r\n\t\0 "):
        raise ValueError("Адрес прокси не должен содержать пробелы или переносы строк.")
    try:
        parsed = urlsplit(cleaned)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("Некорректный формат URL или порта прокси.") from exc
    if parsed.scheme.lower() not in ALLOWED_PROXY_SCHEMES:
        raise ValueError("Поддерживаются только прокси http://, https://, socks4:// и socks5://.")
    if not parsed.hostname:
        raise ValueError("Укажите хост прокси-сервера (например, socks5://user:pass@host:port).")
    return cleaned


def normalize_proxy_url(value: str, remote_dns: bool = True) -> str:
    """Normalize proxy scheme; promote socks5->socks5h and socks4->socks4a for remote DNS."""
    cleaned = validate_proxy_url(value)
    if not cleaned:
        return ""
    scheme, rest = cleaned.split("://", 1)
    low = scheme.lower()
    if remote_dns:
        if low == "socks5":
            low = "socks5h"
        elif low == "socks4":
            low = "socks4a"
    return f"{low}://{rest}"


def mask_proxy_url(value: str) -> str:
    """Hide credentials in a proxy URL for UI status messages or logs."""
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    try:
        parsed = urlsplit(cleaned)
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        prefix = "***@" if parsed.username or parsed.password else ""
        return f"{parsed.scheme}://{prefix}{host}{port}"
    except ValueError:
        return "<proxy>"


def get_configured_proxy(remote_dns: bool = True) -> str:
    """Return normalized proxy URL from application settings, or '' if disabled."""
    try:
        from core.settings import settings
        if not settings.get("proxy_enabled", True):
            return ""
        raw = settings.get("proxy_url", "")
        if not raw:
            return ""
        return normalize_proxy_url(raw, remote_dns=remote_dns)
    except Exception:
        return ""


def get_ytdlp_proxy_opts() -> dict:
    """Return yt-dlp option dict with explicit proxy when configured, else {}."""
    proxy = get_configured_proxy(remote_dns=True)
    return {"proxy": proxy} if proxy else {}


def http_get(url: str, *, requests_mod=None, **kwargs):
    """Perform HTTP GET honoring configured HTTP/HTTPS/SOCKS proxy.

    When no explicit proxy is configured, delegates straight to requests_mod.get
    (or requests.get) without changing call arguments so existing mocks keep working.
    """
    client = requests_mod or requests
    proxy = get_configured_proxy(remote_dns=True)
    if not proxy:
        return client.get(url, **kwargs)

    proxies = {"http": proxy, "https": proxy}
    scheme = urlsplit(proxy).scheme.lower()
    if scheme in SOCKS_PROXY_SCHEMES:
        from curl_cffi import requests as cffi_requests
        call_kwargs = dict(kwargs)
        call_kwargs.setdefault("proxies", proxies)
        resp = cffi_requests.get(url, **call_kwargs)
        return resp if hasattr(resp, "__enter__") else _ManagedResponse(resp)

    call_kwargs = dict(kwargs)
    call_kwargs.setdefault("proxies", proxies)
    return client.get(url, **call_kwargs)


def parse_content_length(headers) -> int:
    raw = headers.get("content-length") if headers else None
    if raw is None:
        return 0
    try:
        value = int(str(raw).strip())
        return value if value > 0 else 0
    except (TypeError, ValueError):
        return 0


def read_limited_response(resp, max_bytes: int = MAX_THUMBNAIL_BYTES, is_cancelled_cb=None):
    """Read response body up to max_bytes, aborting early on cancellation or oversize."""
    content_length = parse_content_length(getattr(resp, "headers", None))
    if content_length > max_bytes:
        return None

    chunks = []
    total = 0
    iter_content = getattr(resp, "iter_content", None)
    if callable(iter_content):
        for chunk in iter_content(chunk_size=65536):
            if is_cancelled_cb and is_cancelled_cb():
                return None
            if not isinstance(chunk, (bytes, bytearray)):
                continue
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                return None
            chunks.append(chunk)
    if chunks:
        return b"".join(chunks)

    if is_cancelled_cb and is_cancelled_cb():
        return None
    raw_content = getattr(resp, "content", None)
    if isinstance(raw_content, (bytes, bytearray)):
        if len(raw_content) > max_bytes:
            return None
        return bytes(raw_content)
    return None
