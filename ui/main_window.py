import os
import subprocess
import ctypes
from ctypes import wintypes
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QComboBox, QFrame, QApplication,
    QSizePolicy, QFileDialog
)
from PySide6.QtCore import Qt, QSize, QEvent
from PySide6.QtGui import QColor, QPixmap

from core.settings import settings
from core.history import history
from core.downloader import MetadataWorker, DownloadWorker
from core.local_processor import get_local_media_info, is_video_file, LocalProcessWorker, LocalBatchProcessWorker
from core.clipboard import ClipboardWatcher
from assets.styles import get_stylesheet
from assets.icons import get_svg_icon
from ui.window_effects import apply_acrylic_effect
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
from core.notifications import NotificationManager

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
        self.setWindowTitle("Aura Downloader")
        
        self.resize(760, 650)
        self.setMinimumSize(660, 540)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)

        self.current_mode = "best"
        self.metadata_worker = None
        self.download_worker = None
        self.current_video_info = None
        self.notification_manager = NotificationManager(parent=self, icon_path=self.icon_path)

        self._init_ui()
        self._apply_theme()
        self._setup_clipboard()

    def showEvent(self, event):
        super().showEvent(event)
        hwnd = int(self.winId())
        apply_acrylic_effect(hwnd)

    def nativeEvent(self, eventType, message):
        if eventType in (b"windows_generic_MSG", "windows_generic_MSG"):
            try:
                msg = wintypes.MSG.from_address(int(message))
                # WM_NCCALCSIZE = 0x0083
                if msg.message == 0x0083 and msg.wParam == 1:
                    return True, 0
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
        files = []
        if event.mimeData().hasUrls():
            for u in event.mimeData().urls():
                p = u.toLocalFile()
                if not p and u.toString().startswith("file:///"):
                    p = u.toString()[8:]
                if p:
                    files.append(p)
        elif event.mimeData().hasText():
            for line in event.mimeData().text().splitlines():
                line = line.strip().strip('"').strip("'")
                if os.path.exists(line):
                    files.append(line)

        valid_videos = []
        for f in files:
            if os.path.isdir(f):
                for root, _, dir_files in os.walk(f):
                    for df in dir_files:
                        full_p = os.path.join(root, df)
                        if is_video_file(full_p):
                            valid_videos.append(full_p)
            elif is_video_file(f):
                valid_videos.append(f)

        if valid_videos:
            event.acceptProposedAction()
            self._load_local_files(valid_videos)
        elif files:
            first = files[0]
            if first.startswith("http"):
                self.url_input.setText(first)
                self._fetch_metadata()

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
        self.url_input.textChanged.connect(self._on_url_text_changed)
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

        # 3. Mode Selection Bar
        modes_card = QFrame()
        modes_card.setProperty("class", "GlassCard")
        modes_card.setFixedHeight(42)
        modes_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        modes_layout = QHBoxLayout(modes_card)
        modes_layout.setContentsMargins(6, 5, 6, 5)
        modes_layout.setSpacing(6)

        self.pill_best = QPushButton(" ЛУЧШЕЕ")
        self.pill_best.setIcon(get_svg_icon("sparkles", color="#000000", size=13))
        self.pill_best.setIconSize(QSize(13, 13))
        self.pill_best.setProperty("class", "ModePill")
        self.pill_best.setProperty("active", "true")
        self.pill_best.clicked.connect(lambda: self._set_mode("best"))
        modes_layout.addWidget(self.pill_best)

        self.pill_custom = QPushButton(" ВИДЕО")
        self.pill_custom.setIcon(get_svg_icon("video", color="#EDEDED", size=13))
        self.pill_custom.setIconSize(QSize(13, 13))
        self.pill_custom.setProperty("class", "ModePill")
        self.pill_custom.clicked.connect(lambda: self._set_mode("custom"))
        modes_layout.addWidget(self.pill_custom)

        self.res_combo = QComboBox()
        self.res_combo.addItems(["4K (2160p)", "2K (1440p)", "1080p Full HD", "720p HD", "480p", "360p"])
        self.res_combo.setCurrentText("1080p Full HD")
        self.res_combo.setVisible(False)
        self.res_combo.currentTextChanged.connect(self._update_download_button_text)
        modes_layout.addWidget(self.res_combo)

        self.pill_audio = QPushButton(" АУДИО")
        self.pill_audio.setIcon(get_svg_icon("music", color="#EDEDED", size=13))
        self.pill_audio.setIconSize(QSize(13, 13))
        self.pill_audio.setProperty("class", "ModePill")
        self.pill_audio.clicked.connect(lambda: self._set_mode("audio_only"))
        modes_layout.addWidget(self.pill_audio)

        self.audio_fmt_combo = QComboBox()
        self.audio_fmt_combo.addItems(["MP3 (320k)", "FLAC (Lossless)", "M4A (AAC)", "OPUS", "WAV"])
        self.audio_fmt_combo.setVisible(False)
        self.audio_fmt_combo.currentTextChanged.connect(self._update_download_button_text)
        modes_layout.addWidget(self.audio_fmt_combo)

        self.pill_gif = QPushButton(" GIF")
        self.pill_gif.setIcon(get_svg_icon("gif", color="#EDEDED", size=13))
        self.pill_gif.setIconSize(QSize(13, 13))
        self.pill_gif.setProperty("class", "ModePill")
        self.pill_gif.setToolTip("Конвертировать в анимированный GIF")
        self.pill_gif.clicked.connect(lambda: self._set_mode("gif"))
        modes_layout.addWidget(self.pill_gif)

        self.pill_discord = QPushButton(" DISCORD")
        self.pill_discord.setIcon(get_svg_icon("discord", color="#EDEDED", size=13))
        self.pill_discord.setIconSize(QSize(13, 13))
        self.pill_discord.setProperty("class", "ModePill")
        self.pill_discord.setToolTip("Сжать видео для отправки в Discord (< 8 МБ)")
        self.pill_discord.clicked.connect(lambda: self._set_mode("discord_8mb"))
        modes_layout.addWidget(self.pill_discord)

        self.pill_video_only = QPushButton(" БЕЗ ЗВУКА")
        self.pill_video_only.setIcon(get_svg_icon("mute", color="#EDEDED", size=13))
        self.pill_video_only.setIconSize(QSize(13, 13))
        self.pill_video_only.setProperty("class", "ModePill")
        self.pill_video_only.setToolTip("Только видеоряд без аудио")
        self.pill_video_only.clicked.connect(lambda: self._set_mode("video_only"))
        modes_layout.addWidget(self.pill_video_only)

        modes_layout.addStretch()
        content_layout.addWidget(modes_card)

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

    def _setup_clipboard(self):
        self.clipboard_watcher = ClipboardWatcher(self)
        self.clipboard_watcher.url_detected.connect(self._on_clipboard_url)

    def _on_clipboard_url(self, url: str):
        if settings.get("auto_paste", False) and not self.download_worker:
            self.url_input.setText(url)
            self._fetch_metadata()

    def _paste_and_fetch(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
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

    def _load_local_files(self, file_paths: list[str]):
        if not file_paths:
            return

        clean_paths = []
        for p in file_paths:
            if isinstance(p, str):
                c = p.strip().strip('"').strip("'")
                if os.path.isdir(c):
                    for root, _, files in os.walk(c):
                        for f in files:
                            full_p = os.path.join(root, f)
                            if is_video_file(full_p):
                                clean_paths.append(full_p)
                elif is_video_file(c):
                    clean_paths.append(c)

        if not clean_paths:
            return

        for path in clean_paths:
            info = get_local_media_info(path)
            if info:
                self.cards_list.add_video(info)

    def _save_current_ui_to_video_info(self):
        if not self.current_video_info:
            return
        item_id = self.current_video_info.get('item_id')
        trim_start, trim_end = self.trim_widget.get_trim_range()
        opts = {
            'mode': self.current_mode,
            'res': self.res_combo.currentText() if self.current_mode in ['custom', 'video_only'] else None,
            'audio_fmt': self.audio_fmt_combo.currentText().split()[0].lower() if self.current_mode == 'audio_only' else 'mp3',
            'audio_q': '320',
            'trim_enabled': self.trim_widget.is_trim_enabled(),
            'trim_start': trim_start,
            'trim_end': trim_end,
            'crop_enabled': self.crop_widget.is_crop_enabled(),
            'crop_params': self.crop_widget.get_crop_params(),
            'smooth_enabled': self.smooth_widget.is_smooth_enabled(),
            'smooth_fps': self.smooth_widget.get_target_fps(),
            'smooth_model': self.smooth_widget.get_model()
        }
        self.current_video_info['options'] = opts
        if item_id:
            self.cards_list.save_card_options(item_id, opts)
        else:
            self.cards_list.save_active_options(opts)

    def _auto_save_active_options(self):
        if getattr(self, '_is_restoring_ui', False):
            return
        self._save_current_ui_to_video_info()

    def _restore_ui_from_video_info(self, info: dict):
        opts = info.get('options')
        if not opts:
            self._set_mode("best")
            self.crop_widget.toggle.setChecked(False)
            self.trim_widget.toggle.setChecked(False)
            self.smooth_widget.toggle.setChecked(False)
            return

        self._set_mode(opts.get('mode', 'best'))
        if opts.get('res'):
            self.res_combo.setCurrentText(opts.get('res'))
        if opts.get('audio_fmt'):
            for i in range(self.audio_fmt_combo.count()):
                if opts['audio_fmt'].lower() in self.audio_fmt_combo.itemText(i).lower():
                    self.audio_fmt_combo.setCurrentIndex(i)
                    break

        # Trim
        self.trim_widget.toggle.setChecked(opts.get('trim_enabled', False))
        if opts.get('trim_start'):
            self.trim_widget.start_input.setText(opts.get('trim_start'))
        if opts.get('trim_end'):
            self.trim_widget.end_input.setText(opts.get('trim_end'))

        # Crop
        self.crop_widget.toggle.setChecked(opts.get('crop_enabled', False))
        self.crop_widget._crop_params = opts.get('crop_params')
        if opts.get('crop_params'):
            w = opts['crop_params'].get('w', 1920)
            h = opts['crop_params'].get('h', 1080)
            self.crop_widget.status_tag.setText(f"{w}×{h}")
            self.crop_widget.status_tag.setVisible(opts.get('crop_enabled', False))
        else:
            self.crop_widget.status_tag.setVisible(False)

        # Smooth
        self.smooth_widget.toggle.setChecked(opts.get('smooth_enabled', False))
        fps = opts.get('smooth_fps', 60)
        if fps == 60:
            self.smooth_widget.fps_combo.setCurrentIndex(0)
        elif fps == 120:
            self.smooth_widget.fps_combo.setCurrentIndex(1)
        else:
            self.smooth_widget.fps_combo.setCurrentIndex(2)

    def _on_active_thumbnail_updated(self, pixmap: QPixmap):
        if self.current_video_info and pixmap and not pixmap.isNull():
            w = self.current_video_info.get("width", 1920)
            h = self.current_video_info.get("height", 1080)
            self.crop_widget.set_source_info(pixmap, width=w, height=h)

    def _on_active_video_changed(self, info: dict, pixmap: QPixmap):
        self._is_restoring_ui = True
        try:
            self.current_video_info = info
            w = info.get("width", 1920)
            h = info.get("height", 1080)
            self.crop_widget.set_source_info(pixmap, width=w, height=h)
            playable = info.get('playable_url') or info.get('direct_url') or info.get('url')
            self.trim_widget.set_source_video(playable, info.get('duration', 60))
            if info.get("available_res"):
                self.res_combo.clear()
                self.res_combo.addItems(info["available_res"])
            self._restore_ui_from_video_info(info)
            self._update_download_button_text()
        finally:
            self._is_restoring_ui = False

    def _on_cards_list_changed(self, count: int):
        if hasattr(self, 'empty_placeholder'):
            self.empty_placeholder.setVisible(count == 0)
        if count == 0:
            self.current_video_info = None
            self.crop_widget.toggle.setChecked(False)
            self.trim_widget.toggle.setChecked(False)
            self.smooth_widget.toggle.setChecked(False)
        self._update_download_button_text()

    def _reset_all_state(self):
        self.current_video_info = None
        self.url_input.blockSignals(True)
        self.url_input.clear()
        self.url_input.blockSignals(False)
        self.cards_list.clear_all()
        if hasattr(self, 'empty_placeholder'):
            self.empty_placeholder.setVisible(True)
        self.crop_widget.toggle.setChecked(False)
        self.trim_widget.toggle.setChecked(False)
        self.smooth_widget.toggle.setChecked(False)
        self._update_download_button_text()

    def _on_url_text_changed(self, text: str):
        if is_video_file(text):
            self.url_input.clear()
            self._load_local_files([text])

    def _fetch_metadata(self):
        url = self.url_input.text().strip()
        if not url:
            return

        # Clear input field immediately upon pressing Enter/Paste
        self.url_input.clear()

        if is_video_file(url):
            self._load_local_files([url])
            return

        if self.metadata_worker and self.metadata_worker.isRunning():
            self.metadata_worker.cancel()
            try:
                self.metadata_worker.info_ready.disconnect()
                self.metadata_worker.info_error.disconnect()
            except Exception:
                pass

        self.download_btn.setEnabled(False)
        self.download_btn.setText("  ПОЛУЧЕНИЕ ИНФОРМАЦИИ...")

        self.metadata_worker = MetadataWorker(url)
        self.metadata_worker.info_ready.connect(self._on_metadata_ready)
        self.metadata_worker.playlist_ready.connect(self._on_playlist_ready)
        self.metadata_worker.info_error.connect(self._on_metadata_error)
        self.metadata_worker.start()

    def _on_playlist_ready(self, playlist_data: dict):
        self.download_btn.setEnabled(True)
        self._update_download_button_text()

        dialog = PlaylistDialog(playlist_data, self)
        if dialog.exec():
            selected = dialog.get_selected_entries()
            for item in selected:
                info = {
                    'url': item.get('url'),
                    'direct_url': None,
                    'playable_url': item.get('url'),
                    'title': item.get('title', 'Без названия'),
                    'uploader': item.get('uploader', 'Автор'),
                    'duration': item.get('duration', 0),
                    'duration_str': item.get('duration_str', '--:--'),
                    'thumbnail': item.get('thumbnail'),
                    'platform': 'youtube',
                    'available_res': ['1080p Full HD', '720p HD', '480p'],
                    'has_video': True,
                    'width': 1920,
                    'height': 1080
                }
                self.cards_list.add_video(info)

    def _on_metadata_ready(self, info: dict):
        self.cards_list.add_video(info)
        self.download_btn.setEnabled(True)
        self._update_download_button_text()

    def _on_metadata_error(self, err_msg: str):
        self.download_btn.setEnabled(True)
        self._update_download_button_text()
        self.progress_widget.set_error(err_msg)

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

        self.crop_widget.setVisible(mode != "audio_only")
        self.smooth_widget.setVisible(mode not in ["audio_only", "gif"])

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
        selected_vids = self.cards_list.get_selected_videos()
        q_count = len(selected_vids)
        is_local = (self.current_video_info and self.current_video_info.get('is_local')) or q_count > 0

        if not self.current_video_info and q_count == 0:
            self.download_btn.setIcon(get_svg_icon("download", color="#000000", size=18))
            self.download_btn.setText("  СКАЧАТЬ В ЛУЧШЕМ КАЧЕСТВЕ (MP4)")
            return

        if q_count > 1:
            self.download_btn.setIcon(get_svg_icon("zap", color="#000000", size=18))
            if self.current_mode in ["best", "custom"]:
                self.download_btn.setText(f"  ОБРАБОТАТЬ ВСЕ ВИДЕО ({q_count})")
            elif self.current_mode == "audio_only":
                fmt = self.audio_fmt_combo.currentText().split()[0]
                self.download_btn.setText(f"  ИЗВЛЕЧЬ АУДИО [{fmt}] ({q_count} ВИДЕО)")
            elif self.current_mode == "gif":
                self.download_btn.setText(f"  КОНВЕРТИРОВАТЬ В GIF ({q_count} ВИДЕО)")
            elif self.current_mode == "discord_8mb":
                self.download_btn.setText(f"  СЖАТЬ ДЛЯ DISCORD ({q_count} ВИДЕО)")
            elif self.current_mode == "video_only":
                self.download_btn.setText(f"  УДАЛИТЬ ЗВУК ({q_count} ВИДЕО)")
            return

        if is_local:
            self.download_btn.setIcon(get_svg_icon("zap", color="#000000", size=18))
            if self.current_mode in ["best", "custom"]:
                self.download_btn.setText("  ОБРАБОТАТЬ И СОХРАНИТЬ ВИДЕО")
            elif self.current_mode == "audio_only":
                fmt = self.audio_fmt_combo.currentText().split()[0]
                self.download_btn.setText(f"  ИЗВЛЕЧЬ АУДИО [{fmt}]")
            elif self.current_mode == "gif":
                self.download_btn.setText("  КОНВЕРТИРОВАТЬ В GIF")
            elif self.current_mode == "discord_8mb":
                self.download_btn.setText("  СЖАТЬ ДЛЯ DISCORD (< 8 МБ)")
            elif self.current_mode == "video_only":
                self.download_btn.setText("  УДАЛИТЬ ЗВУК И СОХРАНИТЬ")
        else:
            self.download_btn.setIcon(get_svg_icon("download", color="#000000", size=18))
            if self.current_mode == "best":
                self.download_btn.setText("  СКАЧАТЬ В ЛУЧШЕМ КАЧЕСТВЕ (MP4)")
            elif self.current_mode == "custom":
                res = self.res_combo.currentText()
                self.download_btn.setText(f"  СКАЧАТЬ ВИДЕО [{res}]")
            elif self.current_mode == "audio_only":
                fmt = self.audio_fmt_combo.currentText().split()[0]
                self.download_btn.setText(f"  СКАЧАТЬ АУДИО [{fmt}]")
            elif self.current_mode == "gif":
                self.download_btn.setText("  КОНВЕРТИРОВАТЬ И СКАЧАТЬ В GIF")
            elif self.current_mode == "discord_8mb":
                self.download_btn.setText("  СЖАТЬ И СКАЧАТЬ ДЛЯ DISCORD (< 8 МБ)")
            elif self.current_mode == "video_only":
                res = self.res_combo.currentText()
                self.download_btn.setText(f"  СКАЧАТЬ БЕЗ ЗВУКА [{res}]")

    def _start_download(self):
        self._save_current_ui_to_video_info()
        url = self.url_input.text().strip()
        selected_queue = self.cards_list.get_selected_videos()

        if not url and not selected_queue and not self.current_video_info:
            return

        if self.download_worker and self.download_worker.isRunning():
            return

        trim_start, trim_end = self.trim_widget.get_trim_range()

        options = {
            'mode': self.current_mode,
            'res': self.res_combo.currentText() if self.current_mode in ['custom', 'video_only'] else None,
            'audio_fmt': self.audio_fmt_combo.currentText().split()[0].lower() if self.current_mode == 'audio_only' else 'mp3',
            'audio_q': '320',
            'trim_enabled': self.trim_widget.is_trim_enabled(),
            'trim_start': trim_start,
            'trim_end': trim_end,
            'crop_enabled': self.crop_widget.is_crop_enabled(),
            'crop_params': self.crop_widget.get_crop_params(),
            'smooth_enabled': self.smooth_widget.is_smooth_enabled(),
            'smooth_fps': self.smooth_widget.get_target_fps(),
            'smooth_model': self.smooth_widget.get_model()
        }

        save_dir = settings.get("download_dir")
        self.progress_widget.start_progress()
        self.download_btn.setEnabled(False)

        if len(selected_queue) > 1:
            self.download_worker = LocalBatchProcessWorker(selected_queue, options, save_dir)
            self.download_worker.progress_updated.connect(self.progress_widget.update_progress)
            self.download_worker.item_completed.connect(self._on_queue_item_completed)
            self.download_worker.batch_completed.connect(self._on_batch_success)
            self.download_worker.download_error.connect(self._on_download_fail)
            self.download_worker.status_message.connect(lambda msg: self.progress_widget.status_label.setText(msg.upper()))
            self.download_worker.start()
            return

        active_video = selected_queue[0] if selected_queue else self.current_video_info
        target_url = (active_video.get('url') if active_video else None) or url
        is_local = (active_video and active_video.get('is_local')) or is_video_file(target_url)

        if is_local:
            self.download_worker = LocalProcessWorker(target_url, options, save_dir)
        else:
            self.download_worker = DownloadWorker(target_url, options, save_dir)

        self.download_worker.progress_updated.connect(self.progress_widget.update_progress)
        self.download_worker.download_completed.connect(self._on_download_success)
        self.download_worker.download_error.connect(self._on_download_fail)
        self.download_worker.status_message.connect(lambda msg: self.progress_widget.status_label.setText(msg.upper()))
        self.download_worker.start()

    def _on_queue_item_completed(self, result: dict):
        fmt_title = result.get('mode', 'MP4').upper()
        history.add_entry(
            title=result.get('title'),
            url=result.get('url'),
            file_path=result.get('file_path'),
            format_type=fmt_title,
            size_bytes=result.get('file_size', 0),
            thumbnail=result.get('thumbnail')
        )

    def _on_batch_success(self, results: list):
        self.download_btn.setEnabled(True)
        self._update_download_button_text()
        last_res = results[-1] if results else {'file_path': settings.get("download_dir"), 'file_size_str': f"{len(results)} файлов"}
        last_res['mode'] = f"Пакет ({len(results)} шт)"
        self.progress_widget.complete(last_res)

        if hasattr(self, 'notification_manager'):
            self.notification_manager.show_download_complete(
                title=f"Очередь завершена ({len(results)} видео)",
                file_path=last_res.get('file_path')
            )

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
            format_type=fmt_title,
            size_bytes=result.get('file_size', 0),
            thumbnail=result.get('thumbnail')
        )

        if hasattr(self, 'notification_manager'):
            self.notification_manager.show_download_complete(
                title=result.get('title', 'Видео'),
                file_path=result.get('file_path')
            )

    def _on_download_fail(self, error_msg: str):
        self.download_btn.setEnabled(True)
        self._update_download_button_text()
        self.progress_widget.set_error(error_msg)

    def _cancel_download(self):
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.cancel()
        self.progress_widget.hide_progress()
        self.download_btn.setEnabled(True)
        self._update_download_button_text()

    def _open_batch_dialog(self):
        dialog = BatchDialog(self)
        dialog.exec()

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
