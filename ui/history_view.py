import os
import subprocess
from PySide6.QtWidgets import (
    QDialog, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QWidget, QSizePolicy
)
from PySide6.QtCore import Qt, QSize
from core.history import history
from assets.icons import get_svg_icon

class HistoryItemWidget(QFrame):
    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.item = item
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
            }
            QFrame:hover {
                background-color: rgba(255, 255, 255, 0.07);
                border: 1px solid rgba(255, 255, 255, 0.22);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        format_type = item.get("format_type", "MP4").upper()
        file_path = item.get("file_path", "")
        file_exists = os.path.exists(file_path) if file_path else False

        # Format Pill Badge
        fmt_badge = QLabel(format_type[:6])
        fmt_badge.setStyleSheet("""
            background-color: #000000;
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.25);
            border-radius: 4px;
            padding: 3px 6px;
            font-size: 10px;
            font-weight: 800;
            font-family: 'Consolas', monospace;
        """)
        fmt_badge.setAlignment(Qt.AlignCenter)
        fmt_badge.setFixedWidth(46)
        layout.addWidget(fmt_badge)

        # Title and Path info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)

        title = item.get("title", "Без названия")
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #FFFFFF;")
        self.title_lbl.setWordWrap(True)
        info_layout.addWidget(self.title_lbl)

        short_path = os.path.basename(file_path) if file_path else ""
        status_text = f"📁 .../{short_path}" if file_exists else "⚠️ Файл перемещен или удален"
        self.sub_lbl = QLabel(status_text)
        self.sub_lbl.setStyleSheet("font-size: 10px; color: #71717A; font-family: 'Consolas', monospace;")
        info_layout.addWidget(self.sub_lbl)

        layout.addLayout(info_layout, stretch=1)

        # Action buttons
        if file_exists:
            self.play_btn = QPushButton(" ▶ ")
            self.play_btn.setProperty("class", "GlassButton")
            self.play_btn.setStyleSheet("font-size: 11px; padding: 4px 8px; font-weight: 700;")
            self.play_btn.setToolTip("Воспроизвести файл")
            self.play_btn.clicked.connect(self._play)
            layout.addWidget(self.play_btn)

            self.folder_btn = QPushButton(" 📂 ")
            self.folder_btn.setProperty("class", "GlassButton")
            self.folder_btn.setStyleSheet("font-size: 11px; padding: 4px 8px; font-weight: 700;")
            self.folder_btn.setToolTip("Показать файл в проводнике")
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


class HistoryModal(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("История загрузок")
        self.resize(660, 490)
        self.setMinimumSize(580, 400)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._drag_pos = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Opaque Cyber Container
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: #11141A;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 12px;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(18, 16, 18, 16)
        container_layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("📜 ИСТОРИЯ ЗАГРУЗОК")
        title.setStyleSheet("font-size: 13px; font-weight: 800; color: #FFFFFF; letter-spacing: 0.8px; background: transparent; border: none;")
        header.addWidget(title)

        header.addStretch()

        clear_btn = QPushButton("ОЧИСТИТЬ")
        clear_btn.setProperty("class", "GlassButton")
        clear_btn.setStyleSheet("font-size: 11px; padding: 4px 10px; font-weight: 700;")
        clear_btn.clicked.connect(self._clear_history)
        header.addWidget(clear_btn)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("TitleButton")
        close_btn.setStyleSheet("font-size: 13px; font-weight: bold; width: 28px; height: 28px; border-radius: 6px;")
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)

        container_layout.addLayout(header)

        # Scroll Area for items
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 4, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch()

        self.scroll.setWidget(self.list_container)
        container_layout.addWidget(self.scroll)

        main_layout.addWidget(container)
        self._refresh()

    def _refresh(self):
        while self.list_layout.count() > 1:
            child = self.list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        items = history.get_all()
        if not items:
            empty_lbl = QLabel("[ ИСТОРИЯ ЗАГРУЗОК ПУСТА ]")
            empty_lbl.setAlignment(Qt.AlignCenter)
            empty_lbl.setStyleSheet("color: #71717A; font-size: 12px; padding: 40px; font-family: 'Consolas', monospace; background: transparent; border: none; font-weight: 700;")
            self.list_layout.insertWidget(0, empty_lbl)
        else:
            for item in items:
                widget = HistoryItemWidget(item)
                self.list_layout.insertWidget(self.list_layout.count() - 1, widget)

    def _clear_history(self):
        history.clear()
        self._refresh()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
