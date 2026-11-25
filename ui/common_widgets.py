"""Reusable UI widgets and mixins shared across dialogs."""
import os
import time
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget
)

from assets.icons import get_svg_pixmap
from core.process_utils import open_path_in_os


class CheckmarkBox(QFrame):
    def __init__(self, checked=True, parent=None):
        super().__init__(parent)
        self.setObjectName("CheckmarkBox")
        self.setFixedSize(22, 22)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._checked = checked

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        self.icon_lbl = QLabel(self)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.icon_lbl.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.icon_lbl)

        self._update_appearance()

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, val: bool):
        if self._checked != val:
            self._checked = val
            self._update_appearance()

    def _update_appearance(self):
        if self._checked:
            self.icon_lbl.setPixmap(get_svg_pixmap("check", color="#000000", size=13))
            self.setStyleSheet("""
                QFrame#CheckmarkBox {
                    background-color: #FFFFFF;
                    border: 1px solid #FFFFFF;
                    border-radius: 6px;
                }
            """)
        else:
            self.icon_lbl.clear()
            self.setStyleSheet("""
                QFrame#CheckmarkBox {
                    background-color: rgba(0, 0, 0, 0.45);
                    border: 1.5px solid rgba(255, 255, 255, 0.40);
                    border-radius: 6px;
                }
            """)


class DraggableMixin:
    """Allow dragging frameless dialogs while always clearing drag state on release."""

    def _init_draggable(self, drag_height: int = None):
        self._drag_pos = None
        self._drag_height = drag_height

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            drag_height = getattr(self, "_drag_height", None)
            if drag_height is None or event.position().y() < drag_height:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.LeftButton) and getattr(self, "_drag_pos", None) is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if getattr(self, "_drag_pos", None) is not None:
            self._drag_pos = None
            event.accept()
            return
        super().mouseReleaseEvent(event)


def show_recovery_sessions_dialog(
    parent,
    sessions: list,
    title: str = "Сохранённые сессии восстановления",
    header_text: str = "📁 Сохранённые файлы после сбоев перемещения:",
    on_delete=None,
):
    """Display preserved recovery staging directories with open and optional delete actions."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(540)
    dialog.setMinimumHeight(320)
    dialog.setStyleSheet("""
        QDialog { background-color: #121217; color: #EDEDED; }
        QLabel { color: #EDEDED; }
        QPushButton {
            background-color: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 6px;
            padding: 4px 10px;
            color: #EDEDED;
            font-weight: 600;
            font-size: 11px;
        }
        QPushButton:hover { background-color: rgba(255, 255, 255, 0.16); }
        QScrollArea { border: none; background: transparent; }
    """)

    d_layout = QVBoxLayout(dialog)
    d_layout.setContentsMargins(16, 16, 16, 16)
    d_layout.setSpacing(12)

    header = QLabel(header_text)
    header.setStyleSheet("font-weight: 700; font-size: 13px; color: #FFFFFF;")
    d_layout.addWidget(header)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll_content = QWidget()
    scroll_layout = QVBoxLayout(scroll_content)
    scroll_layout.setSpacing(8)

    for session in sessions:
        card = QFrame()
        card.setStyleSheet(
            "background: rgba(255, 255, 255, 0.04); "
            "border: 1px solid rgba(255, 255, 255, 0.1); "
            "border-radius: 8px; padding: 8px;"
        )
        card_layout = QVBoxLayout(card)

        path = session.get("path", "")
        is_accessible = session.get("is_accessible", True)
        files = session.get("files") or []
        files_info = ", ".join(f.get("name", "") for f in files) if files else "(нет файлов)"
        dt_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(session.get("timestamp", time.time())))

        if not is_accessible:
            lbl_title = QLabel(f"⚠️ ДИСК НЕДОСТУПЕН // {dt_str}")
            lbl_title.setStyleSheet("font-weight: 700; color: #F59E0B; font-size: 11px;")
        elif session.get("label"):
            lbl_title = QLabel(session["label"])
            lbl_title.setStyleSheet("font-weight: 700; color: #60A5FA; font-size: 11px;")
        else:
            lbl_title = QLabel(f"📅 {dt_str} // {len(files)} файлов")
            lbl_title.setStyleSheet("font-weight: 700; color: #60A5FA; font-size: 11px;")
        card_layout.addWidget(lbl_title)

        lbl_path = QLabel(f"Путь: {path}")
        lbl_path.setStyleSheet("color: #9CA3AF; font-size: 10px; font-family: monospace;")
        lbl_path.setWordWrap(True)
        card_layout.addWidget(lbl_path)

        if is_accessible:
            lbl_files = QLabel(f"Файлы: {files_info}")
            lbl_files.setStyleSheet("color: #D1D5DB; font-size: 11px;")
            lbl_files.setWordWrap(True)
            card_layout.addWidget(lbl_files)

        error_text = session.get("error", "")
        if error_text:
            lbl_err = QLabel(f"Причина: {error_text}")
            lbl_err.setStyleSheet("color: #9CA3AF; font-size: 10px;")
            lbl_err.setWordWrap(True)
            card_layout.addWidget(lbl_err)

        btn_row = QHBoxLayout()
        btn_open = QPushButton("📂 Открыть в Проводнике")
        btn_open.setEnabled(is_accessible and os.path.exists(path))
        btn_open.clicked.connect(lambda _, p=path: open_path_in_os(p))
        btn_row.addWidget(btn_open)

        if on_delete is not None:
            btn_del = QPushButton("🗑️ Удалить" if is_accessible else "🗑️ Удалить из списка")
            btn_del.setStyleSheet("color: #EF4444;")
            btn_del.clicked.connect(lambda _, p=path, c=card, acc=is_accessible: on_delete(dialog, p, c, acc))
            btn_row.addWidget(btn_del)

        btn_row.addStretch()
        card_layout.addLayout(btn_row)
        scroll_layout.addWidget(card)

    scroll_layout.addStretch()
    scroll.setWidget(scroll_content)
    d_layout.addWidget(scroll)

    btn_close = QPushButton("Закрыть")
    btn_close.clicked.connect(dialog.accept)
    d_layout.addWidget(btn_close, alignment=Qt.AlignRight)

    dialog.exec()
    return dialog
