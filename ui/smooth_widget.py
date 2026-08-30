from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QComboBox, QPushButton, QWidget
)
from PySide6.QtCore import Qt, Signal, QThread
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

        # FPS Selector
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["60 FPS (Плавное)", "120 FPS (Ультра)", "2x Удвоение"])
        self.fps_combo.setCurrentIndex(0)
        self.fps_combo.setEnabled(False)
        layout.addWidget(self.fps_combo)

        # AI Engine Badge / Button
        self.engine_btn = QPushButton("⚡ AI RIFE (Vulkan)")
        self.engine_btn.setProperty("class", "GlassButton")
        self.engine_btn.setStyleSheet("""
            font-size: 10px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 6px;
            color: #A1A1AA;
        """)
        self.engine_btn.setEnabled(False)
        self.engine_btn.clicked.connect(self._toggle_engine)
        layout.addWidget(self.engine_btn)

        # Status note
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #71717A; font-size: 10px; font-family: 'Consolas', monospace;")
        layout.addWidget(self.status_lbl)

        layout.addStretch()

        self._update_engine_ui()

    def _update_engine_ui(self):
        if is_rife_available():
            self.engine_btn.setText("⚡ AI RIFE (Vulkan)")
            self.engine_btn.setStyleSheet("""
                font-size: 10px;
                font-weight: 700;
                padding: 3px 8px;
                border-radius: 6px;
                color: #22C55E;
                border: 1px solid rgba(34, 197, 94, 0.3);
                background: rgba(34, 197, 94, 0.1);
            """)
        else:
            self.engine_btn.setText("⚙️ FFmpeg MCI")
            self.engine_btn.setStyleSheet("""
                font-size: 10px;
                font-weight: 700;
                padding: 3px 8px;
                border-radius: 6px;
                color: #A1A1AA;
            """)

    def _on_toggled(self, checked: bool):
        self.fps_combo.setEnabled(checked)
        self.engine_btn.setEnabled(checked)
        self.smooth_toggled.emit(checked)

    def _toggle_engine(self):
        if not is_rife_available():
            if self._dl_thread and self._dl_thread.isRunning():
                return
            self.status_lbl.setText("Загрузка RIFE...")
            self._dl_thread = RifeDownloaderThread()
            self._dl_thread.status_updated.connect(self.status_lbl.setText)
            self._dl_thread.download_finished.connect(self._on_rife_download_done)
            self._dl_thread.start()

    def _on_rife_download_done(self, success: bool):
        self._update_engine_ui()
        if success:
            self.status_lbl.setText("RIFE готов!")
        else:
            self.status_lbl.setText("Используется FFmpeg")

    def is_smooth_enabled(self) -> bool:
        return self.toggle.isChecked()

    def get_target_fps(self) -> int:
        idx = self.fps_combo.currentIndex()
        if idx == 0:
            return 60
        elif idx == 1:
            return 120
        return 60

    def get_model(self) -> str:
        return "rife" if is_rife_available() else "ffmpeg"
