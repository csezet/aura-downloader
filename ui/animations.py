from PySide6.QtWidgets import QWidget, QProgressBar, QGraphicsOpacityEffect, QSizePolicy
from PySide6.QtCore import (
    QObject, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup,
    Signal, Property, Qt
)

class FadeSlideHelper(QObject):
    def __init__(self, widget: QWidget, target_height: int = 115, duration: int = 220):
        super().__init__(widget)
        self.widget = widget
        self.target_height = target_height
        self.duration = duration
        
        self.widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.widget.setVisible(False)

        # Opacity effect
        self.opacity_effect = QGraphicsOpacityEffect(widget)
        self.widget.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        # Animations
        self.anim_height = QPropertyAnimation(widget, b"maximumHeight")
        self.anim_height.setDuration(duration)
        self.anim_height.setEasingCurve(QEasingCurve.OutCubic)

        self.anim_opacity = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_opacity.setDuration(duration)
        self.anim_opacity.setEasingCurve(QEasingCurve.OutCubic)

        self.group = QParallelAnimationGroup()
        self.group.addAnimation(self.anim_height)
        self.group.addAnimation(self.anim_opacity)

    def show_animated(self, target_height: int = None):
        h = target_height or self.target_height
        self.group.stop()
        self.widget.setVisible(True)

        start_h = self.widget.height() if self.widget.isVisible() and self.widget.maximumHeight() > 0 else 0
        self.anim_height.setStartValue(start_h)
        self.anim_height.setEndValue(h)

        self.anim_opacity.setStartValue(self.opacity_effect.opacity())
        self.anim_opacity.setEndValue(1.0)

        try:
            self.group.finished.disconnect()
        except Exception:
            pass

        def on_show_finished():
            self.widget.setMaximumHeight(h)
            self.widget.setFixedHeight(h)
            self.opacity_effect.setOpacity(1.0)

        self.group.finished.connect(on_show_finished)
        self.group.start()

    def hide_animated(self):
        self.group.stop()
        start_h = self.widget.height()
        if start_h <= 0:
            self.widget.setVisible(False)
            return

        self.anim_height.setStartValue(start_h)
        self.anim_height.setEndValue(0)

        self.anim_opacity.setStartValue(self.opacity_effect.opacity())
        self.anim_opacity.setEndValue(0.0)

        try:
            self.group.finished.disconnect()
        except Exception:
            pass

        def on_hide_finished():
            self.widget.setVisible(False)
            self.widget.setMaximumHeight(0)

        self.group.finished.connect(on_hide_finished)
        self.group.start()


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

    def setSmoothValue(self, target_val: float):
        self.anim.stop()
        self.anim.setStartValue(self._current_value)
        self.anim.setEndValue(float(target_val))
        self.anim.start()
