"""Shared HTTP response helpers with size guards and safe header parsing."""

MAX_THUMBNAIL_BYTES = 10 * 1024 * 1024  # 10 MiB limit for preview/thumbnail downloads


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
