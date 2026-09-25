import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from core.downloader import DownloadWorker
from core.media_converter import is_recovery_staging_dir, cleanup_aura_temp_files, get_recovery_sessions
from core.settings import settings
from ui.progress_widget import ProgressWidget


class TestAudit5A86408Fixes(unittest.TestCase):
    def setUp(self):
        self.save_dir_a = tempfile.mkdtemp(prefix="aura_test_a_")
        self.save_dir_b = tempfile.mkdtemp(prefix="aura_test_b_")
        self.orig_dl_dir = settings.get("download_dir")
        self.orig_known = list(settings.get("known_download_dirs", []))
        self.orig_reg = list(settings.get("recovery_registry", []))

    def tearDown(self):
        settings.set("download_dir", self.orig_dl_dir)
        settings.set("known_download_dirs", self.orig_known)
        settings.set("recovery_registry", self.orig_reg)
        shutil.rmtree(self.save_dir_a, ignore_errors=True)
        shutil.rmtree(self.save_dir_b, ignore_errors=True)

    def test_marker_write_oserror_still_emits_recovery_signal_and_activates_button(self):
        """
        Audit Requirement 1, 2, 3:
        When writing .aura_recovery.json fails with OSError (e.g. disk locked),
        recovery_available is STILL emitted, marker_written is False,
        error message does not promise a marker, ProgressWidget shows active
        recovery button, and staging dir survives cleanup(0).
        """
        widget = ProgressWidget()
        worker = DownloadWorker("https://example.com/test_marker_fail", {'download_subs': True}, self.save_dir_a)

        captured_recovery = []
        worker.recovery_available.connect(lambda info: captured_recovery.append(info))

        def fake_extract_info(url, download=True):
            staging_dirs = [os.path.join(self.save_dir_a, d) for d in os.listdir(self.save_dir_a) if d.startswith(".aura_staging_")]
            self.assertEqual(len(staging_dirs), 1)
            staging = staging_dirs[0]
            with open(os.path.join(staging, "Video.mp4"), "wb") as f:
                f.write(b"video content")
            with open(os.path.join(staging, "Video.ru.srt"), "w", encoding="utf-8") as f:
                f.write("sub content")
            worker._last_filename = os.path.join(staging, "Video.mp4")
            return {'title': 'Video', 'ext': 'mp4'}

        orig_move = shutil.move
        def fake_move(src, dst):
            if str(src).endswith(".ru.srt"):
                raise PermissionError("Access denied moving sub")
            return orig_move(src, dst)

        orig_open = open
        def fake_open(file, mode='r', *args, **kwargs):
            if ".aura_recovery" in str(file) and ('w' in mode or 'x' in mode):
                raise OSError("Disk write failed (simulated OSError)")
            return orig_open(file, mode, *args, **kwargs)

        with patch('core.downloader.yt_dlp.YoutubeDL') as mock_ytdl_cls, \
             patch('core.downloader.probe_video_stream', return_value=True), \
             patch('core.downloader.shutil.move', side_effect=fake_move), \
             patch('builtins.open', side_effect=fake_open):

            mock_ydl = MagicMock()
            mock_ydl.extract_info.side_effect = fake_extract_info
            mock_ydl.prepare_filename.return_value = "Video.mp4"
            mock_ytdl_cls.return_value.__enter__.return_value = mock_ydl

            captured_errors = []
            worker.download_error.connect(lambda msg: captured_errors.append(msg))
            worker.run()

        # 1. Check signal was emitted despite marker write failure!
        self.assertEqual(len(captured_recovery), 1, "recovery_available must be emitted even if marker write fails")
        rec_info = captured_recovery[0]
        self.assertFalse(rec_info.get('marker_written'), "marker_written must be False on failure")
        self.assertIsNotNone(rec_info.get('marker_error'), "marker_error must record the write error")
        staging_dir = rec_info['staging_dir']
        self.assertTrue(os.path.exists(staging_dir))

        # 2. Check error message does not promise a marker
        self.assertEqual(len(captured_errors), 1)
        self.assertIn("служебную метку сохранить не удалось", captured_errors[0])
        self.assertIn("файлы сохранены", captured_errors[0])

        # 3. Check UI receives recovery_dir and shows active button
        widget.set_error(captured_errors[0], recovery_dir=staging_dir)
        self.assertTrue(widget.open_dir_btn.isVisible(), "open_dir_btn must be visible")
        self.assertIn("ОТКРЫТЬ ПАПКУ", widget.open_dir_btn.text())
        self.assertIn(staging_dir, widget.open_dir_btn.toolTip())

        # 4. Check staging directory survives cleanup(0)
        cleanup_aura_temp_files(max_age_hours=0, extra_dirs=[self.save_dir_a])
        self.assertTrue(os.path.exists(staging_dir), "Staging dir with completed video must survive cleanup(0)")

    def test_partial_success_with_recovery_dirs_labels_button_recovery(self):
        """
        Audit Requirement 4:
        In complete() with errors and recovery_dirs, the button is named 'ВОССТАНОВЛЕНИЕ',
        and tooltip points to the recovery directory.
        """
        widget = ProgressWidget()
        rec_dir = os.path.join(self.save_dir_a, ".aura_staging_item1")
        os.makedirs(rec_dir, exist_ok=True)
        with open(os.path.join(rec_dir, "saved.mp4"), "wb") as f:
            f.write(b"data")

        # Result has a successful file, but there was also an error with recovery_dirs
        widget.complete(
            result={'file_path': os.path.join(self.save_dir_a, "success.mp4"), 'success_count': 1},
            errors=["Failed item 2: move error"],
            total=2,
            has_retry=True,
            recovery_dirs=[rec_dir]
        )

        self.assertTrue(widget.open_dir_btn.isVisible())
        self.assertIn("ВОССТАНОВЛЕНИЕ", widget.open_dir_btn.text(), "Button must be labeled ВОССТАНОВЛЕНИЕ")
        self.assertIn(rec_dir, widget.open_dir_btn.toolTip())
        self.assertNotIn("ещё каталогов", widget.open_dir_btn.toolTip())

        # Clicking open_dir_btn opens rec_dir
        with patch('os.startfile') as mock_startfile:
            widget._open_dir()
            mock_startfile.assert_called_once_with(rec_dir)

    def test_partial_success_without_recovery_dirs_labels_button_folder(self):
        """
        Audit Requirement 4:
        In complete() with errors but NO recovery_dirs (e.g. network failure),
        button is named 'ПАПКА', and clicking it opens the successful files directory.
        """
        widget = ProgressWidget()
        success_file = os.path.join(self.save_dir_a, "success.mp4")
        with open(success_file, "wb") as f:
            f.write(b"data")

        widget.complete(
            result={'file_path': success_file, 'success_count': 1},
            errors=["Item 2 failed: 404 Not Found"],
            total=2,
            has_retry=True,
            recovery_dirs=[]
        )

        self.assertTrue(widget.open_dir_btn.isVisible())
        self.assertEqual(widget.open_dir_btn.text(), "📂 ПАПКА", "Button must be labeled ПАПКА when no recovery dirs")
        self.assertIn(self.save_dir_a, widget.open_dir_btn.toolTip())

        # Clicking open_dir_btn opens save_dir_a
        with patch('os.startfile') as mock_startfile:
            widget._open_dir()
            mock_startfile.assert_called_once_with(self.save_dir_a)

    def test_multiple_recovery_dirs_shows_count_and_opens_choice_dialog(self):
        """
        Audit Requirement 5, 6:
        When multiple recovery dirs exist in queue errors, tooltip shows '(ещё каталогов: 1)',
        and clicking open_dir_btn opens selection dialog instead of silently opening just the first.
        """
        widget = ProgressWidget()
        rec1 = os.path.join(self.save_dir_a, ".aura_staging_batch_1")
        rec2 = os.path.join(self.save_dir_a, ".aura_staging_batch_2")
        os.makedirs(rec1, exist_ok=True)
        os.makedirs(rec2, exist_ok=True)

        widget.complete_failed(
            errors=["Err 1", "Err 2"],
            total=2,
            has_retry=True,
            recovery_dirs=[rec1, rec2]
        )

        self.assertTrue(widget.open_dir_btn.isVisible())
        self.assertIn("ВОССТАНОВЛЕНИЕ", widget.open_dir_btn.text())
        self.assertIn("ещё каталогов: 1", widget.open_dir_btn.toolTip())
        self.assertIn("Нажмите для выбора", widget.open_dir_btn.toolTip())

        # Clicking triggers _show_recovery_choice_dialog
        with patch.object(widget, '_show_recovery_choice_dialog') as mock_dlg:
            widget._open_dir()
            mock_dlg.assert_called_once_with([rec1, rec2])

    def test_download_dir_change_preserves_old_sessions_in_settings(self):
        """
        Audit Requirement 7, 8, 9:
        Sessions in folder A remain discoverable after download_dir is changed to folder B.
        Explicit deletion removes the folder and unregisters it.
        """
        # 1. Setup session in folder A
        staging_a = os.path.join(self.save_dir_a, ".aura_staging_sess_a")
        os.makedirs(staging_a, exist_ok=True)
        with open(os.path.join(staging_a, "video_a.mp4"), "wb") as f:
            f.write(b"data_a")

        settings.set("download_dir", self.save_dir_a)
        sessions_initial = get_recovery_sessions()
        found_a = [s for s in sessions_initial if s['path'] == staging_a]
        self.assertEqual(len(found_a), 1)

        # 2. Change download_dir to folder B (like user changing settings)
        settings.set("download_dir", self.save_dir_b)
        self.assertIn(self.save_dir_a, settings.get("known_download_dirs"))

        # 3. Discover sessions without passing target_dirs
        sessions_after_switch = get_recovery_sessions()
        found_a_after = [s for s in sessions_after_switch if s['path'] == staging_a]
        self.assertEqual(len(found_a_after), 1, "Session in folder A must remain discoverable after switching to folder B")

        # 4. Explicit deletion of session A
        shutil.rmtree(staging_a, ignore_errors=True)
        settings.unregister_recovery_session(staging_a)

        sessions_after_delete = get_recovery_sessions()
        found_a_deleted = [s for s in sessions_after_delete if s['path'] == staging_a]
        self.assertEqual(len(found_a_deleted), 0, "Deleted session must not appear in sessions list")


if __name__ == '__main__':
    unittest.main()
