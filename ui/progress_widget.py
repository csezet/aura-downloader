import os
import subprocess
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from ui.animations import SmoothProgressBar

class ProgressWidget(QFrame):
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(88)
        self.setVisible(False)
        self._current_file_path = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # Header status and percent
        header_layout = QHBoxLayout()
        self.status_label = QLabel("⚡ СКАЧИВАНИЕ...")
        self.status_label.setStyleSheet("font-size: 11px; font-weight: 800; color: #FFFFFF; letter-spacing: 0.5px;")
        header_layout.addWidget(self.status_label)

        header_layout.addStretch()

        self.percent_label = QLabel("0.0%")
        self.percent_label.setStyleSheet("font-size: 12px; font-weight: 800; color: #FFFFFF; font-family: 'Consolas', monospace;")
        header_layout.addWidget(self.percent_label)

        layout.addLayout(header_layout)

        # Smooth Progress bar
        self.progress_bar = SmoothProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        # Bottom metrics & buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)

        self.metrics_label = QLabel("SPEED: -- MB/S // SIZE: 0 B / 0 B // ETA: --:--")
        self.metrics_label.setStyleSheet("font-size: 10px; color: #A1A1AA; font-family: 'Consolas', monospace;")
        bottom_layout.addWidget(self.metrics_label)

        bottom_layout.addStretch()

        # Action Buttons
        self.cancel_btn = QPushButton("✕ ОТМЕНА")
        self.cancel_btn.setProperty("class", "GlassButton")
        self.cancel_btn.setStyleSheet("color: #EF4444; padding: 2px 8px; font-size: 10px; font-weight: 700;")
        self.cancel_btn.clicked.connect(self.cancelled.emit)
        bottom_layout.addWidget(self.cancel_btn)

        self.open_file_btn = QPushButton("▶ ОТКРЫТЬ")
        self.open_file_btn.setProperty("class", "GlassButton")
        self.open_file_btn.setStyleSheet("padding: 2px 8px; font-size: 10px; font-weight: 700;")
        self.open_file_btn.clicked.connect(self._open_file)
        self.open_file_btn.setVisible(False)
        bottom_layout.addWidget(self.open_file_btn)

        self.open_dir_btn = QPushButton("📂 ПАПКА")
        self.open_dir_btn.setProperty("class", "GlassButton")
        self.open_dir_btn.setStyleSheet("padding: 2px 8px; font-size: 10px; font-weight: 700;")
        self.open_dir_btn.clicked.connect(self._open_dir)
        self.open_dir_btn.setVisible(False)
        bottom_layout.addWidget(self.open_dir_btn)

        layout.addLayout(bottom_layout)

        # Opacity Animation
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.anim_opacity = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_opacity.setDuration(240)
        self.anim_opacity.setEasingCurve(QEasingCurve.OutCubic)

    def start_progress(self, message="⚡ СКАЧИВАНИЕ..."):
        self.progress_bar.setValue(0)
        self.percent_label.setText("0.0%")
        self.status_label.setText(message)
        self.metrics_label.setText("ПОДГОТОВКА...")
        self.cancel_btn.setVisible(True)
        self.open_file_btn.setVisible(False)
        self.open_dir_btn.setVisible(False)
        
        self.setVisible(True)
        self.anim_opacity.stop()
        self.anim_opacity.setStartValue(0.0)
        self.anim_opacity.setEndValue(1.0)
        self.anim_opacity.start()

    def update_progress(self, data: dict):
        percent = data.get('percent', 0.0)
        self.progress_bar.setValue(int(percent))
        self.percent_label.setText(f"{percent:.1f}%")

        speed = data.get('speed_str', '-- MB/s')
        downloaded = data.get('downloaded_str', '0 B')
        total = data.get('total_str', '0 B')
        eta = data.get('eta_str', '--:--')

        self.metrics_label.setText(f"SPEED: {speed} // {downloaded} / {total} // ETA: {eta}")

    def complete(self, result: dict):
        self.progress_bar.setValue(100)
        self.percent_label.setText("100%")
        self.status_label.setText("ГОТОВО!")
        self.metrics_label.setText(f"ФАЙЛ СОХРАНЕН // {result.get('file_size_str', '')}")

        self._current_file_path = result.get('file_path')
        self.cancel_btn.setVisible(False)
        self.open_file_btn.setVisible(True)
        self.open_dir_btn.setVisible(True)

    def set_error(self, err_msg: str):
        self.status_label.setText("ОШИБКА")
        self.metrics_label.setText(err_msg[:60])
        self.cancel_btn.setText("✕ ЗАКРЫТЬ")

    def hide_progress(self):
        self.anim_opacity.stop()
        self.anim_opacity.setStartValue(self.opacity_effect.opacity())
        self.anim_opacity.setEndValue(0.0)
        self.anim_opacity.finished.connect(self._on_hide_done)
        self.anim_opacity.start()

    def _on_hide_done(self):
        if self.opacity_effect.opacity() <= 0.05:
            self.setVisible(False)

    def _open_file(self):
        if self._current_file_path and os.path.exists(self._current_file_path):
            os.startfile(self._current_file_path)

    def _open_dir(self):
        if self._current_file_path and os.path.exists(self._current_file_path):
            dir_path = os.path.dirname(self._current_file_path)
            os.startfile(dir_path)
