import os
import copy
import subprocess
import ctypes
from ctypes import wintypes
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QComboBox, QFrame, QApplication,
    QSizePolicy, QFileDialog, QSizeGrip, QGridLayout
)
from PySide6.QtCore import Qt, QSize, QEvent, QTimer
from PySide6.QtGui import QColor, QPixmap, QIcon, QShortcut, QKeySequence

from core.settings import settings
from core.history import history
from core.downloader import MetadataWorker
from core.unified_batch_worker import UnifiedBatchWorker
from core.clipboard import ClipboardWatcher
from core.media_converter import check_ffmpeg_available
from assets.styles import get_stylesheet
from assets.icons import get_svg_icon
from ui.window_effects import apply_acrylic_effect, set_native_window_icon
from ui.title_bar import CustomTitleBar
from ui.video_cards_list import VideoCardsListWidget
from ui.progress_widget import ProgressWidget
from ui.history_view import HistoryModal
from ui.trim_widget import TrimWidget
from ui.crop_widget import CropWidget
from ui.smooth_widget import SmoothWidget
from ui.batch_dialog import BatchDialog
from ui.settings_modal import SettingsModal
from ui.playlist_dialog import PlaylistDialog
from ui.gallery_dialog import InstagramGalleryDialog
from core.notifications import NotificationManager
from core.workers import worker_registry, start_worker
from core.queue_items import default_options, normalize_item, validate_item, parse_sources, RESOLUTIONS
from core.media_importer import MediaImportWorker

class DropOverlay(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAcceptDrops(False)
        self.setStyleSheet("""
            DropOverlay {
                background-color: rgba(10, 14, 20, 0.92);
                border: 2px dashed rgba(255, 255, 255, 0.85);
                border-radius: 20px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_svg_icon("upload", color="#FFFFFF", size=48).pixmap(48, 48))
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(icon_lbl)

        title = QLabel("ОТПУСТИТЕ ФАЙЛЫ ДЛЯ ОБРАБОТКИ")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 800; letter-spacing: 1px; background: transparent; border: none;")
        layout.addWidget(title)

        subtitle = QLabel("MP4 • MOV • MKV • WEBM • AVI • ПОДДЕРЖКА ПАЧКИ ВИДЕО")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #A1A1AA; font-size: 11px; font-weight: 700; font-family: 'Consolas', monospace; background: transparent; border: none;")
        layout.addWidget(subtitle)

        self.setVisible(False)

    def show_overlay(self):
        if self.parent():
            self.resize(self.parent().size())
            self.raise_()
        self.setVisible(True)

    def hide_overlay(self):
        self.setVisible(False)


class MainWindow(QMainWindow):
    def __init__(self, icon_path=None):
        super().__init__()
        self.icon_path = icon_path
        if self.icon_path and os.path.exists(self.icon_path):
            self.setWindowIcon(QIcon(self.icon_path))
        self.setWindowTitle("Aura Downloader")
        
        self.resize(880, 820)
        self.setMinimumSize(760, 700)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)

        self.current_mode = "best"
        self.metadata_worker = None
        self.download_worker = None
        self.current_video_info = None
        self._queue_busy = False
        self._pending_summary = None
        self._last_failed_items = []
        self._last_queue_save_dir = None
        self._import_workers = []
        self._import_generation = 0
        self.notification_manager = NotificationManager(parent=self, icon_path=self.icon_path)

        self._active_workers = []
        self._closing = False
        self._close_timer = QTimer(self)
        self._close_timer.setInterval(50)
        self._close_timer.timeout.connect(self._finish_pending_close)

        self.setStatusBar(None)

        self._init_ui()
        self._apply_theme()
        self._setup_clipboard()
        self._is_restoring_ui = True
        self._restore_ui_from_video_info({})
        self._is_restoring_ui = False
        self._setup_shortcuts()

    def _track_worker(self, worker):
        worker_registry().track(worker)
        if worker and worker not in self._active_workers:
            self._active_workers.append(worker)
            try:
                worker.finished.connect(lambda: self._untrack_worker(worker))
            except Exception:
                pass

    def _untrack_worker(self, worker):
        if worker in self._active_workers:
            self._active_workers.remove(worker)

    def closeEvent(self, event):
        registry = worker_registry()
        if registry.is_busy():
            event.ignore()
            self._closing = True
            registry.stopping = True
            self.clipboard_watcher.set_enabled(False)
            self.setEnabled(False)
            self.progress_widget.start_progress("ЗАВЕРШЕНИЕ ФОНОВЫХ ЗАДАЧ...")
            registry.cancel_all()
            self._close_timer.start()
            return
        self._close_timer.stop()
        super().closeEvent(event)

    def _finish_pending_close(self):
        if not worker_registry().is_busy():
            self.close()

    def showEvent(self, event):
        super().showEvent(event)
        hwnd = int(self.winId())
        if self.icon_path and os.path.exists(self.icon_path):
            h_big, h_sm = set_native_window_icon(hwnd, self.icon_path)
            if h_big:
                self._hicon_big = h_big
            if h_sm:
                self._hicon_small = h_sm
        apply_acrylic_effect(hwnd, icon_path=self.icon_path)
        sb = self.statusBar()
        if sb:
            sb.setSizeGripEnabled(False)
            sb.hide()
        for g in self.findChildren(QSizeGrip):
            g.hide()

    def nativeEvent(self, eventType, message):
        if eventType in (b"windows_generic_MSG", "windows_generic_MSG"):
            try:
                msg = wintypes.MSG.from_address(int(message))
                # WM_NCCALCSIZE = 0x0083
                if msg.message == 0x0083 and msg.wParam == 1:
                    return True, 0
                # WM_GETICON = 0x007F
                if msg.message == 0x007F:
                    if getattr(self, '_hicon_big', None) and msg.wParam == 1:
                        return True, self._hicon_big
                    elif getattr(self, '_hicon_small', None) and msg.wParam in (0, 2):
                        return True, self._hicon_small
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'drop_overlay') and self.drop_overlay.isVisible():
            self.drop_overlay.resize(self.central_container.size())

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
            self.drop_overlay.show_overlay()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drop_overlay.hide_overlay()
        event.accept()

    def dropEvent(self, event):
        self.drop_overlay.hide_overlay()
        sources = []
        if event.mimeData().hasUrls():
            sources = [url.toLocalFile() if url.isLocalFile() else url.toString() for url in event.mimeData().urls()]
        elif event.mimeData().hasText():
            sources, errors = parse_sources(event.mimeData().text())
            if errors:
                self._show_input_error("\n".join(errors))
        if sources:
            event.acceptProposedAction()
            self._import_sources(sources, self._read_current_options())
        else:
            event.ignore()

    def _apply_theme(self):
        opacity = settings.get("glass_opacity", 0.45)
        self.setStyleSheet(get_stylesheet(opacity))

    def _init_ui(self):
        self.central_container = QFrame(self)
        self.central_container.setObjectName("CentralWidget")
        self.central_container.setAcceptDrops(True)
        self.setCentralWidget(self.central_container)

        main_layout = QVBoxLayout(self.central_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Custom Title Bar
        self.title_bar = CustomTitleBar(self, title="A U R A   D O W N L O A D E R", icon_path=self.icon_path)
        main_layout.addWidget(self.title_bar)

        # Content Area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(22, 12, 22, 18)
        content_layout.setSpacing(10)

        # 2. Upper Input Bar
        input_bar = QHBoxLayout()
        input_bar.setSpacing(8)

        self.url_input = QLineEdit()
        self.url_input.setObjectName("UrlInput")
        self.url_input.setPlaceholderText("https://... или перетащите видеофайлы (Drag & Drop)")
        self.url_input.setClearButtonEnabled(True)
        self.url_input.returnPressed.connect(self._fetch_metadata)
        input_bar.addWidget(self.url_input, stretch=1)

        self.paste_btn = QPushButton(" ВСТАВИТЬ")
        self.paste_btn.setIcon(get_svg_icon("paste", color="#FFFFFF", size=15))
        self.paste_btn.setIconSize(QSize(15, 15))
        self.paste_btn.setProperty("class", "GlassButton")
        self.paste_btn.clicked.connect(self._paste_and_fetch)
        input_bar.addWidget(self.paste_btn)

        self.file_btn = QPushButton(" ФАЙЛЫ")
        self.file_btn.setIcon(get_svg_icon("file", color="#FFFFFF", size=15))
        self.file_btn.setIconSize(QSize(15, 15))
        self.file_btn.setProperty("class", "GlassButton")
        self.file_btn.setToolTip("Выбрать одно или несколько видео с ПК")
        self.file_btn.clicked.connect(self._open_file_dialog)
        input_bar.addWidget(self.file_btn)

        self.batch_btn = QPushButton(" ПАКЕТ")
        self.batch_btn.setIcon(get_svg_icon("batch", color="#FFFFFF", size=15))
        self.batch_btn.setIconSize(QSize(15, 15))
        self.batch_btn.setProperty("class", "GlassButton")
        self.batch_btn.setToolTip("Пакетная загрузка списка ссылок")
        self.batch_btn.clicked.connect(self._open_batch_dialog)
        input_bar.addWidget(self.batch_btn)

        self.history_btn = QPushButton(" ИСТОРИЯ")
        self.history_btn.setIcon(get_svg_icon("history", color="#FFFFFF", size=15))
        self.history_btn.setIconSize(QSize(15, 15))
        self.history_btn.setProperty("class", "GlassButton")
        self.history_btn.setToolTip("Открыть историю загрузок")
        self.history_btn.clicked.connect(self._open_history_modal)
        input_bar.addWidget(self.history_btn)

        self.settings_btn = QPushButton()
        self.settings_btn.setIcon(get_svg_icon("settings", color="#FFFFFF", size=17))
        self.settings_btn.setIconSize(QSize(17, 17))
        self.settings_btn.setProperty("class", "GlassButton")
        self.settings_btn.setFixedSize(34, 34)
        self.settings_btn.setToolTip("Настройки")
        self.settings_btn.clicked.connect(self._open_settings)
        input_bar.addWidget(self.settings_btn)

        content_layout.addLayout(input_bar)

        self.startup_notice = QLabel(settings.startup_warning or "")
        self.startup_notice.setWordWrap(True)
        self.startup_notice.setStyleSheet("color: #FBBF24; font-size: 12px;")
        self.startup_notice.setVisible(bool(settings.startup_warning))
        content_layout.addWidget(self.startup_notice)

        # FFmpeg Availability Warning Banner
        self.ffmpeg_banner = QFrame()
        self.ffmpeg_banner.setStyleSheet("""
            QFrame {
                background-color: rgba(239, 68, 68, 0.15);
                border: 1px solid rgba(239, 68, 68, 0.4);
                border-radius: 8px;
                padding: 4px 8px;
            }
        """)
        ffmpeg_layout = QHBoxLayout(self.ffmpeg_banner)
        ffmpeg_layout.setContentsMargins(10, 6, 10, 6)
        ffmpeg_layout.setSpacing(10)

        warn_icon = QLabel("⚠️")
        warn_icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        ffmpeg_layout.addWidget(warn_icon)

        self.ffmpeg_warn_label = QLabel("FFmpeg не обнаружен в системе. Операции конвертации, сжатия и обрезки будут ограничены.")
        self.ffmpeg_warn_label.setStyleSheet("color: #FCA5A5; font-size: 12px; font-weight: 500; background: transparent; border: none;")
        self.ffmpeg_warn_label.setWordWrap(True)
        ffmpeg_layout.addWidget(self.ffmpeg_warn_label, stretch=1)

        close_warn_btn = QPushButton("✕")
        close_warn_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #FCA5A5;
                font-weight: bold;
                font-size: 12px;
                max-width: 20px;
            }
            QPushButton:hover {
                color: #FFFFFF;
            }
        """)
        close_warn_btn.clicked.connect(lambda: self.ffmpeg_banner.setVisible(False))
        ffmpeg_layout.addWidget(close_warn_btn)

        content_layout.addWidget(self.ffmpeg_banner)

        ffmpeg_ok, ffmpeg_detail = check_ffmpeg_available()
        self.ffmpeg_banner.setVisible(not ffmpeg_ok)
        if not ffmpeg_ok:
            self.ffmpeg_warn_label.setText(f"⚠️ {ffmpeg_detail}. Конвертация, сжатие и обрезка будут ограничены.")

        # 3. Mode Selection Bar
        self.modes_card = QFrame()
        self.modes_card.setProperty("class", "GlassCard")
        self.modes_card.setFixedHeight(42)
        self.modes_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        modes_layout = QGridLayout(self.modes_card)
        modes_layout.setContentsMargins(6, 5, 6, 5)
        modes_layout.setSpacing(6)

        self.pill_best = QPushButton(" ЛУЧШЕЕ")
        self.pill_best.setIcon(get_svg_icon("sparkles", color="#000000", size=13))
        self.pill_best.setIconSize(QSize(13, 13))
        self.pill_best.setProperty("class", "ModePill")
        self.pill_best.setProperty("active", "true")
        self.pill_best.clicked.connect(lambda: self._set_mode("best"))
        modes_layout.addWidget(self.pill_best, 0, 0)

        self.pill_custom = QPushButton(" ВИДЕО")
        self.pill_custom.setIcon(get_svg_icon("video", color="#EDEDED", size=13))
        self.pill_custom.setIconSize(QSize(13, 13))
        self.pill_custom.setProperty("class", "ModePill")
        self.pill_custom.clicked.connect(lambda: self._set_mode("custom"))
        modes_layout.addWidget(self.pill_custom, 0, 1)

        self.res_combo = QComboBox()
        self.res_combo.addItems(["4K (2160p)", "2K (1440p)", "1080p Full HD", "720p HD", "480p", "360p"])
        self.res_combo.setCurrentText("1080p Full HD")
        self.res_combo.setVisible(False)
        self.res_combo.currentTextChanged.connect(self._update_download_button_text)
        modes_layout.addWidget(self.res_combo, 1, 0, 1, 6)

        self.pill_audio = QPushButton(" АУДИО")
        self.pill_audio.setIcon(get_svg_icon("music", color="#EDEDED", size=13))
        self.pill_audio.setIconSize(QSize(13, 13))
        self.pill_audio.setProperty("class", "ModePill")
        self.pill_audio.clicked.connect(lambda: self._set_mode("audio_only"))
        modes_layout.addWidget(self.pill_audio, 0, 2)

        self.audio_fmt_combo = QComboBox()
        self.audio_fmt_combo.addItems(["MP3 (320k)", "FLAC (Lossless)", "M4A (AAC)", "OPUS", "WAV"])
        self.audio_fmt_combo.setVisible(False)
        self.audio_fmt_combo.currentTextChanged.connect(self._update_download_button_text)
        modes_layout.addWidget(self.audio_fmt_combo, 1, 0, 1, 6)

        self.pill_gif = QPushButton(" GIF")
        self.pill_gif.setIcon(get_svg_icon("gif", color="#EDEDED", size=13))
        self.pill_gif.setIconSize(QSize(13, 13))
        self.pill_gif.setProperty("class", "ModePill")
        self.pill_gif.setToolTip("Конвертировать в анимированный GIF")
        self.pill_gif.clicked.connect(lambda: self._set_mode("gif"))
        modes_layout.addWidget(self.pill_gif, 0, 3)

        self.pill_discord = QPushButton(" DISCORD")
        self.pill_discord.setIcon(get_svg_icon("discord", color="#EDEDED", size=13))
        self.pill_discord.setIconSize(QSize(13, 13))
        self.pill_discord.setProperty("class", "ModePill")
        self.pill_discord.setToolTip("Сжать видео для отправки в Discord (< 8 МБ)")
        self.pill_discord.clicked.connect(lambda: self._set_mode("discord_8mb"))
        modes_layout.addWidget(self.pill_discord, 0, 4)

        self.pill_video_only = QPushButton(" БЕЗ ЗВУКА")
        self.pill_video_only.setIcon(get_svg_icon("mute", color="#EDEDED", size=13))
        self.pill_video_only.setIconSize(QSize(13, 13))
        self.pill_video_only.setProperty("class", "ModePill")
        self.pill_video_only.setToolTip("Только видеоряд без аудио")
        self.pill_video_only.clicked.connect(lambda: self._set_mode("video_only"))
        modes_layout.addWidget(self.pill_video_only, 0, 5)

        content_layout.addWidget(self.modes_card)

        # 4. Trimmer, Crop & Smooth FPS Widgets
        tools_layout = QVBoxLayout()
        tools_layout.setSpacing(6)

        self.trim_widget = TrimWidget()
        tools_layout.addWidget(self.trim_widget)

        self.crop_widget = CropWidget()
        tools_layout.addWidget(self.crop_widget)

        self.smooth_widget = SmoothWidget()
        tools_layout.addWidget(self.smooth_widget)

        # Real-time auto-save options to active video card
        self._is_restoring_ui = False
        self.trim_widget.trim_toggled.connect(lambda _: self._auto_save_active_options())
        self.trim_widget.start_input.textChanged.connect(lambda _: self._auto_save_active_options())
        self.trim_widget.end_input.textChanged.connect(lambda _: self._auto_save_active_options())
        self.crop_widget.crop_toggled.connect(lambda _: self._auto_save_active_options())
        self.crop_widget.crop_changed.connect(lambda _: self._auto_save_active_options())
        self.smooth_widget.smooth_toggled.connect(lambda _: self._auto_save_active_options())
        self.smooth_widget.fps_combo.currentIndexChanged.connect(lambda _: self._auto_save_active_options())
        self.res_combo.currentIndexChanged.connect(lambda _: self._auto_save_active_options())
        self.audio_fmt_combo.currentIndexChanged.connect(lambda _: self._auto_save_active_options())

        content_layout.addLayout(tools_layout)

        queue_bar = QHBoxLayout()
        self.queue_count_label = QLabel("В очереди: 0 · выбрано: 0")
        self.queue_count_label.setStyleSheet("color: #A1A1AA; font-size: 11px;")
        queue_bar.addWidget(self.queue_count_label, 1)
        self.queue_buttons = []
        for text, callback in (("Выбрать все", lambda: self.cards_list.select_all()),
                               ("Снять выбор", lambda: self.cards_list.select_all(False)),
                               ("Применить к выбранным", self._apply_options_to_selected),
                               ("Очистить", self._reset_all_state)):
            button = QPushButton(text)
            button.setProperty("class", "GlassButton")
            button.setStyleSheet("font-size: 10px; padding: 4px 8px;")
            button.clicked.connect(callback)
            queue_bar.addWidget(button)
            self.queue_buttons.append(button)
        content_layout.addLayout(queue_bar)

        self.editor_hint = QLabel("Настройки относятся к активной карточке. Флажки выбирают элементы для запуска.")
        self.editor_hint.setWordWrap(True)
        self.editor_hint.setStyleSheet("color: #A1A1AA; font-size: 11px;")
        content_layout.addWidget(self.editor_hint)
        self.metadata_details_btn = QPushButton("Уточнить данные видео для кадрирования")
        self.metadata_details_btn.setProperty("class", "GlassButton")
        self.metadata_details_btn.clicked.connect(self._fetch_active_details)
        self.metadata_details_btn.setVisible(False)
        content_layout.addWidget(self.metadata_details_btn)

        self.import_status_label = QLabel()
        self.import_status_label.setWordWrap(True)
        self.import_status_label.setStyleSheet("color: #93C5FD; font-size: 11px;")
        self.import_status_label.setVisible(False)
        content_layout.addWidget(self.import_status_label)

        # 5. Full Video Cards List (Supports duplicate videos, smooth wheel scrolling without scrollbars)
        self.cards_list = VideoCardsListWidget()
        self.cards_list.active_video_changed.connect(self._on_active_video_changed)
        self.cards_list.active_thumbnail_updated.connect(self._on_active_thumbnail_updated)
        self.cards_list.list_changed.connect(self._on_cards_list_changed)
        content_layout.addWidget(self.cards_list, stretch=10)

        # 5.1 Empty State Placeholder (Visible when no cards loaded)
        self.empty_placeholder = QFrame()
        self.empty_placeholder.setObjectName("EmptyPlaceholder")
        self.empty_placeholder.setStyleSheet("""
            QFrame#EmptyPlaceholder {
                background-color: rgba(255, 255, 255, 0.018);
                border: 1px dashed rgba(255, 255, 255, 0.12);
                border-radius: 14px;
            }
        """)
        ep_layout = QVBoxLayout(self.empty_placeholder)
        ep_layout.setAlignment(Qt.AlignCenter)
        ep_layout.setContentsMargins(16, 24, 16, 24)
        ep_layout.setSpacing(6)

        ep_icon = QLabel()
        ep_icon.setPixmap(get_svg_icon("download", color="#71717A", size=26).pixmap(26, 26))
        ep_icon.setAlignment(Qt.AlignCenter)
        ep_icon.setStyleSheet("background: transparent; border: none;")
        ep_layout.addWidget(ep_icon)

        ep_title = QLabel("Перетащите видеофайлы или вставьте ссылку")
        ep_title.setAlignment(Qt.AlignCenter)
        ep_title.setStyleSheet("color: #A1A1AA; font-size: 12px; font-weight: 600; background: transparent; border: none;")
        ep_layout.addWidget(ep_title)

        ep_sub = QLabel("YouTube • Instagram • TikTok • VK • Файлы с ПК")
        ep_sub.setAlignment(Qt.AlignCenter)
        ep_sub.setStyleSheet("color: #52525B; font-size: 11px; font-weight: 500; font-family: 'Consolas', monospace; background: transparent; border: none;")
        ep_layout.addWidget(ep_sub)

        content_layout.addWidget(self.empty_placeholder)

        # 6. Progress Widget
        self.progress_widget = ProgressWidget()
        self.progress_widget.cancelled.connect(self._cancel_download)
        self.progress_widget.retry_requested.connect(self._retry_failed_batch_items)
        content_layout.addWidget(self.progress_widget)

        # Elastic Stretch pushes Action Button & Footer down cleanly when list is empty
        content_layout.addStretch(1)

        # 7. Main Action Button
        self.download_btn = QPushButton("  СКАЧАТЬ В ЛУЧШЕМ КАЧЕСТВЕ (MP4)")
        self.download_btn.setIcon(get_svg_icon("download", color="#000000", size=18))
        self.download_btn.setIconSize(QSize(18, 18))
        self.download_btn.setObjectName("PrimaryButton")
        self.download_btn.setMinimumHeight(44)
        self.download_btn.setCursor(Qt.PointingHandCursor)
        self.download_btn.clicked.connect(self._start_download)
        content_layout.addWidget(self.download_btn)

        # 8. Footer
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(4, 2, 4, 2)

        self.dest_lbl = QLabel(f"DIR: {settings.get('download_dir')}")
        self.dest_lbl.setStyleSheet("font-size: 10px; color: #71717A; font-family: 'Consolas', monospace;")
        footer_layout.addWidget(self.dest_lbl, stretch=1)

        open_folder_btn = QPushButton(" ОТКРЫТЬ ПАПКУ")
        open_folder_btn.setIcon(get_svg_icon("folder", color="#FFFFFF", size=12))
        open_folder_btn.setIconSize(QSize(12, 12))
        open_folder_btn.setProperty("class", "GlassButton")
        open_folder_btn.setStyleSheet("font-size: 10px; padding: 3px 8px; font-weight: 700;")
        open_folder_btn.clicked.connect(self._open_dest_dir)
        footer_layout.addWidget(open_folder_btn)

        content_layout.addLayout(footer_layout)
        main_layout.addWidget(content_widget)

        # 9. Full-Window Animated Drop Overlay
        self.drop_overlay = DropOverlay(self.central_container)

        # 10. Check for preserved recovery sessions on launch
        try:
            from core.media_converter import get_recovery_sessions
            sessions = get_recovery_sessions()
            if sessions:
                count = len(sessions)
                notice = f"Найдено сессий восстановления: {count}. Откройте раздел восстановления в настройках."
                self.startup_notice.setText("\n".join(filter(None, [settings.startup_warning, notice])))
                self.startup_notice.setVisible(True)
        except Exception:
            pass

    def _setup_clipboard(self):
        self.clipboard_watcher = ClipboardWatcher(self)
        self.clipboard_watcher.url_detected.connect(self._on_clipboard_url)

    def _on_clipboard_url(self, url: str):
        if settings.get("auto_paste", False) and not self._queue_busy and not self.url_input.text().strip():
            self.url_input.setText(url)

    def _paste_and_fetch(self):
        text = self.url_input.text().strip() or QApplication.clipboard().text().strip()
        if text:
            self.url_input.setText(text)
            self._fetch_metadata()

    def _open_file_dialog(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите видео для обработки",
            "",
            "Видео файлы (*.mp4 *.mov *.mkv *.webm *.avi *.flv *.wmv *.m4v *.ts);;Все файлы (*.*)"
        )
        if file_paths:
            self._load_local_files(file_paths)

    def _load_local_files(self, file_paths):
        self._import_sources(file_paths, default_options(settings))

    def _import_sources(self, sources, options):
        if self._closing or not sources:
            return
        worker = MediaImportWorker(sources, options)
        generation = self._import_generation
        self._import_workers.append(worker)
        worker.item_ready.connect(lambda info: self._add_queue_item(info) if generation == self._import_generation else None)
        worker.status_message.connect(lambda message: self.import_status_label.setText(message) if generation == self._import_generation else None)
        worker.import_finished.connect(lambda summary: self._on_import_finished(summary) if generation == self._import_generation else None)
        worker.finished.connect(lambda: self._import_workers.remove(worker) if worker in self._import_workers else None)
        self.import_status_label.setText("Подготовка элементов очереди...")
        self.import_status_label.setVisible(True)
        start_worker(worker, self)

    def _on_import_finished(self, summary):
        if self._closing:
            return
        errors = summary.get('errors', [])
        text = f"Добавлено: {summary.get('added', 0)}. Настройте карточки и нажмите запуск."
        if errors:
            text += "\n" + "\n".join(errors[:3])
        elif not summary.get('added'):
            text = "Подходящие видео не найдены." if not summary.get('cancelled') else "Подготовка остановлена."
        self.import_status_label.setText(text)
        self._update_download_button_text()

    def _add_queue_item(self, info):
        if not self._closing:
            self.cards_list.add_video(normalize_item(info, default_options(settings)))

    def _read_current_options(self):
        trim_start, trim_end = self.trim_widget.get_trim_range()
        return {'mode': self.current_mode,
                'res': self.res_combo.currentText(),
                'audio_fmt': self.audio_fmt_combo.currentText().split()[0].lower(),
                'audio_q': settings.get('audio_quality', '320'),
                'download_subs': settings.get('download_subtitles', False),
                'trim_enabled': self.trim_widget.is_trim_enabled(), 'trim_start': trim_start, 'trim_end': trim_end,
                'crop_enabled': self.crop_widget.is_crop_enabled(), 'crop_params': copy.deepcopy(self.crop_widget.get_crop_params()),
                'smooth_enabled': self.smooth_widget.is_smooth_enabled(), 'smooth_fps': self.smooth_widget.get_target_fps(),
                'smooth_model': self.smooth_widget.get_model()}

    def _apply_options_to_selected(self):
        if self._queue_busy:
            return
        options = self._read_current_options()
        for item in self.cards_list.get_selected_videos():
            normalized = normalize_item({**item, 'options': options})
            self.cards_list.save_card_options(item['item_id'], normalized['options'])
        self.import_status_label.setText("Настройки применены к выбранным карточкам.")
        self.import_status_label.setVisible(True)

    def _show_input_error(self, message):
        self.import_status_label.setText(message)
        self.import_status_label.setVisible(True)
        self.url_input.setFocus()

    def _setup_shortcuts(self):
        self._shortcuts = []
        for sequence, callback in (("Ctrl+O", self._open_file_dialog), ("Ctrl+B", self._open_batch_dialog),
                                   ("Ctrl+Return", self._start_download), ("Ctrl+L", self.url_input.setFocus)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)
        self.download_btn.setToolTip("Запустить выбранные элементы · Ctrl+Enter")
        self.file_btn.setToolTip("Добавить видео · Ctrl+O")
        self.batch_btn.setToolTip("Добавить список ссылок и файлов · Ctrl+B")

    def _save_current_ui_to_video_info(self):
        if not self.current_video_info or self._queue_busy:
            return
        options = normalize_item({**self.current_video_info, 'options': self._read_current_options()})['options']
        self.current_video_info['options'] = copy.deepcopy(options)
        self.cards_list.save_card_options(self.current_video_info.get('item_id'), options)

    def _auto_save_active_options(self):
        if getattr(self, '_is_restoring_ui', False):
            return
        self._save_current_ui_to_video_info()

    def _restore_ui_from_video_info(self, info):
        opts = {**default_options(settings), **(info.get('options') or {})}
        self._set_mode(opts.get('mode', 'best'))
        available = info.get('available_res') or RESOLUTIONS
        self.res_combo.clear()
        self.res_combo.addItems(available)
        resolution = opts.get('res') or available[0]
        if self.res_combo.findText(resolution) < 0:
            self.res_combo.addItem(resolution)
        self.res_combo.setCurrentText(resolution)
        for index in range(self.audio_fmt_combo.count()):
            if self.audio_fmt_combo.itemText(index).split()[0].lower() == opts.get('audio_fmt', 'mp3'):
                self.audio_fmt_combo.setCurrentIndex(index)
                break
        self.trim_widget.start_input.setText(opts.get('trim_start') or '00:00')
        self.trim_widget.end_input.setText(opts.get('trim_end') or '')
        self.trim_widget.toggle.setChecked(bool(opts.get('trim_enabled')))
        self.crop_widget._crop_params = copy.deepcopy(opts.get('crop_params'))
        self.crop_widget.toggle.setChecked(bool(opts.get('crop_enabled')))
        self.crop_widget.status_tag.setVisible(bool(opts.get('crop_enabled') and opts.get('crop_params')))
        crop = opts.get('crop_params') or {}
        self.crop_widget.status_tag.setText(f"{crop.get('w', '?')}×{crop.get('h', '?')}")
        self.smooth_widget.fps_combo.setCurrentIndex({60: 0, 120: 1, 0: 2}.get(opts.get('smooth_fps', 60), 0))
        self.smooth_widget.toggle.setChecked(bool(opts.get('smooth_enabled')))

    def _on_active_thumbnail_updated(self, pixmap):
        if self.current_video_info and pixmap and not pixmap.isNull():
            self.crop_widget.set_source_info(pixmap, width=self.current_video_info.get('width') or 0,
                                            height=self.current_video_info.get('height') or 0)

    def _on_active_video_changed(self, info, pixmap):
        self._is_restoring_ui = True
        try:
            self.current_video_info = info
            self.crop_widget.set_source_info(pixmap, width=info.get('width') or 0, height=info.get('height') or 0)
            playable = info.get('preview_url') or info.get('playable_url') or info.get('direct_url')
            if info.get('is_local') or info.get('direct_media_url'):
                playable = playable or info.get('url')
            # A website page is not a media stream. Resolve it when opening the editor.
            playable = playable or {'url': info.get('url')}
            self.trim_widget.set_source_video(playable, info.get('duration') or 0)
            self._restore_ui_from_video_info(info)
            self._refresh_editor_visibility()
            self._update_download_button_text()
        finally:
            self._is_restoring_ui = False

    def _refresh_editor_visibility(self):
        info = self.current_video_info or {}
        photo = info.get('is_photo') or info.get('media_type') == 'photo'
        self.modes_card.setVisible(not photo)
        self.trim_widget.setVisible(not photo)
        self.crop_widget.setVisible(not photo and self.current_mode != 'audio_only')
        self.smooth_widget.setVisible(not photo and self.current_mode not in ('audio_only', 'gif'))
        dimensions_known = bool(info.get('width') and info.get('height'))
        self.crop_widget.toggle.setEnabled(dimensions_known and not self._queue_busy)
        self.crop_widget.edit_btn.setEnabled(dimensions_known and self.crop_widget.is_crop_enabled() and not self._queue_busy)
        self.trim_widget.visual_btn.setEnabled(bool(info.get('url')) and self.trim_widget.is_trim_enabled() and not self._queue_busy)
        unknown = bool(info and not photo and not dimensions_known and not info.get('is_local'))
        self.metadata_details_btn.setVisible(unknown)
        self.metadata_details_btn.setEnabled(not self._queue_busy)
        title = info.get('title') or 'активная карточка'
        self.editor_hint.setText(f"Настройки: {title}. Для нескольких файлов используйте «Применить к выбранным».")

    def _on_cards_list_changed(self, count: int):
        if hasattr(self, 'empty_placeholder'):
            self.empty_placeholder.setVisible(count == 0)
        if count == 0:
            self.current_video_info = None
            if hasattr(self, 'modes_card'):
                self.modes_card.setVisible(True)
            self.crop_widget.toggle.setChecked(False)
            self.trim_widget.toggle.setChecked(False)
            self.smooth_widget.toggle.setChecked(False)
            self.trim_widget.setVisible(True)
            self.smooth_widget.setVisible(True)
        self._update_download_button_text()

    def _reset_all_state(self):
        if self._queue_busy:
            return
        self._import_generation += 1
        self._last_failed_items = []
        self.progress_widget.hide_progress()
        self.import_status_label.setVisible(False)
        if self.metadata_worker:
            self.metadata_worker.cancel()
            self.metadata_worker = None
        for worker in self._import_workers:
            worker.cancel()
        self.current_video_info = None
        self.url_input.blockSignals(True)
        self.url_input.clear()
        self.url_input.blockSignals(False)
        self.cards_list.clear_all()
        if hasattr(self, 'empty_placeholder'):
            self.empty_placeholder.setVisible(True)
        if hasattr(self, 'modes_card'):
            self.modes_card.setVisible(True)
        self.crop_widget.toggle.setChecked(False)
        self.trim_widget.toggle.setChecked(False)
        self.smooth_widget.toggle.setChecked(False)
        self.trim_widget.setVisible(True)
        self.smooth_widget.setVisible(True)
        self._refresh_editor_visibility()
        self._update_download_button_text()

    def _fetch_metadata(self):
        if self._closing:
            return
        text = self.url_input.text().strip()
        sources, errors = parse_sources(text)
        if errors:
            self._show_input_error("\n".join(errors))
            return
        if not sources:
            return
        self.url_input.blockSignals(True)
        self.url_input.clear()
        self.url_input.blockSignals(False)
        if len(sources) != 1 or not sources[0].startswith(('http://', 'https://')):
            self._import_sources(sources, default_options(settings))
            return
        self._start_metadata_worker(sources[0])

    def _fetch_active_details(self):
        if self.current_video_info and not self._queue_busy:
            self._start_metadata_worker(self.current_video_info['url'], self.current_video_info.get('item_id'))

    def _start_metadata_worker(self, url, item_id=None):
        if self.metadata_worker and self.metadata_worker.isRunning():
            if self.metadata_worker.url == url and not self.metadata_worker.is_cancelled:
                return
            self.metadata_worker.cancel()
        worker = MetadataWorker(url)
        self.metadata_worker = worker
        self.import_status_label.setText("Получение информации о видео...")
        self.import_status_label.setVisible(True)
        def ready(info):
            if self._closing or worker is not self.metadata_worker:
                return
            if item_id:
                self.cards_list.update_card_info(item_id, info)
            else:
                self._on_metadata_ready(info)
            self.import_status_label.setText("Карточка готова. Настройте параметры и запустите обработку.")
        def gallery(info):
            if not self._closing and worker is self.metadata_worker:
                self._on_gallery_ready(info)
        def playlist(info):
            if not self._closing and worker is self.metadata_worker:
                self._on_playlist_ready(info)
        def failed(error):
            if not self._closing and worker is self.metadata_worker:
                self._on_metadata_error(error)
        worker.info_ready.connect(ready)
        worker.gallery_ready.connect(gallery)
        worker.playlist_ready.connect(playlist)
        worker.info_error.connect(failed)
        self._track_worker(worker)
        start_worker(worker, self)

    def _on_gallery_ready(self, gallery_data: dict):
        if self._closing:
            return
        self.download_btn.setEnabled(True)
        self._update_download_button_text()

        dialog = InstagramGalleryDialog(gallery_data, self)
        if dialog.exec():
            selected = dialog.get_selected_items()
            if not selected:
                return

            # Display cards for all selected items in main cards_list
            for item in selected:
                is_vid = bool(item.get('is_video') or item.get('media_type') == 'video')
                media_url = item.get('url') if is_vid else (item.get('best_image') or item.get('url'))
                info = {
                    'url': media_url,
                    'direct_url': media_url,
                    'direct_media_url': media_url,
                    'playable_url': media_url,
                    'title': item.get('title') or f"Instagram {'Видео' if is_vid else 'Фото'} #{item.get('index', 1)}",
                    'uploader': item.get('uploader') or gallery_data.get('uploader') or 'Instagram',
                    'duration': item.get('duration') or 0,
                    'duration_str': 'ФОТО' if not is_vid else 'ВИДЕО',
                    'thumbnail': item.get('thumbnail') or item.get('best_image'),
                    'platform': 'Instagram',
                    'available_res': ['Оригинал (JPG)'] if not is_vid else ['1080p Full HD'],
                    'has_video': is_vid,
                    'is_photo': not is_vid,
                    'is_video': is_vid,
                    'media_type': 'video' if is_vid else 'photo',
                    'width': item.get('width'),
                    'height': item.get('height')
                }
                self._add_queue_item(info)

            self.import_status_label.setText(f"Добавлено из галереи: {len(selected)}. Настройте карточки и нажмите запуск.")
            self.import_status_label.setVisible(True)

    def _on_playlist_ready(self, playlist_data: dict):
        if self._closing:
            return
        self.download_btn.setEnabled(True)
        self._update_download_button_text()

        dialog = PlaylistDialog(playlist_data, self)
        if dialog.exec():
            selected = dialog.get_selected_entries()
            for item in selected:
                info = {
                    'url': item.get('url'),
                    'direct_url': None,
                    'playable_url': None,
                    'title': item.get('title', 'Без названия'),
                    'uploader': item.get('uploader', 'Автор'),
                    'duration': item.get('duration', 0),
                    'duration_str': item.get('duration_str', '--:--'),
                    'thumbnail': item.get('thumbnail'),
                    'platform': 'youtube',
                    'available_res': ['1080p Full HD', '720p HD', '480p'],
                    'has_video': True,
                    'width': item.get('width'),
                    'height': item.get('height')
                }
                self._add_queue_item(info)

    def _on_metadata_ready(self, info: dict):
        if self._closing:
            return
        self._add_queue_item(info)
        self.download_btn.setEnabled(True)
        self._update_download_button_text()

    def _on_metadata_error(self, err_msg):
        self._show_input_error(err_msg)
        self._update_download_button_text()

    def _set_mode(self, mode: str):
        self.current_mode = mode
        pill_map = [
            (self.pill_best, "sparkles", "best"),
            (self.pill_custom, "video", "custom"),
            (self.pill_audio, "music", "audio_only"),
            (self.pill_gif, "gif", "gif"),
            (self.pill_discord, "discord", "discord_8mb"),
            (self.pill_video_only, "mute", "video_only"),
        ]

        self.res_combo.setVisible(mode in ["custom", "video_only"])
        self.audio_fmt_combo.setVisible(mode == "audio_only")

        self.modes_card.setFixedHeight(76 if mode in ("audio_only", "custom", "video_only") else 42)
        self._refresh_editor_visibility()

        for pill, icon_name, p_mode in pill_map:
            if p_mode == mode:
                pill.setProperty("active", "true")
                pill.setIcon(get_svg_icon(icon_name, color="#000000", size=13))
            else:
                pill.setProperty("active", "false")
                pill.setIcon(get_svg_icon(icon_name, color="#EDEDED", size=13))
            pill.style().unpolish(pill)
            pill.style().polish(pill)

        self._update_download_button_text()
        self._auto_save_active_options()

    def _update_download_button_text(self):
        if not hasattr(self, 'download_btn'):
            return
        selected = self.cards_list.get_selected_videos()
        count = len(selected)
        self.queue_count_label.setText(f"В очереди: {self.cards_list.count()} · выбрано: {count}")
        self.download_btn.setEnabled(bool(count) and not self._queue_busy and not self._closing)
        if self._queue_busy:
            self.download_btn.setText("  ВЫПОЛНЯЕТСЯ ОЧЕРЕДЬ...")
        elif count > 1:
            self.download_btn.setText(f"  ЗАПУСТИТЬ ВЫБРАННЫЕ ({count})")
        elif count == 1:
            item = selected[0]
            opts = item.get('options') or default_options(settings)
            if item.get('is_photo'):
                label = 'СКАЧАТЬ ФОТО'
            elif opts.get('mode') == 'audio_only':
                label = f"ИЗВЛЕЧЬ АУДИО [{opts.get('audio_fmt', 'mp3').upper()}]"
            elif item.get('is_local'):
                label = 'ОБРАБОТАТЬ И СОХРАНИТЬ'
            else:
                label = 'СКАЧАТЬ И СОХРАНИТЬ'
            self.download_btn.setText('  ' + label)
        else:
            self.download_btn.setText("  ВЫБЕРИТЕ ЭЛЕМЕНТЫ ДЛЯ ЗАПУСКА")

    def _set_queue_busy(self, busy):
        self._queue_busy = busy
        self.cards_list.set_busy(busy)
        for widget in (self.modes_card, self.trim_widget, self.crop_widget, self.smooth_widget):
            widget.setEnabled(not busy)
        for button in self.queue_buttons:
            button.setEnabled(not busy)
        self.progress_widget.retry_btn.setEnabled(not busy)
        self._refresh_editor_visibility()
        self._update_download_button_text()

    def _start_download(self):
        if self._queue_busy or self._closing:
            return
        self._save_current_ui_to_video_info()
        items = self.cards_list.get_selected_videos()
        if not items:
            if self.url_input.text().strip():
                self._fetch_metadata()
            return
        for item in items:
            try:
                validate_item(item)
            except (ValueError, OSError) as error:
                self._show_input_error(f"{item.get('title', 'Файл')}: {error}")
                return
        self._launch_queue(items, settings.get('download_dir'))

    def _launch_queue(self, items, save_dir):
        if self._queue_busy or self._closing:
            return
        self._last_queue_save_dir = save_dir
        self._last_failed_items = []
        self._pending_summary = None
        self.progress_widget.start_progress("ПОДГОТОВКА ОЧЕРЕДИ...")
        self._set_queue_busy(True)
        worker = UnifiedBatchWorker(items, default_options(settings), save_dir)
        self.download_worker = worker
        for item in worker.items:
            self.cards_list.update_item_state({'item_id': item['item_id'], 'state': 'waiting'})
        worker.progress_updated.connect(self.progress_widget.update_progress)
        worker.item_state_changed.connect(self.cards_list.update_item_state)
        worker.item_completed.connect(self._on_queue_item_completed)
        worker.batch_summary.connect(lambda summary: self._receive_queue_summary(worker, summary))
        worker.status_message.connect(lambda message: self.progress_widget.status_label.setText(message))
        worker.finished.connect(lambda: self._finish_queue(worker))
        self._track_worker(worker)
        start_worker(worker, self)

    def _receive_queue_summary(self, worker, summary):
        if worker is self.download_worker:
            self._pending_summary = summary

    def _finish_queue(self, worker):
        if not worker.wait(0):
            QTimer.singleShot(20, lambda: self._finish_queue(worker))
            return
        if worker is not self.download_worker or self._closing:
            return
        self._set_queue_busy(False)
        summary = self._pending_summary
        self._pending_summary = None
        if summary:
            self._on_batch_summary(summary)
        else:
            self.progress_widget.set_error("Очередь остановилась до получения результата.")

    def _on_queue_item_completed(self, result: dict):
        fmt_title = result.get('mode', 'MP4').upper()
        history.add_entry(
            title=result.get('title'),
            url=result.get('url'),
            file_path=result.get('file_path'),
            format_type=result.get('format_type') or fmt_title,
            size_bytes=result.get('file_size', 0),
            thumbnail=result.get('thumbnail')
        )

    def _on_batch_summary(self, summary: dict):
        self.download_btn.setEnabled(True)
        self._update_download_button_text()

        results = summary.get('results', [])
        errors = summary.get('errors', [])
        failed_items = summary.get('failed_items', [])
        recovery_dirs = summary.get('recovery_dirs', [])
        total = summary.get('total', len(results) + len(errors))
        success_count = summary.get('success_count', len(results))
        self._last_failed_items = copy.deepcopy(summary.get("retry_items", failed_items))
        self._last_queue_save_dir = summary.get("save_dir") or self._last_queue_save_dir
        self.progress_widget.cancel_btn.setEnabled(True)
        if summary.get("cancelled"):
            self.progress_widget.complete_cancelled(summary)
            return

        # 1. Total failure (0 / N)
        if success_count == 0:
            self.progress_widget.complete_failed(
                errors=errors,
                total=total,
                has_retry=bool(failed_items),
                recovery_dirs=recovery_dirs
            )
            return

        # 2. Partial or Full Success
        last_res = dict(results[-1]) if results else {'file_path': settings.get("download_dir"), 'file_size_str': f"{len(results)} файлов"}
        last_res['success_count'] = success_count
        last_res['total_count'] = total
        is_all_photos = all(r.get('mode') in ['JPG', 'PNG', 'WEBP'] for r in results) if results else False
        last_res['mode'] = f"Галерея ({len(results)} фото)" if is_all_photos else f"Пакет ({len(results)} шт)"

        if errors:
            self.progress_widget.complete(last_res, errors=errors, total=total, has_retry=bool(failed_items), recovery_dirs=recovery_dirs)
            if hasattr(self, 'notification_manager'):
                self.notification_manager.show_download_complete(
                    title=f"Завершено частично: {success_count}/{total} (ошибок: {len(errors)})",
                    file_path=last_res.get('file_path')
                )
        else:
            self.progress_widget.complete(last_res, errors=None, total=total, has_retry=False)
            if hasattr(self, 'notification_manager'):
                notice_title = f"Сохранено файлов: {len(results)}"
                self.notification_manager.show_download_complete(
                    title=notice_title,
                    file_path=last_res.get('file_path')
                )

    def _on_batch_success(self, results: list):
        errors = getattr(self.download_worker, 'errors', [])
        failed_items = getattr(self.download_worker, 'failed_items', [])
        self._on_batch_summary({
            'results': results,
            'errors': errors,
            'failed_items': failed_items,
            'total': len(results) + len(errors),
            'success_count': len(results)
        })

    def _retry_failed_batch_items(self):
        if self._queue_busy or not self._last_failed_items:
            return
        self._launch_queue(copy.deepcopy(self._last_failed_items), self._last_queue_save_dir or settings.get('download_dir'))

    def _on_download_success(self, result: dict):
        self.download_btn.setEnabled(True)
        self._update_download_button_text()
        self.progress_widget.complete(result)

        fmt_title = result.get('mode', 'MP4').upper()
        if self.current_mode == 'audio_only':
            fmt_title = result.get('file_path', '').split('.')[-1].upper()
        elif self.current_mode == 'custom':
            fmt_title = self.res_combo.currentText()

        history.add_entry(
            title=result.get('title'),
            url=result.get('url'),
            file_path=result.get('file_path'),
            format_type=result.get('format_type') or fmt_title,
            size_bytes=result.get('file_size', 0),
            thumbnail=result.get('thumbnail')
        )

        if hasattr(self, 'notification_manager'):
            self.notification_manager.show_download_complete(
                title=result.get('title', 'Файл'),
                file_path=result.get('file_path')
            )

    def _on_download_fail(self, error_msg: str):
        if self.download_worker and getattr(self.download_worker, 'is_cancelled', False):
            return
        self.download_btn.setEnabled(True)
        self._update_download_button_text()
        if isinstance(self.download_worker, UnifiedBatchWorker):
            return
        recovery_dir = getattr(self, '_last_single_recovery_dir', None)
        self.progress_widget.set_error(error_msg, recovery_dir=recovery_dir)

    def _on_worker_cancelled(self):
        self.progress_widget.hide_progress()
        self.download_btn.setEnabled(True)
        self._update_download_button_text()

    def _cancel_download(self):
        if self._queue_busy and self.download_worker:
            self.download_worker.cancel()
            self.progress_widget.status_label.setText("ОСТАНОВКА ОЧЕРЕДИ...")
            self.progress_widget.cancel_btn.setEnabled(False)
        else:
            self.progress_widget.hide_progress()

    def _open_batch_dialog(self):
        dialog = BatchDialog(self)
        if dialog.exec():
            options = {**self._read_current_options(), **dialog.options}
            self._import_sources(dialog.sources, options)

    def _open_history_modal(self):
        modal = HistoryModal(self)
        modal.exec()

    def _open_settings(self):
        dialog = SettingsModal(self)
        dialog.opacity_changed.connect(lambda: self._apply_theme())
        if dialog.exec():
            self.dest_lbl.setText(f"DIR: {settings.get('download_dir')}")
            self._apply_theme()

    def _open_dest_dir(self):
        folder = settings.get("download_dir")
        if os.path.exists(folder):
            os.startfile(folder)
