import os
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QSpacerItem, QSizePolicy
from PySide6.QtCore import Qt, QPoint, QSize, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

class CustomTitleBar(QWidget):
    def __init__(self, parent=None, title="A U R A   D O W N L O A D E R", icon_path=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setObjectName("TitleBar")
        self.setFixedHeight(46)

        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 4, 10, 4)
        layout.setSpacing(10)

        # High Quality Crisp SVG / Pixmap Logo
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(26, 26)
        
        svg_path = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.svg")
        if os.path.exists(svg_path):
            renderer = QSvgRenderer(svg_path)
            pixmap = QPixmap(52, 52)  # 2x High-DPI
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            renderer.render(painter)
            painter.end()
            self.icon_label.setPixmap(pixmap.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        elif icon_path and os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(52, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.icon_label.setPixmap(pixmap.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        layout.addWidget(self.icon_label)

        # App Title (Clean, NO //)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("AppTitle")
        layout.addWidget(self.title_label)

        layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

        # Window Controls
        self.min_btn = QPushButton("—")
        self.min_btn.setObjectName("TitleButton")
        self.min_btn.setToolTip("Свернуть")
        self.min_btn.clicked.connect(self._minimize)

        self.max_btn = QPushButton("□")
        self.max_btn.setObjectName("TitleButton")
        self.max_btn.setToolTip("Развернуть")
        self.max_btn.clicked.connect(self._maximize_restore)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("TitleButton")
        self.close_btn.setProperty("id", "CloseButton")
        self.close_btn.setToolTip("Закрыть")
        self.close_btn.clicked.connect(self._close)

        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)

    def _minimize(self):
        if self.parent_window:
            self.parent_window.showMinimized()

    def _maximize_restore(self):
        if self.parent_window:
            if self.parent_window.isMaximized():
                self.parent_window.showNormal()
                self.max_btn.setText("□")
            else:
                self.parent_window.showMaximized()
                self.max_btn.setText("❐")

    def _close(self):
        if self.parent_window:
            self.parent_window.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.parent_window.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            if self.parent_window.isMaximized():
                self.parent_window.showNormal()
                self.max_btn.setText("□")
            self.parent_window.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._maximize_restore()
            event.accept()
