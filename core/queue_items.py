"""Queue snapshots shared by the editor, importer and execution worker."""
import copy
import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit, unquote

from core.media_options import trim_range, resolution_bounds

MODES = ("best", "custom", "audio_only", "video_only", "gif", "discord_8mb")
RESOLUTIONS = ["4K (2160p)", "2K (1440p)", "1080p Full HD", "720p HD", "480p", "360p"]


def default_options(settings):
    return {"mode": settings.get("quality_preset", "best"), "res": "1080p Full HD",
            "audio_fmt": settings.get("audio_format", "mp3"), "audio_q": settings.get("audio_quality", "320"),
            "download_subs": settings.get("download_subtitles", False),
            "trim_enabled": False, "trim_start": "00:00", "trim_end": "",
            "crop_enabled": False, "crop_params": None,
            "smooth_enabled": False, "smooth_fps": 60, "smooth_model": "rife-v4.6"}


def normalize_item(item, fallback_options=None):
    if isinstance(item, dict):
        data = copy.deepcopy(item)
    elif isinstance(item, tuple):
        data = {"url": str(item[0]), "options": copy.deepcopy(item[1] or {})}
    else:
        data = {"url": str(item)}
    source = data.get("url") or data.get("file_path") or data.get("direct_media_url") or data.get("best_image") or ""
    source = str(source).strip().strip('"').strip("'")
    data["url"] = source
    data.setdefault("item_id", uuid.uuid4().hex)
    data.setdefault("title", unquote(urlsplit(source).path.rsplit("/", 1)[-1]) if source.startswith("http") else Path(source).name)
    data["title"] = data["title"] or source or "Без названия"
    options = copy.deepcopy(fallback_options or {})
    options.update(copy.deepcopy(data.get("options") or {}))
    if data.get("is_photo") or data.get("media_type") == "photo":
        # Video tools are not applicable to a photograph.
        options.update(mode="best", trim_enabled=False, crop_enabled=False, smooth_enabled=False)
    data["options"] = options
    return data


def validate_item(item):
    options = item["options"]
    if not item.get("url"):
        raise ValueError("Не указан источник файла.")
    if item.get("is_photo") or item.get("media_type") == "photo":
        return
    if options.get("mode", "best") not in MODES:
        raise ValueError("Неизвестный режим обработки.")
    trim_range(options, item.get("duration"))
    if options.get("mode") in ("custom", "video_only"):
        resolution_bounds(options.get("res"))
    if options.get("crop_enabled") and not options.get("crop_params"):
        raise ValueError("Выберите область кадрирования или отключите кадрирование.")
    if options.get("mode") == "audio_only" and options.get("audio_fmt", "mp3") not in ("mp3", "flac", "m4a", "opus", "wav"):
        raise ValueError("Неизвестный формат аудио.")
    if item.get("is_local") and not os.path.isfile(item["url"]):
        raise ValueError("Исходный файл удалён или перемещён.")


def parse_sources(text):
    sources, errors = [], []
    for number, line in enumerate(str(text).splitlines(), 1):
        source = line.strip().strip('"').strip("'").strip()
        if not source:
            continue
        try:
            url = urlsplit(source) if source.lower().startswith(("http://", "https://")) else None
            valid_url = url and url.hostname
        except ValueError:
            valid_url = False
        if valid_url:
            sources.append(source)
        elif os.path.exists(source):
            sources.append(os.path.abspath(source))
        else:
            errors.append(f"Строка {number}: укажите ссылку HTTP/HTTPS или существующий путь.")
    return sources, errors
