import os
import uuid
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QSizePolicy, QApplication
)
from PySide6.QtCore import Qt, Signal, QSize, QThread, QByteArray
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath
import requests
from assets.icons import get_svg_icon

class ImageLoaderWorker(QThread):
    image_loaded = Signal(QPixmap)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            resp = requests.get(self.url, timeout=6)
            if resp.status_code == 200:
                image = QImage()
                image.loadFromData(QByteArray(resp.content))
                pixmap = QPixmap.fromImage(image)
                self.image_loaded.emit(pixmap)
        except Exception:
            pass


class VideoCardWidget(QFrame):
    removed = Signal(str)  # item_id
    card_clicked = Signal(str, object)  # item_id, mouse_event

    def __init__(self, data: dict, item_id: str, parent=None):
        super().__init__(parent)
        self.data = data
        self.item_id = item_id
        self._raw_pixmap = None
        self._image_worker = None
        self._is_selected = False

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(100)
        self.setCursor(Qt.PointingHandCursor)
        self._update_style(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)

        # Thumbnail (115x72)
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(115, 72)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 6px;
            color: #71717A;
            font-size: 10px;
            font-family: 'Consolas', monospace;
        """)
        self.thumb_label.setText("NO PREVIEW")
        layout.addWidget(self.thumb_label)

        # Info Layout
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)

        # Top line: Badges
        badge_layout = QHBoxLayout()
        badge_layout.setSpacing(6)

        platform_str = data.get("platform", "LOCAL VIDEO" if data.get("is_local") else "VIDEO").upper()
        self.platform_badge = QLabel(platform_str)
        self.platform_badge.setObjectName("PlatformBadge")
        badge_layout.addWidget(self.platform_badge)

        dur_str = data.get("duration_str", "--:--")
        self.duration_badge = QLabel(f"⏱ {dur_str}")
        self.duration_badge.setObjectName("Badge")
        badge_layout.addWidget(self.duration_badge)

        badge_layout.addStretch()
        info_layout.addLayout(badge_layout)

        # Title
        self.title_label = QLabel(data.get("title", "Без названия"))
        self.title_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #FFFFFF;")
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumHeight(34)
        info_layout.addWidget(self.title_label)

        # Author / Stats
        uploader = data.get('uploader') or f"Локальное видео ({data.get('width', 1920)}x{data.get('height', 1080)})"
        self.author_label = QLabel(f"👤 {uploader}")
        self.author_label.setStyleSheet("font-size: 10px; color: #A1A1AA;")
        info_layout.addWidget(self.author_label)

        info_layout.addStretch()
        layout.addLayout(info_layout, stretch=1)

        # Right Action: Close / Remove button
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("TitleButton")
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            QPushButton {
                color: #A1A1AA;
                font-size: 11px;
                font-weight: 800;
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 6px;
            }
            QPushButton:hover {
                color: #FFFFFF;
                background: rgba(239, 68, 68, 0.45);
                border: 1px solid rgba(239, 68, 68, 0.8);
            }
        """)
        self.close_btn.setToolTip("Убрать это видео")
        self.close_btn.clicked.connect(lambda: self.removed.emit(self.item_id))
        right_layout.addWidget(self.close_btn, alignment=Qt.AlignTop | Qt.AlignRight)
        right_layout.addStretch()

        layout.addLayout(right_layout)

        # Load Thumbnail
        self._load_thumb(data.get("thumbnail"))

    def _update_style(self, selected: bool):
        self._is_selected = selected
        if selected:
            self.setStyleSheet("""
                VideoCardWidget {
                    background-color: rgba(255, 255, 255, 0.14);
                    border: 2px solid #FFFFFF;
                    border-radius: 10px;
                }
                VideoCardWidget:hover {
                    background-color: rgba(255, 255, 255, 0.18);
                    border: 2px solid #FFFFFF;
                }
            """)
        else:
            self.setStyleSheet("""
                VideoCardWidget {
                    background-color: rgba(20, 24, 33, 0.65);
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 10px;
                }
                VideoCardWidget:hover {
                    background-color: rgba(30, 36, 48, 0.85);
                    border: 1px solid rgba(255, 255, 255, 0.35);
                }
            """)

    def set_selected(self, selected: bool):
        self._update_style(selected)

    def is_selected(self) -> bool:
        return self._is_selected

    def _load_thumb(self, thumb_val):
        if not thumb_val:
            self.thumb_label.setText("NO PREVIEW")
            return

        if isinstance(thumb_val, str) and os.path.exists(thumb_val):
            pix = QPixmap(thumb_val)
            self._on_image_loaded(pix)
        elif isinstance(thumb_val, str) and thumb_val.startswith("http"):
            self.thumb_label.setText("LOADING...")
            if self._image_worker and self._image_worker.isRunning():
                self._image_worker.terminate()
            self._image_worker = ImageLoaderWorker(thumb_val)
            self._image_worker.image_loaded.connect(self._on_image_loaded)
            self._image_worker.start()
        else:
            self.thumb_label.setText("NO PREVIEW")

    def _on_image_loaded(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            self._raw_pixmap = pixmap
            scaled = pixmap.scaled(115, 72, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            target = QPixmap(115, 72)
            target.fill(Qt.transparent)

            painter = QPainter(target)
            painter.setRenderHint(QPainter.Antialiasing, True)
            path = QPainterPath()
            path.addRoundedRect(0, 0, 115, 72, 6, 6)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, scaled)
            painter.end()

            self.thumb_label.setPixmap(target)
            self.thumb_label.setText("")

    def get_pixmap(self) -> QPixmap:
        return self._raw_pixmap

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.card_clicked.emit(self.item_id, event)
        super().mousePressEvent(event)


class VideoCardsListWidget(QWidget):
    active_video_changed = Signal(dict, QPixmap)
    list_changed = Signal(int)  # count

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards: list[VideoCardWidget] = []
        self.active_id: str = None
        self.last_clicked_id: str = None

        self.setStyleSheet("background: transparent; border: none;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scroll Area without visible scrollbars (scrolls purely via mouse wheel)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
        """)
        self.scroll.viewport().setStyleSheet("background: transparent; border: none;")

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent; border: none;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(8)
        self.scroll.setWidget(self.scroll_content)

        main_layout.addWidget(self.scroll)
        self._update_container_height()

    def _update_container_height(self):
        c = len(self.cards)
        if c == 0:
            self.setVisible(False)
            self.setFixedHeight(0)
        elif c == 1:
            self.setVisible(True)
            self.setFixedHeight(102)
        elif c == 2:
            self.setVisible(True)
            self.setFixedHeight(212)
        else:
            self.setVisible(True)
            self.setFixedHeight(212)

    def add_video(self, info: dict) -> str:
        item_id = uuid.uuid4().hex
        card = VideoCardWidget(info, item_id, self.scroll_content)
        card.removed.connect(self.remove_card)
        card.card_clicked.connect(self._on_card_clicked)

        self.cards.append(card)
        self.scroll_layout.addWidget(card)

        # Select newly added card
        self._select_single(item_id)
        self.last_clicked_id = item_id

        self._update_container_height()
        self.list_changed.emit(len(self.cards))
        return item_id

    def _on_card_clicked(self, item_id: str, event):
        modifiers = event.modifiers() if event else Qt.NoModifier

        if modifiers & Qt.ShiftModifier and self.last_clicked_id:
            # Shift + Click: Select range
            idx1 = self._get_card_index(self.last_clicked_id)
            idx2 = self._get_card_index(item_id)
            if idx1 >= 0 and idx2 >= 0:
                start, end = min(idx1, idx2), max(idx1, idx2)
                for i, c in enumerate(self.cards):
                    c.set_selected(start <= i <= end)
            self._set_active_only(item_id)
        elif modifiers & Qt.ControlModifier:
            # Ctrl + Click: Toggle individual selection
            target = self._get_card(item_id)
            if target:
                target.set_selected(not target.is_selected())
                if target.is_selected():
                    self._set_active_only(item_id)
            self.last_clicked_id = item_id
        else:
            # Normal Click: Select only this video
            self._select_single(item_id)
            self.last_clicked_id = item_id

        self.list_changed.emit(len(self.cards))

    def _select_single(self, item_id: str):
        for c in self.cards:
            c.set_selected(c.item_id == item_id)
        self._set_active_only(item_id)

    def _set_active_only(self, item_id: str):
        self.active_id = item_id
        card = self._get_card(item_id)
        if card:
            self.active_video_changed.emit(card.data, card.get_pixmap())

    def _get_card(self, item_id: str) -> VideoCardWidget:
        for c in self.cards:
            if c.item_id == item_id:
                return c
        return None

    def _get_card_index(self, item_id: str) -> int:
        for i, c in enumerate(self.cards):
            if c.item_id == item_id:
                return i
        return -1

    def remove_card(self, item_id: str):
        idx = -1
        for i, c in enumerate(self.cards):
            if c.item_id == item_id:
                idx = i
                break

        if idx >= 0:
            c = self.cards.pop(idx)
            c.deleteLater()

        self._update_container_height()

        if len(self.cards) == 0:
            self.active_id = None
            self.last_clicked_id = None
            self.list_changed.emit(0)
        else:
            if self.active_id == item_id:
                new_idx = min(idx, len(self.cards) - 1)
                self._select_single(self.cards[new_idx].item_id)
            self.list_changed.emit(len(self.cards))

    def clear_all(self):
        for c in self.cards:
            c.deleteLater()
        self.cards.clear()
        self.active_id = None
        self.last_clicked_id = None
        self._update_container_height()
        self.list_changed.emit(0)

    def get_all_videos(self) -> list[dict]:
        return [c.data for c in self.cards]

    def get_selected_videos(self) -> list[dict]:
        sel = [c.data for c in self.cards if c.is_selected()]
        # If none selected, fallback to active or all
        return sel if sel else ([self.get_active_card().data] if self.get_active_card() else [])

    def get_active_card(self) -> VideoCardWidget:
        for c in self.cards:
            if c.item_id == self.active_id:
                return c
        return self.cards[0] if self.cards else None

    def count(self) -> int:
        return len(self.cards)
