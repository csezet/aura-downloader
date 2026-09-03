import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QProgressBar, QComboBox, QFrame, QWidget
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from core.downloader import DownloadWorker
from core.settings import settings
from core.history import history
from assets.icons import get_svg_icon

class BatchDownloadManager(QThread):
    item_started = Signal(str, int, int)
    item_progress = Signal(dict)
    item_finished = Signal(dict, int, int)
    all_completed = Signal(int)

    def __init__(self, urls: list, options: dict, save_dir: str):
        super().__init__()
        self.urls = [u.strip() for u in urls if u.strip().startswith("http")]
        self.options = options
        self.save_dir = save_dir
        self.is_cancelled = False
        self._current_worker = None

    def cancel(self):
        self.is_cancelled = True
        if self._current_worker:
            self._current_worker.cancel()

    def run(self):
        total = len(self.urls)
        completed_count = 0

        for idx, url in enumerate(self.urls):
            if self.is_cancelled:
                break

            self.item_started.emit(url, idx + 1, total)
            worker = DownloadWorker(url, self.options, self.save_dir)
            self._current_worker = worker

            res_holder = {}
            worker.progress_updated.connect(self.item_progress.emit)
            def on_done(res):
                res_holder['data'] = res
            worker.download_completed.connect(on_done)

            worker.run()

            if 'data' in res_holder:
                completed_count += 1
                r = res_holder['data']
                history.add_entry(
                    title=r.get('title'),
                    url=r.get('url'),
                    file_path=r.get('file_path'),
                    format_type=self.options.get('mode', 'MP4'),
                    size_bytes=r.get('file_size', 0),
                    thumbnail=r.get('thumbnail')
                )
                self.item_finished.emit(r, completed_count, total)

        self.all_completed.emit(completed_count)


class BatchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Пакетная загрузка")
        self.setFixedSize(540, 490)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.manager = None

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

        title = QLabel("ПАКЕТНАЯ ЗАГРУЗКА")
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
        desc = QLabel("Вставьте список ссылок (каждая с новой строки):")
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
        self.fmt_combo.addItems(["Лучшее качество (MP4)", "Только аудио (MP3 320k)", "Аудио (FLAC Lossless)", "Аудио (M4A AAC)"])
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
        self.start_btn = QPushButton("  НАЧАТЬ ЗАГРУЗКУ ОЧЕРЕДИ")
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
        text = self.text_edit.toPlainText().strip()
        urls = [line.strip() for line in text.splitlines() if line.strip().startswith("http")]
        if not urls:
            return

        fmt_idx = self.fmt_combo.currentIndex()
        if fmt_idx == 0:
            options = {'mode': 'best'}
        elif fmt_idx == 1:
            options = {'mode': 'audio_only', 'audio_fmt': 'mp3', 'audio_q': '320'}
        elif fmt_idx == 2:
            options = {'mode': 'audio_only', 'audio_fmt': 'flac'}
        else:
            options = {'mode': 'audio_only', 'audio_fmt': 'm4a'}

        self.start_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_lbl.setVisible(True)
        self.status_lbl.setText(f"Подготовка очереди ({len(urls)} ссылок)...")

        save_dir = settings.get("download_dir")
        self.manager = BatchDownloadManager(urls, options, save_dir)
        self.manager.item_started.connect(self._on_item_started)
        self.manager.item_finished.connect(self._on_item_finished)
        self.manager.all_completed.connect(self._on_all_completed)
        self.manager.start()

    def _on_item_started(self, url, cur, total):
        self.status_lbl.setText(f"[{cur}/{total}] Загрузка: {url[:45]}...")
        self.progress_bar.setValue(int(((cur - 1) / total) * 100))

    def _on_item_finished(self, res, cur, total):
        self.progress_bar.setValue(int((cur / total) * 100))
        self.status_lbl.setText(f"[{cur}/{total}] Готово: {res.get('title', '')[:40]}")

    def _on_all_completed(self, count):
        self.progress_bar.setValue(100)
        self.status_lbl.setText(f"✓ Вся очередь завершена! Скачано: {count} файлов.")
        self.start_btn.setText("  ЗАКРЫТЬ")
        self.start_btn.setIcon(get_svg_icon("check", color="#000000", size=16))
        self.start_btn.setEnabled(True)
        self.start_btn.clicked.disconnect()
        self.start_btn.clicked.connect(self.accept)

    def _on_close(self):
        if self.manager and self.manager.isRunning():
            self.manager.cancel()
        self.accept()
