from PySide6.QtWidgets import QProgressBar
from PySide6.QtCore import QPropertyAnimation, QEasingCurve, Property


class SmoothProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_value = 0.0

        self.anim = QPropertyAnimation(self, b"animatedValue")
        self.anim.setDuration(180)
        self.anim.setEasingCurve(QEasingCurve.OutQuad)

    def get_animated_value(self) -> float:
        return self._current_value

    def set_animated_value(self, val: float):
        self._current_value = val
        super().setValue(int(val))

    animatedValue = Property(float, get_animated_value, set_animated_value)

    def setValue(self, val: int):
        self.anim.stop()
        self._current_value = float(val)
        super().setValue(int(val))

    def setSmoothValue(self, target_val: float):
        self.anim.stop()
        self.anim.setStartValue(self._current_value)
        self.anim.setEndValue(float(target_val))
        self.anim.start()
