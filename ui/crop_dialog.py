import os
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QSize
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QCursor, QPainterPath, QFont
)

HANDLE_NONE = 0
HANDLE_TL = 1
HANDLE_TR = 2
HANDLE_BL = 3
HANDLE_BR = 4
HANDLE_T = 5
HANDLE_B = 6
HANDLE_L = 7
HANDLE_R = 8
HANDLE_MOVE = 9
HANDLE_SIZE = 12

class CropCanvas(QWidget):
    crop_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.pixmap = None
        self.aspect_ratio = None  # None = Free (arbitrary crop)
        self.crop_norm = QRectF(0.0, 0.0, 1.0, 1.0)  # Starts with 100% full original frame
        self.active_handle = HANDLE_NONE
        self.drag_start_pos = None
        self.drag_start_rect = None
        self.source_width = 1920
        self.source_height = 1080

    def set_source_image(self, pixmap: QPixmap, source_w: int = 1920, source_h: int = 1080):
        self.pixmap = pixmap
        if pixmap and not pixmap.isNull():
            pix_is_portrait = pixmap.height() > pixmap.width()
            source_is_portrait = source_h > source_w
            if pix_is_portrait != source_is_portrait:
                source_w, source_h = source_h, source_w
        self.source_width = source_w if source_w > 0 else (pixmap.width() if pixmap else 1920)
        self.source_height = source_h if source_h > 0 else (pixmap.height() if pixmap else 1080)
        self.update()
        self._notify_change()

    def set_aspect_ratio(self, ratio: float):
        self.aspect_ratio = ratio
        if ratio is not None:
            # Adjust current normalized crop to fit ratio centered
            img_aspect = self.source_width / max(1, self.source_height)
            norm_ratio = ratio / img_aspect

            cx = self.crop_norm.center().x()
            cy = self.crop_norm.center().y()

            cur_w = self.crop_norm.width()
            cur_h = cur_w / norm_ratio
            if cur_h > 1.0:
                cur_h = 1.0
                cur_w = cur_h * norm_ratio

            x = max(0.0, min(1.0 - cur_w, cx - cur_w / 2))
            y = max(0.0, min(1.0 - cur_h, cy - cur_h / 2))
            self.crop_norm = QRectF(x, y, cur_w, cur_h)
        self.update()
        self._notify_change()

    def reset_crop(self):
        self.aspect_ratio = None
        self.crop_norm = QRectF(0.0, 0.0, 1.0, 1.0)  # Full original video frame
        self.update()
        self._notify_change()

    def get_crop_params(self) -> dict:
        crop_w = int(round(self.source_width * self.crop_norm.width()))
        crop_h = int(round(self.source_height * self.crop_norm.height()))
        crop_x = int(round(self.source_width * self.crop_norm.x()))
        crop_y = int(round(self.source_height * self.crop_norm.y()))

        if self.aspect_ratio is not None:
            target_w = int(round(crop_h * self.aspect_ratio))
            if target_w <= self.source_width:
                crop_w = target_w
            else:
                crop_h = int(round(crop_w / self.aspect_ratio))

        # Ensure even pixel dimensions
        crop_w = max(2, crop_w - (crop_w % 2))
        crop_h = max(2, crop_h - (crop_h % 2))
        crop_x = crop_x - (crop_x % 2)
        crop_y = crop_y - (crop_y % 2)

        # Clamp bounds
        if crop_x + crop_w > self.source_width:
            crop_x = max(0, self.source_width - crop_w)
        if crop_y + crop_h > self.source_height:
            crop_y = max(0, self.source_height - crop_h)

        return {
            'x_norm': self.crop_norm.x(),
            'y_norm': self.crop_norm.y(),
            'w_norm': self.crop_norm.width(),
            'h_norm': self.crop_norm.height(),
            'w': crop_w,
            'h': crop_h,
            'x': crop_x,
            'y': crop_y,
            'source_w': self.source_width,
            'source_h': self.source_height
        }

    def _get_image_draw_rect(self) -> QRectF:
        cw = self.width() - 20
        ch = self.height() - 20
        if cw <= 0 or ch <= 0:
            return QRectF(0, 0, 10, 10)

        aspect = self.source_width / max(1, self.source_height)
        if cw / ch > aspect:
            draw_h = ch
            draw_w = ch * aspect
        else:
            draw_w = cw
            draw_h = cw / aspect

        ox = 10 + (cw - draw_w) / 2
        oy = 10 + (ch - draw_h) / 2
        return QRectF(ox, oy, draw_w, draw_h)

    def _norm_to_pixel_rect(self, img_rect: QRectF) -> QRectF:
        px = img_rect.x() + self.crop_norm.x() * img_rect.width()
        py = img_rect.y() + self.crop_norm.y() * img_rect.height()
        pw = self.crop_norm.width() * img_rect.width()
        ph = self.crop_norm.height() * img_rect.height()
        return QRectF(px, py, pw, ph)

    def _hit_test(self, pt: QPointF, crop_rect: QRectF) -> int:
        hs = HANDLE_SIZE
        x, y, w, h = crop_rect.x(), crop_rect.y(), crop_rect.width(), crop_rect.height()

        if QRectF(x - hs, y - hs, hs * 2, hs * 2).contains(pt):
            return HANDLE_TL
        if QRectF(x + w - hs, y - hs, hs * 2, hs * 2).contains(pt):
            return HANDLE_TR
        if QRectF(x - hs, y + h - hs, hs * 2, hs * 2).contains(pt):
            return HANDLE_BL
        if QRectF(x + w - hs, y + h - hs, hs * 2, hs * 2).contains(pt):
            return HANDLE_BR

        if QRectF(x + hs, y - hs, w - hs * 2, hs * 2).contains(pt):
            return HANDLE_T
        if QRectF(x + hs, y + h - hs, w - hs * 2, hs * 2).contains(pt):
            return HANDLE_B
        if QRectF(x - hs, y + hs, hs * 2, h - hs * 2).contains(pt):
            return HANDLE_L
        if QRectF(x + w - hs, y + hs, hs * 2, h - hs * 2).contains(pt):
            return HANDLE_R

        if crop_rect.contains(pt):
            return HANDLE_MOVE

        return HANDLE_NONE

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            img_rect = self._get_image_draw_rect()
            crop_px = self._norm_to_pixel_rect(img_rect)
            self.active_handle = self._hit_test(event.position(), crop_px)
            self.drag_start_pos = event.position()
            self.drag_start_rect = QRectF(self.crop_norm)
            event.accept()

    def mouseMoveEvent(self, event):
        img_rect = self._get_image_draw_rect()
        crop_px = self._norm_to_pixel_rect(img_rect)

        if self.active_handle == HANDLE_NONE:
            handle = self._hit_test(event.position(), crop_px)
            if handle in [HANDLE_TL, HANDLE_BR]:
                self.setCursor(Qt.SizeFDiagCursor)
            elif handle in [HANDLE_TR, HANDLE_BL]:
                self.setCursor(Qt.SizeBDiagCursor)
            elif handle in [HANDLE_T, HANDLE_B]:
                self.setCursor(Qt.SizeVerCursor)
            elif handle in [HANDLE_L, HANDLE_R]:
                self.setCursor(Qt.SizeHorCursor)
            elif handle == HANDLE_MOVE:
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            return

        # Dragging in progress
        dx_norm = (event.position().x() - self.drag_start_pos.x()) / max(1, img_rect.width())
        dy_norm = (event.position().y() - self.drag_start_pos.y()) / max(1, img_rect.height())

        r = QRectF(self.drag_start_rect)

        if self.active_handle == HANDLE_MOVE:
            new_x = max(0.0, min(1.0 - r.width(), r.x() + dx_norm))
            new_y = max(0.0, min(1.0 - r.height(), r.y() + dy_norm))
            self.crop_norm = QRectF(new_x, new_y, r.width(), r.height())

        else:
            left, top, right, bottom = r.left(), r.top(), r.right(), r.bottom()
            min_size = 0.03

            if self.active_handle in [HANDLE_TL, HANDLE_L, HANDLE_BL]:
                left = max(0.0, min(right - min_size, left + dx_norm))
            if self.active_handle in [HANDLE_TR, HANDLE_R, HANDLE_BR]:
                right = min(1.0, max(left + min_size, right + dx_norm))
            if self.active_handle in [HANDLE_TL, HANDLE_T, HANDLE_TR]:
                top = max(0.0, min(bottom - min_size, top + dy_norm))
            if self.active_handle in [HANDLE_BL, HANDLE_B, HANDLE_BR]:
                bottom = min(1.0, max(top + min_size, bottom + dy_norm))

            # Ratio constraint only if a specific ratio preset is locked
            if self.aspect_ratio is not None:
                img_aspect = self.source_width / max(1, self.source_height)
                norm_ratio = self.aspect_ratio / img_aspect

                w = right - left
                h = bottom - top

                if self.active_handle in [HANDLE_L, HANDLE_R]:
                    h = w / norm_ratio
                    top = max(0.0, min(1.0 - h, r.center().y() - h / 2))
                    bottom = top + h
                elif self.active_handle in [HANDLE_T, HANDLE_B]:
                    w = h * norm_ratio
                    left = max(0.0, min(1.0 - w, r.center().x() - w / 2))
                    right = left + w
                elif self.active_handle in [HANDLE_TL, HANDLE_TR, HANDLE_BL, HANDLE_BR]:
                    target_h = w / norm_ratio
                    if self.active_handle in [HANDLE_TL, HANDLE_TR]:
                        top = max(0.0, bottom - target_h)
                    else:
                        bottom = min(1.0, top + target_h)

            self.crop_norm = QRectF(left, top, right - left, bottom - top)

        self.update()
        self._notify_change()

    def mouseReleaseEvent(self, event):
        self.active_handle = HANDLE_NONE
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def _notify_change(self):
        self.crop_changed.emit(self.get_crop_params())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # Background fill
        painter.fillRect(self.rect(), QColor(10, 12, 16))

        img_rect = self._get_image_draw_rect()

        # Draw Source Frame or Placeholder
        if self.pixmap and not self.pixmap.isNull():
            painter.drawPixmap(img_rect.toRect(), self.pixmap)
        else:
            painter.fillRect(img_rect, QColor(20, 24, 30))
            painter.setPen(QColor(113, 113, 122))
            painter.setFont(QFont("Segoe UI", 11))
            painter.drawText(img_rect, Qt.AlignCenter, "ПРЕДПРОСМОТР КАДРА ВИДЕО")

        # Darkened Mask outside Crop Rect
        crop_px = self._norm_to_pixel_rect(img_rect)

        path_mask = QPainterPath()
        path_mask.addRect(img_rect)
        path_mask.addRect(crop_px)
        painter.fillPath(path_mask, QColor(0, 0, 0, 175))

        # Rule of Thirds Grid inside Crop Rect
        painter.setPen(QPen(QColor(255, 255, 255, 55), 1, Qt.DashLine))
        x, y, w, h = crop_px.x(), crop_px.y(), crop_px.width(), crop_px.height()

        # Vertical grid
        painter.drawLine(QPointF(x + w / 3, y), QPointF(x + w / 3, y + h))
        painter.drawLine(QPointF(x + 2 * w / 3, y), QPointF(x + 2 * w / 3, y + h))
        # Horizontal grid
        painter.drawLine(QPointF(x, y + h / 3), QPointF(x + w, y + h / 3))
        painter.drawLine(QPointF(x, y + 2 * h / 3), QPointF(x + w, y + 2 * h / 3))

        # Crop Area Border (Crisp White Glow)
        painter.setPen(QPen(QColor(255, 255, 255, 230), 2))
        painter.drawRect(crop_px)

        # 8 Modern Corner / Edge Handles
        painter.setPen(QPen(QColor(0, 0, 0, 180), 1))
        painter.setBrush(QBrush(QColor(255, 255, 255)))

        hs = HANDLE_SIZE
        # Corners
        painter.drawRoundedRect(QRectF(x - hs/2, y - hs/2, hs, hs), 2, 2)
        painter.drawRoundedRect(QRectF(x + w - hs/2, y - hs/2, hs, hs), 2, 2)
        painter.drawRoundedRect(QRectF(x - hs/2, y + h - hs/2, hs, hs), 2, 2)
        painter.drawRoundedRect(QRectF(x + w - hs/2, y + h - hs/2, hs, hs), 2, 2)

        # Edges
        painter.drawRoundedRect(QRectF(x + w/2 - hs/2, y - hs/2, hs, hs), 2, 2)
        painter.drawRoundedRect(QRectF(x + w/2 - hs/2, y + h - hs/2, hs, hs), 2, 2)
        painter.drawRoundedRect(QRectF(x - hs/2, y + h/2 - hs/2, hs, hs), 2, 2)
        painter.drawRoundedRect(QRectF(x + w - hs/2, y + h/2 - hs/2, hs, hs), 2, 2)


class CropDialog(QDialog):
    def __init__(self, parent=None, pixmap: QPixmap = None, source_w: int = 1920, source_h: int = 1080, initial_params: dict = None):
        super().__init__(parent)
        self.setWindowTitle("Кадрирование видео")
        self.resize(820, 620)
        self.setMinimumSize(720, 520)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        if pixmap and not pixmap.isNull():
            pix_is_portrait = pixmap.height() > pixmap.width()
            source_is_portrait = source_h > source_w
            if pix_is_portrait != source_is_portrait:
                source_w, source_h = source_h, source_w

        self.source_w = source_w
        self.source_h = source_h
        self._drag_pos = None
        self.applied_crop_params = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Container
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: #11141A;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 12px;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(18, 14, 18, 14)
        container_layout.setSpacing(10)

        # Top Header
        header = QHBoxLayout()
        header.setSpacing(10)

        title = QLabel("КАДРИРОВАНИЕ ВИДЕО (CROP)")
        title.setStyleSheet("font-size: 13px; font-weight: 800; color: #FFFFFF; letter-spacing: 0.8px; background: transparent; border: none;")
        header.addWidget(title)

        self.res_badge = QLabel(f"исходный: {self.source_w}×{self.source_h} ➔ кадр: {self.source_w}×{self.source_h}")
        self.res_badge.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 6px;
            color: #EDEDED;
            font-size: 11px;
            font-weight: 700;
            font-family: 'Consolas', monospace;
            padding: 3px 8px;
        """)
        header.addWidget(self.res_badge)

        header.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setObjectName("TitleButton")
        close_btn.setStyleSheet("font-size: 13px; font-weight: bold; width: 28px; height: 28px; border-radius: 6px;")
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn)

        container_layout.addLayout(header)

        # Interactive Canvas
        self.canvas = CropCanvas()
        self.canvas.crop_changed.connect(self._on_crop_changed)
        container_layout.addWidget(self.canvas, stretch=1)

        # Aspect Ratio Toolbar
        preset_bar = QHBoxLayout()
        preset_bar.setSpacing(6)

        lbl_ratio = QLabel("ПРОПОРЦИИ:")
        lbl_ratio.setStyleSheet("color: #71717A; font-size: 11px; font-weight: 700; background: transparent; border: none;")
        preset_bar.addWidget(lbl_ratio)

        self.pill_free = QPushButton("Свободный")
        self.pill_free.setProperty("class", "ModePill")
        self.pill_free.setToolTip("Свободный выбор пропорций [0]")
        self.pill_free.clicked.connect(lambda: self._set_preset(None, self.pill_free))
        preset_bar.addWidget(self.pill_free)

        self.pill_1_1 = QPushButton("1:1 (Квадрат)")
        self.pill_1_1.setProperty("class", "ModePill")
        self.pill_1_1.setToolTip("Пропорция 1:1 Квадрат [1]")
        self.pill_1_1.clicked.connect(lambda: self._set_preset(1.0, self.pill_1_1))
        preset_bar.addWidget(self.pill_1_1)

        self.pill_9_16 = QPushButton("9:16 (Reels/Shorts)")
        self.pill_9_16.setProperty("class", "ModePill")
        self.pill_9_16.setToolTip("Пропорция 9:16 Reels/Shorts [2]")
        self.pill_9_16.clicked.connect(lambda: self._set_preset(9.0/16.0, self.pill_9_16))
        preset_bar.addWidget(self.pill_9_16)

        self.pill_16_9 = QPushButton("16:9 (YouTube)")
        self.pill_16_9.setProperty("class", "ModePill")
        self.pill_16_9.setToolTip("Пропорция 16:9 YouTube [3]")
        self.pill_16_9.clicked.connect(lambda: self._set_preset(16.0/9.0, self.pill_16_9))
        preset_bar.addWidget(self.pill_16_9)

        self.pill_4_5 = QPushButton("4:5 (Портрет)")
        self.pill_4_5.setProperty("class", "ModePill")
        self.pill_4_5.setToolTip("Пропорция 4:5 Портрет [4]")
        self.pill_4_5.clicked.connect(lambda: self._set_preset(4.0/5.0, self.pill_4_5))
        preset_bar.addWidget(self.pill_4_5)

        preset_bar.addStretch()

        reset_btn = QPushButton("↺ ВЕСЬ КАДР")
        reset_btn.setProperty("class", "GlassButton")
        reset_btn.setStyleSheet("font-size: 11px; font-weight: 700; padding: 4px 10px;")
        reset_btn.setToolTip("Сбросить выделение на весь исходный кадр [R]")
        reset_btn.clicked.connect(self._reset)
        preset_bar.addWidget(reset_btn)

        container_layout.addLayout(preset_bar)

        # Action Buttons
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)

        cancel_btn = QPushButton("ОТМЕНА")
        cancel_btn.setProperty("class", "GlassButton")
        cancel_btn.setStyleSheet("font-size: 11px; font-weight: 700; padding: 6px 14px;")
        cancel_btn.setToolTip("Отменить кадрирование [Esc]")
        cancel_btn.clicked.connect(self.reject)
        actions_layout.addWidget(cancel_btn)

        actions_layout.addStretch()

        apply_btn = QPushButton("✓ ПРИМЕНИТЬ КАДРИРОВАНИЕ")
        apply_btn.setObjectName("PrimaryButton")
        apply_btn.setStyleSheet("font-size: 12px; font-weight: 800; padding: 6px 18px; border-radius: 6px;")
        apply_btn.setToolTip("Применить кадрирование [ENTER]")
        apply_btn.clicked.connect(self._apply)
        actions_layout.addWidget(apply_btn)

        container_layout.addLayout(actions_layout)
        main_layout.addWidget(container)

        # Load image & initial params (Starts with Full Frame & Freeform crop!)
        self.canvas.set_source_image(pixmap, source_w=source_w, source_h=source_h)
        if initial_params and 'x_norm' in initial_params:
            self.canvas.crop_norm = QRectF(
                initial_params['x_norm'],
                initial_params['y_norm'],
                initial_params['w_norm'],
                initial_params['h_norm']
            )
            self.canvas.update()
            self._on_crop_changed(self.canvas.get_crop_params())
        else:
            self._reset()

    def _set_preset(self, ratio: float, active_btn: QPushButton):
        for btn in [self.pill_free, self.pill_1_1, self.pill_9_16, self.pill_16_9, self.pill_4_5]:
            btn.setProperty("active", "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        active_btn.setProperty("active", "true")
        active_btn.style().unpolish(active_btn)
        active_btn.style().polish(active_btn)

        self.canvas.set_aspect_ratio(ratio)

    def _reset(self):
        self.canvas.reset_crop()
        self._set_preset(None, self.pill_free)

    def _on_crop_changed(self, params: dict):
        sw = params.get('source_w', 1920)
        sh = params.get('source_h', 1080)
        cw = params.get('w', sw)
        ch = params.get('h', sh)
        self.res_badge.setText(f"ИСХОДНЫЙ: {sw}×{sh}  ➔  КАДР: {cw}×{ch}")

    def _apply(self):
        self.applied_crop_params = self.canvas.get_crop_params()
        self.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_0, Qt.Key_F, 1040, 1072):  # 0, F, or А / а
            self._set_preset(None, self.pill_free)
            event.accept()
            return
        elif key == Qt.Key_1:
            self._set_preset(1.0, self.pill_1_1)
            event.accept()
            return
        elif key == Qt.Key_2:
            self._set_preset(9.0/16.0, self.pill_9_16)
            event.accept()
            return
        elif key == Qt.Key_3:
            self._set_preset(16.0/9.0, self.pill_16_9)
            event.accept()
            return
        elif key == Qt.Key_4:
            self._set_preset(4.0/5.0, self.pill_4_5)
            event.accept()
            return
        elif key in (Qt.Key_R, 1050, 1082):  # R or К / к
            self._reset()
            event.accept()
            return
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self._apply()
            event.accept()
            return
        elif key == Qt.Key_Escape:
            self.reject()
            event.accept()
            return

        super().keyPressEvent(event)
