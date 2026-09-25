import os
import re
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from core.downloader import DownloadWorker, format_bytes


class UnifiedBatchWorker(QThread):
    progress_updated = Signal(dict)
    item_completed = Signal(dict)
    batch_completed = Signal(list)
    batch_summary = Signal(dict)
    download_error = Signal(str)
    status_message = Signal(str)

    def __init__(self, items: list, fallback_options: dict, save_dir: str):
        super().__init__()
        self.items = list(items) if items else []
        self.fallback_options = dict(fallback_options) if fallback_options else {}
        self.save_dir = save_dir
        self.is_cancelled = False
        self._current_worker = None
        self.results = []
        self.errors = []
        self.total = len(self.items)

    def cancel(self):
        self.is_cancelled = True
        if self._current_worker:
            try:
                self._current_worker.cancel()
            except Exception:
                pass

    def run(self):
        from core.local_processor import process_single_local_file, is_video_file
        results = []
        errors = []
        failed_items = []
        total = len(self.items)
        if total == 0:
            return

        os.makedirs(self.save_dir, exist_ok=True)

        for idx, item in enumerate(self.items):
            if self.is_cancelled:
                break

            # 1. Parse item info and options
            if isinstance(item, dict):
                direct_url = item.get('direct_media_url') or item.get('best_image')
                source_url = item.get('url') or item.get('file_path') or direct_url or ''
                path_or_url = source_url.strip().strip('"').strip("'")
                item_title = item.get('title') or Path(path_or_url).name or f"Элемент #{idx+1}"
                is_local = item.get('is_local', False) or is_video_file(path_or_url)
                is_photo = item.get('is_photo', False) or (item.get('media_type') == 'photo')
                is_video = item.get('is_video', False) or (item.get('media_type') == 'video') or item.get('has_video', False)
                card_opts = item.get('options') or {}
                cur_opts = {**self.fallback_options, **card_opts}
                if is_photo:
                    cur_opts['is_photo'] = True
                    cur_opts['media_type'] = 'photo'
                    if direct_url:
                        cur_opts['direct_media_url'] = direct_url
                    cur_opts['title'] = item_title
                elif is_video:
                    cur_opts['is_video'] = True
                    cur_opts['media_type'] = 'video'
                    if direct_url:
                        cur_opts['direct_media_url'] = direct_url
                    cur_opts['title'] = item_title
            elif isinstance(item, tuple):
                path_or_url = str(item[0]).strip().strip('"').strip("'")
                item_title = Path(path_or_url).name or f"Элемент #{idx+1}"
                is_local = is_video_file(path_or_url)
                is_photo = False
                is_video = True
                direct_url = None
                cur_opts = {**self.fallback_options, **(item[1] or {})}
            else:
                path_or_url = str(item).strip().strip('"').strip("'")
                item_title = Path(path_or_url).name or f"Элемент #{idx+1}"
                is_local = is_video_file(path_or_url)
                is_photo = False
                is_video = True
                direct_url = None
                cur_opts = dict(self.fallback_options)

            self.status_message.emit(f"[{idx+1}/{total}] {item_title}")

            def forward_item_progress(prog_data):
                if isinstance(prog_data, dict):
                    item_pct = prog_data.get('percent', 0.0)
                    speed_str = prog_data.get('speed_str', '-- MB/s')
                    overall_pct = ((idx + (item_pct / 100.0)) / total) * 100.0
                    self.progress_updated.emit({
                        'percent': overall_pct,
                        'speed_str': speed_str,
                        'eta_str': prog_data.get('eta_str', '--:--'),
                        'downloaded_str': f"{len(results)}/{total} готово",
                        'total_str': f"{total} в очереди",
                        'status': 'processing'
                    })

            item_result = None
            item_error = None

            try:
                if is_local:
                    # Execute local file processing (FFmpeg)
                    item_result = process_single_local_file(
                        path_or_url,
                        cur_opts,
                        self.save_dir,
                        status_cb=lambda msg: self.status_message.emit(f"[{idx+1}/{total}] {msg}"),
                        progress_cb=forward_item_progress,
                        is_cancelled_cb=lambda: self.is_cancelled
                    )
                else:
                    # Online media download (video/audio/photo)
                    worker = DownloadWorker(path_or_url, cur_opts, self.save_dir)
                    self._current_worker = worker

                    item_recovery_dir = None
                    def on_done(res):
                        nonlocal item_result
                        item_result = res

                    def on_err(err):
                        nonlocal item_error
                        item_error = err

                    def on_rec(info):
                        nonlocal item_recovery_dir
                        item_recovery_dir = info.get('staging_dir')

                    worker.progress_updated.connect(forward_item_progress)
                    worker.status_message.connect(lambda msg: self.status_message.emit(f"[{idx+1}/{total}] {msg}"))
                    worker.download_completed.connect(on_done)
                    worker.download_error.connect(on_err)
                    try:
                        worker.recovery_available.connect(on_rec)
                    except Exception:
                        pass

                    # Run synchronously on this batch thread
                    worker.run()
                    self._current_worker = None

                if self.is_cancelled:
                    break

                if item_result:
                    results.append(item_result)
                    self.item_completed.emit(item_result)
                elif item_error:
                    errors.append(f"{item_title}: {item_error}")
                    item_rec = dict(item)
                    if item_recovery_dir:
                        item_rec['recovery_dir'] = item_recovery_dir
                    failed_items.append(item_rec)
                    self.status_message.emit(f"[{idx+1}/{total}] ОШИБКА: {item_error}")
            except Exception as e:
                errors.append(f"{item_title}: {e}")
                failed_items.append(item)
                self.status_message.emit(f"[{idx+1}/{total}] ОШИБКА: {e}")

        self.results = results
        self.errors = errors
        self.failed_items = failed_items
        self.total = total

        if not self.is_cancelled:
            recovery_dirs = [it.get('recovery_dir') for it in failed_items if it.get('recovery_dir')]
            summary = {
                'results': results,
                'errors': errors,
                'failed_items': failed_items,
                'recovery_dirs': recovery_dirs,
                'total': total,
                'success_count': len(results),
                'error_count': len(errors),
                'is_partial': len(errors) > 0 and len(results) > 0,
                'is_all_failed': len(results) == 0 and len(errors) > 0,
                'is_full_success': len(results) > 0 and len(errors) == 0
            }
            if results and not errors:
                self.progress_updated.emit({
                    'percent': 100.0,
                    'speed_str': "ГОТОВО",
                    'eta_str': "00:00",
                    'downloaded_str': f"{len(results)}/{total} готово",
                    'total_str': f"{total} файлов",
                    'status': 'finished'
                })
                self.batch_completed.emit(results)
                self.batch_summary.emit(summary)
            elif results and errors:
                pct = (len(results) / total) * 100.0
                self.progress_updated.emit({
                    'percent': pct,
                    'speed_str': f"ЧАСТИЧНО ({len(results)}/{total})",
                    'eta_str': "00:00",
                    'downloaded_str': f"{len(results)}/{total} (ошибок: {len(errors)})",
                    'total_str': f"{total} в очереди",
                    'status': 'finished_with_errors'
                })
                self.batch_completed.emit(results)
                self.batch_summary.emit(summary)
            elif errors:
                self.progress_updated.emit({
                    'percent': 0.0,
                    'speed_str': "СБОЙ ОЧЕРЕДИ",
                    'eta_str': "00:00",
                    'downloaded_str': f"0/{total} (ошибок: {len(errors)})",
                    'total_str': f"{total} в очереди",
                    'status': 'error'
                })
                self.download_error.emit("\n".join(errors))
                self.batch_summary.emit(summary)
            else:
                self.download_error.emit("Очередь пуста или отменена.")
