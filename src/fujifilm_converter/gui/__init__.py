"""
PySide6 + PySide6-Fluent-Widgets desktop GUI for fujifilm-converter.

Entry points:
    python -m fujifilm_converter.gui
    fuji-convert-gui
"""

from .app import main, run_app

__all__ = ["main", "run_app"]