"""Keep background threads alive until cooperative cancellation has finished."""
import logging
import threading
import time
import weakref
from PySide6.QtCore import QObject, QRunnable, QThread, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication

_fallback_pool = None


def thumbnail_thread_pool() -> QThreadPool:
    """Shared bounded thread pool for network thumbnail downloads."""
    app = QApplication.instance()
    if app is not None:
        if not hasattr(app, "_aura_thumbnail_pool"):
            pool = QThreadPool(app)
            pool.setMaxThreadCount(4)
            app._aura_thumbnail_pool = pool
        return app._aura_thumbnail_pool
    global _fallback_pool
    if _fallback_pool is None:
        _fallback_pool = QThreadPool()
        _fallback_pool.setMaxThreadCount(4)
    return _fallback_pool


class CancellableThread(QThread):
    def cancel(self):
        self.requestInterruption()


class _PooledRunnable(QRunnable):
    def __init__(self, owner):
        super().__init__()
        self.setAutoDelete(False)
        self._owner = owner

    def run(self):
        self._owner._execute_from_pool()


class PooledWorker(QObject):
    """QThread-compatible worker executed on a bounded QThreadPool."""
    finished = Signal()

    def __init__(self, pool: QThreadPool = None, parent=None):
        super().__init__(parent)
        self._pool = pool or thumbnail_thread_pool()
        self._interrupted = threading.Event()
        self._done = threading.Event()
        self._done.set()
        self._state_lock = threading.Lock()
        self._state = "idle"
        self._runnable = None

    def requestInterruption(self):
        self._interrupted.set()

    def isInterruptionRequested(self) -> bool:
        return self._interrupted.is_set()

    def cancel(self):
        self._interrupted.set()
        emit_now = False
        with self._state_lock:
            if self._state == "queued" and self._runnable is not None:
                if self._pool.tryTake(self._runnable):
                    self._state = "finished"
                    self._runnable = None
                    self._done.set()
                    emit_now = True
        if emit_now:
            self.finished.emit()

    def start(self):
        emit_now = False
        with self._state_lock:
            if self._state != "idle":
                return
            if self._interrupted.is_set():
                self._state = "finished"
                self._done.set()
                emit_now = True
            else:
                self._state = "queued"
                self._done.clear()
                self._runnable = _PooledRunnable(self)
                self._pool.start(self._runnable)
        if emit_now:
            self.finished.emit()

    def _execute_from_pool(self):
        with self._state_lock:
            if self._state != "queued":
                return
            self._state = "running"
        try:
            if not self._interrupted.is_set():
                self.run()
        finally:
            with self._state_lock:
                self._state = "finished"
                self._runnable = None
            try:
                self.finished.emit()
            finally:
                self._done.set()

    def run(self):
        pass

    def isRunning(self) -> bool:
        return not self._done.is_set()

    def wait(self, msecs: int = -1) -> bool:
        if msecs == 0:
            return self._done.is_set()
        if msecs is None or msecs < 0:
            return self._done.wait()
        return self._done.wait(msecs / 1000.0)


class WorkerRegistry(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.workers = []
        self._worker_owners = {}
        self.stopping = False

    def track(self, worker, owner_window=None):
        if worker not in self.workers:
            self.workers.append(worker)
            worker.finished.connect(self._on_finished)
            for name in ("download_error", "info_error"):
                signal = getattr(worker, name, None)
                if signal is not None:
                    task_name = type(worker).__name__
                    signal.connect(lambda message, task=task_name: logging.getLogger("aura.worker").error("%s: %s", task, message))
        if owner_window is not None and hasattr(owner_window, "_owned_workers"):
            if worker not in owner_window._owned_workers:
                owner_window._owned_workers.append(worker)
            owners = self._worker_owners.setdefault(worker, [])
            if not any(ref() is owner_window for ref in owners):
                owners.append(weakref.ref(owner_window))
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
        for owner_ref in self._worker_owners.pop(worker, ()):
            owner_window = owner_ref()
            if owner_window is not None and hasattr(owner_window, "_owned_workers"):
                try:
                    owner_window._owned_workers.remove(worker)
                except ValueError:
                    pass

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
    owner_window = owner.window() if owner is not None else None
    registry.track(worker, owner_window=owner_window)
    worker.start()
    return worker


def shutdown_background_tasks(timeout_ms: int = 5000):
    """Fallback for app.quit()/system exit; normal window closing waits asynchronously."""
    registry = worker_registry()
    registry.stopping = True
    registry.cancel_all()
    deadline = time.monotonic() + max(0.0, timeout_ms / 1000.0)
    for worker in list(registry.workers):
        remaining = max(1, int((deadline - time.monotonic()) * 1000))
        if not worker.wait(remaining):
            logging.getLogger("aura.worker").warning(
                "Timed out waiting for background worker %s during shutdown",
                type(worker).__name__,
            )
