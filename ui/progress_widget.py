import os
import subprocess
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
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

    def start_progress(self, message="⚡ СКАЧИВАНИЕ..."):
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

        self.metrics_label.setText(f"SPEED: {speed} // {downloaded} / {total} // ETA: {eta}")

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
        self.anim_opacity.finished.connect(self._on_hide_done)
        self.anim_opacity.start()

    def _on_hide_done(self):
        if self.opacity_effect.opacity() <= 0.05:
            self.setVisible(False)

    def _open_file(self):
        if self._current_file_path and os.path.exists(self._current_file_path):
            try:
                os.startfile(self._current_file_path)
            except Exception:
                pass

    def _open_dir(self):
        btn_text = self.open_dir_btn.text()
        if "ВОССТАНОВЛЕНИЕ" in btn_text or (btn_text == "📂 ОТКРЫТЬ ПАПКУ" and self._recovery_dir):
            if len(self._recovery_dirs) > 1:
                self._show_recovery_choice_dialog(self._recovery_dirs)
            elif self._recovery_dirs and os.path.exists(self._recovery_dirs[0]):
                try:
                    os.startfile(self._recovery_dirs[0])
                except Exception:
                    pass
            elif self._recovery_dir and os.path.exists(self._recovery_dir):
                try:
                    os.startfile(self._recovery_dir)
                except Exception:
                    pass
        else:
            # Open successful download target directory
            target_dir = None
            if self._current_file_path and os.path.exists(self._current_file_path):
                target_dir = self._current_file_path if os.path.isdir(self._current_file_path) else os.path.dirname(self._current_file_path)
            elif self._save_dir and os.path.exists(self._save_dir):
                target_dir = self._save_dir
            if target_dir and os.path.exists(target_dir):
                try:
                    os.startfile(target_dir)
                except Exception:
                    pass

    def _show_recovery_choice_dialog(self, recovery_dirs: list):
        try:
            import json
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QScrollArea, QWidget, QFrame, QHBoxLayout

            dialog = QDialog(self)
            dialog.setWindowTitle("Выбор каталога восстановления")
            dialog.setMinimumWidth(520)
            dialog.setMinimumHeight(300)
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
            d_layout.setSpacing(10)

            header = QLabel(f"📁 Обнаружено каталогов восстановления: {len(recovery_dirs)}")
            header.setStyleSheet("font-weight: 700; font-size: 13px; color: #FFFFFF;")
            d_layout.addWidget(header)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            content = QWidget()
            c_layout = QVBoxLayout(content)
            c_layout.setSpacing(8)

            for idx, p in enumerate(recovery_dirs, 1):
                card = QFrame()
                card.setStyleSheet("background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 8px;")
                card_lay = QVBoxLayout(card)

                marker_p = os.path.join(p, ".aura_recovery.json")
                files_desc = ""
                if os.path.exists(marker_p):
                    try:
                        with open(marker_p, 'r', encoding='utf-8') as mf:
                            m_data = json.load(mf)
                            files_list = m_data.get('files', [])
                            if files_list:
                                files_desc = ", ".join(f.get('name', '') for f in files_list)
                    except Exception:
                        pass
                if not files_desc and os.path.exists(p):
                    try:
                        files_desc = ", ".join(f for f in os.listdir(p) if not f.startswith('.'))
                    except Exception:
                        files_desc = os.path.basename(p)

                lbl_title = QLabel(f"Элемент #{idx}: {os.path.basename(p)}")
                lbl_title.setStyleSheet("font-weight: 700; color: #60A5FA; font-size: 11px;")
                card_lay.addWidget(lbl_title)

                lbl_path = QLabel(f"Путь: {p}")
                lbl_path.setStyleSheet("color: #9CA3AF; font-size: 10px; font-family: monospace;")
                lbl_path.setWordWrap(True)
                card_lay.addWidget(lbl_path)

                lbl_files = QLabel(f"Файлы: {files_desc}")
                lbl_files.setStyleSheet("color: #D1D5DB; font-size: 10px;")
                lbl_files.setWordWrap(True)
                card_lay.addWidget(lbl_files)

                btn_row = QHBoxLayout()
                btn_open = QPushButton("📂 Открыть каталог в Проводнике")
                btn_open.clicked.connect(lambda _, target=p: os.startfile(target) if os.path.exists(target) else None)
                btn_row.addWidget(btn_open)
                btn_row.addStretch()
                card_lay.addLayout(btn_row)

                c_layout.addWidget(card)

            c_layout.addStretch()
            scroll.setWidget(content)
            d_layout.addWidget(scroll)

            btn_close = QPushButton("Закрыть")
            btn_close.clicked.connect(dialog.accept)
            d_layout.addWidget(btn_close, alignment=Qt.AlignRight)

            dialog.exec()
        except Exception as e:
            print(f"Error opening recovery choice dialog: {e}")
