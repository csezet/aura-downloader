import copy
import math
import os
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from core.downloader import DownloadWorker
from core.queue_items import normalize_item


class UnifiedBatchWorker(QThread):
    progress_updated = Signal(dict)
    item_state_changed = Signal(dict)
    item_completed = Signal(dict)
    batch_completed = Signal(list)
    batch_summary = Signal(dict)
    download_error = Signal(str)
    status_message = Signal(str)

    def __init__(self, items: list, fallback_options: dict, save_dir: str):
        super().__init__()
        self.fallback_options = copy.deepcopy(fallback_options or {})
        self.items = [normalize_item(item, self.fallback_options) for item in (items or [])]
        self.save_dir = save_dir
        self.is_cancelled = False
        self._current_worker = None
        self.results, self.errors, self.failed_items = [], [], []
        self.total = len(self.items)

    def cancel(self):
        self.is_cancelled = True
        self.requestInterruption()
        if self._current_worker:
            self._current_worker.cancel()

    def run(self):
        from core.local_processor import process_single_local_file, is_video_file
        results, errors, failed, pending = [], [], [], []
        total = self.total
        overall = 0.0

        def state(item, value, **extra):
            self.item_state_changed.emit({"item_id": item["item_id"], "state": value, **extra})

        try:
            os.makedirs(self.save_dir, exist_ok=True)
            directory_error = None
        except OSError as error:
            directory_error = str(error)

        for idx, item in enumerate(self.items):
            if self.is_cancelled:
                pending.extend(self.items[idx:])
                break
            options = copy.deepcopy(item["options"])
            path = item["url"]
            title = item["title"]
            local = item.get("is_local") or is_video_file(path)
            item_result, item_error, recovery_dir = None, None, None
            self.status_message.emit(f"[{idx + 1}/{total}] {title}")
            state(item, "processing" if local else "downloading")

            def on_progress(data):
                nonlocal overall
                if not isinstance(data, dict):
                    return
                try:
                    percent = float(data.get("percent", 0))
                    if not math.isfinite(percent):
                        percent = 0
                except (TypeError, ValueError):
                    percent = 0
                percent = max(0.0, min(99.0, percent))
                overall = max(overall, (idx + percent / 100) / max(1, total) * 100)
                self.progress_updated.emit({**data, "percent": overall,
                                            "downloaded_str": f"{len(results)}/{total} готово",
                                            "total_str": f"{total} файлов", "status": "processing"})
                state(item, "processing" if local or data.get("status") != "downloading" else "downloading",
                      percent=percent)

            def on_status(message):
                self.status_message.emit(f"[{idx + 1}/{total}] {message}")

            try:
                if directory_error:
                    raise OSError(f"Папка сохранения недоступна: {directory_error}")
                if local:
                    item_result = process_single_local_file(path, options, self.save_dir,
                                                            status_cb=on_status, progress_cb=on_progress,
                                                            is_cancelled_cb=lambda: self.is_cancelled)
                else:
                    direct = item.get("direct_media_url") or item.get("best_image")
                    photo = item.get("is_photo") or item.get("media_type") == "photo"
                    options.update(title=title, is_photo=bool(photo),
                                   is_video=bool(not photo and (item.get("is_video") or item.get("has_video"))),
                                   media_type="photo" if photo else "video")
                    if direct:
                        options["direct_media_url"] = direct
                    worker = DownloadWorker(path, options, self.save_dir)
                    self._current_worker = worker
                    def on_done(result):
                        nonlocal item_result
                        item_result = result
                    def on_error(error):
                        nonlocal item_error
                        item_error = error
                    def on_recovery(info):
                        nonlocal recovery_dir
                        recovery_dir = info.get("staging_dir")
                    worker.download_completed.connect(on_done)
                    worker.download_error.connect(on_error)
                    worker.progress_updated.connect(on_progress)
                    worker.status_message.connect(on_status)
                    if hasattr(worker, "recovery_available"):
                        worker.recovery_available.connect(on_recovery)
                    worker.run()
            except Exception as error:
                item_error = str(error)
            finally:
                self._current_worker = None

            if item_result:
                result = {**item_result, "item_id": item["item_id"], "save_dir": self.save_dir,
                          "format_type": Path(item_result.get("file_path", "")).suffix.lstrip(".").upper()}
                results.append(result)
                self.item_completed.emit(result)
                state(item, "completed", result=result, percent=100)
                overall = (idx + 1) / max(1, total) * 100
                self.progress_updated.emit({"percent": overall, "speed_str": "ГОТОВО", "eta_str": "--:--",
                                            "downloaded_str": f"{len(results)}/{total} готово",
                                            "total_str": f"{total} файлов", "status": "processing"})
            elif self.is_cancelled:
                pending.extend(self.items[idx:])
                break
            else:
                item_error = item_error or "Обработка завершилась без сохранённого файла."
                errors.append(f"{title}: {item_error}")
                snapshot = copy.deepcopy(item)
                if recovery_dir:
                    snapshot["recovery_dir"] = recovery_dir
                failed.append(snapshot)
                state(item, "error", error=item_error, recovery_dir=recovery_dir)
                on_status(f"Ошибка: {item_error}")

        for item in pending:
            state(item, "cancelled")
        self.results, self.errors, self.failed_items = results, errors, failed
        cancelled = self.is_cancelled
        status = "cancelled" if cancelled else ("finished_with_errors" if results and errors else "error" if errors else "finished")
        self.progress_updated.emit({"percent": len(results) / max(1, total) * 100,
                                    "speed_str": "ОСТАНОВЛЕНО" if cancelled else f"ЧАСТИЧНО ({len(results)}/{total})" if errors and results else "СБОЙ ОЧЕРЕДИ" if errors else "ГОТОВО",
                                    "eta_str": "00:00", "downloaded_str": f"{len(results)}/{total} готово",
                                    "total_str": f"{total} файлов", "status": status})
        summary = {"results": results, "errors": errors, "failed_items": failed,
                   "pending_items": copy.deepcopy(pending), "retry_items": copy.deepcopy(failed + pending),
                   "recovery_dirs": [it["recovery_dir"] for it in failed if it.get("recovery_dir")],
                   "save_dir": self.save_dir, "total": total, "success_count": len(results),
                   "error_count": len(errors), "cancelled": cancelled,
                   "is_partial": bool(results and (errors or pending)), "is_all_failed": not results and bool(errors),
                   "is_full_success": bool(results) and not errors and not cancelled}
        if results:
            self.batch_completed.emit(results)
        elif errors and not cancelled:
            self.download_error.emit("\n".join(errors))
        self.batch_summary.emit(summary)
