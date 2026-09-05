import os
import requests
from PySide6.QtWidgets import (
    QDialog, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QCheckBox, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QSize, QThread
from PySide6.QtGui import QColor, QPixmap, QImage, QPainter, QPainterPath
from assets.icons import get_svg_icon, get_svg_pixmap

class ThumbnailLoader(QThread):
    loaded = Signal(QPixmap)

    def __init__(self, url: str, target_size: QSize = QSize(70, 70)):
        super().__init__()
        self.url = url
        self.target_size = target_size

    def run(self):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Referer': 'https://www.instagram.com/'
            }
            resp = requests.get(self.url, headers=headers, timeout=8)
            if resp.status_code == 200:
                image = QImage.fromData(resp.content)
                if not image.isNull():
                    pix = QPixmap.fromImage(image).scaled(
                        self.target_size,
                        Qt.KeepAspectRatioByExpanding,
                        Qt.SmoothTransformation
                    )
                    if pix.width() > self.target_size.width() or pix.height() > self.target_size.height():
                        x = max(0, (pix.width() - self.target_size.width()) // 2)
                        y = max(0, (pix.height() - self.target_size.height()) // 2)
                        pix = pix.copy(x, y, self.target_size.width(), self.target_size.height())

                    rounded = QPixmap(self.target_size)
                    rounded.fill(Qt.transparent)
                    painter = QPainter(rounded)
                    painter.setRenderHint(QPainter.Antialiasing, True)
                    path = QPainterPath()
                    path.addRoundedRect(0, 0, self.target_size.width(), self.target_size.height(), 9, 9)
                    painter.setClipPath(path)
                    painter.drawPixmap(0, 0, pix)
                    painter.end()
                    self.loaded.emit(rounded)
        except Exception:
            pass


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


class GalleryItemWidget(QFrame):
    toggled = Signal()

    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.item = item
        self._is_selected = True
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("GalleryCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 16, 12)
        layout.setSpacing(14)

        # High-contrast Checkbox with crisp checkmark icon
        self.checkbox = CheckmarkBox(checked=True, parent=self)
        layout.addWidget(self.checkbox)

        # Thumbnail container
        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(70, 70)
        self.thumb_lbl.setAlignment(Qt.AlignCenter)
        self.thumb_lbl.setStyleSheet("""
            background-color: #090C10;
            border: 1.5px solid rgba(255, 255, 255, 0.18);
            border-radius: 10px;
        """)
        self.thumb_lbl.setPixmap(get_svg_pixmap("image", color="#52525B", size=24))
        layout.addWidget(self.thumb_lbl)

        # Asynchronously load thumbnail
        thumb_url = item.get('thumbnail') or item.get('best_image') or item.get('url')
        if thumb_url and thumb_url.startswith('http'):
            self.loader = ThumbnailLoader(thumb_url, QSize(70, 70))
            self.loader.loaded.connect(self._on_thumb_loaded)
            self.loader.start()

        # Information column
        info_layout = QVBoxLayout()
        info_layout.setSpacing(5)

        # Top tag row: Badge + Format
        tags_layout = QHBoxLayout()
        tags_layout.setSpacing(8)

        is_video = item.get('is_video', False)
        self.type_badge = QLabel(f"ВИДЕО #{item.get('index', 1)}" if is_video else f"ФОТО #{item.get('index', 1)}")
        tags_layout.addWidget(self.type_badge)

        self.format_badge = QLabel("MP4 VIDEO" if is_video else "JPG ORIGINAL (HD)")
        tags_layout.addWidget(self.format_badge)
        tags_layout.addStretch()
        info_layout.addLayout(tags_layout)

        # Title
        title = item.get('title') or f"Instagram Media #{item.get('index', 1)}"
        self.title_lbl = QLabel(title)
        self.title_lbl.setWordWrap(True)
        info_layout.addWidget(self.title_lbl)

        # Uploader
        uploader = item.get('uploader') or 'Instagram'
        self.sub_lbl = QLabel(f"Автор: @{uploader}")
        info_layout.addWidget(self.sub_lbl)

        layout.addLayout(info_layout, stretch=1)
        self._update_appearance()

    def _on_thumb_loaded(self, pix: QPixmap):
        self.thumb_lbl.setPixmap(pix)

    def _update_appearance(self):
        if self._is_selected:
            self.setStyleSheet("""
                QFrame#GalleryCard {
                    background-color: rgba(30, 38, 52, 0.90);
                    border: 1.5px solid rgba(255, 255, 255, 0.40);
                    border-radius: 12px;
                }
                QFrame#GalleryCard:hover {
                    background-color: rgba(36, 46, 64, 0.98);
                    border: 1.5px solid #FFFFFF;
                }
            """)
            self.type_badge.setStyleSheet("""
                background-color: #FFFFFF;
                color: #000000;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 900;
                font-family: 'Consolas', monospace;
                letter-spacing: 0.5px;
            """)
            self.format_badge.setStyleSheet("""
                background-color: rgba(255, 255, 255, 0.10);
                color: #E4E4E7;
                border: 1px solid rgba(255, 255, 255, 0.22);
                border-radius: 4px;
                padding: 2px 7px;
                font-size: 10px;
                font-weight: 700;
                font-family: 'Consolas', monospace;
            """)
            self.title_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #FFFFFF; background: transparent; border: none;")
            self.sub_lbl.setStyleSheet("font-size: 10px; color: #A1A1AA; background: transparent; border: none;")
        else:
            self.setStyleSheet("""
                QFrame#GalleryCard {
                    background-color: rgba(18, 22, 30, 0.50);
                    border: 1px solid rgba(255, 255, 255, 0.14);
                    border-radius: 12px;
                }
                QFrame#GalleryCard:hover {
                    background-color: rgba(26, 32, 44, 0.75);
                    border: 1px solid rgba(255, 255, 255, 0.28);
                }
            """)
            self.type_badge.setStyleSheet("""
                background-color: rgba(255, 255, 255, 0.08);
                color: #A1A1AA;
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 800;
                font-family: 'Consolas', monospace;
                letter-spacing: 0.5px;
            """)
            self.format_badge.setStyleSheet("""
                background-color: rgba(255, 255, 255, 0.04);
                color: #71717A;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 4px;
                padding: 2px 7px;
                font-size: 10px;
                font-weight: 600;
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


class InstagramGalleryDialog(QDialog):
    def __init__(self, gallery_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Галерея Instagram — Выбор фото")
        self.resize(680, 560)
        self.setMinimumSize(580, 460)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.gallery_data = gallery_data
        self.items = gallery_data.get('items', [])
        self.item_widgets = []
        self._drag_pos = None

        self._init_ui()

    def _init_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(12, 12, 12, 12)

        # Fluent Glass Card Container
        container = QFrame()
        container.setObjectName("GalleryContainer")
        container.setStyleSheet("""
            QFrame#GalleryContainer {
                background-color: #0E1218;
                border-radius: 18px;
                border: 1px solid rgba(255, 255, 255, 0.16);
            }
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setColor(QColor(0, 0, 0, 220))
        shadow.setOffset(0, 10)
        container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(22, 20, 22, 20)
        container_layout.setSpacing(16)

        # 1. Header with Camera Icon, Title, and Close Button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_svg_pixmap("camera", color="#FFFFFF", size=22))
        icon_lbl.setFixedSize(36, 36)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.14);
            border-radius: 10px;
        """)
        header_layout.addWidget(icon_lbl)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        title_lbl = QLabel("ГАЛЕРЕЯ INSTAGRAM")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #FFFFFF; letter-spacing: 1px;")
        title_vbox.addWidget(title_lbl)

        author = self.gallery_data.get('uploader') or 'Instagram'
        subtitle_lbl = QLabel(f"Пост от @{author} • Найдено {len(self.items)} фото/видео")
        subtitle_lbl.setStyleSheet("font-size: 11px; color: #71717A; font-weight: 500;")
        title_vbox.addWidget(subtitle_lbl)

        header_layout.addLayout(title_vbox, stretch=1)

        # Close button
        close_btn = QPushButton()
        close_btn.setIcon(get_svg_icon("x", color="#A1A1AA", size=14))
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 14px;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.20);
                border: 1px solid rgba(239, 68, 68, 0.40);
            }
        """)
        close_btn.clicked.connect(self.reject)
        header_layout.addWidget(close_btn)

        container_layout.addLayout(header_layout)

        # 2. Control bar: Selection Buttons + Counter
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(8)

        select_all_btn = QPushButton("ВЫБРАТЬ ВСЕ")
        select_all_btn.setCursor(Qt.PointingHandCursor)
        select_all_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.20);
                color: #FFFFFF;
                font-size: 10px;
                font-weight: 800;
                border-radius: 6px;
                padding: 6px 12px;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.16);
                border: 1px solid rgba(255, 255, 255, 0.40);
                color: #FFFFFF;
            }
        """)
        select_all_btn.clicked.connect(lambda: self._set_all_selected(True))
        ctrl_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("СНЯТЬ ВЫБОР")
        deselect_all_btn.setCursor(Qt.PointingHandCursor)
        deselect_all_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.14);
                color: #A1A1AA;
                font-size: 10px;
                font-weight: 700;
                border-radius: 6px;
                padding: 6px 12px;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(255, 255, 255, 0.30);
                color: #FFFFFF;
            }
        """)
        deselect_all_btn.clicked.connect(lambda: self._set_all_selected(False))
        ctrl_layout.addWidget(deselect_all_btn)

        ctrl_layout.addStretch()

        self.count_lbl = QLabel(f"Выбрано: {len(self.items)} из {len(self.items)}")
        self.count_lbl.setStyleSheet("color: #D4D4D8; font-size: 11px; font-weight: 700;")
        ctrl_layout.addWidget(self.count_lbl)

        container_layout.addLayout(ctrl_layout)

        # 3. Scrollable List of Items
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.18);
                min-height: 20px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.35);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        list_container = QWidget()
        list_container.setStyleSheet("background: transparent;")
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 4, 0)
        list_layout.setSpacing(8)

        for item in self.items:
            widget = GalleryItemWidget(item, self)
            widget.toggled.connect(self._update_counter)
            self.item_widgets.append(widget)
            list_layout.addWidget(widget)

        list_layout.addStretch()
        scroll.setWidget(list_container)
        container_layout.addWidget(scroll, stretch=1)

        # 4. Bottom Action Button
        self.action_btn = QPushButton(f"СКАЧАТЬ ВЫБРАННЫЕ ({len(self.items)})")
        self.action_btn.setIcon(get_svg_icon("download", color="#000000", size=15))
        self.action_btn.setIconSize(QSize(15, 15))
        self.action_btn.setCursor(Qt.PointingHandCursor)
        self.action_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #000000;
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 0.5px;
                border: none;
                border-radius: 10px;
                padding: 12px 16px;
            }
            QPushButton:hover {
                background-color: #E4E4E7;
            }
            QPushButton:pressed {
                background-color: #D4D4D8;
            }
            QPushButton:disabled {
                background-color: rgba(255, 255, 255, 0.15);
                color: rgba(255, 255, 255, 0.40);
            }
        """)
        self.action_btn.clicked.connect(self.accept)
        container_layout.addWidget(self.action_btn)

        outer_layout.addWidget(container)

    def _set_all_selected(self, val: bool):
        for w in self.item_widgets:
            w.set_selected(val)
        self._update_counter()

    def _update_counter(self):
        selected_count = sum(1 for w in self.item_widgets if w.is_selected())
        total = len(self.item_widgets)
        self.count_lbl.setText(f"Выбрано: {selected_count} из {total}")
        self.action_btn.setText(f"СКАЧАТЬ ВЫБРАННЫЕ ({selected_count})")
        self.action_btn.setEnabled(selected_count > 0)

    def get_selected_items(self) -> list:
        return [w.item for w in self.item_widgets if w.is_selected()]

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < 60:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def showEvent(self, event):
        super().showEvent(event)
        if self.parent():
            parent_geo = self.parent().geometry()
            x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - self.height()) // 2
            self.move(max(0, x), max(0, y))
        self.raise_()
        self.activateWindow()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
