"""Keep background threads alive until cooperative cancellation has finished."""
import logging
from PySide6.QtCore import QObject, QThread, QTimer, Slot
from PySide6.QtWidgets import QApplication


class CancellableThread(QThread):
    def cancel(self):
        self.requestInterruption()


class WorkerRegistry(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.workers = []
        self.stopping = False

    def track(self, worker):
        if worker not in self.workers:
            self.workers.append(worker)
            worker.finished.connect(self._on_finished)
            for name in ("download_error", "info_error"):
                signal = getattr(worker, name, None)
                if signal is not None:
                    task_name = type(worker).__name__
                    signal.connect(lambda message, task=task_name: logging.getLogger("aura.worker").error("%s: %s", task, message))
        return worker

    @Slot()
    def _on_finished(self):
        worker = self.sender()
        self._forget_finished(worker)

    def _forget_finished(self, worker):
        if worker not in self.workers:
            return
        if not worker.wait(0):
            QTimer.singleShot(20, lambda: self._forget_finished(worker))
            return
        self.workers.remove(worker)

    def is_busy(self):
        return any(not worker.wait(0) for worker in self.workers)

    def cancel_all(self):
        for worker in list(self.workers):
            cancel_worker(worker)


def worker_registry():
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("Background UI workers require a QApplication.")
    if not hasattr(app, "_aura_worker_registry"):
        app._aura_worker_registry = WorkerRegistry(app)
    return app._aura_worker_registry


def cancel_worker(worker):
    worker.requestInterruption()
    cancel = getattr(worker, "cancel", None)
    if cancel:
        cancel()


def start_worker(worker, owner=None):
    registry = worker_registry()
    if registry.stopping:
        cancel_worker(worker)
        return worker
    registry.track(worker)
    if owner is not None:
        window = owner.window()
        if hasattr(window, "_owned_workers"):
            window._owned_workers.append(worker)
    worker.start()
    return worker


def shutdown_background_tasks():
    """Fallback for app.quit()/system exit; normal window closing waits asynchronously."""
    registry = worker_registry()
    registry.stopping = True
    registry.cancel_all()
    for worker in list(registry.workers):
        worker.wait()
