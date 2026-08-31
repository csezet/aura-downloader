import os
from pathlib import Path
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QCheckBox, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath
from assets.icons import get_svg_icon
from core.downloader import format_bytes, format_seconds

class VideoQueueItem(QFrame):
    removed = Signal(str)  # emits file_path/url
    selected_for_preview = Signal(dict) # emits item dict
    toggled_selection = Signal()

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.data = data
        self.setFixedHeight(54)
        self.setCursor(Qt.PointingHandCursor)
        self.set_active(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        # Checkbox
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.stateChanged.connect(lambda: self.toggled_selection.emit())
        layout.addWidget(self.checkbox)

        # Thumbnail (60x36)
        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(60, 36)
        self.thumb_lbl.setAlignment(Qt.AlignCenter)
        self.thumb_lbl.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 4px;
            color: #71717A;
            font-size: 8px;
            font-family: 'Consolas', monospace;
        """)
        self.thumb_lbl.setText("THUMB")
        self._load_thumbnail(data.get("thumbnail"))
        layout.addWidget(self.thumb_lbl)

        # Info
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        self.title_lbl = QLabel(data.get("title", "Без названия"))
        self.title_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #FFFFFF;")
        self.title_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        info_layout.addWidget(self.title_lbl)

        meta_text = f"⏱ {data.get('duration_str', '--:--')} | {data.get('width', 1920)}x{data.get('height', 1080)} | {data.get('file_size_str', '')}"
        self.meta_lbl = QLabel(meta_text)
        self.meta_lbl.setStyleSheet("font-size: 9px; color: #A1A1AA; font-family: 'Consolas', monospace;")
        info_layout.addWidget(self.meta_lbl)

        layout.addLayout(info_layout, stretch=1)

        # Remove Button
        self.remove_btn = QPushButton("✕")
        self.remove_btn.setFixedSize(22, 22)
        self.remove_btn.setCursor(Qt.PointingHandCursor)
        self.remove_btn.setStyleSheet("""
            QPushButton {
                color: #71717A;
                font-size: 10px;
                font-weight: 800;
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 4px;
            }
            QPushButton:hover {
                color: #FFFFFF;
                background: rgba(239, 68, 68, 0.35);
                border: 1px solid rgba(239, 68, 68, 0.6);
            }
        """)
        self.remove_btn.setToolTip("Убрать из списка")
        self.remove_btn.clicked.connect(lambda: self.removed.emit(self.data.get('url', '')))
        layout.addWidget(self.remove_btn)

    def set_active(self, active: bool):
        if active:
            self.setStyleSheet("""
                VideoQueueItem {
                    background-color: rgba(255, 255, 255, 0.14);
                    border: 1.5px solid rgba(255, 255, 255, 0.6);
                    border-radius: 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                VideoQueueItem {
                    background-color: rgba(255, 255, 255, 0.04);
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 8px;
                }
                VideoQueueItem:hover {
                    background-color: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.25);
                }
            """)

    def _load_thumbnail(self, thumb_path: str):
        if thumb_path and os.path.exists(thumb_path):
            pix = QPixmap(thumb_path)
            if not pix.isNull():
                scaled = pix.scaled(60, 36, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                target = QPixmap(60, 36)
                target.fill(Qt.transparent)
                p = QPainter(target)
                p.setRenderHint(QPainter.Antialiasing, True)
                path = QPainterPath()
                path.addRoundedRect(0, 0, 60, 36, 4, 4)
                p.setClipPath(path)
                p.drawPixmap(0, 0, scaled)
                p.end()
                self.thumb_lbl.setPixmap(target)
                self.thumb_lbl.setText("")

    def is_selected(self) -> bool:
        return self.checkbox.isChecked()

    def set_selected(self, checked: bool):
        self.checkbox.setChecked(checked)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.selected_for_preview.emit(self.data)
        super().mousePressEvent(event)


class VideoQueueWidget(QFrame):
    queue_changed = Signal(int)  # emits total count
    active_video_selected = Signal(dict)
    add_more_requested = Signal()
    clear_all_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[dict] = []
        self.item_widgets: list[VideoQueueItem] = []
        self.active_url = None

        self.setProperty("class", "GlassCard")
        self.setVisible(False)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # Header Bar
        header = QHBoxLayout()
        self.count_lbl = QLabel("ОЧЕРЕДЬ: 0 ВИДЕО")
        self.count_lbl.setStyleSheet("font-size: 11px; font-weight: 800; color: #FFFFFF; letter-spacing: 0.5px;")
        header.addWidget(self.count_lbl)

        self.select_all_cb = QCheckBox("Выбрать все")
        self.select_all_cb.setChecked(True)
        self.select_all_cb.setStyleSheet("font-size: 10px; color: #A1A1AA; font-weight: 600;")
        self.select_all_cb.stateChanged.connect(self._on_select_all_toggled)
        header.addWidget(self.select_all_cb)

        header.addStretch()

        self.add_btn = QPushButton(" + ДОБАВИТЬ")
        self.add_btn.setProperty("class", "GlassButton")
        self.add_btn.setStyleSheet("font-size: 10px; font-weight: 700; padding: 2px 8px;")
        self.add_btn.clicked.connect(self.add_more_requested.emit)
        header.addWidget(self.add_btn)

        self.clear_all_btn = QPushButton(" ✕ ОЧИСТИТЬ")
        self.clear_all_btn.setProperty("class", "GlassButton")
        self.clear_all_btn.setStyleSheet("font-size: 10px; font-weight: 700; padding: 2px 8px; color: #EF4444;")
        self.clear_all_btn.clicked.connect(self._on_clear_btn_clicked)
        header.addWidget(self.clear_all_btn)

        main_layout.addLayout(header)

        # Scroll Area for video list
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: rgba(0, 0, 0, 0.2);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.2);
                min-height: 20px;
                border-radius: 3px;
            }
        """)
        self.scroll.setMaximumHeight(160)

        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(4)
        self.scroll.setWidget(self.scroll_content)

        main_layout.addWidget(self.scroll)

    def _on_clear_btn_clicked(self):
        self.clear_all_requested.emit()

    def set_videos(self, info_list: list[dict]):
        self.clear_all()
        for info in info_list:
            if info:
                self.items.append(info)
                item_w = VideoQueueItem(info, self.scroll_content)
                item_w.removed.connect(self.remove_video)
                item_w.selected_for_preview.connect(self._on_item_clicked)
                item_w.toggled_selection.connect(self._update_header)
                self.item_widgets.append(item_w)
                self.scroll_layout.addWidget(item_w)

        if self.items:
            self.set_active_video(self.items[0].get('url'))

        self._update_header()
        self.setVisible(len(self.items) > 1)
        self.queue_changed.emit(len(self.items))

    def _on_item_clicked(self, info: dict):
        self.set_active_video(info.get('url'))
        self.active_video_selected.emit(info)

    def set_active_video(self, url: str):
        self.active_url = url
        for w in self.item_widgets:
            w.set_active(w.data.get('url') == url)

    def add_video(self, info: dict):
        if not info:
            return
        url = info.get('url')
        for it in self.items:
            if it.get('url') == url:
                self.set_active_video(url)
                return

        self.items.append(info)
        item_w = VideoQueueItem(info, self.scroll_content)
        item_w.removed.connect(self.remove_video)
        item_w.selected_for_preview.connect(self._on_item_clicked)
        item_w.toggled_selection.connect(self._update_header)
        
        self.item_widgets.append(item_w)
        self.scroll_layout.addWidget(item_w)

        self.set_active_video(url)
        self._update_header()
        self.setVisible(len(self.items) > 1)
        self.queue_changed.emit(len(self.items))

    def remove_video(self, url: str):
        found_idx = -1
        for i, it in enumerate(self.items):
            if it.get('url') == url:
                found_idx = i
                break

        if found_idx >= 0:
            self.items.pop(found_idx)
            w = self.item_widgets.pop(found_idx)
            w.deleteLater()

        self._update_header()
        if len(self.items) == 0:
            self.setVisible(False)
            self.active_url = None
        else:
            self.setVisible(len(self.items) > 1)
            if self.active_url == url:
                new_idx = min(found_idx, len(self.items) - 1)
                self.set_active_video(self.items[new_idx].get('url'))
                self.active_video_selected.emit(self.items[new_idx])

        self.queue_changed.emit(len(self.items))

    def clear_all(self):
        for w in self.item_widgets:
            w.deleteLater()
        self.items.clear()
        self.item_widgets.clear()
        self.active_url = None
        self.setVisible(False)
        self.queue_changed.emit(0)

    def _on_select_all_toggled(self, state):
        checked = (state == Qt.Checked.value or state == 2 or state is True)
        for w in self.item_widgets:
            w.set_selected(checked)
        self._update_header()

    def _update_header(self):
        total = len(self.items)
        selected = len(self.get_selected_videos())
        self.count_lbl.setText(f"ОЧЕРЕДЬ: {total} ВИДЕО (Выбрано: {selected})")

    def get_selected_videos(self) -> list[dict]:
        return [self.items[i] for i, w in enumerate(self.item_widgets) if w.is_selected()]

    def get_all_videos(self) -> list[dict]:
        return self.items

    def count(self) -> int:
        return len(self.items)
