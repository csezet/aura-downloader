import os
import subprocess
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from PySide6.QtCore import Qt, Signal
from ui.animations import FadeSlideHelper, SmoothProgressBar

class ProgressWidget(QFrame):
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")
        self.setMaximumHeight(0)
        self.setVisible(False)
        self._current_file_path = None

        self._anim = FadeSlideHelper(self, target_height=90, duration=240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        # Header status and percent
        header_layout = QHBoxLayout()
        self.status_label = QLabel("ПОДГОТОВКА...")
        self.status_label.setStyleSheet("font-size: 12px; font-weight: 800; color: #FFFFFF; letter-spacing: 0.5px;")
        header_layout.addWidget(self.status_label)

        header_layout.addStretch()

        self.percent_label = QLabel("0.0%")
        self.percent_label.setStyleSheet("font-size: 13px; font-weight: 800; color: #FFFFFF; font-family: 'Consolas', monospace;")
        header_layout.addWidget(self.percent_label)

        layout.addLayout(header_layout)

        # Smooth Progress bar
        self.progress_bar = SmoothProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        # Bottom metrics & buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(10)

        self.metrics_label = QLabel("SPEED: -- MB/S // SIZE: 0 B / 0 B // ETA: --:--")
        self.metrics_label.setStyleSheet("font-size: 11px; color: #A1A1AA; font-family: 'Consolas', monospace;")
        bottom_layout.addWidget(self.metrics_label)

        bottom_layout.addStretch()

        # Action Buttons
        self.cancel_btn = QPushButton("✕ ОТМЕНА")
        self.cancel_btn.setProperty("class", "GlassButton")
        self.cancel_btn.setStyleSheet("color: #EF4444; padding: 3px 8px; font-size: 11px; font-weight: 700;")
        self.cancel_btn.clicked.connect(self.cancelled.emit)
        bottom_layout.addWidget(self.cancel_btn)

        self.open_file_btn = QPushButton("▶ ОТКРЫТЬ")
        self.open_file_btn.setProperty("class", "GlassButton")
        self.open_file_btn.setStyleSheet("padding: 3px 8px; font-size: 11px; font-weight: 700;")
        self.open_file_btn.clicked.connect(self._open_file)
        self.open_file_btn.setVisible(False)
        bottom_layout.addWidget(self.open_file_btn)

        self.open_dir_btn = QPushButton("📂 ПАПКА")
        self.open_dir_btn.setProperty("class", "GlassButton")
        self.open_dir_btn.setStyleSheet("padding: 3px 8px; font-size: 11px; font-weight: 700;")
        self.open_dir_btn.clicked.connect(self._open_dir)
        self.open_dir_btn.setVisible(False)
        bottom_layout.addWidget(self.open_dir_btn)

        layout.addLayout(bottom_layout)

    def start_progress(self, message="ЗАПУСК ЗАГРУЗКИ..."):
        self.progress_bar.setValue(0)
        self.percent_label.setText("0.0%")
        self.status_label.setText(message)
        self.status_label.setStyleSheet("font-size: 12px; font-weight: 800; color: #FFFFFF;")
        self.metrics_label.setText("SPEED: -- MB/S // SIZE: 0 B / 0 B // ETA: --:--")
        self.cancel_btn.setVisible(True)
        self.open_file_btn.setVisible(False)
        self.open_dir_btn.setVisible(False)
        self._current_file_path = None
        self._anim.show_animated(90)

    def update_progress(self, data: dict):
        percent = data.get("percent", 0.0)
        self.progress_bar.setSmoothValue(percent)
        self.percent_label.setText(f"{percent:.1f}%")

        speed = data.get("speed_str", "-- MB/S").upper()
        downloaded = data.get("downloaded_str", "0 B")
        total = data.get("total_str", "...")
        eta = data.get("eta_str", "--:--")
        status = data.get("status")

        if status == "processing":
            self.status_label.setText("⚙ ОБРАБОТКА ПОТОКОВ (FFMPEG)...")
        else:
            self.status_label.setText("⚡ СКАЧИВАНИЕ...")

        self.metrics_label.setText(f"{speed} // {downloaded} OF {total} // ETA {eta}")

    def complete(self, result: dict):
        self.progress_bar.setSmoothValue(100)
        self.percent_label.setText("100%")
        self.status_label.setText("✓ ЗАВЕРШЕНО УСПЕШНО")
        self.status_label.setStyleSheet("font-size: 12px; font-weight: 800; color: #FFFFFF;")
        
        file_size_str = result.get("file_size_str", "")
        self.metrics_label.setText(f"ИТОГОВЫЙ РАЗМЕР: {file_size_str}")
        self._current_file_path = result.get("file_path")

        self.cancel_btn.setVisible(False)
        self.open_file_btn.setVisible(True)
        self.open_dir_btn.setVisible(True)

    def set_error(self, message: str):
        self.status_label.setText("✕ ОШИБКА ЗАГРУЗКИ")
        self.status_label.setStyleSheet("font-size: 12px; font-weight: 800; color: #EF4444;")
        self.metrics_label.setText(message[:75] + ("..." if len(message) > 75 else ""))
        self.cancel_btn.setText("ЗАКРЫТЬ")
        self.cancel_btn.setVisible(True)
        self._anim.show_animated(90)

    def hide_progress(self):
        self._anim.hide_animated()

    def _open_file(self):
        if self._current_file_path and os.path.exists(self._current_file_path):
            os.startfile(self._current_file_path)

    def _open_dir(self):
        if self._current_file_path and os.path.exists(self._current_file_path):
            subprocess.run(['explorer', '/select,', os.path.normpath(self._current_file_path)])
        elif self._current_file_path:
            folder = os.path.dirname(self._current_file_path)
            if os.path.exists(folder):
                os.startfile(folder)
