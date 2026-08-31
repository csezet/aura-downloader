import os
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QUrl, Signal, QSize
from PySide6.QtGui import QIcon, QColor, QFont
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from assets.icons import get_svg_icon
from ui.timeline_slider import TimelineRangeSlider, ms_to_time_str
from core.media_converter import get_or_create_preview_proxy

def parse_time_to_ms(time_str: str) -> int:
    if not time_str:
        return 0
    parts = time_str.strip().split(":")
    try:
        if len(parts) == 1:
            return int(float(parts[0]) * 1000)
        elif len(parts) == 2:
            return int((float(parts[0]) * 60 + float(parts[1])) * 1000)
        elif len(parts) == 3:
            return int((float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])) * 1000)
    except Exception:
        return 0
    return 0

def ms_to_fmt(ms: int) -> str:
    total_sec = max(0, int(ms / 1000))
    m, s = divmod(total_sec, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class TrimDialog(QDialog):
    def __init__(self, parent=None, video_source=None, duration_sec: float = 60, initial_start="00:00", initial_end=None):
        super().__init__(parent)
        self.setWindowTitle("Визуальная вырезка отрезка видео")
        self.resize(880, 680)
        self.setMinimumSize(760, 560)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.video_source = video_source
        self.duration_ms = max(100, int(round((float(duration_sec) if duration_sec else 60.0) * 1000.0)))
        self.start_ms = parse_time_to_ms(initial_start)
        self.end_ms = parse_time_to_ms(initial_end) if initial_end else self.duration_ms
        if self.end_ms <= self.start_ms or self.end_ms > self.duration_ms:
            self.end_ms = self.duration_ms

        self.current_pos_ms = self.start_ms
        self.is_looping = True
        self._drag_pos = None
        self.applied_range = None

        self._init_ui()
        self._init_player()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Main Dialog Container with explicit ID
        container = QFrame()
        container.setObjectName("TrimDialogContainer")
        container.setStyleSheet("""
            QFrame#TrimDialogContainer {
                background-color: #10141B;
                border: 1px solid rgba(255, 255, 255, 0.20);
                border-radius: 12px;
            }
        """)
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(16, 12, 16, 16)
        c_layout.setSpacing(10)

        # 1. Title Bar
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(8)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_svg_icon("scissors", color="#FFFFFF", size=18).pixmap(18, 18))
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        title_layout.addWidget(icon_lbl)

        title_lbl = QLabel("ВИЗУАЛЬНАЯ ВЫРЕЗКА ОТРЕЗКА ВИДЕО")
        title_lbl.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: 800; letter-spacing: 1px; background: transparent; border: none;")
        title_layout.addWidget(title_lbl)

        title_layout.addStretch()

        close_btn = QPushButton()
        close_btn.setIcon(get_svg_icon("x", color="#A1A1AA", size=16))
        close_btn.setObjectName("TitleButton")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton#TitleButton {
                background: transparent;
                border: none;
                border-radius: 6px;
            }
            QPushButton#TitleButton:hover {
                background: rgba(239, 68, 68, 0.4);
            }
        """)
        close_btn.clicked.connect(self.reject)
        title_layout.addWidget(close_btn)

        c_layout.addLayout(title_layout)

        # 2. Video Player View Area
        self.video_container = QFrame()
        self.video_container.setObjectName("VideoBox")
        self.video_container.setStyleSheet("""
            QFrame#VideoBox {
                background-color: #000000;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
            }
        """)
        v_layout = QVBoxLayout(self.video_container)
        v_layout.setContentsMargins(0, 0, 0, 0)

        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background-color: #000000; border-radius: 8px;")
        v_layout.addWidget(self.video_widget)

        c_layout.addWidget(self.video_container, stretch=1)

        # 3. Playback Controls Bar
        play_bar = QHBoxLayout()
        play_bar.setSpacing(8)

        # Jump to Start
        self.btn_jump_start = QPushButton(" НАЧАЛО")
        self.btn_jump_start.setIcon(get_svg_icon("skip-back", color="#FFFFFF", size=13))
        self.btn_jump_start.setIconSize(QSize(13, 13))
        self.btn_jump_start.setProperty("class", "GlassButton")
        self.btn_jump_start.setCursor(Qt.PointingHandCursor)
        self.btn_jump_start.clicked.connect(lambda: self._seek_to_ms(self.start_ms))
        play_bar.addWidget(self.btn_jump_start)

        # Step Back
        self.btn_step_back = QPushButton("-0.1s")
        self.btn_step_back.setProperty("class", "GlassButton")
        self.btn_step_back.setCursor(Qt.PointingHandCursor)
        self.btn_step_back.clicked.connect(lambda: self._seek_relative(-100))
        play_bar.addWidget(self.btn_step_back)

        # Play / Pause
        self.btn_play = QPushButton(" ВОСПРОИЗВЕДЕНИЕ")
        self.btn_play.setIcon(get_svg_icon("play", color="#000000", size=13))
        self.btn_play.setIconSize(QSize(13, 13))
        self.btn_play.setCursor(Qt.PointingHandCursor)
        self.btn_play.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #000000;
                font-size: 12px;
                font-weight: 800;
                padding: 6px 16px;
                border-radius: 6px;
                border: none;
                min-width: 140px;
            }
            QPushButton:hover {
                background-color: #E4E4E7;
            }
            QPushButton:pressed {
                background-color: #A1A1AA;
            }
        """)
        self.btn_play.clicked.connect(self._toggle_playback)
        play_bar.addWidget(self.btn_play)

        # Step Forward
        self.btn_step_fwd = QPushButton("+0.1s")
        self.btn_step_fwd.setProperty("class", "GlassButton")
        self.btn_step_fwd.setCursor(Qt.PointingHandCursor)
        self.btn_step_fwd.clicked.connect(lambda: self._seek_relative(100))
        play_bar.addWidget(self.btn_step_fwd)

        # Jump to End
        self.btn_jump_end = QPushButton(" КОНЕЦ")
        self.btn_jump_end.setIcon(get_svg_icon("skip-forward", color="#FFFFFF", size=13))
        self.btn_jump_end.setIconSize(QSize(13, 13))
        self.btn_jump_end.setProperty("class", "GlassButton")
        self.btn_jump_end.setCursor(Qt.PointingHandCursor)
        self.btn_jump_end.clicked.connect(lambda: self._seek_to_ms(self.end_ms))
        play_bar.addWidget(self.btn_jump_end)

        play_bar.addStretch()

        # Current Time / Duration Badge
        self.time_lbl = QLabel("00:00 / 00:00")
        self.time_lbl.setStyleSheet("""
            color: #FFFFFF;
            font-size: 12px;
            font-weight: 700;
            font-family: 'Consolas', monospace;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 6px;
            padding: 4px 10px;
        """)
        play_bar.addWidget(self.time_lbl)

        c_layout.addLayout(play_bar)

        # 4. Interactive Timeline Range Slider
        self.timeline_slider = TimelineRangeSlider()
        self.timeline_slider.set_duration(self.duration_ms)
        self.timeline_slider.set_range(self.start_ms, self.end_ms)
        self.timeline_slider.range_changed.connect(self._on_range_changed)
        self.timeline_slider.seek_requested.connect(self._on_slider_seek)
        c_layout.addWidget(self.timeline_slider)

        # 5. Quick Marker Buttons, Loop Toggle & Precise Time Info
        info_bar = QHBoxLayout()
        info_bar.setSpacing(8)

        self.btn_mark_start = QPushButton(" СДЕЛАТЬ НАЧАЛОМ")
        self.btn_mark_start.setIcon(get_svg_icon("flag", color="#FFFFFF", size=13))
        self.btn_mark_start.setIconSize(QSize(13, 13))
        self.btn_mark_start.setProperty("class", "GlassButton")
        self.btn_mark_start.setCursor(Qt.PointingHandCursor)
        self.btn_mark_start.setToolTip("Установить текущий кадр видео как точку начала")
        self.btn_mark_start.clicked.connect(self._set_current_as_start)
        info_bar.addWidget(self.btn_mark_start)

        self.btn_mark_end = QPushButton(" СДЕЛАТЬ КОНЦОМ")
        self.btn_mark_end.setIcon(get_svg_icon("flag-end", color="#FFFFFF", size=13))
        self.btn_mark_end.setIconSize(QSize(13, 13))
        self.btn_mark_end.setProperty("class", "GlassButton")
        self.btn_mark_end.setCursor(Qt.PointingHandCursor)
        self.btn_mark_end.setToolTip("Установить текущий кадр видео как точку конца")
        self.btn_mark_end.clicked.connect(self._set_current_as_end)
        info_bar.addWidget(self.btn_mark_end)

        # Loop Trim Section Toggle
        self.btn_loop = QPushButton(" ЗАЦИКЛИТЬ ОТРЕЗОК")
        self.btn_loop.setIcon(get_svg_icon("repeat", color="#4ADE80", size=13))
        self.btn_loop.setIconSize(QSize(13, 13))
        self.btn_loop.setCursor(Qt.PointingHandCursor)
        self.btn_loop.setCheckable(True)
        self.btn_loop.setChecked(True)
        self.btn_loop.toggled.connect(self._on_loop_toggled)
        self._update_loop_btn_style()
        info_bar.addWidget(self.btn_loop)

        info_bar.addStretch()

        # Start / End Badges
        self.badge_start = QLabel(f"ОТ: {ms_to_fmt(self.start_ms)}")
        self.badge_start.setStyleSheet("color: #4ADE80; font-weight: 800; font-family: 'Consolas', monospace; font-size: 11px;")
        info_bar.addWidget(self.badge_start)

        self.badge_end = QLabel(f"ДО: {ms_to_fmt(self.end_ms)}")
        self.badge_end.setStyleSheet("color: #F87171; font-weight: 800; font-family: 'Consolas', monospace; font-size: 11px;")
        info_bar.addWidget(self.badge_end)

        dur_cut = max(0, self.end_ms - self.start_ms)
        self.badge_len = QLabel(f"ИТОГО: {ms_to_fmt(dur_cut)}")
        self.badge_len.setStyleSheet("""
            background: rgba(255, 255, 255, 0.12);
            color: #FFFFFF;
            font-weight: 800;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            padding: 3px 8px;
            border-radius: 6px;
        """)
        info_bar.addWidget(self.badge_len)

        c_layout.addLayout(info_bar)

        # 6. Bottom Actions Bar
        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(10)

        reset_btn = QPushButton(" СБРОСИТЬ (НА ВСЕ ВИДЕО)")
        reset_btn.setIcon(get_svg_icon("rotate-ccw", color="#FFFFFF", size=13))
        reset_btn.setIconSize(QSize(13, 13))
        reset_btn.setProperty("class", "GlassButton")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setStyleSheet("font-size: 11px; font-weight: 700; padding: 6px 14px;")
        reset_btn.clicked.connect(self._reset_to_full)
        actions_layout.addWidget(reset_btn)

        cancel_btn = QPushButton(" ОТМЕНА")
        cancel_btn.setIcon(get_svg_icon("x", color="#FFFFFF", size=13))
        cancel_btn.setIconSize(QSize(13, 13))
        cancel_btn.setProperty("class", "GlassButton")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet("font-size: 11px; font-weight: 700; padding: 6px 14px;")
        cancel_btn.clicked.connect(self.reject)
        actions_layout.addWidget(cancel_btn)

        actions_layout.addStretch()

        apply_btn = QPushButton(" ПРИМЕНИТЬ ОТРЕЗОК")
        apply_btn.setIcon(get_svg_icon("check", color="#000000", size=15))
        apply_btn.setIconSize(QSize(15, 15))
        apply_btn.setObjectName("PrimaryButton")
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.setStyleSheet("""
            QPushButton#PrimaryButton {
                background-color: #FFFFFF;
                color: #000000;
                font-size: 12px;
                font-weight: 800;
                padding: 7px 20px;
                border-radius: 6px;
            }
            QPushButton#PrimaryButton:hover {
                background-color: #E4E4E7;
            }
        """)
        apply_btn.clicked.connect(self._apply)
        actions_layout.addWidget(apply_btn)

        c_layout.addLayout(actions_layout)
        main_layout.addWidget(container)

    def _init_player(self):
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)

        self.player.positionChanged.connect(self._on_player_position_changed)
        self.player.durationChanged.connect(self._on_player_duration_changed)
        self.player.errorOccurred.connect(self._on_player_error)

        if self.video_source:
            if isinstance(self.video_source, str) and (self.video_source.startswith("http://") or self.video_source.startswith("https://")):
                self.player.setSource(QUrl(self.video_source))
                self.player.pause()
                self._seek_to_ms(self.start_ms)
            elif os.path.exists(self.video_source):
                playable = get_or_create_preview_proxy(self.video_source)
                self.player.setSource(QUrl.fromLocalFile(playable))
                self.player.pause()
                self._seek_to_ms(self.start_ms)

    def _on_player_error(self, error, error_string):
        if self.video_source and os.path.exists(self.video_source):
            proxy = get_or_create_preview_proxy(self.video_source)
            if proxy != self.video_source and os.path.exists(proxy):
                self.player.setSource(QUrl.fromLocalFile(proxy))
                self.player.pause()
                self._seek_to_ms(self.current_pos_ms)

    def _on_player_duration_changed(self, dur_ms: int):
        if dur_ms > 0:
            was_full = (self.end_ms >= self.duration_ms or self.end_ms == 0)
            self.duration_ms = dur_ms
            self.timeline_slider.set_duration(dur_ms)
            if was_full:
                self.end_ms = dur_ms
            else:
                self.end_ms = min(self.end_ms, dur_ms)
            self.timeline_slider.set_range(self.start_ms, self.end_ms)
            self._update_badges()
            self.time_lbl.setText(f"{ms_to_fmt(self.current_pos_ms)} / {ms_to_fmt(self.duration_ms)}")

    def _on_player_position_changed(self, pos_ms: int):
        self.current_pos_ms = pos_ms
        self.timeline_slider.set_current_position(pos_ms)
        self.time_lbl.setText(f"{ms_to_fmt(pos_ms)} / {ms_to_fmt(self.duration_ms)}")

        # Loop check within trimmed range (or when reaching end)
        if self.is_looping and pos_ms >= (self.end_ms - 50) and self.player.playbackState() == QMediaPlayer.PlayingState:
            self._seek_to_ms(self.start_ms)

    def _toggle_playback(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.btn_play.setText(" ВОСПРОИЗВЕДЕНИЕ")
            self.btn_play.setIcon(get_svg_icon("play", color="#000000", size=13))
        else:
            if self.current_pos_ms >= (self.end_ms - 50) or self.current_pos_ms < self.start_ms:
                self._seek_to_ms(self.start_ms)
            self.player.play()
            self.btn_play.setText(" ПАУЗА")
            self.btn_play.setIcon(get_svg_icon("pause", color="#000000", size=13))

    def _seek_to_ms(self, pos_ms: int):
        pos_ms = max(0, min(self.duration_ms, pos_ms))
        self.current_pos_ms = pos_ms
        # Keep last frame rendered on screen without flushing to black at EOF
        safe_max = max(0, self.duration_ms - 40) if self.duration_ms > 100 else self.duration_ms
        player_pos = min(pos_ms, safe_max)
        self.player.setPosition(player_pos)
        self.timeline_slider.set_current_position(pos_ms)
        self.time_lbl.setText(f"{ms_to_fmt(pos_ms)} / {ms_to_fmt(self.duration_ms)}")

    def _seek_relative(self, delta_ms: int):
        cur = self.current_pos_ms
        self._seek_to_ms(cur + delta_ms)

    def _on_slider_seek(self, pos_ms: int):
        self._seek_to_ms(pos_ms)

    def _on_range_changed(self, start_ms: int, end_ms: int):
        self.start_ms = start_ms
        self.end_ms = end_ms
        self._update_badges()

    def _update_badges(self):
        self.badge_start.setText(f"ОТ: {ms_to_fmt(self.start_ms)}")
        self.badge_end.setText(f"ДО: {ms_to_fmt(self.end_ms)}")
        dur = max(0, self.end_ms - self.start_ms)
        self.badge_len.setText(f"ИТОГО: {ms_to_fmt(dur)}")

    def _set_current_as_start(self):
        pos = self.current_pos_ms
        if pos < self.end_ms:
            self.start_ms = pos
            self.timeline_slider.set_range(self.start_ms, self.end_ms)
            self._update_badges()

    def _set_current_as_end(self):
        pos = self.current_pos_ms
        if pos > self.start_ms:
            self.end_ms = pos
            self.timeline_slider.set_range(self.start_ms, self.end_ms)
            self._update_badges()

    def _on_loop_toggled(self, checked: bool):
        self.is_looping = checked
        self._update_loop_btn_style()

    def _update_loop_btn_style(self):
        if self.btn_loop.isChecked():
            self.btn_loop.setIcon(get_svg_icon("repeat", color="#4ADE80", size=13))
            self.btn_loop.setStyleSheet("""
                QPushButton {
                    background-color: rgba(34, 197, 94, 0.16);
                    border: 1px solid rgba(34, 197, 94, 0.6);
                    color: #4ADE80;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 4px 10px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: rgba(34, 197, 94, 0.25);
                }
            """)
        else:
            self.btn_loop.setIcon(get_svg_icon("repeat", color="#A1A1AA", size=13))
            self.btn_loop.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.14);
                    color: #A1A1AA;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 4px 10px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.12);
                    color: #FFFFFF;
                }
            """)

    def _reset_to_full(self):
        self.start_ms = 0
        self.end_ms = self.duration_ms
        self.timeline_slider.set_range(0, self.duration_ms)
        self._update_badges()
        self._seek_to_ms(0)

    def _apply(self):
        self.applied_range = (ms_to_fmt(self.start_ms), ms_to_fmt(self.end_ms))
        self.player.stop()
        self.accept()

    def reject(self):
        self.player.stop()
        super().reject()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
