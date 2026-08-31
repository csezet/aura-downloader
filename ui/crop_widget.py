from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QWidget
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap
from assets.icons import get_svg_icon
from ui.toggle_switch import ToggleSwitch
from ui.crop_dialog import CropDialog

class CropWidget(QFrame):
    crop_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")
        self.setFixedHeight(44)

        self._preview_pixmap = None
        self._source_w = 1920
        self._source_h = 1080
        self._crop_params = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        # Toggle Switch
        self.toggle = ToggleSwitch(checked=False)
        self.toggle.toggled.connect(self._on_toggled)
        layout.addWidget(self.toggle)

        # Crop Icon
        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(get_svg_icon("crop", color="#FFFFFF", size=16).pixmap(16, 16))
        layout.addWidget(self.icon_lbl)

        # Title Label
        self.title_lbl = QLabel("Кадрирование кадра (Crop):")
        self.title_lbl.setStyleSheet("color: #EDEDED; font-size: 12px; font-weight: 700;")
        layout.addWidget(self.title_lbl)

        # Controls Container
        self.controls_container = QWidget()
        ctrl_layout = QHBoxLayout(self.controls_container)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(8)

        # Edit Button with sleek vector icon
        self.edit_btn = QPushButton(" НАСТРОИТЬ ОБЛАСТЬ")
        self.edit_btn.setIcon(get_svg_icon("crop", color="#52525B", size=13))
        self.edit_btn.setIconSize(QSize(13, 13))
        self.edit_btn.setProperty("class", "GlassButton")
        self.edit_btn.setStyleSheet("""
            QPushButton {
                font-size: 11px;
                font-weight: 700;
                padding: 3px 10px;
                color: #EDEDED;
                border-radius: 6px;
            }
            QPushButton:disabled {
                color: #52525B;
                border: 1px solid rgba(255, 255, 255, 0.05);
                background: rgba(0, 0, 0, 0.2);
            }
        """)
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._open_crop_dialog)
        ctrl_layout.addWidget(self.edit_btn)

        # Status Tag Badge
        self.status_tag = QLabel("")
        self.status_tag.setStyleSheet("""
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 6px;
            color: #A1A1AA;
            font-size: 10px;
            font-weight: 700;
            font-family: 'Consolas', monospace;
            padding: 2px 8px;
        """)
        self.status_tag.setVisible(False)
        ctrl_layout.addWidget(self.status_tag)

        layout.addWidget(self.controls_container)
        layout.addStretch()

    def set_source_info(self, pixmap: QPixmap = None, width: int = 1920, height: int = 1080):
        self._preview_pixmap = pixmap
        self._source_w = width if width > 0 else 1920
        self._source_h = height if height > 0 else 1080

    def _on_toggled(self, checked: bool):
        self.edit_btn.setEnabled(checked)
        self.edit_btn.setIcon(get_svg_icon("crop", color="#EDEDED" if checked else "#52525B", size=13))
        self.status_tag.setVisible(checked and self._crop_params is not None)
        self.crop_toggled.emit(checked)
        if checked and self._crop_params is None:
            self._open_crop_dialog()

    def _open_crop_dialog(self):
        dialog = CropDialog(
            parent=self.window(),
            pixmap=self._preview_pixmap,
            source_w=self._source_w,
            source_h=self._source_h,
            initial_params=self._crop_params
        )
        if dialog.exec() and dialog.applied_crop_params:
            self._crop_params = dialog.applied_crop_params
            w = self._crop_params.get('w', self._source_w)
            h = self._crop_params.get('h', self._source_h)
            self.status_tag.setText(f"{w}×{h}")
            self.status_tag.setVisible(True)
            if not self.toggle.isChecked():
                self.toggle.setChecked(True)

    def is_crop_enabled(self) -> bool:
        return self.toggle.isChecked() and self._crop_params is not None

    def get_crop_params(self) -> dict:
        return self._crop_params
