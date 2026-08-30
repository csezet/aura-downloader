import os
import subprocess
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QComboBox, QFrame, QApplication, QGraphicsDropShadowEffect,
    QSizePolicy
)
from PySide6.QtCore import Qt, QSize, QEvent
from PySide6.QtGui import QColor

from core.settings import settings
from core.history import history
from core.downloader import MetadataWorker, DownloadWorker
from core.clipboard import ClipboardWatcher
from assets.styles import get_stylesheet
from assets.icons import get_svg_icon
from ui.window_effects import apply_acrylic_effect
from ui.title_bar import CustomTitleBar
from ui.preview_card import PreviewCard
from ui.progress_widget import ProgressWidget
from ui.history_view import HistoryModal
from ui.trim_widget import TrimWidget
from ui.crop_widget import CropWidget
from ui.batch_dialog import BatchDialog
from ui.settings_modal import SettingsModal

class HoverIconFilter(QWidget):
    def __init__(self, button: QPushButton, icon_name: str, size: int = 16):
        super().__init__(button)
        self.button = button
        self.icon_name = icon_name
        self.size = size
        self.button.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj == self.button:
            if event.type() == QEvent.Enter:
                self.button.setIcon(get_svg_icon(self.icon_name, color="#000000", size=self.size))
            elif event.type() == QEvent.Leave:
                self.button.setIcon(get_svg_icon(self.icon_name, color="#EDEDED", size=self.size))
        return super().eventFilter(obj, event)


class MainWindow(QMainWindow):
    def __init__(self, icon_path=None):
        super().__init__()
        self.icon_path = icon_path
        self.setWindowTitle("Aura Downloader")
        
        # Generous, well-spaced window dimensions to prevent any clipping/overlap
        self.resize(760, 610)
        self.setMinimumSize(660, 520)

        # Frameless and translucent window flags
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.current_mode = "best"
        self.metadata_worker = None
        self.download_worker = None
        self.current_video_info = None

        self._init_ui()
        self._apply_theme()
        self._setup_clipboard()

    def showEvent(self, event):
        super().showEvent(event)
        hwnd = int(self.winId())
        apply_acrylic_effect(hwnd)

    def _apply_theme(self):
        opacity = settings.get("glass_opacity", 0.45)
        self.setStyleSheet(get_stylesheet(opacity))

    def _init_ui(self):
        self.central_container = QFrame(self)
        self.central_container.setObjectName("CentralWidget")
        self.setCentralWidget(self.central_container)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 6)
        self.central_container.setGraphicsEffect(shadow)

        main_layout = QVBoxLayout(self.central_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Custom Title Bar (Clean, NO //)
        self.title_bar = CustomTitleBar(self, title="A U R A   D O W N L O A D E R", icon_path=self.icon_path)
        main_layout.addWidget(self.title_bar)

        # Content Area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(18, 14, 18, 16)
        content_layout.setSpacing(10)

        # 2. Upper Input Bar
        input_bar = QHBoxLayout()
        input_bar.setSpacing(8)

        self.url_input = QLineEdit()
        self.url_input.setObjectName("UrlInput")
        self.url_input.setPlaceholderText("https://... [ YouTube, TikTok, Instagram, VK, Twitter, Twitch ]")
        self.url_input.textChanged.connect(self._on_url_text_changed)
        self.url_input.returnPressed.connect(self._fetch_metadata)
        input_bar.addWidget(self.url_input, stretch=1)

        self.paste_btn = QPushButton(" ВСТАВИТЬ")
        self.paste_btn.setIcon(get_svg_icon("paste", color="#EDEDED", size=15))
        self.paste_btn.setIconSize(QSize(15, 15))
        self.paste_btn.setProperty("class", "GlassButton")
        self.paste_btn.clicked.connect(self._paste_and_fetch)
        self._h_paste = HoverIconFilter(self.paste_btn, "paste", 15)
        input_bar.addWidget(self.paste_btn)

        self.batch_btn = QPushButton(" ПАКЕТ")
        self.batch_btn.setIcon(get_svg_icon("batch", color="#EDEDED", size=15))
        self.batch_btn.setIconSize(QSize(15, 15))
        self.batch_btn.setProperty("class", "GlassButton")
        self.batch_btn.setToolTip("Пакетная загрузка списка ссылок")
        self.batch_btn.clicked.connect(self._open_batch_dialog)
        self._h_batch = HoverIconFilter(self.batch_btn, "batch", 15)
        input_bar.addWidget(self.batch_btn)

        self.history_btn = QPushButton(" ИСТОРИЯ")
        self.history_btn.setIcon(get_svg_icon("history", color="#EDEDED", size=15))
        self.history_btn.setIconSize(QSize(15, 15))
        self.history_btn.setProperty("class", "GlassButton")
        self.history_btn.setToolTip("Открыть историю загрузок")
        self.history_btn.clicked.connect(self._open_history_modal)
        self._h_history = HoverIconFilter(self.history_btn, "history", 15)
        input_bar.addWidget(self.history_btn)

        self.settings_btn = QPushButton()
        self.settings_btn.setIcon(get_svg_icon("settings", color="#EDEDED", size=17))
        self.settings_btn.setIconSize(QSize(17, 17))
        self.settings_btn.setProperty("class", "GlassButton")
        self.settings_btn.setFixedSize(34, 34)
        self.settings_btn.setToolTip("Настройки")
        self.settings_btn.clicked.connect(self._open_settings)
        self._h_settings = HoverIconFilter(self.settings_btn, "settings", 17)
        input_bar.addWidget(self.settings_btn)

        content_layout.addLayout(input_bar)

        # 3. Mode Selection Bar
        modes_card = QFrame()
        modes_card.setProperty("class", "GlassCard")
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

        # 4. Trimmer & Crop Widgets
        tools_layout = QVBoxLayout()
        tools_layout.setSpacing(6)

        self.trim_widget = TrimWidget()
        tools_layout.addWidget(self.trim_widget)

        self.crop_widget = CropWidget()
        tools_layout.addWidget(self.crop_widget)

        content_layout.addLayout(tools_layout)

        # 5. Preview Card (shows on metadata loaded)
        self.preview_card = PreviewCard()
        self.preview_card.image_ready.connect(self._on_preview_image_ready)
        content_layout.addWidget(self.preview_card)

        # 6. Progress Widget (shows on download)
        self.progress_widget = ProgressWidget()
        self.progress_widget.cancelled.connect(self._cancel_download)
        content_layout.addWidget(self.progress_widget)

        # Elastic Stretch pushes Download Button & Footer to the bottom by default!
        content_layout.addStretch(1)

        # 7. Main Action Button (Anchored at the bottom!)
        self.download_btn = QPushButton("  СКАЧАТЬ В ЛУЧШЕМ КАЧЕСТВЕ (MP4)")
        self.download_btn.setIcon(get_svg_icon("download", color="#000000", size=18))
        self.download_btn.setIconSize(QSize(18, 18))
        self.download_btn.setObjectName("PrimaryButton")
        self.download_btn.setMinimumHeight(44)
        self.download_btn.setCursor(Qt.PointingHandCursor)
        self.download_btn.clicked.connect(self._start_download)
        content_layout.addWidget(self.download_btn)

        # 8. Footer (Anchored at the very bottom!)
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(2, 0, 2, 0)

        self.dest_lbl = QLabel(f"DIR: {settings.get('download_dir')}")
        self.dest_lbl.setStyleSheet("font-size: 10px; color: #71717A; font-family: 'Consolas', monospace;")
        footer_layout.addWidget(self.dest_lbl, stretch=1)

        open_folder_btn = QPushButton(" ОТКРЫТЬ ПАПКУ")
        open_folder_btn.setIcon(get_svg_icon("folder", color="#EDEDED", size=12))
        open_folder_btn.setIconSize(QSize(12, 12))
        open_folder_btn.setProperty("class", "GlassButton")
        open_folder_btn.setStyleSheet("font-size: 10px; padding: 3px 8px; font-weight: 700;")
        open_folder_btn.clicked.connect(self._open_dest_dir)
        self._h_folder = HoverIconFilter(open_folder_btn, "folder", 12)
        footer_layout.addWidget(open_folder_btn)

        content_layout.addLayout(footer_layout)
        main_layout.addWidget(content_widget)

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

    def _on_url_text_changed(self, text: str):
        if not text.strip():
            self.preview_card.clear()
            self.current_video_info = None

    def _on_preview_image_ready(self, pixmap):
        sw = 1920
        sh = 1080
        if self.current_video_info:
            formats = self.current_video_info.get("available_res", [])
            if formats and "4K" in formats[0]:
                sw, sh = 3840, 2160
            elif formats and "2K" in formats[0]:
                sw, sh = 2560, 1440
            elif formats and "720p" in formats[0] and len(formats) == 1:
                sw, sh = 1280, 720
        self.crop_widget.set_source_info(pixmap, width=sw, height=sh)

    def _fetch_metadata(self):
        url = self.url_input.text().strip()
        if not url:
            return

        if self.metadata_worker and self.metadata_worker.isRunning():
            self.metadata_worker.terminate()

        self.download_btn.setEnabled(False)
        self.download_btn.setText("  ПОЛУЧЕНИЕ ИНФОРМАЦИИ...")

        self.metadata_worker = MetadataWorker(url)
        self.metadata_worker.info_ready.connect(self._on_metadata_ready)
        self.metadata_worker.info_error.connect(self._on_metadata_error)
        self.metadata_worker.start()

    def _on_metadata_ready(self, info: dict):
        self.current_video_info = info
        self.preview_card.set_data(info)
        
        if info.get("duration"):
            self.trim_widget.set_duration_hint(info["duration"])

        if info.get("available_res"):
            self.res_combo.clear()
            self.res_combo.addItems(info["available_res"])

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

        # Disable crop for audio_only
        self.crop_widget.setVisible(mode != "audio_only")

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

    def _update_download_button_text(self):
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
        url = self.url_input.text().strip()
        if not url:
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
            'crop_params': self.crop_widget.get_crop_params()
        }

        save_dir = settings.get("download_dir")
        self.progress_widget.start_progress()
        self.download_btn.setEnabled(False)

        self.download_worker = DownloadWorker(url, options, save_dir)
        self.download_worker.progress_updated.connect(self.progress_widget.update_progress)
        self.download_worker.download_completed.connect(self._on_download_success)
        self.download_worker.download_error.connect(self._on_download_fail)
        self.download_worker.status_message.connect(lambda msg: self.progress_widget.status_label.setText(msg.upper()))
        self.download_worker.start()

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
