"""Shared Qt test helpers."""

import os
import time
from typing import Callable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from premerge.ui import theme  # noqa: E402


def app() -> QApplication:
    """The singleton QApplication, themed."""
    inst = QApplication.instance()
    if inst is None:
        inst = QApplication([])
        theme.apply(inst)
    return inst


def wait_until(pred: Callable[[], bool], timeout: float = 5.0) -> bool:
    """Pump events until `pred()` is true or the timeout passes."""
    app()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        if pred():
            return True
        time.sleep(0.01)
    return pred()
