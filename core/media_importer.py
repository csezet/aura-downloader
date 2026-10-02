"""Prepare local media and mixed input without probing files on the GUI thread."""
import os
import copy
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import Signal
from core.workers import CancellableThread
from core.queue_items import normalize_item, RESOLUTIONS


class MediaImportWorker(CancellableThread):
    item_ready = Signal(dict)
    status_message = Signal(str)
    import_finished = Signal(dict)

    def __init__(self, sources, options):
        super().__init__()
        self.sources = list(sources)
        self.options = copy.deepcopy(options)

    def run(self):
        from core.local_processor import is_video_file, get_local_media_info
        from core.downloader import detect_platform
        pending = list(reversed(self.sources))
        added, errors = 0, []
        while pending and not self.isInterruptionRequested():
            source = pending.pop()
            try:
                if source.lower().startswith(("http://", "https://")):
                    ext = Path(urlsplit(source).path).suffix.lower()
                    photo = ext in (".jpg", ".jpeg", ".png", ".webp")
                    direct_video = ext in (".mp4", ".webm", ".mkv")
                    info = {"url": source, "platform": detect_platform(source), "is_photo": photo,
                            "has_video": not photo, "is_video": direct_video, "duration": 0,
                            "duration_str": "ФОТО" if photo else "--:--",
                            "available_res": [] if photo else RESOLUTIONS,
                            "direct_media_url": source if photo or direct_video else None}
                elif os.path.isdir(source):
                    path = Path(source)
                    if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                        continue
                    with os.scandir(source) as entries:
                        children = sorted((entry.path for entry in entries if not entry.is_symlink()), reverse=True)
                    pending.extend(children)
                    continue
                elif is_video_file(source):
                    self.status_message.emit(f"Подготовка: {Path(source).name}")
                    info = get_local_media_info(source)
                    if not info:
                        raise ValueError("не удалось прочитать файл")
                else:
                    # Ignore unrelated files while scanning a folder.
                    continue
                if self.isInterruptionRequested():
                    break
                self.item_ready.emit(normalize_item(info, self.options))
                added += 1
            except Exception as error:
                errors.append(f"{Path(source).name or source}: {error}")
        self.import_finished.emit({"added": added, "errors": errors, "cancelled": self.isInterruptionRequested()})
