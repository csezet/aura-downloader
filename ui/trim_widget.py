from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QWidget, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from assets.icons import get_svg_icon
from ui.toggle_switch import ToggleSwitch

class TrimWidget(QFrame):
    trim_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")
        self.setFixedHeight(44)

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

        # Start Time Input
        self.lbl_from = QLabel("От:")
        self.lbl_from.setStyleSheet("color: #71717A; font-size: 11px; font-weight: bold;")
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
        self.lbl_to.setStyleSheet("color: #71717A; font-size: 11px; font-weight: bold;")
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

    def _on_toggled(self, checked: bool):
        self.start_input.setEnabled(checked)
        self.end_input.setEnabled(checked)
        self.lbl_from.setStyleSheet("color: #EDEDED; font-size: 11px; font-weight: bold;" if checked else "color: #52525B; font-size: 11px; font-weight: bold;")
        self.lbl_to.setStyleSheet("color: #EDEDED; font-size: 11px; font-weight: bold;" if checked else "color: #52525B; font-size: 11px; font-weight: bold;")
        self.trim_toggled.emit(checked)

    def is_trim_enabled(self) -> bool:
        return self.toggle.isChecked()

    def get_trim_range(self) -> tuple:
        return self.start_input.text().strip(), self.end_input.text().strip()

    def set_duration_hint(self, duration_sec: int):
        if duration_sec > 0:
            m, s = divmod(duration_sec, 60)
            h, m = divmod(m, 60)
            if h > 0:
                self.end_input.setText(f"{h:02d}:{m:02d}:{s:02d}")
            else:
                self.end_input.setText(f"{m:02d}:{s:02d}")
