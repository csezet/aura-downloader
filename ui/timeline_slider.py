import math
from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QFont, QCursor

def ms_to_time_str(ms: int) -> str:
    if ms is None or ms < 0:
        return "00:00"
    total_sec = ms / 1000.0
    m, s = divmod(int(total_sec), 60)
    h, m = divmod(m, 60)
    # fractional tenths
    tenths = int((total_sec - int(total_sec)) * 10)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}.{tenths}"
    return f"{m:02d}:{s:02d}.{tenths}"

HANDLE_NONE = 0
HANDLE_START = 1
HANDLE_END = 2
HANDLE_PLAYHEAD = 3

class TimelineRangeSlider(QWidget):
    range_changed = Signal(int, int)  # start_ms, end_ms
    seek_requested = Signal(int)      # current_pos_ms

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(54)

        self.duration_ms = 60000  # Default 60s
        self.start_ms = 0
        self.end_ms = 60000
        self.current_pos_ms = 0

        self.active_drag = HANDLE_NONE
        self.handle_width = 14
        self.track_height = 28
        self.track_margin_x = 16

    def set_duration(self, duration_ms: int):
        self.duration_ms = max(100, duration_ms)
        self.start_ms = 0
        self.end_ms = self.duration_ms
        self.current_pos_ms = 0
        self.update()

    def set_range(self, start_ms: int, end_ms: int):
        self.start_ms = max(0, min(self.duration_ms, start_ms))
        self.end_ms = max(self.start_ms, min(self.duration_ms, end_ms))
        self.update()

    def set_current_position(self, pos_ms: int):
        self.current_pos_ms = max(0, min(self.duration_ms, pos_ms))
        self.update()

    def _ms_to_x(self, ms: int) -> float:
        w = self.width() - 2 * self.track_margin_x
        if self.duration_ms <= 0:
            return self.track_margin_x
        ratio = max(0.0, min(1.0, ms / self.duration_ms))
        return self.track_margin_x + ratio * w

    def _x_to_ms(self, x: float) -> int:
        w = self.width() - 2 * self.track_margin_x
        if w <= 0:
            return 0
        ratio = max(0.0, min(1.0, (x - self.track_margin_x) / w))
        return int(round(ratio * self.duration_ms))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        w = self.width()
        h = self.height()
        track_y = 12
        track_h = self.track_height
        track_w = w - 2 * self.track_margin_x

        # 1. Background Track
        track_path = QPainterPath()
        track_path.addRoundedRect(QRectF(self.track_margin_x, track_y, track_w, track_h), 6, 6)
        painter.fillPath(track_path, QColor(15, 18, 25, 230))
        painter.strokePath(track_path, QPen(QColor(255, 255, 255, 30), 1))

        # Time ticks
        tick_pen = QPen(QColor(255, 255, 255, 40), 1)
        painter.setPen(tick_pen)
        num_ticks = 10
        for i in range(1, num_ticks):
            tx = self.track_margin_x + (i / num_ticks) * track_w
            painter.drawLine(QPointF(tx, track_y + 4), QPointF(tx, track_y + track_h - 4))

        start_x = self._ms_to_x(self.start_ms)
        end_x = self._ms_to_x(self.end_ms)
        play_x = self._ms_to_x(self.current_pos_ms)

        # 2. Dimmed Excluded Regions
        if start_x > self.track_margin_x:
            left_dim = QRectF(self.track_margin_x, track_y, start_x - self.track_margin_x, track_h)
            painter.fillRect(left_dim, QColor(0, 0, 0, 160))

        if end_x < self.track_margin_x + track_w:
            right_dim = QRectF(end_x, track_y, (self.track_margin_x + track_w) - end_x, track_h)
            painter.fillRect(right_dim, QColor(0, 0, 0, 160))

        # 3. Active Trimmed Selection Box
        sel_rect = QRectF(start_x, track_y, max(2.0, end_x - start_x), track_h)
        painter.fillRect(sel_rect, QColor(255, 255, 255, 35))
        
        # Border for active region
        sel_pen = QPen(QColor(255, 255, 255, 180), 1.5)
        painter.setPen(sel_pen)
        painter.drawRect(sel_rect)

        # 4. Start Handle ([)
        start_handle_rect = QRectF(start_x - self.handle_width, track_y - 2, self.handle_width, track_h + 4)
        start_path = QPainterPath()
        start_path.addRoundedRect(start_handle_rect, 4, 4)
        painter.fillPath(start_path, QColor(255, 255, 255, 240))
        painter.strokePath(start_path, QPen(QColor(0, 0, 0, 80), 1))

        # Start handle grips
        painter.setPen(QPen(QColor(40, 40, 40), 1.5))
        painter.drawLine(QPointF(start_x - self.handle_width * 0.6, track_y + 6),
                         QPointF(start_x - self.handle_width * 0.6, track_y + track_h - 4))

        # 5. End Handle (])
        end_handle_rect = QRectF(end_x, track_y - 2, self.handle_width, track_h + 4)
        end_path = QPainterPath()
        end_path.addRoundedRect(end_handle_rect, 4, 4)
        painter.fillPath(end_path, QColor(255, 255, 255, 240))
        painter.strokePath(end_path, QPen(QColor(0, 0, 0, 80), 1))

        # End handle grips
        painter.drawLine(QPointF(end_x + self.handle_width * 0.6, track_y + 6),
                         QPointF(end_x + self.handle_width * 0.6, track_y + track_h - 4))

        # 6. Playhead Needle (|)
        play_pen = QPen(QColor(255, 255, 255), 2)
        painter.setPen(play_pen)
        painter.drawLine(QPointF(play_x, 4), QPointF(play_x, track_y + track_h + 4))

        # Top indicator pointer
        head_path = QPainterPath()
        head_path.moveTo(play_x - 5, 2)
        head_path.lineTo(play_x + 5, 2)
        head_path.lineTo(play_x, 9)
        head_path.closeSubpath()
        painter.fillPath(head_path, QColor(255, 255, 255))

        painter.end()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        x = event.position().x()
        start_x = self._ms_to_x(self.start_ms)
        end_x = self._ms_to_x(self.end_ms)
        play_x = self._ms_to_x(self.current_pos_ms)

        # Check Hit
        if abs(x - (start_x - self.handle_width / 2)) <= self.handle_width:
            self.active_drag = HANDLE_START
        elif abs(x - (end_x + self.handle_width / 2)) <= self.handle_width:
            self.active_drag = HANDLE_END
        elif abs(x - play_x) <= 8:
            self.active_drag = HANDLE_PLAYHEAD
        else:
            # Clicked on track: jump playhead and seek
            ms = self._x_to_ms(x)
            self.current_pos_ms = ms
            self.active_drag = HANDLE_PLAYHEAD
            self.seek_requested.emit(ms)
            self.update()

    def mouseMoveEvent(self, event):
        x = event.position().x()
        start_x = self._ms_to_x(self.start_ms)
        end_x = self._ms_to_x(self.end_ms)

        # Update cursor
        if self.active_drag == HANDLE_NONE:
            if abs(x - (start_x - self.handle_width / 2)) <= self.handle_width or abs(x - (end_x + self.handle_width / 2)) <= self.handle_width:
                self.setCursor(Qt.SizeHorCursor)
            else:
                self.setCursor(Qt.PointingHandCursor)

        if self.active_drag == HANDLE_START:
            ms = self._x_to_ms(x + self.handle_width / 2)
            self.start_ms = max(0, min(self.end_ms - 200, ms))
            self.current_pos_ms = self.start_ms
            self.range_changed.emit(self.start_ms, self.end_ms)
            self.seek_requested.emit(self.start_ms)
            self.update()
        elif self.active_drag == HANDLE_END:
            ms = self._x_to_ms(x - self.handle_width / 2)
            self.end_ms = max(self.start_ms + 200, min(self.duration_ms, ms))
            self.current_pos_ms = self.end_ms
            self.range_changed.emit(self.start_ms, self.end_ms)
            self.seek_requested.emit(self.end_ms)
            self.update()
        elif self.active_drag == HANDLE_PLAYHEAD:
            ms = self._x_to_ms(x)
            self.current_pos_ms = ms
            self.seek_requested.emit(ms)
            self.update()

    def mouseReleaseEvent(self, event):
        self.active_drag = HANDLE_NONE
        self.setCursor(Qt.ArrowCursor)
