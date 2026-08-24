from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QByteArray
from PySide6.QtGui import QPixmap, QImage, QPainter, QPainterPath
import requests

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


class PreviewCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(115)
        self.setVisible(False)

        self._image_worker = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(14)

        # Thumbnail Label
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(130, 85)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet("""
            background-color: rgba(0, 0, 0, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 6px;
            color: #71717A;
            font-size: 11px;
            font-family: 'Consolas', monospace;
        """)
        self.thumb_label.setText("NO PREVIEW")
        layout.addWidget(self.thumb_label)

        # Info Layout
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 2, 0, 2)
        info_layout.setSpacing(5)

        # Top line: Badges
        badge_layout = QHBoxLayout()
        badge_layout.setSpacing(8)
        
        self.platform_badge = QLabel("YOUTUBE")
        self.platform_badge.setObjectName("PlatformBadge")
        badge_layout.addWidget(self.platform_badge)

        self.duration_badge = QLabel("00:00")
        self.duration_badge.setObjectName("Badge")
        badge_layout.addWidget(self.duration_badge)

        badge_layout.addStretch()
        info_layout.addLayout(badge_layout)

        # Title
        self.title_label = QLabel("Название видео")
        self.title_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #FFFFFF;")
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumHeight(38)
        info_layout.addWidget(self.title_label)

        # Author / Channel
        self.author_label = QLabel("Автор канала")
        self.author_label.setStyleSheet("font-size: 11px; color: #A1A1AA;")
        info_layout.addWidget(self.author_label)

        info_layout.addStretch()
        layout.addLayout(info_layout)

    def set_data(self, data: dict):
        self.title_label.setText(data.get("title", "Без названия"))
        self.author_label.setText(f"👤 {data.get('uploader', 'Неизвестный автор')}")
        self.platform_badge.setText(data.get("platform", "VIDEO").upper())
        self.duration_badge.setText(f"⏱ {data.get('duration_str', '--:--')}")
        
        self.thumb_label.setText("LOADING...")
        thumb_url = data.get("thumbnail")
        if thumb_url:
            self._image_worker = ImageLoaderWorker(thumb_url)
            self._image_worker.image_loaded.connect(self._on_image_loaded)
            self._image_worker.start()
        else:
            self.thumb_label.setText("NO PREVIEW")

        self.setVisible(True)

    def _on_image_loaded(self, pixmap: QPixmap):
        if not pixmap.isNull():
            scaled = pixmap.scaled(130, 85, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            target = QPixmap(130, 85)
            target.fill(Qt.transparent)

            painter = QPainter(target)
            painter.setRenderHint(QPainter.Antialiasing, True)
            path = QPainterPath()
            path.addRoundedRect(0, 0, 130, 85, 6, 6)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, scaled)
            painter.end()

            self.thumb_label.setPixmap(target)
            self.thumb_label.setText("")

    def clear(self):
        self.setVisible(False)
        self.thumb_label.clear()
        self.thumb_label.setText("NO PREVIEW")
