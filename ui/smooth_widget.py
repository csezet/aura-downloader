from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QComboBox, QPushButton, QWidget, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QThread, QSize
from PySide6.QtGui import QIcon
from assets.icons import get_svg_icon
from ui.toggle_switch import ToggleSwitch
from core.interpolator import is_rife_available, download_rife_engine

class RifeDownloaderThread(QThread):
    status_updated = Signal(str)
    download_finished = Signal(bool)

    def run(self):
        success = download_rife_engine(progress_callback=self.status_updated.emit)
        self.download_finished.emit(success)

class SmoothWidget(QFrame):
    smooth_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")
        self.setFixedHeight(44)

        self._dl_thread = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)

        # Toggle Switch
        self.toggle = ToggleSwitch(checked=False)
        self.toggle.toggled.connect(self._on_toggled)
        layout.addWidget(self.toggle)

        # Zap Icon
        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(get_svg_icon("zap", color="#FFFFFF", size=16).pixmap(16, 16))
        layout.addWidget(self.icon_lbl)

        # Title Label
        self.title_lbl = QLabel("Плавность кадров (AI Smooth FPS):")
        self.title_lbl.setStyleSheet("color: #EDEDED; font-size: 12px; font-weight: 700;")
        layout.addWidget(self.title_lbl)

        # Controls Container
        self.controls_container = QWidget()
        self.controls_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        ctrl_layout = QHBoxLayout(self.controls_container)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(8)

        # FPS Selector
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["60 FPS (Плавное)", "120 FPS (Ультра)", "2x Удвоение"])
        self.fps_combo.setCurrentIndex(0)
        self.fps_combo.setEnabled(False)
        self.fps_combo.setStyleSheet("""
            QComboBox {
                font-size: 11px;
                font-weight: 700;
                padding: 3px 8px;
            }
            QComboBox:disabled {
                color: #52525B;
                border: 1px solid rgba(255, 255, 255, 0.05);
                background: rgba(0, 0, 0, 0.2);
            }
        """)
        ctrl_layout.addWidget(self.fps_combo)

        # AI Engine Badge / Button with sleek SVG icon
        self.engine_btn = QPushButton(" AI RIFE (Vulkan)")
        self.engine_btn.setIcon(get_svg_icon("zap", color="#52525B", size=12))
        self.engine_btn.setIconSize(QSize(12, 12))
        self.engine_btn.setProperty("class", "GlassButton")
        self.engine_btn.setStyleSheet("""
            QPushButton {
                font-size: 10px;
                font-weight: 700;
                padding: 3px 8px;
                border-radius: 6px;
                color: #A1A1AA;
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.16);
            }
            QPushButton:hover {
                color: #FFFFFF;
                background-color: rgba(255, 255, 255, 0.16);
                border: 1px solid rgba(255, 255, 255, 0.40);
            }
            QPushButton:disabled {
                color: #52525B;
                border: 1px solid rgba(255, 255, 255, 0.05);
                background: rgba(0, 0, 0, 0.2);
            }
        """)
        self.engine_btn.setEnabled(False)
        self.engine_btn.clicked.connect(self._toggle_engine)
        ctrl_layout.addWidget(self.engine_btn)

        # Status note
        self.status_lbl = QLabel("Готов к ускорению")
        self.status_lbl.setStyleSheet("color: #71717A; font-size: 11px; font-weight: 600; background: transparent; border: none;")
        ctrl_layout.addWidget(self.status_lbl)

        layout.addWidget(self.controls_container)
        layout.addStretch(1)

        self._update_engine_ui()

    def _update_engine_ui(self):
        checked = self.toggle.isChecked()
        if is_rife_available():
            self.engine_btn.setText(" AI RIFE (Vulkan)")
            self.engine_btn.setIcon(get_svg_icon("zap", color="#22C55E" if checked else "#52525B", size=12))
            if checked:
                self.engine_btn.setStyleSheet("""
                    QPushButton {
                        font-size: 10px;
                        font-weight: 700;
                        padding: 3px 8px;
                        border-radius: 6px;
                        color: #22C55E;
                        border: 1px solid rgba(34, 197, 94, 0.4);
                        background: rgba(34, 197, 94, 0.1);
                    }
                    QPushButton:hover {
                        color: #4ADE80;
                        border: 1px solid rgba(34, 197, 94, 0.7);
                        background: rgba(34, 197, 94, 0.18);
                    }
                """)
                self.status_lbl.setStyleSheet("color: #4ADE80; font-size: 11px; font-weight: 600; background: transparent; border: none;")
            else:
                self.engine_btn.setStyleSheet("""
                    QPushButton {
                        font-size: 10px;
                        font-weight: 700;
                        padding: 3px 8px;
                        border-radius: 6px;
                        color: #52525B;
                        border: 1px solid rgba(255, 255, 255, 0.05);
                        background: rgba(0, 0, 0, 0.2);
                    }
                """)
                self.status_lbl.setStyleSheet("color: #71717A; font-size: 11px; font-weight: 600; background: transparent; border: none;")
            self.status_lbl.setText("Готов к ускорению")
        else:
            self.engine_btn.setText(" СКАЧАТЬ RIFE AI")
            self.engine_btn.setIcon(get_svg_icon("download", color="#3B82F6" if checked else "#52525B", size=12))
            if checked:
                self.engine_btn.setStyleSheet("""
                    QPushButton {
                        font-size: 10px;
                        font-weight: 700;
                        padding: 3px 8px;
                        border-radius: 6px;
                        color: #60A5FA;
                        border: 1px solid rgba(59, 130, 246, 0.4);
                        background: rgba(59, 130, 246, 0.1);
                    }
                    QPushButton:hover {
                        color: #93C5FD;
                        border: 1px solid rgba(59, 130, 246, 0.7);
                        background: rgba(59, 130, 246, 0.18);
                    }
                """)
            else:
                self.engine_btn.setStyleSheet("""
                    QPushButton {
                        font-size: 10px;
                        font-weight: 700;
                        padding: 3px 8px;
                        border-radius: 6px;
                        color: #52525B;
                        border: 1px solid rgba(255, 255, 255, 0.05);
                        background: rgba(0, 0, 0, 0.2);
                    }
                """)
            self.status_lbl.setText("Требуется ~40 МБ")

    def _on_toggled(self, checked: bool):
        self.fps_combo.setEnabled(checked)
        self.engine_btn.setEnabled(checked)
        self._update_engine_ui()
        self.smooth_toggled.emit(checked)

    def _toggle_engine(self):
        if not is_rife_available():
            self._start_download()

    def _start_download(self):
        self.engine_btn.setEnabled(False)
        self.engine_btn.setText(" ЗАГРУЗКА...")
        self._dl_thread = RifeDownloaderThread()
        self._dl_thread.status_updated.connect(lambda s: self.status_lbl.setText(s))
        self._dl_thread.download_finished.connect(self._on_download_finished)
        self._dl_thread.start()

    def _on_download_finished(self, success: bool):
        self.engine_btn.setEnabled(True)
        self._update_engine_ui()

    def is_smooth_enabled(self) -> bool:
        return self.toggle.isChecked()

    def get_target_fps(self) -> int:
        idx = self.fps_combo.currentIndex()
        if idx == 0:
            return 60
        elif idx == 1:
            return 120
        else:
            return 0  # 2x multiplier

    def get_model(self) -> str:
        return "rife-v4.6"
