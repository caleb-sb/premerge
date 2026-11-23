"""Run blocking work on the global thread pool and deliver results on the GUI thread."""

import sys
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal

_inflight: set[Any] = set()


class _Bridge(QObject):
    """Lives in the GUI thread; its queued signal runs callbacks there."""

    delivered = Signal(object, object, object)

    def __init__(self) -> None:
        super().__init__()
        self.delivered.connect(self._deliver, Qt.ConnectionType.QueuedConnection)

    def _deliver(self, callback: Callable | None, value: Any, holder: Any) -> None:
        _inflight.discard(holder)
        if callback is not None:
            callback(value)


_bridge: _Bridge | None = None


def _get_bridge() -> _Bridge:
    global _bridge
    if _bridge is None:
        _bridge = _Bridge()
    return _bridge


def _report(exc: BaseException) -> None:
    traceback.print_exception(exc, file=sys.stderr)


class _Task(QRunnable):
    def __init__(self, bridge: _Bridge, fn: Callable, args: tuple, kwargs: dict,
                 on_done: Callable | None, on_error: Callable | None) -> None:
        super().__init__()
        self.bridge, self.fn, self.args, self.kwargs = bridge, fn, args, kwargs
        self.on_done, self.on_error = on_done, on_error

    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # delivered to on_error on the GUI thread
            self.bridge.delivered.emit(self.on_error or _report, exc, self)
        else:
            self.bridge.delivered.emit(self.on_done, result, self)


def run(fn: Callable, *args: Any, on_done: Callable | None = None,
        on_error: Callable | None = None, **kwargs: Any) -> None:
    """Run `fn(*args, **kwargs)` in the thread pool; callbacks run on the GUI thread."""
    task = _Task(_get_bridge(), fn, args, kwargs, on_done, on_error)
    task.setAutoDelete(False)
    _inflight.add(task)
    QThreadPool.globalInstance().start(task)
