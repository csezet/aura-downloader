import os
from PySide6.QtWidgets import (
    QDialog, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QSize
from assets.icons import get_svg_icon

class PlaylistItemWidget(QFrame):
    toggled = Signal()

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.item = item
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(255, 255, 255, 0.09);
                border-radius: 10px;
            }
            QFrame:hover {
                background-color: rgba(255, 255, 255, 0.065);
                border: 1px solid rgba(255, 255, 255, 0.20);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.setCursor(Qt.PointingHandCursor)
        self.checkbox.setStyleSheet("""
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid rgba(255, 255, 255, 0.3);
                background: rgba(0, 0, 0, 0.5);
            }
            QCheckBox::indicator:checked {
                background-color: #FFFFFF;
                border: 1px solid #FFFFFF;
                image: none;
            }
            QCheckBox::indicator:hover {
                border: 1px solid #FFFFFF;
            }
        """)
        self.checkbox.toggled.connect(lambda _: self.toggled.emit())
        layout.addWidget(self.checkbox)

        # Duration badge
        dur_str = item.get('duration_str', '--:--')
        dur_badge = QLabel(dur_str)
        dur_badge.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.10);
            color: #EDEDED;
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 5px;
            padding: 3px 6px;
            font-size: 10px;
            font-weight: 700;
            font-family: 'Consolas', monospace;
        """)
        dur_badge.setAlignment(Qt.AlignCenter)
        dur_badge.setFixedWidth(52)
        layout.addWidget(dur_badge)

        # Title and uploader
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        title = item.get('title', 'Без названия')
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #FFFFFF; background: transparent; border: none;")
        self.title_lbl.setWordWrap(True)
        info_layout.addWidget(self.title_lbl)

        uploader = item.get('uploader', '')
        self.sub_lbl = QLabel(uploader)
        self.sub_lbl.setStyleSheet("font-size: 10px; color: #71717A; background: transparent; border: none;")
        info_layout.addWidget(self.sub_lbl)

        layout.addLayout(info_layout, stretch=1)

    def is_selected(self) -> bool:
        return self.checkbox.isChecked()

    def set_selected(self, val: bool):
        self.checkbox.setChecked(val)


class PlaylistDialog(QDialog):
    def __init__(self, playlist_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Выбор видео из плейлиста")
        self.resize(680, 540)
        self.setMinimumSize(580, 440)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.playlist_data = playlist_data
        self.entries = playlist_data.get('entries', [])
        self.item_widgets: list[PlaylistItemWidget] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("PlaylistContainer")
        container.setStyleSheet("""
            QFrame#PlaylistContainer {
                background-color: #0E1218;
                border-radius: 18px;
                border: 1px solid rgba(255, 255, 255, 0.16);
            }
        """)
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(22, 18, 22, 20)
        c_layout.setSpacing(12)

        # 1. Header
        header = QHBoxLayout()
        header.setSpacing(10)

        header_icon = QLabel()
        header_icon.setPixmap(get_svg_icon("video", color="#FFFFFF", size=18).pixmap(18, 18))
        header.addWidget(header_icon)

        pl_title = playlist_data.get('title', 'Плейлист YouTube')
        if len(pl_title) > 35:
            pl_title = pl_title[:32] + "..."
        title = QLabel(pl_title)
        title.setStyleSheet("font-size: 14px; font-weight: 800; color: #FFFFFF; letter-spacing: 0.8px;")
        header.addWidget(title)

        count_badge = QLabel(f"{len(self.entries)} ВИДЕО")
        count_badge.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 5px;
            padding: 2px 6px;
            font-size: 9px;
            font-weight: 800;
            color: #A1A1AA;
            font-family: 'Consolas', monospace;
        """)
        header.addWidget(count_badge)

        header.addStretch()

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
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn)
        c_layout.addLayout(header)

        # 2. Controls bar: Select all / Deselect all
        controls_bar = QHBoxLayout()
        controls_bar.setSpacing(8)

        btn_select_all = QPushButton("Выбрать все")
        btn_select_all.setCursor(Qt.PointingHandCursor)
        btn_select_all.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 7px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
                color: #EDEDED;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
                color: #FFFFFF;
            }
        """)
        btn_select_all.clicked.connect(self._select_all)
        controls_bar.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("Снять выбор")
        btn_deselect_all.setCursor(Qt.PointingHandCursor)
        btn_deselect_all.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 7px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
                color: #A1A1AA;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
                color: #FFFFFF;
            }
        """)
        btn_deselect_all.clicked.connect(self._deselect_all)
        controls_bar.addWidget(btn_deselect_all)

        controls_bar.addStretch()

        self.selected_count_lbl = QLabel("")
        self.selected_count_lbl.setStyleSheet("font-size: 11px; color: #A1A1AA; font-weight: 600;")
        controls_bar.addWidget(self.selected_count_lbl)

        c_layout.addLayout(controls_bar)

        # 3. Scroll Area for playlist items
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

        list_container = QWidget()
        list_container.setStyleSheet("background: transparent;")
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 6, 0)
        list_layout.setSpacing(6)

        for entry in self.entries:
            w = PlaylistItemWidget(entry)
            w.toggled.connect(self._update_selected_count)
            self.item_widgets.append(w)
            list_layout.addWidget(w)

        list_layout.addStretch()
        self.scroll.setWidget(list_container)
        c_layout.addWidget(self.scroll, stretch=1)

        # 4. Action Button
        self.add_btn = QPushButton("  ДОБАВИТЬ В ОЧЕРЕДЬ")
        self.add_btn.setIcon(get_svg_icon("download", color="#000000", size=16))
        self.add_btn.setIconSize(QSize(16, 16))
        self.add_btn.setMinimumHeight(44)
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #FFFFFF;
                border-radius: 12px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 800;
                letter-spacing: 0.8px;
            }
            QPushButton:hover {
                background-color: #F4F4F5;
            }
            QPushButton:pressed {
                background-color: #D4D4D8;
            }
            QPushButton:disabled {
                background-color: rgba(255, 255, 255, 0.08);
                color: #52525B;
                border: 1px solid rgba(255, 255, 255, 0.05);
            }
        """)
        self.add_btn.clicked.connect(self.accept)
        c_layout.addWidget(self.add_btn)

        layout.addWidget(container)
        self._update_selected_count()

    def _select_all(self):
        for w in self.item_widgets:
            w.set_selected(True)
        self._update_selected_count()

    def _deselect_all(self):
        for w in self.item_widgets:
            w.set_selected(False)
        self._update_selected_count()

    def _update_selected_count(self):
        sel = sum(1 for w in self.item_widgets if w.is_selected())
        tot = len(self.item_widgets)
        self.selected_count_lbl.setText(f"Выбрано: {sel} из {tot}")
        self.add_btn.setText(f"  ДОБАВИТЬ В ОЧЕРЕДЬ ({sel})")
        self.add_btn.setEnabled(sel > 0)

    def get_selected_entries(self) -> list:
        return [w.item for w in self.item_widgets if w.is_selected()]
