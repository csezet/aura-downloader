from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog
from core.workers import cancel_worker


class WorkerDialog(QDialog):
    """Defer closing a modal until its own threads have stopped."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._owned_workers = []
        self._pending_result = None
        self._close_timer = QTimer(self)
        self._close_timer.setInterval(50)
        self._close_timer.timeout.connect(self._finish_pending_close)

    def done(self, result):
        running = [worker for worker in self._owned_workers if not worker.wait(0)]
        if running:
            self._pending_result = result
            self.setEnabled(False)
            for worker in running:
                cancel_worker(worker)
            self._close_timer.start()
            return
        self._close_timer.stop()
        super().done(result)

    def _finish_pending_close(self):
        if not any(not worker.wait(0) for worker in self._owned_workers):
            self.done(self._pending_result)

    def accept(self):
        self.done(QDialog.Accepted)

    def reject(self):
        self.done(QDialog.Rejected)

    def closeEvent(self, event):
        if any(not worker.wait(0) for worker in self._owned_workers):
            event.ignore()
            self.reject()
        else:
            super().closeEvent(event)
