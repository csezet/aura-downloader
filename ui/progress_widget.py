import logging
import os
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QGraphicsOpacityEffect
)
from PySide6.QtCore import Signal, QPropertyAnimation, QEasingCurve
from core.process_utils import open_path_in_os
from ui.animations import SmoothProgressBar

class ProgressWidget(QFrame):
    cancelled = Signal()
    retry_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("class", "GlassCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(88)
        self.setVisible(False)
        self._current_file_path = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # Header status and percent
        header_layout = QHBoxLayout()
        self.status_label = QLabel("⚡ СКАЧИВАНИЕ...")
        self.status_label.setStyleSheet("font-size: 11px; font-weight: 800; color: #FFFFFF; letter-spacing: 0.5px;")
        header_layout.addWidget(self.status_label)

        header_layout.addStretch()

        self.percent_label = QLabel("0.0%")
        self.percent_label.setStyleSheet("font-size: 12px; font-weight: 800; color: #FFFFFF; font-family: 'Consolas', monospace;")
        header_layout.addWidget(self.percent_label)

        layout.addLayout(header_layout)

        # Smooth Progress bar
        self.progress_bar = SmoothProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        # Bottom metrics & buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)

        self.metrics_label = QLabel("SPEED: -- MB/S // SIZE: 0 B / 0 B // ETA: --:--")
        self.metrics_label.setStyleSheet("font-size: 10px; color: #A1A1AA; font-family: 'Consolas', monospace;")
        bottom_layout.addWidget(self.metrics_label)

        bottom_layout.addStretch()

        # Action Buttons
        self.retry_btn = QPushButton("↺ ПОВТОРИТЬ СБОИ")
        self.retry_btn.setProperty("class", "GlassButton")
        self.retry_btn.setStyleSheet("color: #F59E0B; padding: 2px 8px; font-size: 10px; font-weight: 700;")
        self.retry_btn.clicked.connect(self.retry_requested.emit)
        self.retry_btn.setVisible(False)
        bottom_layout.addWidget(self.retry_btn)

        self.cancel_btn = QPushButton("✕ ОТМЕНА")
        self.cancel_btn.setProperty("class", "GlassButton")
        self.cancel_btn.setStyleSheet("color: #EF4444; padding: 2px 8px; font-size: 10px; font-weight: 700;")
        self.cancel_btn.clicked.connect(self.cancelled.emit)
        bottom_layout.addWidget(self.cancel_btn)

        self.open_file_btn = QPushButton("▶ ОТКРЫТЬ")
        self.open_file_btn.setProperty("class", "GlassButton")
        self.open_file_btn.setStyleSheet("padding: 2px 8px; font-size: 10px; font-weight: 700;")
        self.open_file_btn.clicked.connect(self._open_file)
        self.open_file_btn.setVisible(False)
        bottom_layout.addWidget(self.open_file_btn)

        self.open_dir_btn = QPushButton("📂 ПАПКА")
        self.open_dir_btn.setProperty("class", "GlassButton")
        self.open_dir_btn.setStyleSheet("padding: 2px 8px; font-size: 10px; font-weight: 700;")
        self.open_dir_btn.clicked.connect(self._open_dir)
        self.open_dir_btn.setVisible(False)
        bottom_layout.addWidget(self.open_dir_btn)

        layout.addLayout(bottom_layout)

        # Opacity Animation
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.anim_opacity = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_opacity.setDuration(240)
        self.anim_opacity.setEasingCurve(QEasingCurve.OutCubic)
        self.anim_opacity.finished.connect(self._on_hide_done)

    def start_progress(self, message="⚡ СКАЧИВАНИЕ..."):
        self.cancel_btn.setEnabled(True)
        self.retry_btn.setText("↺ ПОВТОРИТЬ СБОИ")
        self._current_file_path = None
        self._recovery_dir = None
        self._recovery_dirs = []
        self._save_dir = None
        self.progress_bar.setValue(0)
        self.percent_label.setText("0.0%")
        self.status_label.setText(message)
        self.status_label.setToolTip("")
        self.metrics_label.setText("ПОДГОТОВКА...")
        self.metrics_label.setToolTip("")
        self.setToolTip("")
        self.retry_btn.setVisible(False)
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setText("✕ ОТМЕНА")
        self.open_file_btn.setVisible(False)
        self.open_dir_btn.setVisible(False)
        self.open_dir_btn.setText("📂 ПАПКА")
        self.open_dir_btn.setToolTip("")
        
        self.setVisible(True)
        self.anim_opacity.stop()
        self.anim_opacity.setStartValue(0.0)
        self.anim_opacity.setEndValue(1.0)
        self.anim_opacity.start()

    def update_progress(self, data: dict):
        percent = data.get('percent', 0.0)
        self.progress_bar.setValue(int(percent))
        self.percent_label.setText(f"{percent:.1f}%")

        speed = data.get('speed_str', '-- MB/s')
        downloaded = data.get('downloaded_str', '0 B')
        total = data.get('total_str', '0 B')
        eta = data.get('eta_str', '--:--')

        self.metrics_label.setText(f"{downloaded} / {total} · {speed} · осталось {eta}")

    def complete_cancelled(self, summary):
        results = summary.get('results') or []
        errors = summary.get('errors') or []
        retry = summary.get('retry_items') or []
        self._current_file_path = results[-1].get('file_path') if results else None
        self._save_dir = summary.get('save_dir')
        self._recovery_dirs = [p for p in summary.get('recovery_dirs', []) if os.path.isdir(p)]
        self._recovery_dir = self._recovery_dirs[0] if self._recovery_dirs else None
        total = summary.get('total', 0)
        percent = len(results) / max(1, total) * 100
        self.progress_bar.setValue(int(percent))
        self.percent_label.setText(f"{percent:.0f}%")
        self.status_label.setText("ОЧЕРЕДЬ ОСТАНОВЛЕНА")
        self.metrics_label.setText(f"Сохранено: {len(results)}/{total} · осталось: {len(retry)} · ошибок: {len(errors)}")
        details = '\n'.join(errors)
        if self._recovery_dirs:
            details += '\n' + '\n'.join(self._recovery_dirs)
        self.status_label.setToolTip(details)
        self.metrics_label.setToolTip(details)
        self.retry_btn.setText("↺ ПРОДОЛЖИТЬ")
        self.retry_btn.setVisible(bool(retry))
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("✕ ЗАКРЫТЬ")
        self.cancel_btn.setVisible(True)
        self.open_file_btn.setVisible(bool(self._current_file_path and os.path.isfile(self._current_file_path)))
        self.open_dir_btn.setVisible(bool(self._recovery_dirs or self._save_dir))
        self.open_dir_btn.setText("📂 ВОССТАНОВЛЕНИЕ" if self._recovery_dirs else "📂 ПАПКА")
        self.open_dir_btn.setToolTip('\n'.join(self._recovery_dirs) if self._recovery_dirs else self._save_dir or '')
        self.setVisible(True)

    def complete(self, result: dict, errors: list = None, total: int = None, has_retry: bool = False, recovery_dirs: list = None):
        self._current_file_path = result.get('file_path') if isinstance(result, dict) else None
        self._save_dir = result.get('save_dir') if isinstance(result, dict) else None
        valid_rec = [d for d in (recovery_dirs or []) if d and os.path.exists(d)]
        self._recovery_dirs = valid_rec
        self._recovery_dir = valid_rec[0] if valid_rec else None

        if errors:
            success_count = result.get('success_count', 0) if isinstance(result, dict) else 0
            total_count = total or (success_count + len(errors))
            pct = int((success_count / max(1, total_count)) * 100) if total_count > 0 else 50
            self.progress_bar.setValue(pct)
            self.percent_label.setText(f"{pct}%")
            self.status_label.setText("ЧАСТИЧНО ЗАВЕРШЕНО")
            self.metrics_label.setText(f"СОХРАНЕНО: {success_count}/{total_count} // СБОЕВ: {len(errors)}")
            err_tooltip = "Ошибки при обработке очереди:\n" + "\n".join(f"• {e}" for e in errors)
            if self._recovery_dirs:
                err_tooltip += "\n\n📁 Каталоги восстановления:\n" + "\n".join(f"• {d}" for d in self._recovery_dirs)
            self.status_label.setToolTip(err_tooltip)
            self.metrics_label.setToolTip(err_tooltip)
            self.setToolTip(err_tooltip)
            self.retry_btn.setVisible(has_retry)
            self.cancel_btn.setVisible(True)
            self.cancel_btn.setText("✕ ЗАКРЫТЬ")
            self.open_file_btn.setVisible(bool(self._current_file_path and os.path.exists(self._current_file_path)))
            
            # Action button naming according to action
            if self._recovery_dirs:
                self.open_dir_btn.setVisible(True)
                self.open_dir_btn.setText("📂 ВОССТАНОВЛЕНИЕ")
                if len(self._recovery_dirs) == 1:
                    self.open_dir_btn.setToolTip(f"Открыть каталог восстановления:\n{self._recovery_dirs[0]}")
                else:
                    self.open_dir_btn.setToolTip(
                        f"Открыть каталог восстановления:\n{self._recovery_dirs[0]}\n"
                        f"(ещё каталогов: {len(self._recovery_dirs) - 1}). Нажмите для выбора."
                    )
            else:
                target_dir = self._current_file_path if (self._current_file_path and os.path.isdir(self._current_file_path)) else (os.path.dirname(self._current_file_path) if self._current_file_path else self._save_dir)
                self.open_dir_btn.setVisible(bool(target_dir and os.path.exists(target_dir)))
                self.open_dir_btn.setText("📂 ПАПКА")
                self.open_dir_btn.setToolTip(f"Открыть папку сохранения:\n{target_dir}" if target_dir else "")
        else:
            self.progress_bar.setValue(100)
            self.percent_label.setText("100%")
            self.status_label.setText("ГОТОВО!")
            self.metrics_label.setText(f"ФАЙЛ СОХРАНЕН // {result.get('file_size_str', '')}")
            self.status_label.setToolTip("")
            self.metrics_label.setToolTip("")
            self.setToolTip("")
            self.retry_btn.setVisible(False)
            self.cancel_btn.setVisible(False)
            self.open_file_btn.setVisible(True)
            self.open_dir_btn.setVisible(True)
            self.open_dir_btn.setText("📂 ПАПКА")
            target_dir = self._current_file_path if (self._current_file_path and os.path.isdir(self._current_file_path)) else (os.path.dirname(self._current_file_path) if self._current_file_path else self._save_dir)
            self.open_dir_btn.setToolTip(f"Открыть папку сохранения:\n{target_dir}" if target_dir else "")

        self.setVisible(True)

    def complete_failed(self, errors: list = None, total: int = None, has_retry: bool = False, recovery_dirs: list = None):
        self._current_file_path = None
        self._save_dir = None
        valid_rec = [d for d in (recovery_dirs or []) if d and os.path.exists(d)]
        self._recovery_dirs = valid_rec
        self._recovery_dir = valid_rec[0] if valid_rec else None

        err_list = errors or []
        total_count = total or len(err_list)
        self.progress_bar.setValue(0)
        self.percent_label.setText("0%")
        self.status_label.setText("ОШИБКА ОЧЕРЕДИ")
        self.metrics_label.setText(f"СОХРАНЕНО: 0/{total_count} // СБОЕВ: {len(err_list)}")
        err_tooltip = "Ошибки при обработке очереди:\n" + "\n".join(f"• {e}" for e in err_list)
        if self._recovery_dirs:
            err_tooltip += "\n\n📁 Каталоги восстановления:\n" + "\n".join(f"• {d}" for d in self._recovery_dirs)
        self.status_label.setToolTip(err_tooltip)
        self.metrics_label.setToolTip(err_tooltip)
        self.setToolTip(err_tooltip)
        self.retry_btn.setVisible(has_retry)
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setText("✕ ЗАКРЫТЬ")
        self.open_file_btn.setVisible(False)

        if self._recovery_dirs:
            self.open_dir_btn.setVisible(True)
            self.open_dir_btn.setText("📂 ВОССТАНОВЛЕНИЕ")
            if len(self._recovery_dirs) == 1:
                self.open_dir_btn.setToolTip(f"Открыть каталог восстановления:\n{self._recovery_dirs[0]}")
            else:
                self.open_dir_btn.setToolTip(
                    f"Открыть каталог восстановления:\n{self._recovery_dirs[0]}\n"
                    f"(ещё каталогов: {len(self._recovery_dirs) - 1}). Нажмите для выбора."
                )
        else:
            self.open_dir_btn.setVisible(False)

        self.setVisible(True)

    def set_error(self, err_msg: str, has_retry: bool = False, recovery_dir: str = None):
        self._current_file_path = None
        self._save_dir = None
        self._recovery_dir = recovery_dir if (recovery_dir and os.path.exists(recovery_dir)) else None
        self._recovery_dirs = [self._recovery_dir] if self._recovery_dir else []

        if self._recovery_dir:
            self.status_label.setText("ОШИБКА (ФАЙЛЫ СОХРАНЕНЫ)")
            folder_name = os.path.basename(self._recovery_dir)
            self.metrics_label.setText(f"Сохранено в: {folder_name} (нажмите 📂 ОТКРЫТЬ ПАПКУ)")
        else:
            self.status_label.setText("ОШИБКА")
            self.metrics_label.setText(err_msg[:80] if err_msg else "Ошибка получения информации")

        full_tooltip = err_msg or ""
        if self._recovery_dir:
            full_tooltip = (
                f"{err_msg}\n\n"
                f"📁 Папка восстановления: {self._recovery_dir}\n"
                f"Нажмите кнопку '📂 ОТКРЫТЬ ПАПКУ', чтобы открыть каталог в Проводнике и скопировать файлы."
            )
        self.status_label.setToolTip(full_tooltip)
        self.metrics_label.setToolTip(full_tooltip)
        self.setToolTip(full_tooltip)

        self.retry_btn.setVisible(has_retry)
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setText("✕ ЗАКРЫТЬ")
        self.open_file_btn.setVisible(False)

        if self._recovery_dir and os.path.exists(self._recovery_dir):
            self.open_dir_btn.setVisible(True)
            self.open_dir_btn.setText("📂 ОТКРЫТЬ ПАПКУ")
            self.open_dir_btn.setToolTip(f"Открыть папку с сохранёнными файлами:\n{self._recovery_dir}")
        else:
            self.open_dir_btn.setVisible(False)

        self.progress_bar.setValue(0)
        self.percent_label.setText("✕")
        self.setVisible(True)
        self.anim_opacity.stop()
        self.anim_opacity.setStartValue(self.opacity_effect.opacity())
        self.anim_opacity.setEndValue(1.0)
        self.anim_opacity.start()

    def hide_progress(self):
        self.anim_opacity.stop()
        self.anim_opacity.setStartValue(self.opacity_effect.opacity())
        self.anim_opacity.setEndValue(0.0)
        self.anim_opacity.start()

    def _on_hide_done(self):
        if self.opacity_effect.opacity() <= 0.05:
            self.setVisible(False)

    def _open_file(self):
        open_path_in_os(self._current_file_path)

    def _open_dir(self):
        btn_text = self.open_dir_btn.text()
        if "ВОССТАНОВЛЕНИЕ" in btn_text or (btn_text == "📂 ОТКРЫТЬ ПАПКУ" and self._recovery_dir):
            if len(self._recovery_dirs) > 1:
                self._show_recovery_choice_dialog(self._recovery_dirs)
            elif self._recovery_dirs and os.path.exists(self._recovery_dirs[0]):
                open_path_in_os(self._recovery_dirs[0])
            elif self._recovery_dir and os.path.exists(self._recovery_dir):
                open_path_in_os(self._recovery_dir)
        else:
            # Open successful download target directory
            target_dir = None
            if self._current_file_path and os.path.exists(self._current_file_path):
                target_dir = self._current_file_path if os.path.isdir(self._current_file_path) else os.path.dirname(self._current_file_path)
            elif self._save_dir and os.path.exists(self._save_dir):
                target_dir = self._save_dir
            if target_dir:
                open_path_in_os(target_dir)

    def _show_recovery_choice_dialog(self, recovery_dirs: list):
        try:
            from core.media_converter import _build_recovery_session
            from ui.common_widgets import show_recovery_sessions_dialog

            sessions = []
            for idx, p in enumerate(recovery_dirs, 1):
                session = _build_recovery_session(p, os.path.dirname(p))
                session["label"] = f"Элемент #{idx}: {os.path.basename(p)}"
                session["error"] = ""
                sessions.append(session)

            show_recovery_sessions_dialog(
                self,
                sessions,
                title="Выбор каталога восстановления",
                header_text=f"📁 Обнаружено каталогов восстановления: {len(recovery_dirs)}",
            )
        except Exception as e:
            logging.getLogger("aura.ui").warning("Error opening recovery choice dialog: %s", e)
