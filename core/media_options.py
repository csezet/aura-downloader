"""Validation shared by local processing and downloaded media."""
import math
import re


def parse_time_str(value):
    if value is None or str(value).strip() == "":
        return None
    parts = str(value).strip().split(":")
    if not 1 <= len(parts) <= 3:
        return None
    try:
        numbers = [float(part) for part in parts]
        if any(not math.isfinite(n) or n < 0 for n in numbers):
            return None
        if len(numbers) > 1 and any(n >= 60 for n in numbers[1:]):
            return None
        return sum(n * 60 ** i for i, n in enumerate(reversed(numbers)))
    except (ValueError, TypeError):
        return None


def trim_range(options, duration=None):
    if not options.get("trim_enabled"):
        return 0.0, None
    start_text, end_text = options.get("trim_start"), options.get("trim_end")
    start, end = parse_time_str(start_text), parse_time_str(end_text)
    if (start_text and start is None) or (end_text and end is None):
        raise ValueError("Некорректное время фрагмента. Используйте секунды или ЧЧ:ММ:СС.")
    start = start or 0.0
    if end is not None and end <= start:
        raise ValueError("Конец фрагмента должен быть позже начала.")
    if duration and start >= duration:
        raise ValueError("Начало фрагмента находится за пределами видео.")
    return start, min(end, duration) if end is not None and duration else end


def resolution_bounds(value):
    """A quality label caps height, as in yt-dlp; WxH caps both dimensions."""
    if not value:
        return None
    value = str(value).strip().lower()
    match = re.search(r"(\d+)\s*[x×]\s*(\d+)", value)
    if match:
        bounds = tuple(int(n) for n in match.groups())
    else:
        match = re.search(r"(\d+)p\b", value)
        if not match:
            raise ValueError(f"Неизвестное разрешение: {value}")
        bounds = (int(match.group(1)),)
    if any(n < 2 or n > 16384 for n in bounds):
        raise ValueError("Недопустимое разрешение видео.")
    return bounds


def scale_filter(value):
    bounds = resolution_bounds(value)
    if not bounds:
        return ""
    if len(bounds) == 1:
        factor = f"min(1\\,{bounds[0]}/ih)"
    else:
        factor = f"min(1\\,min({bounds[0]}/iw\\,{bounds[1]}/ih))"
    return f"scale=trunc(iw*{factor}/2)*2:trunc(ih*{factor}/2)*2,setsar=1"
