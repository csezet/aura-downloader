import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QSlider, QComboBox, QFrame, QWidget
)
from PySide6.QtCore import Qt, Signal, QThread, QSize
from core.settings import settings
from core.cookies_helper import SUPPORTED_BROWSERS
from core.media_converter import cleanup_aura_temp_files
from ui.toggle_switch import ToggleSwitch
from assets.icons import get_svg_icon

class SettingsModal(QDialog):
    opacity_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки Aura")
        self.setFixedWidth(520)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Solid dark frosted container with premium borders & generous 18px radius
        container = QFrame()
        container.setObjectName("SettingsContainer")
        container.setStyleSheet("""
            QFrame#SettingsContainer {
                background-color: #0E1218;
                border-radius: 18px;
                border: 1px solid rgba(255, 255, 255, 0.16);
            }
            .SettingsCard {
                background-color: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
            .SectionHeader {
                font-size: 10px;
                font-weight: 800;
                color: #71717A;
                text-transform: uppercase;
                letter-spacing: 0.9px;
            }
            QComboBox {
                background-color: rgba(0, 0, 0, 0.55);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 6px 12px;
                color: #EDEDED;
                font-size: 12px;
                font-weight: 600;
            }
            QComboBox:hover {
                border: 1px solid rgba(255, 255, 255, 0.25);
                background-color: rgba(255, 255, 255, 0.07);
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background-color: #161A22;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 8px;
                selection-background-color: rgba(255, 255, 255, 0.14);
                selection-color: #FFFFFF;
                color: #EDEDED;
                padding: 4px;
                outline: none;
            }
        """)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(22, 18, 22, 20)
        container_layout.setSpacing(12)

        # --- 1. Header ---
        header = QHBoxLayout()
        header.setSpacing(10)

        header_icon = QLabel()
        header_icon.setPixmap(get_svg_icon("settings", color="#FFFFFF", size=18).pixmap(18, 18))
        header.addWidget(header_icon)

        title = QLabel("НАСТРОЙКИ AURA")
        title.setStyleSheet("font-size: 14px; font-weight: 800; color: #FFFFFF; letter-spacing: 1px;")
        header.addWidget(title)

        header.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                color: #A1A1AA;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.16);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.20);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.24);
            }
        """)
        close_btn.clicked.connect(self.accept)
        header.addWidget(close_btn)
        container_layout.addLayout(header)

        # --- Card 1: Сохранение и буфер обмена ---
        card1 = QFrame()
        card1.setProperty("class", "SettingsCard")
        c1_layout = QVBoxLayout(card1)
        c1_layout.setContentsMargins(14, 12, 14, 12)
        c1_layout.setSpacing(10)

        lbl_dir_header = QLabel("Папка для сохранения:")
        lbl_dir_header.setProperty("class", "SectionHeader")
        c1_layout.addWidget(lbl_dir_header)

        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)

        self.path_lbl = QLabel(settings.get("download_dir"))
        self.path_lbl.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.55);
            border: 1px solid rgba(255, 255, 255, 0.10);
            border-radius: 8px;
            padding: 7px 10px;
            color: #E4E4E7;
            font-size: 11px;
            font-family: 'Consolas', monospace;
        """)
        folder_row.addWidget(self.path_lbl, stretch=1)

        browse_btn = QPushButton(" Обзор...")
        browse_btn.setIcon(get_svg_icon("folder", color="#FFFFFF", size=14))
        browse_btn.setIconSize(QSize(14, 14))
        browse_btn.setProperty("class", "GlassButton")
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setStyleSheet("padding: 7px 14px; font-weight: 700;")
        browse_btn.clicked.connect(self._browse_dir)
        folder_row.addWidget(browse_btn)
        c1_layout.addLayout(folder_row)

        # Divider
        div1 = QFrame()
        div1.setFixedHeight(1)
        div1.setStyleSheet("background-color: rgba(255, 255, 255, 0.06);")
        c1_layout.addWidget(div1)

        # Clipboard auto-paste row
        clip_row = QHBoxLayout()
        clip_row.setContentsMargins(0, 2, 0, 0)
        lbl_clip = QLabel("Автоматически подхватывать скопированные ссылки")
        lbl_clip.setStyleSheet("color: #E4E4E7; font-size: 12px; font-weight: 600;")
        clip_row.addWidget(lbl_clip, stretch=1)

        self.clip_toggle = ToggleSwitch(checked=settings.get("auto_paste", True))
        self.clip_toggle.toggled.connect(lambda v: settings.set("auto_paste", v))
        clip_row.addWidget(self.clip_toggle)
        c1_layout.addLayout(clip_row)

        container_layout.addWidget(card1)

        # --- Card 2: Оформление и форматы ---
        card2 = QFrame()
        card2.setProperty("class", "SettingsCard")
        c2_layout = QVBoxLayout(card2)
        c2_layout.setContentsMargins(14, 12, 14, 12)
        c2_layout.setSpacing(10)

        # Opacity slider
        opacity_header = QHBoxLayout()
        lbl_opacity = QLabel("Прозрачность окна (видимость рабочего стола):")
        lbl_opacity.setProperty("class", "SectionHeader")
        opacity_header.addWidget(lbl_opacity)

        self.opacity_val_lbl = QLabel(f"{int(settings.get('glass_opacity', 0.50) * 100)}%")
        self.opacity_val_lbl.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.10);
            border-radius: 5px;
            padding: 2px 7px;
            font-size: 11px;
            color: #FFFFFF;
            font-weight: 800;
            font-family: 'Consolas', monospace;
        """)
        opacity_header.addWidget(self.opacity_val_lbl)
        c2_layout.addLayout(opacity_header)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(20, 90)
        self.slider.setValue(int(settings.get("glass_opacity", 0.50) * 100))
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid rgba(255, 255, 255, 0.12);
                height: 5px;
                background: rgba(0, 0, 0, 0.6);
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #FFFFFF;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                border: 1px solid #18181B;
                width: 14px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 7px;
            }
        """)
        self.slider.valueChanged.connect(self._on_opacity_slider_changed)
        c2_layout.addWidget(self.slider)

        # Audio format & Cookies rows
        dropdown_row = QHBoxLayout()
        dropdown_row.setSpacing(12)

        # Audio
        audio_col = QVBoxLayout()
        audio_col.setSpacing(4)
        lbl_audio = QLabel("Аудио формат:")
        lbl_audio.setProperty("class", "SectionHeader")
        audio_col.addWidget(lbl_audio)

        self.audio_combo = QComboBox()
        self.audio_combo.addItems(["MP3 (320 kbps)", "FLAC (Lossless)", "M4A (AAC)", "OPUS", "WAV"])
        fmt_map = {"mp3": 0, "flac": 1, "m4a": 2, "opus": 3, "wav": 4}
        self.audio_combo.setCurrentIndex(fmt_map.get(settings.get("audio_format", "mp3"), 0))
        self.audio_combo.currentIndexChanged.connect(self._on_audio_format_changed)
        audio_col.addWidget(self.audio_combo)
        dropdown_row.addLayout(audio_col, stretch=1)

        # Cookies
        cookies_col = QVBoxLayout()
        cookies_col.setSpacing(4)
        lbl_cookies = QLabel("Cookies браузера (18+):")
        lbl_cookies.setProperty("class", "SectionHeader")
        cookies_col.addWidget(lbl_cookies)

        self.cookies_combo = QComboBox()
        current_browser = settings.get("browser_cookies", "none")
        selected_idx = 0
        for i, (b_id, b_name) in enumerate(SUPPORTED_BROWSERS):
            self.cookies_combo.addItem(b_name, b_id)
            if b_id == current_browser:
                selected_idx = i
        self.cookies_combo.setCurrentIndex(selected_idx)
        self.cookies_combo.currentIndexChanged.connect(self._on_cookies_changed)
        cookies_col.addWidget(self.cookies_combo)
        dropdown_row.addLayout(cookies_col, stretch=1)

        c2_layout.addLayout(dropdown_row)
        container_layout.addWidget(card2)

        # --- Card 3: Служебные утилиты и обновления ---
        card3 = QFrame()
        card3.setProperty("class", "SettingsCard")
        c3_layout = QVBoxLayout(card3)
        c3_layout.setContentsMargins(14, 12, 14, 12)
        c3_layout.setSpacing(10)

        lbl_util = QLabel("Служебные утилиты и движок:")
        lbl_util.setProperty("class", "SectionHeader")
        c3_layout.addWidget(lbl_util)

        util_row = QHBoxLayout()
        util_row.setSpacing(10)

        self.btn_clear_cache = QPushButton("  Очистить кэш (%TEMP%)")
        self.btn_clear_cache.setIcon(get_svg_icon("repeat", color="#FFFFFF", size=14))
        self.btn_clear_cache.setIconSize(QSize(14, 14))
        self.btn_clear_cache.setCursor(Qt.PointingHandCursor)
        self.btn_clear_cache.setToolTip("Удалить временные прокси-файлы и эскизы")
        self.btn_clear_cache.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 9px;
                padding: 8px 14px;
                color: #EDEDED;
                font-weight: 700;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(255, 255, 255, 0.25);
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.18);
            }
        """)
        self.btn_clear_cache.clicked.connect(self._clear_cache)
        util_row.addWidget(self.btn_clear_cache, stretch=1)

        self.btn_update_ytdlp = QPushButton("  Обновить yt-dlp")
        self.btn_update_ytdlp.setIcon(get_svg_icon("zap", color="#FBBF24", size=14))
        self.btn_update_ytdlp.setIconSize(QSize(14, 14))
        self.btn_update_ytdlp.setCursor(Qt.PointingHandCursor)
        self.btn_update_ytdlp.setToolTip("Проверить и обновить загрузчик yt-dlp до последней версии")
        self.btn_update_ytdlp.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 9px;
                padding: 8px 14px;
                color: #EDEDED;
                font-weight: 700;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(255, 255, 255, 0.25);
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.18);
            }
        """)
        self.btn_update_ytdlp.clicked.connect(self._update_ytdlp)
        util_row.addWidget(self.btn_update_ytdlp, stretch=1)

        c3_layout.addLayout(util_row)

        self.util_status_lbl = QLabel("")
        self.util_status_lbl.setStyleSheet("font-size: 11px; color: #4ADE80; font-weight: 600; padding: 2px 4px;")
        self.util_status_lbl.setVisible(False)
        c3_layout.addWidget(self.util_status_lbl)

        container_layout.addWidget(card3)

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
