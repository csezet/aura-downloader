from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon
from assets.icons import get_svg_icon
from ui.toggle_switch import ToggleSwitch
from ui.trim_dialog import TrimDialog

class TrimWidget(QFrame):
    trim_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")
        self.setFixedHeight(44)

        self._video_source = None
        self._duration_sec = 60

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        # Sleek Toggle Switch
        self.toggle = ToggleSwitch(checked=False)
        self.toggle.toggled.connect(self._on_toggled)
        layout.addWidget(self.toggle)

        # Scissors icon
        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(get_svg_icon("scissors", color="#FFFFFF", size=16).pixmap(16, 16))
        layout.addWidget(self.icon_lbl)

        # Title Label
        self.title_lbl = QLabel("Скачать отрезок (Таймкоды):")
        self.title_lbl.setStyleSheet("color: #EDEDED; font-size: 12px; font-weight: 700;")
        layout.addWidget(self.title_lbl)

        # Controls Container (Fixed size, tightly packed on the left)
        self.controls_container = QWidget()
        self.controls_container.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        ctrl_layout = QHBoxLayout(self.controls_container)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(8)

        # Visual Trim Button (Opens interactive video player trim modal)
        self.visual_btn = QPushButton(" НАСТРОИТЬ ОТРЕЗОК")
        self.visual_btn.setIcon(get_svg_icon("scissors", color="#52525B", size=13))
        self.visual_btn.setIconSize(QSize(13, 13))
        self.visual_btn.setProperty("class", "GlassButton")
        self.visual_btn.setStyleSheet("""
            QPushButton {
                font-size: 11px;
                font-weight: 700;
                padding: 3px 10px;
                color: #EDEDED;
                border-radius: 6px;
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.16);
            }
            QPushButton:hover {
                color: #FFFFFF;
                background-color: rgba(255, 255, 255, 0.16);
                border: 1px solid rgba(255, 255, 255, 0.40);
            }
            QPushButton:pressed {
                color: #FFFFFF;
                background-color: rgba(255, 255, 255, 0.24);
                border: 1px solid rgba(255, 255, 255, 0.60);
            }
            QPushButton:disabled {
                color: #52525B;
                border: 1px solid rgba(255, 255, 255, 0.05);
                background: rgba(0, 0, 0, 0.2);
            }
        """)
        self.visual_btn.setEnabled(False)
        self.visual_btn.clicked.connect(self._open_trim_dialog)
        ctrl_layout.addWidget(self.visual_btn)

        # Start Time Input
        self.lbl_from = QLabel("От:")
        self.lbl_from.setStyleSheet("color: #52525B; font-size: 11px; font-weight: bold;")
        ctrl_layout.addWidget(self.lbl_from)

        self.start_input = QLineEdit()
        self.start_input.setPlaceholderText("00:00")
        self.start_input.setText("00:00")
        self.start_input.setFixedWidth(64)
        self.start_input.setStyleSheet("""
            QLineEdit {
                background: rgba(0, 0, 0, 0.6);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
                color: #FFFFFF;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                padding: 3px 6px;
                text-align: center;
            }
            QLineEdit:disabled {
                color: #52525B;
                border: 1px solid rgba(255, 255, 255, 0.05);
                background: rgba(0, 0, 0, 0.3);
            }
        """)
        self.start_input.setEnabled(False)
        ctrl_layout.addWidget(self.start_input)

        # End Time Input
        self.lbl_to = QLabel("До:")
        self.lbl_to.setStyleSheet("color: #52525B; font-size: 11px; font-weight: bold;")
        ctrl_layout.addWidget(self.lbl_to)

        self.end_input = QLineEdit()
        self.end_input.setPlaceholderText("01:30")
        self.end_input.setText("01:30")
        self.end_input.setFixedWidth(64)
        self.end_input.setStyleSheet("""
            QLineEdit {
                background: rgba(0, 0, 0, 0.6);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
                color: #FFFFFF;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                padding: 3px 6px;
                text-align: center;
            }
            QLineEdit:disabled {
                color: #52525B;
                border: 1px solid rgba(255, 255, 255, 0.05);
                background: rgba(0, 0, 0, 0.3);
            }
        """)
        self.end_input.setEnabled(False)
        ctrl_layout.addWidget(self.end_input)

        layout.addWidget(self.controls_container)
        layout.addStretch(1)

    def set_source_video(self, video_source: str, duration_sec: float = 60):
        self._video_source = video_source
        self._duration_sec = duration_sec
        self.set_duration_hint(duration_sec)

    def set_duration_hint(self, duration_sec: int):
        if duration_sec > 0:
            self._duration_sec = duration_sec
            m, s = divmod(int(duration_sec), 60)
            h, m = divmod(m, 60)
            if h > 0:
                self.end_input.setText(f"{h:02d}:{m:02d}:{s:02d}")
            else:
                self.end_input.setText(f"{m:02d}:{s:02d}")

    def _on_toggled(self, checked: bool):
        self.visual_btn.setEnabled(checked)
        self.visual_btn.setIcon(get_svg_icon("scissors", color="#FFFFFF" if checked else "#52525B", size=13))
        self.start_input.setEnabled(checked)
        self.end_input.setEnabled(checked)
        self.lbl_from.setStyleSheet("color: #EDEDED; font-size: 11px; font-weight: bold;" if checked else "color: #52525B; font-size: 11px; font-weight: bold;")
        self.lbl_to.setStyleSheet("color: #EDEDED; font-size: 11px; font-weight: bold;" if checked else "color: #52525B; font-size: 11px; font-weight: bold;")
        self.trim_toggled.emit(checked)

    def _open_trim_dialog(self):
        dialog = TrimDialog(
            parent=self.window(),
            video_source=self._video_source,
            duration_sec=self._duration_sec,
            initial_start=self.start_input.text().strip(),
            initial_end=self.end_input.text().strip()
        )
        if dialog.exec() and dialog.applied_range:
            start_str, end_str = dialog.applied_range
            self.start_input.setText(start_str)
            self.end_input.setText(end_str)

    def is_trim_enabled(self) -> bool:
        return self.toggle.isChecked()

    def get_trim_range(self) -> tuple:
        return self.start_input.text().strip(), self.end_input.text().strip()
