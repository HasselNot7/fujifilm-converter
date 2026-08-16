"""
Background worker that runs pipeline work on a QThread so the UI never
blocks. All log.info() output produced while the worker runs is forwarded
to the GUI thread through the log_line signal.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from .. import log


class Worker(QThread):
    log_line = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def _on_log(self, msg: str) -> None:
        self.log_line.emit(msg)

    def run(self) -> None:
        log.add_handler(self._on_log)
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            log.remove_handler(self._on_log)