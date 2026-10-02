import os
import uuid
import copy
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QSizePolicy, QApplication, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QSize, QByteArray
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath
import requests
from assets.icons import get_svg_icon
from core.workers import CancellableThread, start_worker, cancel_worker

class ImageLoaderWorker(CancellableThread):
    image_loaded = Signal(QPixmap)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                'Referer': 'https://www.instagram.com/'
            }
            resp = requests.get(self.url, headers=headers, timeout=8)
            if resp.status_code == 200 and not self.isInterruptionRequested():
                image = QImage()
                image.loadFromData(QByteArray(resp.content))
                pixmap = QPixmap.fromImage(image)
                if not self.isInterruptionRequested():
                    self.image_loaded.emit(pixmap)
        except Exception:
            pass


class VideoCardWidget(QFrame):
    removed = Signal(str)  # item_id
    card_clicked = Signal(str, object)  # item_id, mouse_event
    thumb_loaded = Signal(str, QPixmap)  # item_id, pixmap
    selection_toggled = Signal(str, bool)

    def __init__(self, data: dict, item_id: str, parent=None):
        super().__init__(parent)
        self.data = copy.deepcopy(data)
        self.item_id = item_id
        self.item_options = copy.deepcopy(data.get('options', {}))
        self.result_path = None
        self._raw_pixmap = None
        self._image_worker = None
        self._is_selected = False

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(118)
        self.setCursor(Qt.PointingHandCursor)
        self._update_style(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)
        self.select_check = QCheckBox()
        self.select_check.setToolTip("Включить в обработку")
        self.select_check.toggled.connect(lambda checked: self.selection_toggled.emit(self.item_id, checked))
        layout.addWidget(self.select_check)

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
        self.thumb_label.setText("Без превью")
        layout.addWidget(self.thumb_label)

        # Info Layout
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)

        # Top line: Badges
        badge_layout = QHBoxLayout()
        badge_layout.setSpacing(6)

        platform_str = data.get("platform", "LOCAL VIDEO" if data.get("is_local") else "VIDEO").upper()
        self.platform_badge = QLabel(f" {platform_str} ")
        self.platform_badge.setObjectName("PlatformBadge")
        self.platform_badge.setStyleSheet("""
            QLabel#PlatformBadge {
                background-color: #FFFFFF;
                color: #000000;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 900;
                font-family: 'Consolas', monospace;
                letter-spacing: 0.5px;
            }
        """)
        badge_layout.addWidget(self.platform_badge)

        dur_str = data.get("duration_str", "--:--")
        dur_icon = "📸" if data.get("is_photo") else "⏱"
        self.duration_badge = QLabel(f"{dur_icon} {dur_str}")
        self.duration_badge.setObjectName("Badge")
        self.duration_badge.setStyleSheet("""
            QLabel#Badge {
                background-color: rgba(255, 255, 255, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.20);
                border-radius: 4px;
                color: #EDEDED;
                padding: 2px 6px;
                font-size: 10px;
                font-family: 'Consolas', monospace;
                font-weight: 700;
            }
        """)
        badge_layout.addWidget(self.duration_badge)
        self.state_badge = QLabel("В очереди")
        self.state_badge.setStyleSheet("font-size: 10px; color: #A1A1AA;")
        badge_layout.addWidget(self.state_badge)

        badge_layout.addStretch()
        info_layout.addLayout(badge_layout)

        # Title
        self.title_label = QLabel(data.get("title", "Без названия"))
        self.title_label.setStyleSheet("font-size: 12px; font-weight: 700; color: #FFFFFF;")
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumHeight(34)
        info_layout.addWidget(self.title_label)

        # Author / Stats
        if data.get('uploader'):
            uploader = data.get('uploader')
        elif data.get('width') and data.get('height'):
            fps_part = f", {int(data.get('fps'))} FPS" if data.get('fps') else ""
            source_label = "Локальное видео" if data.get('is_local') else "Видео"
            uploader = f"{source_label} ({data.get('width')}×{data.get('height')}{fps_part})"
        else:
            uploader = "Фото" if data.get('is_photo') else "Локальное видео" if data.get('is_local') else "Ссылка на видео"
        self.author_label = QLabel(f"{uploader}")
        self.author_label.setToolTip(data.get('url') or '')
        self.author_label.setStyleSheet("font-size: 10px; color: #A1A1AA;")
        info_layout.addWidget(self.author_label)
        self.options_label = QLabel()
        self.options_label.setStyleSheet("font-size: 10px; color: #93C5FD;")
        self.options_label.setWordWrap(True)
        info_layout.addWidget(self.options_label)
        self._update_options_label()

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
        self.open_btn = QPushButton("▶")
        self.open_btn.setFixedSize(26, 26)
        self.open_btn.setToolTip("Открыть готовый файл")
        self.open_btn.setVisible(False)
        self.open_btn.clicked.connect(self._open_result)
        right_layout.addWidget(self.open_btn)
        right_layout.addStretch()

        layout.addLayout(right_layout)

        # Load Thumbnail
        self._load_thumb(data.get("thumbnail"))

    def set_options(self, opts: dict):
        self.item_options = copy.deepcopy(opts or {})
        self.data['options'] = copy.deepcopy(self.item_options)
        self._update_options_label()

    def get_options(self) -> dict:
        return copy.deepcopy(self.item_options)

    def _update_options_label(self):
        opts = self.item_options
        labels = {'best': 'Лучшее качество', 'custom': 'Видео', 'video_only': 'Без звука',
                  'audio_only': 'Аудио', 'gif': 'GIF', 'discord_8mb': 'Discord < 8 МБ'}
        if self.data.get('is_photo'):
            text = "Фото · оригинал"
        else:
            parts = [labels.get(opts.get('mode', 'best'), 'Видео')]
            if opts.get('mode') == 'audio_only':
                parts.append(opts.get('audio_fmt', 'mp3').upper())
            elif opts.get('mode') in ('custom', 'video_only') and opts.get('res'):
                parts.append(opts['res'])
            if opts.get('trim_enabled'):
                parts.append(f"{opts.get('trim_start') or '0'}–{opts.get('trim_end') or 'конец'}")
            if opts.get('crop_enabled'):
                parts.append("кадрирование")
            if opts.get('smooth_enabled') and opts.get('mode') not in ('audio_only', 'gif'):
                fps = opts.get('smooth_fps', 60)
                parts.append('2x FPS' if fps == 0 else f'{fps} FPS')
            text = " · ".join(parts)
        self.options_label.setText(text)
        self.options_label.setToolTip(text)

    def set_state(self, state, percent=None, error=None, result=None, **extra):
        labels = {'waiting': 'В очереди', 'downloading': 'Загрузка', 'processing': 'Обработка',
                  'completed': 'Готово', 'error': 'Ошибка', 'cancelled': 'Остановлено'}
        text = labels.get(state, state)
        if percent is not None and state in ('downloading', 'processing'):
            text += f" {percent:.0f}%"
        color = '#4ADE80' if state == 'completed' else '#FCA5A5' if state == 'error' else '#93C5FD'
        self.state_badge.setText(text)
        self.state_badge.setStyleSheet(f"font-size: 10px; color: {color};")
        self.state_badge.setToolTip(error or '')
        if result:
            self.result_path = result.get('file_path')
            self.open_btn.setVisible(bool(self.result_path))
            self.open_btn.setToolTip(f"Открыть файл:\n{self.result_path}")

    def _open_result(self):
        if self.result_path and os.path.isfile(self.result_path):
            os.startfile(self.result_path)

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
        self.select_check.blockSignals(True)
        self.select_check.setChecked(selected)
        self.select_check.blockSignals(False)
        self._update_style(selected)

    def is_selected(self) -> bool:
        return self._is_selected

    def _load_thumb(self, thumb_val):
        if not thumb_val:
            self.thumb_label.setText("Без превью")
            return

        if isinstance(thumb_val, str) and os.path.exists(thumb_val):
            pix = QPixmap(thumb_val)
            self._on_image_loaded(pix)
        elif isinstance(thumb_val, str) and thumb_val.startswith("http"):
            self.thumb_label.setText("Загрузка...")
            if self._image_worker and self._image_worker.isRunning():
                cancel_worker(self._image_worker)
                try:
                    self._image_worker.image_loaded.disconnect()
                except Exception:
                    pass
            self._image_worker = ImageLoaderWorker(thumb_val)
            self._image_worker.image_loaded.connect(self._on_image_loaded)
            start_worker(self._image_worker, self)
        else:
            self.thumb_label.setText("Без превью")

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
            self.thumb_loaded.emit(self.item_id, pixmap)

    def get_pixmap(self) -> QPixmap:
        return self._raw_pixmap if self._raw_pixmap else QPixmap()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.card_clicked.emit(self.item_id, event)
        super().mousePressEvent(event)


class VideoCardsListWidget(QWidget):
    active_video_changed = Signal(dict, object)
    active_thumbnail_updated = Signal(object)
    list_changed = Signal(int)  # count

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards: list[VideoCardWidget] = []
        self.active_id: str = None
        self.last_clicked_id: str = None
        self.busy = False

        self.setStyleSheet("background: transparent; border: none;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scroll Area without visible scrollbars (scrolls purely via mouse wheel)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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
        self.scroll_layout.setAlignment(Qt.AlignTop)
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
            self.setMinimumHeight(120)
            self.setMaximumHeight(120)
        else:
            self.setVisible(True)
            self.setMinimumHeight(120)
            self.setMaximumHeight(16777215)  # Dynamically fills entire fullscreen height!

    def add_video(self, info: dict, select=True) -> str:
        item_id = info.get('item_id') or uuid.uuid4().hex
        card = VideoCardWidget(info, item_id, self.scroll_content)
        card.removed.connect(self.remove_card)
        card.card_clicked.connect(self._on_card_clicked)
        card.thumb_loaded.connect(self._on_card_thumb_loaded)
        card.selection_toggled.connect(self._on_card_check)
        card.close_btn.setEnabled(not self.busy)

        self.cards.append(card)
        self.scroll_layout.addWidget(card)

        # Select newly added card
        if select:
            card.set_selected(True)
            self._set_active_only(item_id)
        self.last_clicked_id = item_id

        self._update_container_height()
        self.list_changed.emit(len(self.cards))
        return item_id

    def _on_card_check(self, item_id, selected):
        card = self._get_card(item_id)
        if card:
            card.set_selected(selected)
            if selected:
                self._set_active_only(item_id)
            self.list_changed.emit(len(self.cards))

    def select_all(self, selected=True):
        for card in self.cards:
            card.set_selected(selected)
        self.list_changed.emit(len(self.cards))

    def set_busy(self, busy):
        self.busy = busy
        for card in self.cards:
            card.close_btn.setEnabled(not busy)

    def update_item_state(self, data):
        card = self._get_card(data.get('item_id'))
        if card:
            card.set_state(**{key: value for key, value in data.items() if key != 'item_id'})
            if data.get('state') == 'completed':
                card.set_selected(False)
                self.list_changed.emit(len(self.cards))

    def update_card_info(self, item_id, info):
        card = self._get_card(item_id)
        if card:
            card.data.update(copy.deepcopy(info))
            card.title_label.setText(card.data.get('title', 'Без названия'))
            card.duration_badge.setText(card.data.get('duration_str', '--:--'))
            card.author_label.setText(card.data.get('uploader') or '')
            card._load_thumb(card.data.get('thumbnail'))
            if item_id == self.active_id:
                self._set_active_only(item_id)

    def _on_card_thumb_loaded(self, item_id: str, pixmap: QPixmap):
        if item_id == self.active_id and pixmap and not pixmap.isNull():
            self.active_thumbnail_updated.emit(pixmap)

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
            # Attach live options before emitting
            payload = dict(card.data)
            payload['options'] = card.get_options()
            payload['item_id'] = item_id
            self.active_video_changed.emit(payload, card.get_pixmap())

    def save_card_options(self, item_id: str, opts: dict):
        card = self._get_card(item_id)
        if card and opts:
            card.set_options(opts)

    def save_active_options(self, opts: dict):
        card = self.get_active_card()
        if card and opts:
            card.set_options(opts)

    def get_active_options(self) -> dict:
        card = self.get_active_card()
        return card.get_options() if card else {}

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
        if self.busy:
            return
        idx = -1
        for i, c in enumerate(self.cards):
            if c.item_id == item_id:
                idx = i
                break

        if idx >= 0:
            c = self.cards.pop(idx)
            if c._image_worker:
                cancel_worker(c._image_worker)
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
        if self.busy:
            return
        for c in self.cards:
            if c._image_worker:
                cancel_worker(c._image_worker)
            c.deleteLater()
        self.cards.clear()
        self.active_id = None
        self.last_clicked_id = None
        self._update_container_height()
        self.list_changed.emit(0)

    def get_all_videos(self) -> list[dict]:
        return [copy.deepcopy({**c.data, 'options': c.get_options(), 'item_id': c.item_id}) for c in self.cards]

    def get_selected_videos(self) -> list[dict]:
        return [copy.deepcopy({**c.data, 'options': c.get_options(), 'item_id': c.item_id}) for c in self.cards if c.is_selected()]

    def get_active_card(self) -> VideoCardWidget:
        for c in self.cards:
            if c.item_id == self.active_id:
                return c
        return self.cards[0] if self.cards else None

    def count(self) -> int:
        return len(self.cards)
