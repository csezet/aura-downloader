import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QSlider, QComboBox, QFrame, QWidget
)
from PySide6.QtCore import Qt, Signal, QThread
from core.settings import settings
from core.cookies_helper import SUPPORTED_BROWSERS
from core.media_converter import cleanup_aura_temp_files
from ui.toggle_switch import ToggleSwitch

class SettingsModal(QDialog):
    opacity_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки Aura")
        self.setFixedWidth(500)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Solid dark frosted container (NO double-exposure with main window)
        container = QFrame()
        container.setStyleSheet("""
            QFrame#SettingsContainer {
                background-color: #11141A;
                border-radius: 14px;
                border: 1px solid rgba(255, 255, 255, 0.22);
            }
        """)
        container.setObjectName("SettingsContainer")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(24, 20, 24, 22)
        container_layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title = QLabel("⚙️  НАСТРОЙКИ AURA")
        title.setStyleSheet("font-size: 14px; font-weight: 800; color: #FFFFFF; letter-spacing: 0.8px;")
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setObjectName("TitleButton")
        close_btn.clicked.connect(self.accept)
        header.addWidget(close_btn)
        container_layout.addLayout(header)

        # 1. Download Folder
        folder_group = QVBoxLayout()
        folder_group.setSpacing(5)
        lbl_dir = QLabel("Папка для сохранения:")
        lbl_dir.setStyleSheet("font-size: 11px; font-weight: 700; color: #A1A1AA; text-transform: uppercase;")
        folder_group.addWidget(lbl_dir)

        folder_row = QHBoxLayout()
        self.path_lbl = QLabel(settings.get("download_dir"))
        self.path_lbl.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.75);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 6px;
            padding: 6px 10px;
            color: #EDEDED;
            font-size: 11px;
            font-family: 'Consolas', monospace;
        """)
        folder_row.addWidget(self.path_lbl, stretch=1)

        browse_btn = QPushButton("Обзор...")
        browse_btn.setProperty("class", "GlassButton")
        browse_btn.clicked.connect(self._browse_dir)
        folder_row.addWidget(browse_btn)

        folder_group.addLayout(folder_row)
        container_layout.addLayout(folder_group)

        # 2. Glass Opacity Slider (30% to 90%)
        opacity_group = QVBoxLayout()
        opacity_group.setSpacing(4)
        
        opacity_header = QHBoxLayout()
        lbl_opacity = QLabel("Прозрачность главного окна (видимость рабочего стола):")
        lbl_opacity.setStyleSheet("font-size: 11px; font-weight: 700; color: #A1A1AA; text-transform: uppercase;")
        opacity_header.addWidget(lbl_opacity)

        self.opacity_val_lbl = QLabel(f"{int(settings.get('glass_opacity', 0.50) * 100)}%")
        self.opacity_val_lbl.setStyleSheet("font-size: 12px; color: #FFFFFF; font-weight: 800; font-family: 'Consolas', monospace;")
        opacity_header.addWidget(self.opacity_val_lbl)
        opacity_group.addLayout(opacity_header)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(20, 90)
        self.slider.setValue(int(settings.get("glass_opacity", 0.50) * 100))
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid rgba(255, 255, 255, 0.15);
                height: 4px;
                background: rgba(0, 0, 0, 0.8);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #FFFFFF;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: 1px solid #000000;
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }
        """)
        self.slider.valueChanged.connect(self._on_opacity_slider_changed)
        opacity_group.addWidget(self.slider)
        container_layout.addLayout(opacity_group)

        # 3. Browser Cookies Integration
        cookies_group = QVBoxLayout()
        cookies_group.setSpacing(4)
        lbl_cookies = QLabel("Импорт Cookies из браузера (для приватных / 18+ видео):")
        lbl_cookies.setStyleSheet("font-size: 11px; font-weight: 700; color: #A1A1AA; text-transform: uppercase;")
        cookies_group.addWidget(lbl_cookies)

        self.cookies_combo = QComboBox()
        current_browser = settings.get("browser_cookies", "none")
        selected_idx = 0
        for i, (b_id, b_name) in enumerate(SUPPORTED_BROWSERS):
            self.cookies_combo.addItem(b_name, b_id)
            if b_id == current_browser:
                selected_idx = i
        self.cookies_combo.setCurrentIndex(selected_idx)
        self.cookies_combo.currentIndexChanged.connect(self._on_cookies_changed)
        cookies_group.addWidget(self.cookies_combo)
        container_layout.addLayout(cookies_group)

        # 4. Audio format preset
        audio_row = QHBoxLayout()
        lbl_audio = QLabel("Формат аудио по умолчанию:")
        lbl_audio.setStyleSheet("font-size: 11px; font-weight: 700; color: #A1A1AA; text-transform: uppercase;")
        audio_row.addWidget(lbl_audio)

        self.audio_combo = QComboBox()
        self.audio_combo.addItems(["MP3 (320 kbps)", "FLAC (Lossless)", "M4A (AAC)", "OPUS", "WAV"])
        fmt_map = {"mp3": 0, "flac": 1, "m4a": 2, "opus": 3, "wav": 4}
        self.audio_combo.setCurrentIndex(fmt_map.get(settings.get("audio_format", "mp3"), 0))
        self.audio_combo.currentIndexChanged.connect(self._on_audio_format_changed)
        audio_row.addWidget(self.audio_combo)
        container_layout.addLayout(audio_row)

        # 5. Clipboard Toggle
        clip_row = QHBoxLayout()
        self.clip_toggle = ToggleSwitch(checked=settings.get("auto_paste", True))
        self.clip_toggle.toggled.connect(lambda v: settings.set("auto_paste", v))
        clip_row.addWidget(self.clip_toggle)

        lbl_clip = QLabel("Автоматически подхватывать скопированные ссылки")
        lbl_clip.setStyleSheet("color: #EDEDED; font-size: 12px; font-weight: 600;")
        clip_row.addWidget(lbl_clip, stretch=1)
        container_layout.addLayout(clip_row)

        # 6. Maintenance & Utilities (Cache & yt-dlp updates)
        util_group = QVBoxLayout()
        util_group.setSpacing(6)

        lbl_util = QLabel("Служебные утилиты:")
        lbl_util.setStyleSheet("font-size: 11px; font-weight: 700; color: #A1A1AA; text-transform: uppercase;")
        util_group.addWidget(lbl_util)

        util_row = QHBoxLayout()
        util_row.setSpacing(8)

        self.btn_clear_cache = QPushButton("🧹 Очистить кэш (%TEMP%)")
        self.btn_clear_cache.setProperty("class", "GlassButton")
        self.btn_clear_cache.setCursor(Qt.PointingHandCursor)
        self.btn_clear_cache.setToolTip("Удалить временные прокси-файлы и эскизы из системной папки")
        self.btn_clear_cache.clicked.connect(self._clear_cache)
        util_row.addWidget(self.btn_clear_cache)

        self.btn_update_ytdlp = QPushButton("⚡ Обновить yt-dlp")
        self.btn_update_ytdlp.setProperty("class", "GlassButton")
        self.btn_update_ytdlp.setCursor(Qt.PointingHandCursor)
        self.btn_update_ytdlp.setToolTip("Проверить и обновить загрузчик yt-dlp до последней версии")
        self.btn_update_ytdlp.clicked.connect(self._update_ytdlp)
        util_row.addWidget(self.btn_update_ytdlp)

        util_group.addLayout(util_row)

        self.util_status_lbl = QLabel("")
        self.util_status_lbl.setStyleSheet("font-size: 11px; color: #4ADE80; font-weight: 600;")
        self.util_status_lbl.setVisible(False)
        util_group.addWidget(self.util_status_lbl)

        container_layout.addLayout(util_group)

        layout.addWidget(container)

    def _browse_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для сохранения", settings.get("download_dir"))
        if folder:
            settings.set("download_dir", folder)
            self.path_lbl.setText(folder)

    def _on_opacity_slider_changed(self, val):
        opacity = val / 100.0
        self.opacity_val_lbl.setText(f"{val}%")
        settings.set("glass_opacity", opacity)
        self.opacity_changed.emit(opacity)

    def _on_cookies_changed(self, idx):
        browser_id = self.cookies_combo.itemData(idx)
        settings.set("browser_cookies", browser_id)

    def _on_audio_format_changed(self, idx):
        formats = ["mp3", "flac", "m4a", "opus", "wav"]
        if idx < len(formats):
            settings.set("audio_format", formats[idx])

    def _clear_cache(self):
        count = cleanup_aura_temp_files(max_age_hours=0)
        self.util_status_lbl.setText(f"✓ Временные файлы очищены ({count} шт.)")
        self.util_status_lbl.setStyleSheet("font-size: 11px; color: #4ADE80; font-weight: 600;")
        self.util_status_lbl.setVisible(True)

    def _update_ytdlp(self):
        self.btn_update_ytdlp.setEnabled(False)
        self.util_status_lbl.setText("Проверка и обновление yt-dlp...")
        self.util_status_lbl.setStyleSheet("font-size: 11px; color: #60A5FA; font-weight: 600;")
        self.util_status_lbl.setVisible(True)

        self.update_worker = UpdateYtdlpWorker()
        self.update_worker.finished_signal.connect(self._on_ytdlp_update_finished)
        self.update_worker.start()

    def _on_ytdlp_update_finished(self, msg: str, success: bool):
        self.btn_update_ytdlp.setEnabled(True)
        color = "#4ADE80" if success else "#EF4444"
        self.util_status_lbl.setText(msg)
        self.util_status_lbl.setStyleSheet(f"font-size: 11px; color: {color}; font-weight: 600;")
        self.util_status_lbl.setVisible(True)


class UpdateYtdlpWorker(QThread):
    finished_signal = Signal(str, bool)

    def run(self):
        try:
            import subprocess, sys
            cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=0x08000000
            )
            if res.returncode == 0:
                if "Requirement already satisfied" in res.stdout:
                    self.finished_signal.emit("Установлена самая актуальная версия yt-dlp.", True)
                else:
                    self.finished_signal.emit("Движок yt-dlp успешно обновлен!", True)
            else:
                self.finished_signal.emit(f"Ошибка обновления: {res.stderr[:60]}", False)
        except Exception as e:
            self.finished_signal.emit(f"Ошибка: {str(e)[:60]}", False)
