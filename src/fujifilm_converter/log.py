"""
Lightweight logging hooks shared by the CLI and the PySide6 GUI.

Pipeline modules report through log.info() instead of print() so the GUI
can capture the same output. When no handler is registered we fall back to
print() so the CLI behaves exactly as before.
"""

from __future__ import annotations

from typing import Callable, List

_handlers: List[Callable[[str], None]] = []


def add_handler(handler: Callable[[str], None]) -> None:
    if handler not in _handlers:
        _handlers.append(handler)


def remove_handler(handler: Callable[[str], None]) -> None:
    if handler in _handlers:
        _handlers.remove(handler)


def info(msg: str) -> None:
    if _handlers:
        for handler in _handlers:
            handler(msg)
    else:
        print(msg)