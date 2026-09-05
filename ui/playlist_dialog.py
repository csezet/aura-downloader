import os
from PySide6.QtWidgets import (
    QDialog, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor
from assets.icons import get_svg_icon, get_svg_pixmap

class CheckmarkBox(QFrame):
    def __init__(self, checked=True, parent=None):
        super().__init__(parent)
        self.setObjectName("CheckmarkBox")
        self.setFixedSize(22, 22)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._checked = checked

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        self.icon_lbl = QLabel(self)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.icon_lbl.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.icon_lbl)

        self._update_appearance()

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, val: bool):
        if self._checked != val:
            self._checked = val
            self._update_appearance()

    def _update_appearance(self):
        if self._checked:
            self.icon_lbl.setPixmap(get_svg_pixmap("check", color="#000000", size=13))
            self.setStyleSheet("""
                QFrame#CheckmarkBox {
                    background-color: #FFFFFF;
                    border: 1px solid #FFFFFF;
                    border-radius: 6px;
                }
            """)
        else:
            self.icon_lbl.clear()
            self.setStyleSheet("""
                QFrame#CheckmarkBox {
                    background-color: rgba(0, 0, 0, 0.45);
                    border: 1.5px solid rgba(255, 255, 255, 0.40);
                    border-radius: 6px;
                }
            """)


class PlaylistItemWidget(QFrame):
    toggled = Signal()

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.item = item
        self._is_selected = True
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("PlaylistItemCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        self.checkbox = CheckmarkBox(checked=True, parent=self)
        layout.addWidget(self.checkbox)

        # Duration badge
        dur_str = item.get('duration_str', '--:--')
        self.dur_badge = QLabel(dur_str)
        self.dur_badge.setAlignment(Qt.AlignCenter)
        self.dur_badge.setFixedWidth(54)
        layout.addWidget(self.dur_badge)

        # Title and uploader
        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)

        title = item.get('title', 'Без названия')
        self.title_lbl = QLabel(title)
        self.title_lbl.setWordWrap(True)
        info_layout.addWidget(self.title_lbl)

        uploader = item.get('uploader', '')
        self.sub_lbl = QLabel(uploader)
        info_layout.addWidget(self.sub_lbl)

        layout.addLayout(info_layout, stretch=1)
        self._update_appearance()

    def _update_appearance(self):
        if self._is_selected:
            self.setStyleSheet("""
                QFrame#PlaylistItemCard {
                    background-color: rgba(30, 38, 52, 0.90);
                    border: 1.5px solid rgba(255, 255, 255, 0.40);
                    border-radius: 10px;
                }
                QFrame#PlaylistItemCard:hover {
                    background-color: rgba(36, 46, 64, 0.98);
                    border: 1.5px solid #FFFFFF;
                }
            """)
            self.dur_badge.setStyleSheet("""
                background-color: #FFFFFF;
                color: #000000;
                border-radius: 5px;
                padding: 3px 6px;
                font-size: 10px;
                font-weight: 900;
                font-family: 'Consolas', monospace;
            """)
            self.title_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #FFFFFF; background: transparent; border: none;")
            self.sub_lbl.setStyleSheet("font-size: 10px; color: #A1A1AA; background: transparent; border: none;")
        else:
            self.setStyleSheet("""
                QFrame#PlaylistItemCard {
                    background-color: rgba(18, 22, 30, 0.50);
                    border: 1px solid rgba(255, 255, 255, 0.14);
                    border-radius: 10px;
                }
                QFrame#PlaylistItemCard:hover {
                    background-color: rgba(26, 32, 44, 0.75);
                    border: 1px solid rgba(255, 255, 255, 0.28);
                }
            """)
            self.dur_badge.setStyleSheet("""
                background-color: rgba(255, 255, 255, 0.08);
                color: #A1A1AA;
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 5px;
                padding: 3px 6px;
                font-size: 10px;
                font-weight: 800;
                font-family: 'Consolas', monospace;
            """)
            self.title_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #A1A1AA; background: transparent; border: none;")
            self.sub_lbl.setStyleSheet("font-size: 10px; color: #71717A; background: transparent; border: none;")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.set_selected(not self._is_selected)
            self.toggled.emit()
        super().mousePressEvent(event)

    def is_selected(self) -> bool:
        return self._is_selected

    def set_selected(self, val: bool):
        self._is_selected = val
        self.checkbox.setChecked(val)
        self._update_appearance()


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

        btn_select_all = QPushButton("ВЫБРАТЬ ВСЕ")
        btn_select_all.setCursor(Qt.PointingHandCursor)
        btn_select_all.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.20);
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 10px;
                font-weight: 800;
                color: #FFFFFF;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.16);
                border: 1px solid rgba(255, 255, 255, 0.40);
                color: #FFFFFF;
            }
        """)
        btn_select_all.clicked.connect(self._select_all)
        controls_bar.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("СНЯТЬ ВЫБОР")
        btn_deselect_all.setCursor(Qt.PointingHandCursor)
        btn_deselect_all.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 10px;
                font-weight: 700;
                color: #A1A1AA;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(255, 255, 255, 0.30);
                color: #FFFFFF;
            }
        """)
        btn_deselect_all.clicked.connect(self._deselect_all)
        controls_bar.addWidget(btn_deselect_all)

        controls_bar.addStretch()

        self.selected_count_lbl = QLabel("")
        self.selected_count_lbl.setStyleSheet("font-size: 11px; color: #D4D4D8; font-weight: 700;")
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
