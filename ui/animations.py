from PySide6.QtWidgets import QWidget, QProgressBar, QGraphicsOpacityEffect
from PySide6.QtCore import (
    QObject, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup,
    QSequentialAnimationGroup, Signal, Property, Qt
)

class FadeSlideHelper(QObject):
    def __init__(self, widget: QWidget, target_height: int = 120, duration: int = 260):
        super().__init__(widget)
        self.widget = widget
        self.target_height = target_height
        self.duration = duration
        
        # Opacity effect
        self.opacity_effect = QGraphicsOpacityEffect(widget)
        self.widget.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        # Height animation
        self.anim_height = QPropertyAnimation(widget, b"maximumHeight")
        self.anim_height.setDuration(duration)
        self.anim_height.setEasingCurve(QEasingCurve.OutCubic)

        # Opacity animation
        self.anim_opacity = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_opacity.setDuration(duration)
        self.anim_opacity.setEasingCurve(QEasingCurve.OutCubic)

        # Group
        self.group = QParallelAnimationGroup()
        self.group.addAnimation(self.anim_height)
        self.group.addAnimation(self.anim_opacity)

    def show_animated(self, target_height: int = None):
        h = target_height or self.target_height
        self.widget.setVisible(True)
        self.group.stop()

        self.anim_height.setStartValue(self.widget.height() if self.widget.isVisible() else 0)
        self.anim_height.setEndValue(h)

        self.anim_opacity.setStartValue(self.opacity_effect.opacity())
        self.anim_opacity.setEndValue(1.0)

        self.group.start()

    def hide_animated(self):
        self.group.stop()

        self.anim_height.setStartValue(self.widget.height())
        self.anim_height.setEndValue(0)

        self.anim_opacity.setStartValue(self.opacity_effect.opacity())
        self.anim_opacity.setEndValue(0.0)

        def on_finished():
            if self.anim_opacity.endValue() == 0.0:
                self.widget.setVisible(False)

        try:
            self.group.finished.disconnect()
        except Exception:
            pass
        self.group.finished.connect(on_finished)
        self.group.start()


class SmoothProgressBar(QProgressBar):
    """
    Progress bar with smooth interpolation animation so it glides like in modern iOS/Mac apps.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_value = 0.0

        self.anim = QPropertyAnimation(self, b"animatedValue")
        self.anim.setDuration(220)
        self.anim.setEasingCurve(QEasingCurve.OutQuad)

    def get_animated_value(self) -> float:
        return self._current_value

    def set_animated_value(self, val: float):
        self._current_value = val
        super().setValue(int(val))

    animatedValue = Property(float, get_animated_value, set_animated_value)

    def setSmoothValue(self, target_val: float):
        self.anim.stop()
        self.anim.setStartValue(self._current_value)
        self.anim.setEndValue(float(target_val))
        self.anim.start()
