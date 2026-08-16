"""Style sheets for the GUI, following the PyQt-Fluent-Widgets gallery pattern.

Each interface applies its own light/dark QSS. Thanks to
`qfluentwidgets.setStyleSheet` registration, styles are re-applied
automatically when the theme changes.
"""

from __future__ import annotations

import os
from enum import Enum

from qfluentwidgets import StyleSheetBase, Theme, qconfig


class StyleSheet(StyleSheetBase, Enum):
    CONVERT_INTERFACE = "convert_interface"
    TOOLS_INTERFACE = "tools_interface"

    def path(self, theme: Theme = Theme.AUTO) -> str:
        theme = qconfig.theme if theme == Theme.AUTO else theme
        folder = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "resource",
            "qss",
            theme.value.lower(),
        )
        return os.path.join(folder, self.value + ".qss")