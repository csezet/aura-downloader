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
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 11px;
            }
            QFrame:hover {
                background-color: rgba(255, 255, 255, 0.065);
                border: 1px solid rgba(255, 255, 255, 0.22);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        format_type = item.get("format_type", "MP4").upper()
        file_path = item.get("file_path", "")
        file_exists = os.path.exists(file_path) if file_path else False

        # Format Pill Badge
        fmt_badge = QLabel(format_type[:6])
        fmt_badge.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.10);
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 6px;
            padding: 3px 7px;
            font-size: 10px;
            font-weight: 800;
            font-family: 'Consolas', monospace;
        """)
        fmt_badge.setAlignment(Qt.AlignCenter)
        fmt_badge.setFixedWidth(50)
        layout.addWidget(fmt_badge)

        # Title and Path info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)

        title = item.get("title", "Без названия")
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #FFFFFF; background: transparent; border: none;")
        self.title_lbl.setWordWrap(True)
        info_layout.addWidget(self.title_lbl)

        short_path = os.path.basename(file_path) if file_path else ""
        status_text = f"📁 {short_path}" if file_exists else "⚠️ Файл перемещен или удален"
        status_color = "#71717A" if file_exists else "#EF4444"
        self.sub_lbl = QLabel(status_text)
        self.sub_lbl.setStyleSheet(f"font-size: 10px; color: {status_color}; font-family: 'Consolas', monospace; background: transparent; border: none;")
        info_layout.addWidget(self.sub_lbl)

        layout.addLayout(info_layout, stretch=1)

        # Action buttons
        if file_exists:
            self.play_btn = QPushButton(" Воспроизвести")
            self.play_btn.setIcon(get_svg_icon("play", color="#FFFFFF", size=12))
            self.play_btn.setIconSize(QSize(12, 12))
            self.play_btn.setCursor(Qt.PointingHandCursor)
            self.play_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.06);
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 7px;
                    padding: 5px 10px;
                    color: #EDEDED;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.14);
                    border: 1px solid rgba(255, 255, 255, 0.28);
                    color: #FFFFFF;
                }
            """)
            self.play_btn.setToolTip("Воспроизвести файл в плеере")
            self.play_btn.clicked.connect(self._play)
            layout.addWidget(self.play_btn)

            self.folder_btn = QPushButton(" Папка")
            self.folder_btn.setIcon(get_svg_icon("folder", color="#FFFFFF", size=12))
            self.folder_btn.setIconSize(QSize(12, 12))
            self.folder_btn.setCursor(Qt.PointingHandCursor)
            self.folder_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.06);
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 7px;
                    padding: 5px 10px;
                    color: #EDEDED;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.14);
                    border: 1px solid rgba(255, 255, 255, 0.28);
                    color: #FFFFFF;
                }
            """)
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
        self.resize(680, 500)
        self.setMinimumSize(580, 420)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._drag_pos = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Solid Dark Container with 18px radius
        container = QFrame()
        container.setObjectName("HistoryContainer")
        container.setStyleSheet("""
            QFrame#HistoryContainer {
                background-color: #0E1218;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 18px;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(22, 18, 22, 20)
        container_layout.setSpacing(14)

        # Header
        header = QHBoxLayout()
        header.setSpacing(10)

        header_icon = QLabel()
        header_icon.setPixmap(get_svg_icon("history", color="#FFFFFF", size=18).pixmap(18, 18))
        header.addWidget(header_icon)

        title = QLabel("ИСТОРИЯ ЗАГРУЗОК")
        title.setStyleSheet("font-size: 14px; font-weight: 800; color: #FFFFFF; letter-spacing: 1px; background: transparent; border: none;")
        header.addWidget(title)

        header.addStretch()

        clear_btn = QPushButton(" Очистить историю")
        clear_btn.setIcon(get_svg_icon("repeat", color="#A1A1AA", size=13))
        clear_btn.setIconSize(QSize(13, 13))
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 11px;
                font-weight: 700;
                color: #A1A1AA;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.15);
                border: 1px solid rgba(239, 68, 68, 0.35);
                color: #EF4444;
            }
            QPushButton:pressed {
                background-color: rgba(239, 68, 68, 0.25);
            }
        """)
        clear_btn.clicked.connect(self._clear_history)
        header.addWidget(clear_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                color: #A1A1AA;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.16);
                color: #FFFFFF;
                border: 1px solid rgba(255, 255, 255, 0.20);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.24);
            }
        """)
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)

        container_layout.addLayout(header)

        # Scroll Area for items
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.18);
                min-height: 24px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.35);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
            }
        """)

        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 6, 0)
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
            empty_card = QFrame()
            empty_card.setStyleSheet("""
                QFrame {
                    background-color: rgba(255, 255, 255, 0.02);
                    border: 1px dashed rgba(255, 255, 255, 0.10);
                    border-radius: 14px;
                    padding: 30px;
                }
            """)
            ec_layout = QVBoxLayout(empty_card)
            ec_layout.setAlignment(Qt.AlignCenter)
            ec_layout.setSpacing(8)

            ec_icon = QLabel()
            ec_icon.setPixmap(get_svg_icon("history", color="#52525B", size=36).pixmap(36, 36))
            ec_icon.setAlignment(Qt.AlignCenter)
            ec_icon.setStyleSheet("background: transparent; border: none;")
            ec_layout.addWidget(ec_icon)

            ec_title = QLabel("История загрузок пуста")
            ec_title.setAlignment(Qt.AlignCenter)
            ec_title.setStyleSheet("color: #A1A1AA; font-size: 13px; font-weight: 700; background: transparent; border: none;")
            ec_layout.addWidget(ec_title)

            ec_sub = QLabel("Все сохраненные и обработанные видео будут отображаться здесь")
            ec_sub.setAlignment(Qt.AlignCenter)
            ec_sub.setStyleSheet("color: #52525B; font-size: 11px; background: transparent; border: none;")
            ec_layout.addWidget(ec_sub)

            self.list_layout.insertWidget(0, empty_card)
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
