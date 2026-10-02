from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QProgressBar, QComboBox, QFrame, QWidget
)
from PySide6.QtCore import Qt, QSize
from assets.icons import get_svg_icon
from core.queue_items import parse_sources
from ui.worker_dialog import WorkerDialog

class BatchDialog(WorkerDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить в очередь")
        self.setFixedSize(540, 490)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.sources = []
        self.options = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setObjectName("BatchContainer")
        container.setStyleSheet("""
            QFrame#BatchContainer {
                background-color: #0E1218;
                border-radius: 18px;
                border: 1px solid rgba(255, 255, 255, 0.16);
            }
            .SectionHeader {
                font-size: 11px;
                font-weight: 700;
                color: #A1A1AA;
                letter-spacing: 0.5px;
            }
            QComboBox {
                background-color: rgba(0, 0, 0, 0.55);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 6px 12px;
                color: #EDEDED;
                font-size: 12px;
                font-weight: 600;
            }
            QComboBox:hover {
                border: 1px solid rgba(255, 255, 255, 0.25);
                background-color: rgba(255, 255, 255, 0.07);
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background-color: #161A22;
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 8px;
                selection-background-color: rgba(255, 255, 255, 0.14);
                selection-color: #FFFFFF;
                color: #EDEDED;
                padding: 4px;
                outline: none;
            }
            QProgressBar {
                background-color: rgba(255, 255, 255, 0.08);
                border-radius: 4px;
                height: 6px;
                text-align: center;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #FFFFFF;
                border-radius: 4px;
            }
        """)
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(22, 18, 22, 20)
        c_layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        header.setSpacing(10)

        header_icon = QLabel()
        header_icon.setPixmap(get_svg_icon("batch", color="#FFFFFF", size=18).pixmap(18, 18))
        header.addWidget(header_icon)

        title = QLabel("ДОБАВИТЬ В ОЧЕРЕДЬ")
        title.setStyleSheet("font-size: 14px; font-weight: 800; color: #FFFFFF; letter-spacing: 1px;")
        header.addWidget(title)

        badge = QLabel("МУЛЬТИ-ССЫЛКИ")
        badge.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 5px;
            padding: 2px 6px;
            font-size: 9px;
            font-weight: 800;
            color: #A1A1AA;
            font-family: 'Consolas', monospace;
        """)
        header.addWidget(badge)

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
        close_btn.clicked.connect(self._on_close)
        header.addWidget(close_btn)
        c_layout.addLayout(header)

        # Instructions
        desc = QLabel("Ссылки, пути к видео или папкам — по одному на строку.")
        desc.setProperty("class", "SectionHeader")
        c_layout.addWidget(desc)

        # Text edit for multiple URLs
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("https://www.youtube.com/watch?v=...\nhttps://www.tiktok.com/@user/video/...\nhttps://www.instagram.com/reel/...")
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: rgba(0, 0, 0, 0.6);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
                color: #FFFFFF;
                font-family: 'Consolas', 'JetBrains Mono', monospace;
                font-size: 11px;
                padding: 10px;
                selection-background-color: #FFFFFF;
                selection-color: #000000;
            }
            QTextEdit:focus {
                border: 1px solid #FFFFFF;
                background-color: rgba(0, 0, 0, 0.8);
            }
        """)
        c_layout.addWidget(self.text_edit, stretch=1)

        # Format selector row
        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(10)
        lbl_fmt = QLabel("Режим для всех:")
        lbl_fmt.setStyleSheet("font-size: 12px; font-weight: 600; color: #E4E4E7;")
        fmt_row.addWidget(lbl_fmt)

        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(["Текущие настройки", "Лучшее качество", "Аудио MP3", "Аудио FLAC", "Аудио M4A", "Аудио OPUS", "Аудио WAV"])
        fmt_row.addWidget(self.fmt_combo, stretch=1)
        c_layout.addLayout(fmt_row)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        c_layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("font-size: 11px; color: #4ADE80; font-family: 'Consolas', monospace; font-weight: 600;")
        self.status_lbl.setVisible(False)
        c_layout.addWidget(self.status_lbl)

        # Action button
        self.start_btn = QPushButton("  ДОБАВИТЬ В ГЛАВНОЕ ОКНО")
        self.start_btn.setIcon(get_svg_icon("download", color="#000000", size=16))
        self.start_btn.setIconSize(QSize(16, 16))
        self.start_btn.setMinimumHeight(44)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setStyleSheet("""
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
        self.start_btn.clicked.connect(self._start_batch)
        c_layout.addWidget(self.start_btn)

        layout.addWidget(container)

    def _start_batch(self):
        sources, errors = parse_sources(self.text_edit.toPlainText())
        if errors or not sources:
            self.status_lbl.setStyleSheet("font-size: 11px; color: #FCA5A5;")
            self.status_lbl.setWordWrap(True)
            self.status_lbl.setText("\n".join(errors[:3]) if errors else "Добавьте хотя бы один источник.")
            self.status_lbl.setVisible(True)
            return
        index = self.fmt_combo.currentIndex()
        self.options = {} if index == 0 else {"mode": "best"} if index == 1 else {
            "mode": "audio_only", "audio_fmt": ("mp3", "flac", "m4a", "opus", "wav")[index - 2]}
        self.sources = sources
        self.accept()

    def _on_close(self):
        self.reject()
