from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QWidget, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
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

        # Controls Container (Animated)
        self.controls_container = QWidget()
        ctrl_layout = QHBoxLayout(self.controls_container)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(8)

        # Start Time Input
        lbl_from = QLabel("От:")
        lbl_from.setStyleSheet("color: #71717A; font-size: 11px; font-weight: bold;")
        ctrl_layout.addWidget(lbl_from)

        self.start_input = QLineEdit()
        self.start_input.setPlaceholderText("00:00")
        self.start_input.setText("00:00")
        self.start_input.setFixedWidth(64)
        self.start_input.setStyleSheet("""
            background: rgba(0, 0, 0, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 6px;
            color: #FFFFFF;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            padding: 3px 6px;
            text-align: center;
        """)
        self.start_input.setEnabled(False)
        ctrl_layout.addWidget(self.start_input)

        # End Time Input
        lbl_to = QLabel("До:")
        lbl_to.setStyleSheet("color: #71717A; font-size: 11px; font-weight: bold;")
        ctrl_layout.addWidget(lbl_to)

        self.end_input = QLineEdit()
        self.end_input.setPlaceholderText("01:30")
        self.end_input.setText("01:30")
        self.end_input.setFixedWidth(64)
        self.end_input.setStyleSheet("""
            background: rgba(0, 0, 0, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 6px;
            color: #FFFFFF;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            padding: 3px 6px;
            text-align: center;
        """)
        self.end_input.setEnabled(False)
        ctrl_layout.addWidget(self.end_input)

        # Opacity Animation Effect
        self.opacity_effect = QGraphicsOpacityEffect(self.controls_container)
        self.opacity_effect.setOpacity(0.3)
        self.controls_container.setGraphicsEffect(self.opacity_effect)
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(220)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

        layout.addWidget(self.controls_container)
        layout.addStretch()

    def _on_toggled(self, checked: bool):
        self.start_input.setEnabled(checked)
        self.end_input.setEnabled(checked)
        
        self.anim.stop()
        self.anim.setStartValue(self.opacity_effect.opacity())
        self.anim.setEndValue(1.0 if checked else 0.3)
        self.anim.start()

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
