from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, Signal, QRectF, QPropertyAnimation, Property
from PySide6.QtGui import QPainter, QColor, QBrush, QPen

class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, parent=None, checked=False):
        super().__init__(parent)
        self.setFixedSize(38, 22)
        self.setCursor(Qt.PointingHandCursor)
        self._checked = checked
        self._thumb_pos = 1.0 if checked else 0.0

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        if self._checked != checked:
            self._checked = checked
            self._thumb_pos = 1.0 if checked else 0.0
            self.update()
            self.toggled.emit(self._checked)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setChecked(not self._checked)
            event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        width = self.width()
        height = self.height()
        radius = height / 2.0

        # Background track
        track_rect = QRectF(0, 0, width, height)
        if self._checked:
            track_color = QColor(255, 255, 255, 255)  # Stark White
            border_color = QColor(255, 255, 255, 255)
            thumb_color = QColor(0, 0, 0, 255)        # Pure Black knob
        else:
            track_color = QColor(255, 255, 255, 18)   # Translucent dark
            border_color = QColor(255, 255, 255, 50)
            thumb_color = QColor(161, 161, 170, 255)  # Zinc 400

        painter.setPen(QPen(border_color, 1))
        painter.setBrush(QBrush(track_color))
        painter.drawRoundedRect(track_rect, radius, radius)

        # Thumb Knob
        thumb_radius = radius - 3.0
        if self._checked:
            thumb_x = width - radius - thumb_radius + 3.0
        else:
            thumb_x = 3.0

        thumb_rect = QRectF(thumb_x, 3.0, thumb_radius * 2, thumb_radius * 2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(thumb_color))
        painter.drawEllipse(thumb_rect)

        painter.end()
