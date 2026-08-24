import os
import subprocess
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QWidget, QSizePolicy, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from core.history import history

class HistoryItemWidget(QFrame):
    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.item = item
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 3px;
            }
            QFrame:hover {
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        title = item.get("title", "Без названия")
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #FFFFFF;")
        info_layout.addWidget(self.title_lbl)

        format_type = item.get("format_type", "MP4")
        file_path = item.get("file_path", "")
        file_exists = os.path.exists(file_path) if file_path else False

        status_text = f"[{format_type.upper()}] // {file_path}" if file_exists else f"[{format_type.upper()}] // Файл перемещен"
        self.sub_lbl = QLabel(status_text)
        self.sub_lbl.setStyleSheet("font-size: 10px; color: #71717A; font-family: 'Consolas', monospace;")
        info_layout.addWidget(self.sub_lbl)

        layout.addLayout(info_layout, stretch=1)

        if file_exists:
            self.play_btn = QPushButton("▶")
            self.play_btn.setFixedSize(26, 26)
            self.play_btn.setProperty("class", "GlassButton")
            self.play_btn.setToolTip("Воспроизвести")
            self.play_btn.clicked.connect(self._play)
            layout.addWidget(self.play_btn)

            self.folder_btn = QPushButton("📂")
            self.folder_btn.setFixedSize(26, 26)
            self.folder_btn.setProperty("class", "GlassButton")
            self.folder_btn.setToolTip("Показать в папке")
            self.folder_btn.clicked.connect(self._open_folder)
            layout.addWidget(self.folder_btn)

    def _play(self):
        fp = self.item.get("file_path")
        if fp and os.path.exists(fp):
            os.startfile(fp)

    def _open_folder(self):
        fp = self.item.get("file_path")
        if fp and os.path.exists(fp):
            subprocess.run(['explorer', '/select,', os.path.normpath(fp)])


class HistoryDrawer(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(180)
        self.setVisible(False)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)

        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(200)
        self.fade_anim.setEasingCurve(QEasingCurve.OutCubic)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("📜 ИСТОРИЯ ЗАГРУЗОК")
        title.setStyleSheet("font-size: 12px; font-weight: 800; color: #FFFFFF; letter-spacing: 0.8px;")
        header.addWidget(title)

        header.addStretch()

        clear_btn = QPushButton("ОЧИСТИТЬ")
        clear_btn.setProperty("class", "GlassButton")
        clear_btn.setStyleSheet("font-size: 10px; padding: 2px 6px; font-weight: 700;")
        clear_btn.clicked.connect(self._clear_history)
        header.addWidget(clear_btn)

        close_btn = QPushButton("✕")
        close_btn.setProperty("class", "GlassButton")
        close_btn.setFixedSize(22, 22)
        close_btn.clicked.connect(self.hide_animated)
        header.addWidget(close_btn)

        main_layout.addLayout(header)

        # Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(4)
        self.list_layout.addStretch()

        self.scroll.setWidget(self.list_container)
        main_layout.addWidget(self.scroll)

    def show_animated(self):
        self.refresh()
        self.setVisible(True)
        self.fade_anim.stop()
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.start()

    def hide_animated(self):
        self.setVisible(False)

    def toggle_animated(self):
        if self.isVisible():
            self.hide_animated()
        else:
            self.show_animated()

    def refresh(self):
        while self.list_layout.count() > 1:
            child = self.list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        items = history.get_all()
        if not items:
            empty_lbl = QLabel("История загрузок пуста")
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet("color: #71717A; font-size: 11px; padding: 16px; font-family: 'Consolas', monospace;")
            self.list_layout.insertWidget(0, empty_lbl)
        else:
            for item in items:
                widget = HistoryItemWidget(item)
                self.list_layout.insertWidget(self.list_layout.count() - 1, widget)

    def _clear_history(self):
        history.clear()
        self.refresh()
