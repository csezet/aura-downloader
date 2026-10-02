import copy
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtWidgets import QApplication, QDialog
from core.queue_items import normalize_item, parse_sources, default_options
from core.media_importer import MediaImportWorker
from core.unified_batch_worker import UnifiedBatchWorker
from core.workers import worker_registry
from core.settings import settings
from ui.main_window import MainWindow
from ui.batch_dialog import BatchDialog
from ui.trim_dialog import ms_to_fmt, PreviewProxyWorker


def pump_until(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.instance().processEvents()
        if predicate():
            return True
        time.sleep(.01)
    return False


class DownloadStub(QThread):
    progress_updated = Signal(dict)
    status_message = Signal(str)
    download_completed = Signal(dict)
    download_error = Signal(str)
    recovery_available = Signal(dict)
    calls = []

    def __init__(self, url, options, save_dir):
        super().__init__()
        self.url, self.options, self.save_dir = url, options, save_dir
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        self.calls.append((self.url, copy.deepcopy(self.options), self.save_dir))
        if 'fail' in self.url:
            self.download_error.emit('CDN failed')
            return
        self.progress_updated.emit({'percent': 100, 'status': 'downloading'})
        self.progress_updated.emit({'percent': 20, 'status': 'processing'})
        path = Path(self.save_dir) / ('file_' + str(len(self.calls)) + '.mp4')
        path.write_bytes(b'media')
        self.download_completed.emit({'title': 'result', 'file_path': str(path), 'file_size': 5, 'mode': 'MP4'})


class TestQueueWorker(unittest.TestCase):
    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory()
        self.output = self.sandbox.name
        DownloadStub.calls = []

    def tearDown(self):
        self.sandbox.cleanup()

    def test_string_and_tuple_failures_keep_exact_retry_options(self):
        worker = UnifiedBatchWorker(['https://host/fail', ('https://host/fail2', {'audio_fmt': 'opus'})],
                                    {'mode': 'audio_only', 'audio_fmt': 'flac'}, self.output)
        summaries = []
        worker.batch_summary.connect(summaries.append)
        with patch('core.unified_batch_worker.DownloadWorker', DownloadStub):
            worker.run()
        self.assertEqual(len(worker.failed_items), 2)
        self.assertEqual(worker.failed_items[0]['options']['audio_fmt'], 'flac')
        self.assertEqual(worker.failed_items[1]['options']['audio_fmt'], 'opus')
        self.assertEqual(summaries[0]['error_count'], 2)
        self.assertEqual(summaries[0]['save_dir'], self.output)

    def test_worker_snapshots_nested_options_and_never_silently_loses_a_job(self):
        source = {'url': 'local.mp4', 'is_local': True, 'options': {'crop_params': {'x_norm': .2}}}
        worker = UnifiedBatchWorker([source], {'mode': 'best'}, self.output)
        source['options']['crop_params']['x_norm'] = .9
        with patch('core.local_processor.process_single_local_file', return_value=None):
            worker.run()
        self.assertEqual(worker.failed_items[0]['options']['crop_params']['x_norm'], .2)
        self.assertEqual(len(worker.errors), 1)

    def test_cancel_keeps_success_and_marks_remaining_jobs_for_continuation(self):
        items = [{'url': f'local{i}.mp4', 'is_local': True, 'options': {'mode': 'audio_only', 'audio_fmt': 'opus'}} for i in range(3)]
        worker = UnifiedBatchWorker(items, {}, self.output)
        summaries = []
        worker.batch_summary.connect(summaries.append)
        def first_result(*args, **kwargs):
            worker.cancel()
            return {'file_path': str(Path(self.output) / 'saved.opus')}
        with patch('core.local_processor.process_single_local_file', side_effect=first_result):
            worker.run()
        summary = summaries[0]
        self.assertTrue(summary['cancelled'])
        self.assertEqual(len(summary['results']), 1)
        self.assertEqual(len(summary['retry_items']), 2)
        self.assertEqual(summary['retry_items'][0]['options']['audio_fmt'], 'opus')

    def test_started_qthread_receives_child_results_and_monotonic_progress(self):
        worker = UnifiedBatchWorker(['https://host/ok', 'https://host/fail'], {}, self.output)
        summaries, progress = [], []
        worker.batch_summary.connect(summaries.append)
        worker.progress_updated.connect(progress.append)
        with patch('core.unified_batch_worker.DownloadWorker', DownloadStub):
            worker.start()
            self.assertTrue(pump_until(lambda: worker.wait(0) and bool(summaries)))
        self.assertEqual(len(worker.results), 1)
        self.assertEqual(len(worker.failed_items), 1)
        running = [p['percent'] for p in progress if p['status'] == 'processing']
        self.assertEqual(running, sorted(running))

    def test_photo_does_not_inherit_video_transform_options(self):
        item = normalize_item({'url': 'https://host/photo.jpg', 'is_photo': True},
                              {'mode': 'audio_only', 'crop_enabled': True, 'trim_enabled': True, 'smooth_enabled': True})
        self.assertEqual(item['options']['mode'], 'best')
        self.assertFalse(any(item['options'][k] for k in ('crop_enabled', 'trim_enabled', 'smooth_enabled')))

    def test_mixed_input_preserves_paths_with_spaces_and_reports_invalid_lines(self):
        video = Path(self.output) / 'my clip.mp4'
        video.touch()
        sources, errors = parse_sources(f'"{video}"\nhttps://host/video\nhttp://[invalid\nnot a URL')
        self.assertEqual(sources, [str(video), 'https://host/video'])
        self.assertEqual(len(errors), 2)


class TestQueueUI(unittest.TestCase):
    def setUp(self):
        registry = worker_registry()
        registry.stopping = False
        self.defaults = copy.deepcopy(settings.settings)
        self.window = MainWindow()
        self.window.notification_manager.show_download_complete = lambda **kw: None
        self.sandbox = tempfile.TemporaryDirectory()
        DownloadStub.calls = []

    def tearDown(self):
        for worker in list(worker_registry().workers):
            if worker.isRunning():
                worker.requestInterruption()
                if hasattr(worker, 'cancel'):
                    worker.cancel()
                worker.wait(4000)
        QApplication.instance().processEvents()
        self.window.close()
        self.window.deleteLater()
        settings.settings = self.defaults
        worker_registry().stopping = False
        self.sandbox.cleanup()

    def add(self, **extra):
        info = {'url': 'https://host/video', 'title': 'Video', 'width': 320, 'height': 240,
                'duration': 20, 'available_res': ['240p'], **extra}
        self.window._add_queue_item(info)
        return self.window.cards_list.cards[-1]

    def test_new_card_resets_crop_trim_and_honors_audio_preference(self):
        settings.settings['audio_format'] = 'flac'
        first = self.add()
        self.window.crop_widget._crop_params = {'x_norm': .2, 'w_norm': .5}
        self.window.crop_widget.toggle.setChecked(True)
        self.window.trim_widget.toggle.setChecked(True)
        self.window.trim_widget.start_input.setText('1')
        self.window.trim_widget.end_input.setText('2')
        self.window.smooth_widget.toggle.setChecked(True)
        self.window.smooth_widget.fps_combo.setCurrentIndex(2)
        second = self.add(title='Next')
        self.assertIsNone(self.window.crop_widget._crop_params)
        self.assertFalse(self.window.trim_widget.is_trim_enabled())
        self.assertEqual(self.window.trim_widget.start_input.text(), '00:00')
        self.assertEqual(self.window.trim_widget.end_input.text(), '')
        self.assertEqual(self.window.audio_fmt_combo.currentText().split()[0], 'FLAC')
        self.window.cards_list._select_single(first.item_id)
        self.assertEqual(self.window.crop_widget._crop_params['x_norm'], .2)
        self.assertEqual(self.window.trim_widget.start_input.text(), '1')
        self.assertEqual(self.window.smooth_widget.get_target_fps(), 0)

    def test_deselect_all_does_not_run_an_unselected_active_card(self):
        self.add()
        self.window.cards_list.select_all(False)
        self.assertEqual(self.window.cards_list.get_selected_videos(), [])
        self.assertFalse(self.window.download_btn.isEnabled())
        with patch.object(self.window, '_launch_queue') as launch:
            self.window._start_download()
        launch.assert_not_called()

    def test_single_selection_uses_its_own_options_even_when_another_card_is_active(self):
        first = self.add(options={'mode': 'audio_only', 'audio_fmt': 'opus'})
        second = self.add(options={'mode': 'gif'})
        self.window.cards_list.select_all(False)
        first.set_selected(True)
        with patch.object(self.window, '_launch_queue') as launch:
            self.window._start_download()
        snapshot = launch.call_args.args[0]
        self.assertEqual(snapshot[0]['options']['audio_fmt'], 'opus')
        self.assertEqual(snapshot[0]['options']['mode'], 'audio_only')

    def test_apply_selected_settings_is_explicit_and_photos_keep_original(self):
        first = self.add()
        self.add(is_photo=True)
        self.add()
        self.window._set_mode('audio_only')
        self.window.audio_fmt_combo.setCurrentIndex(3)
        self.assertEqual(first.get_options()['mode'], 'best')
        self.window._apply_options_to_selected()
        all_items = self.window.cards_list.get_all_videos()
        self.assertEqual(all_items[0]['options']['audio_fmt'], 'opus')
        self.assertEqual(all_items[1]['options']['mode'], 'best')
        self.assertTrue(self.window.crop_widget.isHidden())

    def test_gallery_enqueues_without_starting_download_or_inventing_dimensions(self):
        class Gallery:
            def __init__(self, *args): pass
            def exec(self): return True
            def get_selected_items(self):
                return [{'url': 'https://cdn/video.mp4', 'is_video': True, 'media_type': 'video'}]
        with patch('ui.main_window.InstagramGalleryDialog', Gallery), patch('ui.main_window.start_worker') as start:
            self.window._on_gallery_ready({})
        start.assert_not_called()
        item = self.window.cards_list.get_all_videos()[0]
        self.assertIsNone(item['width'])
        self.assertFalse(self.window.crop_widget.toggle.isEnabled())
        self.assertTrue(self.window.download_btn.isEnabled())

    def test_batch_dialog_validates_and_returns_sources_without_another_worker(self):
        dialog = BatchDialog(self.window)
        dialog.text_edit.setPlainText('bad line')
        dialog._start_batch()
        self.assertEqual(dialog.result(), QDialog.Rejected)
        self.assertIn('Строка', dialog.status_lbl.text())
        dialog.text_edit.setPlainText('https://host/video')
        dialog.fmt_combo.setCurrentIndex(5)
        dialog._start_batch()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(dialog.options['audio_fmt'], 'opus')
        self.assertEqual(dialog.sources, ['https://host/video'])

    def test_real_thread_finishes_ui_and_retry_uses_original_folder_and_options(self):
        self.add(url='https://host/ok')
        self.add(url='https://host/fail', options={'mode': 'audio_only', 'audio_fmt': 'opus'})
        directory = self.sandbox.name
        with patch('core.unified_batch_worker.DownloadWorker', DownloadStub):
            self.window._launch_queue(self.window.cards_list.get_selected_videos(), directory)
            self.assertTrue(self.window._queue_busy)
            self.assertTrue(pump_until(lambda: not self.window._queue_busy))
            self.assertEqual(len(self.window._last_failed_items), 1)
            self.window._set_mode('gif')
            settings.settings['download_dir'] = str(Path(directory) / 'changed')
            self.window._retry_failed_batch_items()
            self.assertTrue(pump_until(lambda: not self.window._queue_busy))
        self.assertEqual(DownloadStub.calls[-1][1]['audio_fmt'], 'opus')
        self.assertEqual(DownloadStub.calls[-1][2], directory)
        self.assertIn('Готово', self.window.cards_list.cards[0].state_badge.text())
        self.assertFalse(self.window.cards_list.cards[0].is_selected())

    def test_import_is_off_gui_thread_and_clear_ignores_late_results(self):
        source = Path(self.sandbox.name) / 'clip.mp4'
        source.touch()
        entered, release = threading.Event(), threading.Event()
        owner_thread = threading.get_ident()
        calls = []
        def probe(path):
            calls.append(threading.get_ident())
            entered.set()
            release.wait(2)
            return {'url': path, 'is_local': True, 'title': 'clip'}
        with patch('core.local_processor.get_local_media_info', side_effect=probe):
            self.window._load_local_files([str(source)])
            self.assertTrue(entered.wait(1))
            self.window._reset_all_state()
            release.set()
            self.assertTrue(pump_until(lambda: not self.window._import_workers))
        self.assertNotEqual(calls[0], owner_thread)
        self.assertEqual(self.window.cards_list.count(), 0)

    def test_invalid_trim_is_reported_before_worker_start(self):
        self.add()
        self.window.trim_widget.toggle.setChecked(True)
        self.window.trim_widget.start_input.setText('oops')
        with patch.object(self.window, '_launch_queue') as start:
            self.window._start_download()
        start.assert_not_called()
        self.assertIn('Некорректное', self.window.import_status_label.text())

    def test_proxy_worker_runs_outside_gui_and_cancellation_discards_ready_signal(self):
        calls, ready = [], []
        owner = threading.get_ident()
        worker = PreviewProxyWorker('source.mp4')
        worker.ready.connect(ready.append)
        def prepare(path, is_cancelled_cb):
            calls.append(threading.get_ident())
            worker.requestInterruption()
            return 'proxy.mp4'
        with patch('ui.trim_dialog.get_or_create_preview_proxy', side_effect=prepare):
            worker.start()
            self.assertTrue(pump_until(lambda: worker.wait(0)))
        self.assertNotEqual(calls[0], owner)
        self.assertEqual(ready, [])
        self.assertEqual(ms_to_fmt(1250), '00:01.25')
