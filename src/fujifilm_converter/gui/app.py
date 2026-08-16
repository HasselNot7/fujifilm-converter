"""
PySide6 desktop GUI for fujifilm-converter built with PySide6-Fluent-Widgets.

The UI follows the PyQt-Fluent-Widgets gallery layout: each page has a fixed
header bar (title + subtitle + action buttons), and the content scrolls below
it as a set of fluent cards. Light/dark styling is provided through per-page
QSS files in resource/qss and re-applies automatically on theme change.
"""

from __future__ import annotations

import os
import platform
import sys
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QAbstractItemView, QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidgetItem, QMenu, QVBoxLayout, QWidget

import shiboken6

from qfluentwidgets.common.config import QConfig

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ComboBox,
    ConfigItem,
    FluentIcon,
    HeaderCardWidget,
    IconWidget,
    InfoBadge,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    ListWidget,
    MessageBox,
    MSFluentWindow,
    NavigationItemPosition,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    ScrollArea,
    StateToolTip,
    StrongBodyLabel,
    SwitchButton,
    TextBrowser,
    TitleLabel,
    qconfig,
    toggleTheme,
    setTheme,
    setThemeColor,
    Theme,
)

from .. import log
from ..cameras import list_presets
from ..converters import (
    DNGLAB_ENV,
    EXIFTOOL_ENV,
    _cached_dnglab,
    cached_exiftool_install,
    cache_dir,
    find_adobe_dng_converter,
    find_dnglab,
    find_exiftool,
    install_dnglab,
    install_exiftool,
    is_valid_dnglab,
    is_valid_exiftool,
    uninstall_dnglab,
    uninstall_exiftool,
)
from ..core import collect_input_paths, process_file, print_status
from .i18n import t, tr
from .style import StyleSheet
from .worker import Worker

APP_TITLE = "Fujifilm Converter"

_APP_ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resource", "images", "app.png")
APP_ICON = _APP_ICON_PATH if os.path.isfile(_APP_ICON_PATH) else ":/qfluentwidgets/images/logo.png"


class AppConfig(QConfig):
    """Application settings persisted through qconfig (class attributes only)."""

    lastDialogDir = ConfigItem("General", "lastDialogDir", "")
    exiftoolPath = ConfigItem("General", "exiftoolPath", "")
    dnglabPath = ConfigItem("General", "dnglabPath", "")
    language = ConfigItem("General", "language", "zh")


app_cfg = AppConfig()


class PageHeader(QWidget):
    """Gallery-style page header: title, subtitle and right-aligned actions."""

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("pageHeader")
        self.setMinimumHeight(150)

        self.titleLabel = TitleLabel(title, self)
        self.subtitleLabel = CaptionLabel(subtitle, self)
        self.subtitleLabel.setWordWrap(True)

        self.vBoxLayout = QVBoxLayout(self)
        self.buttonLayout = QHBoxLayout()

        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.setContentsMargins(36, 22, 36, 16)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addSpacing(4)
        self.vBoxLayout.addWidget(self.subtitleLabel)
        self.vBoxLayout.addSpacing(8)
        self.vBoxLayout.addLayout(self.buttonLayout, 1)
        self.vBoxLayout.setAlignment(Qt.AlignTop)

        self.buttonLayout.setSpacing(8)
        self.buttonLayout.setContentsMargins(0, 0, 0, 0)
        self.buttonLayout.addStretch(1)

    def addActionButton(self, button) -> None:
        """Add an action button to the right side of the header."""
        self.buttonLayout.addWidget(button)

    def set_texts(self, title: str, subtitle: str) -> None:
        self.titleLabel.setText(title)
        self.subtitleLabel.setText(subtitle)


class InterfaceBase(ScrollArea):
    """Gallery-style scroll page: fixed header on top, scrolling card content."""

    def __init__(self, objectName: str, title: str, subtitle: str, parent=None):
        super().__init__(parent=parent)
        self.setObjectName(objectName)

        self.header = PageHeader(title, subtitle, self)
        self.view = QWidget(self)
        self.view.setObjectName("view")

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._headerHeight = self.header.minimumHeight()
        self.setViewportMargins(0, self._headerHeight, 0, 0)
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.enableTransparentBackground()

        self.vBoxLayout = QVBoxLayout(self.view)
        self.vBoxLayout.setSpacing(20)
        self.vBoxLayout.setContentsMargins(36, 20, 36, 36)
        self.vBoxLayout.setAlignment(Qt.AlignTop)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        height = max(150, self.header.sizeHint().height())
        self.header.resize(self.width(), height)
        if self._headerHeight != height:
            self._headerHeight = height
            self.setViewportMargins(0, height, 0, 0)
        self.header.raise_()
        self._place_state()

    def _place_state(self) -> None:
        """Keep the state tooltip anchored at the top-right, below the header."""
        tip = getattr(self, "_stateToolTip", None)
        if tip is not None and shiboken6.isValid(tip) and tip.isVisible():
            x = max(0, self.width() - tip.width() - 24)
            tip.move(x, self.header.height() + 8)


class ElidedLabel(QLabel):
    """Single-line label that elides long paths in the middle."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._fullText = text

    def setFullText(self, text: str) -> None:
        self._fullText = text
        self._updateElide()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._updateElide()

    def _updateElide(self) -> None:
        width = max(40, self.width())
        QLabel.setText(self, self.fontMetrics().elidedText(self._fullText, Qt.ElideMiddle, width))


class FileItemWidget(QWidget):
    """Row widget inside the input list: status badge + path + retry button."""

    def __init__(self, path: str, status: str, on_retry, parent=None):
        super().__init__(parent)
        self.path = path
        self.badge = InfoBadge.info("", self)
        self.pathLabel = ElidedLabel(path, self)
        self.pathLabel.setToolTip(path)
        self.retryButton = PushButton(tr("btn_retry"), self)
        self.retryButton.setFixedWidth(64)
        self.retryButton.setVisible(False)
        self.retryButton.clicked.connect(lambda: on_retry(path))

        row = QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(8)
        row.addWidget(self.badge, 0, Qt.AlignVCenter)
        row.addWidget(self.pathLabel, 1)
        row.addWidget(self.retryButton, 0, Qt.AlignVCenter)

        self.set_status(status)

    def set_status(self, status: str) -> None:
        self.status = status
        old = self.layout().itemAt(0).widget()
        if status == "success":
            new = InfoBadge.success(tr("st_success"), self)
        elif status == "failed":
            new = InfoBadge.error(tr("st_failed"), self)
        elif status == "processing":
            new = InfoBadge.info(tr("st_processing"), self)
        else:
            new = InfoBadge.custom(tr("st_pending"), "#8a8a8a", "#8a8a8a", self)
        self.badge = new
        self.layout().replaceWidget(old, new)
        old.deleteLater()
        new.show()
        self.retryButton.setVisible(status == "failed")
        self.retryButton.setText(tr("btn_retry"))


class DropListWidget(ListWidget):
    """List that accepts file/folder drops and forwards them to a callback."""

    def __init__(self, on_drop, parent=None):
        super().__init__(parent)
        self._onDrop = on_drop
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in e.mimeData().urls() if url.isLocalFile()]
            if paths:
                self._onDrop(paths)
            e.acceptProposedAction()
        else:
            super().dropEvent(e)


class InputCard(HeaderCardWidget):
    """Card for choosing RAW/DNG files or directories. Supports drag & drop
    and shows a per-file conversion status."""

    retryRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBorderRadius(8)

        self.countBadge = InfoBadge.info(0, self)
        self.listWidget = DropListWidget(self._add_paths, self)
        self.listPanel = QFrame(self)
        self.listPanel.setObjectName("listPanel")
        self.addFileButton = PushButton("", self, FluentIcon.DOCUMENT)
        self.addFolderButton = PushButton("", self, FluentIcon.FOLDER)
        self.removeButton = PushButton("", self)
        self.clearButton = PushButton("", self)
        self.dropHint = CaptionLabel("", self)
        self.dropHint.setTextColor(QColor(96, 96, 96), QColor(216, 216, 216))
        self.dropHint.setAlignment(Qt.AlignCenter)

        panelLayout = QVBoxLayout(self.listPanel)
        panelLayout.setContentsMargins(2, 2, 2, 2)
        panelLayout.setSpacing(2)
        panelLayout.addWidget(self.listWidget)
        self.listWidget.setMinimumHeight(160)

        buttonLayout = QHBoxLayout()
        buttonLayout.setContentsMargins(0, 0, 0, 0)
        buttonLayout.setSpacing(8)
        buttonLayout.addWidget(self.addFileButton)
        buttonLayout.addWidget(self.addFolderButton)
        buttonLayout.addStretch(1)
        buttonLayout.addWidget(self.removeButton)
        buttonLayout.addWidget(self.clearButton)

        self.headerLayout.addWidget(self.countBadge, 0, Qt.AlignRight)

        contentLayout = QVBoxLayout()
        contentLayout.setContentsMargins(0, 0, 0, 0)
        contentLayout.setSpacing(12)
        contentLayout.addWidget(self.listPanel, 1)
        contentLayout.addWidget(self.dropHint)
        contentLayout.addLayout(buttonLayout)
        self.viewLayout.addLayout(contentLayout, 1)

        self.addFileButton.clicked.connect(self._add_files)
        self.addFolderButton.clicked.connect(self._add_folder)
        self.removeButton.clicked.connect(self._remove_selected)
        self.clearButton.clicked.connect(self._clear)
        self.listWidget.model().rowsInserted.connect(self._update_count)
        self.listWidget.model().rowsRemoved.connect(self._update_count)
        self.apply_language()

    def apply_language(self) -> None:
        self.setTitle(tr("input_title"))
        self.addFileButton.setText(tr("btn_add_files"))
        self.addFolderButton.setText(tr("btn_add_folder"))
        self.removeButton.setText(tr("btn_remove_selected"))
        self.clearButton.setText(tr("btn_clear"))
        self.dropHint.setText(tr("hint_drop"))
        for i in range(self.listWidget.count()):
            item = self.listWidget.item(i)
            widget = self.listWidget.itemWidget(item)
            if isinstance(widget, FileItemWidget):
                widget.set_status(widget.status)

    def _update_count(self) -> None:
        self.countBadge.setText(str(self.listWidget.count()))

    def _clear(self) -> None:
        self.listWidget.clear()

    def _add_files(self) -> None:
        start_dir = qconfig.get(app_cfg.lastDialogDir)
        if start_dir and not os.path.isdir(start_dir):
            start_dir = ""
        paths, _ = QFileDialog.getOpenFileNames(
            self.window(),
            tr("dlg_open_files"),
            start_dir,
            tr("dlg_file_filter"),
        )
        if paths:
            qconfig.set(app_cfg.lastDialogDir, os.path.dirname(paths[0]))
        self._add_paths(paths)

    def _add_folder(self) -> None:
        start_dir = qconfig.get(app_cfg.lastDialogDir)
        if start_dir and not os.path.isdir(start_dir):
            start_dir = ""
        folder = QFileDialog.getExistingDirectory(self.window(), tr("dlg_open_folder"), start_dir)
        if folder:
            qconfig.set(app_cfg.lastDialogDir, folder)
            self._add_paths([folder])

    def _add_paths(self, paths: List[str]) -> None:
        try:
            expanded = collect_input_paths(list(paths))
        except (FileNotFoundError, RuntimeError):
            expanded = []
        existing = {self.listWidget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.listWidget.count())}
        for path in expanded:
            if path not in existing:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, path)
                widget = FileItemWidget(path, "pending", self.retryRequested.emit)
                item.setSizeHint(widget.sizeHint())
                self.listWidget.addItem(item)
                self.listWidget.setItemWidget(item, widget)

    def _remove_selected(self) -> None:
        for item in self.listWidget.selectedItems():
            self.listWidget.takeItem(self.listWidget.row(item))

    def paths(self) -> List[str]:
        return [self.listWidget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.listWidget.count())]

    def set_file_status(self, path: str, status: str) -> None:
        for i in range(self.listWidget.count()):
            item = self.listWidget.item(i)
            if os.path.normcase(item.data(Qt.ItemDataRole.UserRole)) == os.path.normcase(path):
                widget = self.listWidget.itemWidget(item)
                if isinstance(widget, FileItemWidget):
                    widget.set_status(status)
                return

    def set_all_status(self, status: str) -> None:
        for i in range(self.listWidget.count()):
            widget = self.listWidget.itemWidget(self.listWidget.item(i))
            if isinstance(widget, FileItemWidget):
                widget.set_status(status)


class CameraCard(HeaderCardWidget):
    """Card for choosing the camera identity (preset or custom)."""

    def __init__(self, presets: List[str], parent=None):
        super().__init__(parent)
        self.setBorderRadius(8)

        self.presetCombo = ComboBox(self)
        self.presetCombo.addItems(presets)
        self.presetCombo.setCurrentText("fuji")
        self.presetCombo.setMinimumWidth(200)

        self.customSwitch = SwitchButton(self)
        self.makeEdit = LineEdit(self)
        self.modelEdit = LineEdit(self)
        self.ucmEdit = LineEdit(self)

        self.makeEdit.setClearButtonEnabled(True)
        self.modelEdit.setClearButtonEnabled(True)
        self.ucmEdit.setClearButtonEnabled(True)

        self.presetLabel = StrongBodyLabel(self)
        presetRow = QHBoxLayout()
        presetRow.setContentsMargins(0, 0, 0, 0)
        presetRow.setSpacing(12)
        presetRow.addWidget(self.presetLabel)
        presetRow.addWidget(self.presetCombo, 1)
        presetRow.addStretch(1)

        self.presetHint = CaptionLabel(self)
        self.presetHint.setTextColor(QColor(96, 96, 96), QColor(216, 216, 216))
        self.presetHint.setWordWrap(True)

        self.customLabel = StrongBodyLabel(self)
        customRow = QHBoxLayout()
        customRow.setContentsMargins(0, 0, 0, 0)
        customRow.setSpacing(12)
        customRow.addWidget(self.customLabel)
        customRow.addStretch(1)
        customRow.addWidget(self.customSwitch)

        self._customHint = CaptionLabel(self)
        self._customHint.setTextColor(QColor(96, 96, 96), QColor(216, 216, 216))
        self._customHint.setWordWrap(True)
        self._customHint.setVisible(False)

        contentLayout = QVBoxLayout()
        contentLayout.setContentsMargins(0, 0, 0, 0)
        contentLayout.setSpacing(10)
        contentLayout.addLayout(presetRow)
        contentLayout.addWidget(self.presetHint)
        contentLayout.addLayout(customRow)
        contentLayout.addWidget(self._customHint)
        contentLayout.addWidget(self.makeEdit)
        contentLayout.addWidget(self.modelEdit)
        contentLayout.addWidget(self.ucmEdit)
        self.viewLayout.addLayout(contentLayout, 1)

        self._update_custom_enabled(False)
        self.customSwitch.checkedChanged.connect(self._update_custom_enabled)
        self.apply_language()

    def apply_language(self) -> None:
        self.setTitle(tr("camera_title"))
        self.presetLabel.setText(tr("label_preset"))
        self.presetHint.setText(tr("hint_preset"))
        self.customLabel.setText(tr("label_custom"))
        self._customHint.setText(tr("hint_custom"))
        self.makeEdit.setPlaceholderText(tr("ph_make"))
        self.modelEdit.setPlaceholderText(tr("ph_model"))
        self.ucmEdit.setPlaceholderText(tr("ph_ucm"))

    def _update_custom_enabled(self, enabled: bool) -> None:
        self.makeEdit.setEnabled(enabled)
        self.modelEdit.setEnabled(enabled)
        self.ucmEdit.setEnabled(enabled)
        self._customHint.setVisible(enabled)
        if not enabled:
            self.makeEdit.clear()
            self.modelEdit.clear()
            self.ucmEdit.clear()

    def camera_args(self):
        if self.customSwitch.isChecked():
            make = self.makeEdit.text().strip()
            model = self.modelEdit.text().strip()
            ucm = self.ucmEdit.text().strip()
            return None, make, model, ucm
        return self.presetCombo.currentText(), None, None, None


class OptionCard(HeaderCardWidget):
    """Card for conversion options."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBorderRadius(8)

        self.archiveSwitch = SwitchButton(self)
        self.skipSwitch = SwitchButton(self)
        self.backupSwitch = SwitchButton(self)
        self.outputSwitch = SwitchButton(self)
        self.archiveDirEdit = LineEdit(self)
        self.outputBrowseButton = PushButton("", self, FluentIcon.FOLDER)
        self.outputBrowseButton.setMinimumWidth(140)
        self._outputDir = ""

        self.archiveSwitch.setChecked(True)
        self.archiveDirEdit.setText("originals")
        self.archiveDirEdit.setMinimumWidth(140)
        self.archiveDirEdit.setClearButtonEnabled(True)
        self._contentLayout = None
        self._rows = []

        self._add_row("opt_archive", "opt_archive_desc", self.archiveSwitch, self.archiveDirEdit, "label_archive_dir")
        self._add_row("opt_skip", "opt_skip_desc", self.skipSwitch, None, None)
        self._add_row("opt_backup", "opt_backup_desc", self.backupSwitch, None, None)
        self._add_row("opt_output", "opt_output_desc", self.outputSwitch, self.outputBrowseButton, None)

        self.archiveSwitch.checkedChanged.connect(self.archiveDirEdit.setEnabled)
        self.archiveDirEdit.setEnabled(self.archiveSwitch.isChecked())
        self.outputSwitch.checkedChanged.connect(self.outputBrowseButton.setEnabled)
        self.outputBrowseButton.setEnabled(False)
        self.outputBrowseButton.clicked.connect(self._pick_output_dir)
        self.apply_language()

    def _pick_output_dir(self) -> None:
        start_dir = self._outputDir or qconfig.get(app_cfg.lastDialogDir) or ""
        if start_dir and not os.path.isdir(start_dir):
            start_dir = ""
        folder = QFileDialog.getExistingDirectory(self.window(), tr("dlg_output_dir"), start_dir)
        if folder:
            self._outputDir = folder
            self.outputSwitch.setChecked(True)
            qconfig.set(app_cfg.lastDialogDir, folder)
            self._update_output_button()

    def _update_output_button(self) -> None:
        if self._outputDir:
            fm = self.outputBrowseButton.fontMetrics()
            self.outputBrowseButton.setText(fm.elidedText(self._outputDir, Qt.ElideMiddle, 240))
            self.outputBrowseButton.setToolTip(self._outputDir)
        else:
            self.outputBrowseButton.setText(tr("btn_browse"))
            self.outputBrowseButton.setToolTip("")

    def output_dir(self) -> Optional[str]:
        if not self.outputSwitch.isChecked():
            return None
        return self._outputDir or None

    def _add_row(self, titleKey: str, descKey: str, switch: SwitchButton, extra: Optional[QWidget], extraLabelKey: Optional[str]) -> None:
        labelLayout = QVBoxLayout()
        labelLayout.setContentsMargins(0, 0, 0, 0)
        labelLayout.setSpacing(2)
        titleLabel = StrongBodyLabel(tr(titleKey), self)
        descLabel = CaptionLabel(tr(descKey), self)
        descLabel.setTextColor(QColor(96, 96, 96), QColor(216, 216, 216))
        descLabel.setWordWrap(True)
        labelLayout.addWidget(titleLabel)
        labelLayout.addWidget(descLabel)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        row.addLayout(labelLayout, 1)
        extraLabel = None
        if extra is not None:
            if extraLabelKey:
                extraLabel = CaptionLabel(tr(extraLabelKey), self)
                row.addWidget(extraLabel)
            row.addWidget(extra)
        row.addWidget(switch)

        if self._contentLayout is None:
            self._contentLayout = QVBoxLayout()
            self._contentLayout.setContentsMargins(0, 0, 0, 0)
            self._contentLayout.setSpacing(14)
            self.viewLayout.addLayout(self._contentLayout, 1)
        self._contentLayout.addLayout(row)
        self._rows.append((titleKey, descKey, extraLabelKey, titleLabel, descLabel, extraLabel))

    def apply_language(self) -> None:
        self.setTitle(tr("options_title"))
        self.archiveDirEdit.setPlaceholderText(tr("ph_archive_dir"))
        for titleKey, descKey, extraLabelKey, titleLabel, descLabel, extraLabel in self._rows:
            titleLabel.setText(tr(titleKey))
            descLabel.setText(tr(descKey))
            if extraLabel is not None:
                extraLabel.setText(tr(extraLabelKey))
        self._update_output_button()


class ConvertWorker(Worker):
    """Runs the conversion file-by-file and reports each file's result."""

    file_done = Signal(str, bool, str)

    def __init__(self, files: List[str], opts: dict):
        super().__init__(self._run)
        self._files = files
        self._opts = opts

    def _run(self) -> List[tuple]:
        results: List[tuple] = []
        for path in self._files:
            try:
                process_file(path, **self._opts)
                self.file_done.emit(path, True, "")
                results.append((path, True, ""))
            except Exception as exc:
                msg = str(exc)
                log.info(f"Error: {msg}")
                self.file_done.emit(path, False, msg)
                results.append((path, False, msg))
        return results


class ConvertInterface(InterfaceBase):
    """Main page: inputs, options, actions and the live log."""

    def __init__(self, parent=None):
        super().__init__(
            "convertInterface",
            tr("convert_title"),
            tr("convert_subtitle"),
            parent,
        )

        self.inputCard = InputCard(self)
        self.cameraCard = CameraCard(list_presets(), self)
        self.optionCard = OptionCard(self)
        self.logBrowser = TextBrowser(self)
        self.logBrowser.setObjectName("logBrowser")
        self.progressBar = ProgressBar(self)
        self.checkButton = PushButton("", self, FluentIcon.ROBOT)
        self.startButton = PrimaryPushButton("", self, FluentIcon.PLAY)

        self.header.addActionButton(self.checkButton)
        self.header.addActionButton(self.startButton)
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)

        self._logCard = HeaderCardWidget(self)
        self._logCard.setBorderRadius(8)
        logContent = QVBoxLayout()
        logContent.setContentsMargins(0, 0, 0, 0)
        logContent.setSpacing(12)
        logContent.addWidget(self.logBrowser, 1)
        logContent.addWidget(self.progressBar)
        self._logCard.viewLayout.addLayout(logContent, 1)

        self.vBoxLayout.addWidget(self.inputCard)
        self.vBoxLayout.addWidget(self.cameraCard)
        self.vBoxLayout.addWidget(self.optionCard)
        self.vBoxLayout.addWidget(self._logCard, 1)

        StyleSheet.CONVERT_INTERFACE.apply(self)

        self.checkButton.clicked.connect(self._check_tools)
        self.startButton.clicked.connect(self._start)
        self.inputCard.retryRequested.connect(self._retry_file)

        self._worker: Optional[Worker] = None
        self._check_mode = False
        self._total = 0
        self._done = 0
        self._stateToolTip: Optional[StateToolTip] = None
        self._last_opts: dict = {}

        self.apply_language()

    def apply_language(self) -> None:
        self.header.set_texts(tr("convert_title"), tr("convert_subtitle"))
        self.checkButton.setText(tr("btn_check_tools"))
        self.startButton.setText(tr("btn_processing") if not self.startButton.isEnabled() else tr("btn_start"))
        self._logCard.setTitle(tr("log_title"))
        self.inputCard.apply_language()
        self.cameraCard.apply_language()
        self.optionCard.apply_language()

    def _show_info(self, content: str, level: str = "info") -> None:
        parent = self.window() or self
        if level == "success":
            InfoBar.success(tr("info_title"), content, isClosable=True, duration=4000, position=InfoBarPosition.BOTTOM_RIGHT, parent=parent)
        elif level == "warning":
            InfoBar.warning(tr("info_title"), content, isClosable=True, duration=5000, position=InfoBarPosition.BOTTOM_RIGHT, parent=parent)
        else:
            InfoBar.error(tr("error_title"), content, isClosable=True, duration=6000, position=InfoBarPosition.BOTTOM_RIGHT, parent=parent)

    def _show_state(self, title: str, content: str) -> None:
        if self._stateToolTip is None or not shiboken6.isValid(self._stateToolTip):
            self._stateToolTip = StateToolTip(title, content, self)
            self._stateToolTip.destroyed.connect(self._on_state_destroyed)
        else:
            self._stateToolTip.setTitle(title)
            self._stateToolTip.setContent(content)
            self._stateToolTip.setState(False)
        self._stateToolTip.show()
        self._place_state()

    def _on_state_destroyed(self) -> None:
        self._stateToolTip = None

    def _hide_state(self) -> None:
        if self._stateToolTip is not None and shiboken6.isValid(self._stateToolTip):
            self._stateToolTip.hide()

    def _set_running(self, running: bool) -> None:
        self.checkButton.setEnabled(not running)
        self.startButton.setEnabled(not running)
        self.startButton.setText(tr("btn_processing") if running else tr("btn_start"))
        self.progressBar.setValue(0)
        self._done = 0

    def _collect_inputs(self) -> List[str]:
        return collect_input_paths(self.inputCard.paths())

    def _camera_args(self):
        return self.cameraCard.camera_args()

    def _validate(self):
        if not self.inputCard.paths():
            self._show_info(tr("warn_no_inputs"), "warning")
            return None
        preset, make, model, ucm = self._camera_args()
        if (make or model or ucm) and not (make and model and ucm):
            self._show_info(tr("warn_custom_incomplete"), "warning")
            return None
        try:
            files = self._collect_inputs()
        except (FileNotFoundError, RuntimeError) as exc:
            self._show_info(str(exc), "warning")
            return None
        if not files:
            self._show_info(tr("warn_no_supported"), "warning")
            return None
        return preset, make, model, ucm, files

    def _build_opts(self, preset, make, model, ucm) -> dict:
        return dict(
            preset=preset,
            archive_raw=self.optionCard.archiveSwitch.isChecked(),
            skip_raw_conversion=self.optionCard.skipSwitch.isChecked(),
            archive_dir=self.optionCard.archiveDirEdit.text().strip() or "originals",
            keep_exif_backup=self.optionCard.backupSwitch.isChecked(),
            make=make,
            model=model,
            uniquecameramodel=ucm,
            output_dir=self.optionCard.output_dir(),
        )

    def _start(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        result = self._validate()
        if result is None:
            return
        preset, make, model, ucm, files = result

        self._total = len(files)
        self._check_mode = False
        self._set_running(True)
        self._last_opts = self._build_opts(preset, make, model, ucm)
        self.inputCard.set_all_status("pending")
        self.logBrowser.clear()
        self.logBrowser.append(tr("log_found_files", n=self._total))
        self._show_state(tr("state_converting"), tr("log_found_files", n=self._total))

        self._worker = ConvertWorker(files, self._last_opts)
        self._connect_worker()

    def _retry_file(self, path: str) -> None:
        if self._worker and self._worker.isRunning():
            self._show_info(tr("warn_busy"), "warning")
            return
        preset, make, model, ucm = self._camera_args()
        opts = self._last_opts or self._build_opts(preset, make, model, ucm)
        self._last_opts = opts
        self._total = 1
        self._check_mode = False
        self._set_running(True)
        self.inputCard.set_file_status(path, "processing")
        self.logBrowser.append(tr("log_retry", path=path))
        self._show_state(tr("state_converting"), tr("log_retry", path=path))

        self._worker = ConvertWorker([path], opts)
        self._connect_worker()

    def _check_tools(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._check_mode = True
        self._total = 0
        self._set_running(True)
        self.logBrowser.clear()
        self.logBrowser.append(tr("state_checking"))
        self._show_state(tr("state_checking"), tr("state_checking_content"))
        self._worker = Worker(print_status)
        self._connect_worker()

    def _connect_worker(self) -> None:
        self._worker.log_line.connect(self._on_log_line)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        if isinstance(self._worker, ConvertWorker):
            self._worker.file_done.connect(self._on_file_done)
        self._worker.start()

    def _on_log_line(self, msg: str) -> None:
        self.logBrowser.append(msg)

    def _on_file_done(self, path: str, ok: bool, error: str) -> None:
        self.inputCard.set_file_status(path, "success" if ok else "failed")
        if not self._check_mode:
            self._done += 1
            self.progressBar.setValue(int(self._done * 100 / self._total))
            if self._stateToolTip is not None:
                self._stateToolTip.setContent(tr("state_processed", done=self._done, total=self._total))

    def _on_finished(self, result) -> None:
        self._set_running(False)
        if self._check_mode:
            self._hide_state()
            self._show_info(tr("msg_check_done"), "success")
            return
        if isinstance(result, list) and result and isinstance(result[0], tuple):
            ok = sum(1 for r in result if r[1])
            fail = len(result) - ok
        else:
            ok, fail = self._done, 0
        self.progressBar.setValue(100)
        summary = tr("msg_convert_summary", ok=ok, fail=fail)
        self.logBrowser.append(summary)
        if self._stateToolTip is not None and shiboken6.isValid(self._stateToolTip):
            self._stateToolTip.setContent(summary)
            self._stateToolTip.setState(True)
        self._show_info(summary, "success" if fail == 0 else "warning")

    def _on_failed(self, exc: str) -> None:
        self._set_running(False)
        self._hide_state()
        self.logBrowser.append(tr("log_error", exc=exc))
        self._show_info(exc, "error")


class ToolStatusCard(CardWidget):
    """A single row showing one helper tool's install status and install button."""

    def __init__(self, icon, name: str, descKey: str, parent=None):
        super().__init__(parent)
        self._descKey = descKey
        self.iconWidget = IconWidget(icon, self)
        self.titleLabel = StrongBodyLabel(name, self)
        self.descriptionLabel = CaptionLabel(self)
        self.successBadge = InfoBadge.success("", self)
        self.errorBadge = InfoBadge.error("", self)
        self.statusLabel = CaptionLabel(self)
        self.installButton = PrimaryPushButton("", self)
        self.installButton.setIcon(FluentIcon.DOWNLOAD)
        self.installButton.setFixedWidth(150)
        self.uninstallButton = PushButton("", self)
        self.uninstallButton.setIcon(FluentIcon.DELETE)
        self.uninstallButton.setFixedWidth(150)
        self.manualButton = PushButton("", self)
        self.manualButton.setIcon(FluentIcon.FOLDER)
        self.manualButton.setFixedWidth(150)
        self.manualMenu = QMenu(self.manualButton)
        self.pickAction = self.manualMenu.addAction(tr("menu_pick_path"))
        self.clearAction = self.manualMenu.addAction(tr("menu_clear_path"))
        self.clearAction.setEnabled(False)
        self.manualButton.setMenu(self.manualMenu)

        self.iconWidget.setFixedSize(48, 48)
        self.descriptionLabel.setTextColor(QColor(96, 96, 96), QColor(216, 216, 216))
        self.descriptionLabel.setWordWrap(True)
        self.statusLabel.setWordWrap(True)

        titleRow = QHBoxLayout()
        titleRow.setContentsMargins(0, 0, 0, 0)
        titleRow.setSpacing(10)
        titleRow.addWidget(self.titleLabel)
        titleRow.addWidget(self.successBadge)
        titleRow.addWidget(self.errorBadge)
        titleRow.addStretch(1)

        self.hBoxLayout = QHBoxLayout(self)
        self.vBoxLayout = QVBoxLayout()
        self.hBoxLayout.setContentsMargins(20, 14, 16, 14)
        self.hBoxLayout.setSpacing(20)
        self.hBoxLayout.addWidget(self.iconWidget)

        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(3)
        self.vBoxLayout.addLayout(titleRow)
        self.vBoxLayout.addWidget(self.descriptionLabel)
        self.vBoxLayout.addWidget(self.statusLabel)
        self.hBoxLayout.addLayout(self.vBoxLayout, 1)
        self.buttonLayout = QGridLayout()
        self.buttonLayout.setContentsMargins(0, 0, 0, 0)
        self.buttonLayout.setHorizontalSpacing(8)
        self.buttonLayout.setVerticalSpacing(8)
        self.buttonLayout.setRowStretch(0, 1)
        self.buttonLayout.setRowStretch(1, 1)
        self.buttonLayout.addWidget(self.installButton, 0, 0)
        self.buttonLayout.addWidget(self.uninstallButton, 0, 1)
        self.buttonLayout.addWidget(self.manualButton, 1, 0)
        self.hBoxLayout.addLayout(self.buttonLayout, 0)

    def set_status(self, text: str, installed: bool, uninstallable: bool = False) -> None:
        self.statusLabel.setText(text)
        self.successBadge.setVisible(installed)
        self.errorBadge.setVisible(not installed)
        self.installButton.setText(tr("badge_installed") if installed else tr("btn_install"))
        self.installButton.setEnabled(not installed)
        self.uninstallButton.setEnabled(uninstallable)

    def apply_language(self) -> None:
        self.descriptionLabel.setText(tr(self._descKey))
        self.successBadge.setText(tr("badge_installed"))
        self.errorBadge.setText(tr("badge_missing"))
        self.uninstallButton.setText(tr("btn_uninstall"))
        self.manualButton.setText(tr("btn_manual"))
        self.pickAction.setText(tr("menu_pick_path"))
        self.clearAction.setText(tr("menu_clear_path"))


class ToolsInterface(InterfaceBase):
    """Page for installing/checking the external helper tools (exiftool, dnglab)."""

    def __init__(self, parent=None):
        super().__init__(
            "toolsInterface",
            tr("tools_title"),
            tr("tools_subtitle"),
            parent,
        )

        self.exifCard = ToolStatusCard(FluentIcon.PHOTO, "ExifTool", "exif_desc", self)
        self.dnglabCard = ToolStatusCard(FluentIcon.CLOUD_DOWNLOAD, "dnglab", "dnglab_desc", self)
        self.refreshButton = PushButton("", self, FluentIcon.SYNC)
        self.installAllButton = PrimaryPushButton("", self, FluentIcon.DOWNLOAD)
        self.logBrowser = TextBrowser(self)
        self.logBrowser.setObjectName("logBrowser")
        self.progressBar = ProgressBar(self)

        self.header.addActionButton(self.refreshButton)
        self.header.addActionButton(self.installAllButton)
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)

        self._installCard = HeaderCardWidget(self)
        self._installCard.setBorderRadius(8)
        self._infoLabel = CaptionLabel(self)
        self._infoLabel.setTextColor(QColor(96, 96, 96), QColor(216, 216, 216))
        self._infoLabel.setWordWrap(True)
        installContent = QVBoxLayout()
        installContent.setContentsMargins(0, 0, 0, 0)
        installContent.setSpacing(10)
        installContent.addWidget(self.exifCard)
        installContent.addWidget(self.dnglabCard)
        installContent.addWidget(self._infoLabel)
        self._installCard.viewLayout.addLayout(installContent, 1)

        self._logCard = HeaderCardWidget(self)
        self._logCard.setBorderRadius(8)
        logContent = QVBoxLayout()
        logContent.setContentsMargins(0, 0, 0, 0)
        logContent.setSpacing(12)
        logContent.addWidget(self.logBrowser, 1)
        logContent.addWidget(self.progressBar)
        self._logCard.viewLayout.addLayout(logContent, 1)

        self.vBoxLayout.addWidget(self._installCard)
        self.vBoxLayout.addWidget(self._logCard, 1)

        StyleSheet.TOOLS_INTERFACE.apply(self)

        self.exifCard.installButton.clicked.connect(self._install_exiftool)
        self.dnglabCard.installButton.clicked.connect(self._install_dnglab)
        self.exifCard.uninstallButton.clicked.connect(self._uninstall_exiftool)
        self.dnglabCard.uninstallButton.clicked.connect(self._uninstall_dnglab)
        self.exifCard.pickAction.triggered.connect(self._pick_exiftool_path)
        self.exifCard.clearAction.triggered.connect(self._clear_exiftool_path)
        self.dnglabCard.pickAction.triggered.connect(self._pick_dnglab_path)
        self.dnglabCard.clearAction.triggered.connect(self._clear_dnglab_path)
        self.refreshButton.clicked.connect(self._refresh_status)
        self.installAllButton.clicked.connect(self._install_all)

        self._worker: Optional[Worker] = None
        self._queue: Optional[List[str]] = None
        self._stateToolTip: Optional[StateToolTip] = None

        self.apply_language()
        self._refresh_status()

    def apply_language(self) -> None:
        self.header.set_texts(tr("tools_title"), tr("tools_subtitle"))
        self.refreshButton.setText(tr("btn_refresh"))
        self.installAllButton.setText(tr("btn_install_all"))
        self._installCard.setTitle(tr("tools_card_title"))
        self._logCard.setTitle(tr("log_install_title"))
        self._infoLabel.setText(tr("tools_info", system=platform.system(), machine=platform.machine(), dir=cache_dir()))
        self.exifCard.apply_language()
        self.dnglabCard.apply_language()

    def _show_info(self, content: str, level: str = "info") -> None:
        parent = self.window() or self
        if level == "success":
            InfoBar.success(tr("info_title"), content, isClosable=True, duration=4000, position=InfoBarPosition.BOTTOM_RIGHT, parent=parent)
        elif level == "warning":
            InfoBar.warning(tr("info_title"), content, isClosable=True, duration=5000, position=InfoBarPosition.BOTTOM_RIGHT, parent=parent)
        else:
            InfoBar.error(tr("error_title"), content, isClosable=True, duration=6000, position=InfoBarPosition.BOTTOM_RIGHT, parent=parent)

    def _show_state(self, title: str, content: str) -> None:
        if self._stateToolTip is None or not shiboken6.isValid(self._stateToolTip):
            self._stateToolTip = StateToolTip(title, content, self)
            self._stateToolTip.destroyed.connect(self._on_state_destroyed)
        else:
            self._stateToolTip.setTitle(title)
            self._stateToolTip.setContent(content)
            self._stateToolTip.setState(False)
        self._stateToolTip.show()
        self._place_state()

    def _on_state_destroyed(self) -> None:
        self._stateToolTip = None

    def _hide_state(self) -> None:
        if self._stateToolTip is not None and shiboken6.isValid(self._stateToolTip):
            self._stateToolTip.hide()

    def _ensure_idle(self) -> bool:
        if self._worker and self._worker.isRunning():
            return False
        return True

    def _set_running(self, running: bool) -> None:
        self.refreshButton.setEnabled(not running)
        self.installAllButton.setEnabled(not running)
        self.exifCard.installButton.setEnabled(not running and find_exiftool() is None)
        self.dnglabCard.installButton.setEnabled(not running and find_dnglab() is None)
        self.exifCard.uninstallButton.setEnabled(not running and cached_exiftool_install() is not None)
        self.dnglabCard.uninstallButton.setEnabled(not running and _cached_dnglab() is not None)
        self.exifCard.manualButton.setEnabled(not running)
        self.dnglabCard.manualButton.setEnabled(not running)
        self.progressBar.setValue(0)

    @staticmethod
    def _is_manual(path: Optional[str], custom: str) -> bool:
        if not path or not custom or not os.path.isfile(custom):
            return False
        return os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(custom))

    def _refresh_status(self) -> None:
        custom_exif = qconfig.get(app_cfg.exiftoolPath)
        exif = find_exiftool()
        self.exifCard.clearAction.setEnabled(bool(custom_exif))
        if exif:
            text = tr("status_manual", path=exif) if self._is_manual(exif, custom_exif) else tr("status_installed", path=exif)
            self.exifCard.set_status(text, True, cached_exiftool_install() is not None)
        else:
            extra = tr("status_manual_invalid") if custom_exif else ""
            self.exifCard.set_status(tr("status_missing") + extra, False, cached_exiftool_install() is not None)

        custom_dng = qconfig.get(app_cfg.dnglabPath)
        dng = find_dnglab()
        self.dnglabCard.clearAction.setEnabled(bool(custom_dng))
        if dng:
            text = tr("status_manual", path=dng) if self._is_manual(dng, custom_dng) else tr("status_installed", path=dng)
            self.dnglabCard.set_status(text, True, _cached_dnglab() is not None)
        else:
            adobe = find_adobe_dng_converter()
            if custom_dng:
                text = tr("status_manual_invalid_short")
            elif adobe:
                text = tr("status_adobe", path=adobe)
            else:
                text = tr("status_missing")
            self.dnglabCard.set_status(text, False, _cached_dnglab() is not None)

    def _install_exiftool(self) -> None:
        if not self._ensure_idle():
            return
        self._queue = None
        self._start_install("exiftool", install_exiftool)

    def _install_dnglab(self) -> None:
        if not self._ensure_idle():
            return
        self._queue = None
        self._start_install("dnglab", install_dnglab)

    def _pick_tool_path(self, title: str, env_name: str, item: ConfigItem, validator, filter_: str) -> None:
        if not self._ensure_idle():
            return
        start = qconfig.get(item)
        if start and not os.path.isdir(start):
            start = os.path.dirname(start)
        if not start or not os.path.isdir(start):
            start = cache_dir()
        path, _ = QFileDialog.getOpenFileName(self.window(), title, start, filter_)
        if not path:
            return
        if not validator(path):
            self._show_info(tr("msg_invalid_tool"), "error")
            return
        os.environ[env_name] = path
        qconfig.set(item, path)
        self._refresh_status()
        self._show_info(tr("msg_manual_set", path=path), "success")

    def _clear_tool_path(self, env_name: str, item: ConfigItem) -> None:
        if not self._ensure_idle():
            return
        os.environ.pop(env_name, None)
        qconfig.set(item, "")
        self._refresh_status()
        self._show_info(tr("msg_manual_cleared"), "success")

    def _pick_exiftool_path(self) -> None:
        file_filter = tr("file_filter_exec") if os.name == "nt" else tr("file_filter_all")
        self._pick_tool_path(tr("dlg_pick_exif"), EXIFTOOL_ENV, app_cfg.exiftoolPath, is_valid_exiftool, file_filter)

    def _pick_dnglab_path(self) -> None:
        file_filter = tr("file_filter_exec") if os.name == "nt" else tr("file_filter_all")
        self._pick_tool_path(tr("dlg_pick_dnglab"), DNGLAB_ENV, app_cfg.dnglabPath, is_valid_dnglab, file_filter)

    def _clear_exiftool_path(self) -> None:
        self._clear_tool_path(EXIFTOOL_ENV, app_cfg.exiftoolPath)

    def _clear_dnglab_path(self) -> None:
        self._clear_tool_path(DNGLAB_ENV, app_cfg.dnglabPath)

    def _uninstall_exiftool(self) -> None:
        if not self._ensure_idle():
            return
        target = cached_exiftool_install()
        if target is None:
            self._show_info(tr("msg_no_cached_exif"), "warning")
            return
        self._confirm_uninstall("ExifTool", target, uninstall_exiftool)

    def _uninstall_dnglab(self) -> None:
        if not self._ensure_idle():
            return
        target = _cached_dnglab()
        if target is None:
            self._show_info(tr("msg_no_cached_dnglab"), "warning")
            return
        self._confirm_uninstall("dnglab", target, uninstall_dnglab)

    def _confirm_uninstall(self, name: str, target: str, fn) -> None:
        box = MessageBox(tr("dlg_confirm_uninstall"), tr("dlg_confirm_uninstall_body", name=name, target=target), self.window())
        box.yesButton.setText(tr("btn_uninstall"))
        box.cancelButton.setText(tr("btn_cancel"))
        if not box.exec():
            return
        self._start_uninstall(name, fn)

    def _start_uninstall(self, name: str, fn) -> None:
        self._set_running(True)
        self.logBrowser.clear()
        self.logBrowser.append(tr("log_uninstalling", name=name))
        self._show_state(tr("state_uninstalling"), tr("state_uninstalling_content", name=name))
        self._worker = Worker(fn)
        self._worker.log_line.connect(self.logBrowser.append)
        self._worker.finished.connect(lambda _r: self._on_uninstall_done(name))
        self._worker.failed.connect(self._on_uninstall_failed)
        self._worker.start()

    def _on_uninstall_done(self, name: str) -> None:
        self._set_running(False)
        self._hide_state()
        self._refresh_status()
        self._show_info(tr("msg_uninstalled", name=name), "success")

    def _on_uninstall_failed(self, exc: str) -> None:
        self._set_running(False)
        self._hide_state()
        self._refresh_status()
        self._show_info(exc, "error")

    def _install_all(self) -> None:
        if not self._ensure_idle():
            return
        missing = []
        if find_exiftool() is None:
            missing.append("exiftool")
        if find_dnglab() is None:
            missing.append("dnglab")
        if not missing:
            self._show_info(tr("msg_all_installed"), "success")
            return
        self._queue = missing
        self._start_next()

    def _start_next(self) -> None:
        if self._queue:
            tool = self._queue.pop(0)
            fn = install_exiftool if tool == "exiftool" else install_dnglab
            self._start_install(tool, fn)
        else:
            self._finish_install()

    def _start_install(self, name: str, fn) -> None:
        self._set_running(True)
        self.logBrowser.clear()
        self.logBrowser.append(tr("log_installing", name=name))
        self._show_state(tr("state_installing"), tr("state_installing_content", name=name))
        self._worker = Worker(fn)
        self._worker.log_line.connect(self.logBrowser.append)
        self._worker.finished.connect(lambda _r: self._on_install_done())
        self._worker.failed.connect(self._on_install_failed)
        self._worker.start()

    def _on_install_done(self) -> None:
        self._start_next()

    def _on_install_failed(self, exc: str) -> None:
        self._queue = None
        self._set_running(False)
        self._hide_state()
        self._refresh_status()
        self._show_info(exc, "error")

    def _finish_install(self) -> None:
        self._queue = None
        self._set_running(False)
        self._refresh_status()
        if self._stateToolTip is not None and shiboken6.isValid(self._stateToolTip):
            self._stateToolTip.setContent(tr("state_install_done"))
            self._stateToolTip.setState(True)
        self._show_info(tr("msg_install_done"), "success")


class MainWindow(MSFluentWindow):
    def __init__(self):
        super().__init__()
        self.convertInterface = ConvertInterface(self)
        self.toolsInterface = ToolsInterface(self)

        self.initNavigation()
        self.initWindow()

    def initNavigation(self) -> None:
        self.addSubInterface(self.convertInterface, FluentIcon.PHOTO, tr("nav_convert"))
        self.addSubInterface(self.toolsInterface, FluentIcon.CONNECT, tr("nav_tools"))
        self.navigationInterface.addItem(
            routeKey="theme",
            icon=FluentIcon.CONSTRACT,
            text=tr("nav_theme"),
            onClick=lambda: toggleTheme(True),
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )
        self.navigationInterface.addItem(
            routeKey="language",
            icon=FluentIcon.LANGUAGE,
            text=tr("nav_language"),
            onClick=self._toggle_language,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )
        self.navigationInterface.addItem(
            routeKey="about",
            icon=FluentIcon.INFO,
            text=tr("nav_about"),
            onClick=self._show_about,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )
        nav = self.navigationInterface
        self.navigationInterface.setCurrentItem(self.convertInterface.objectName())

    def _toggle_language(self) -> None:
        t.toggle()
        qconfig.set(app_cfg.language, t.lang)
        self.convertInterface.apply_language()
        self.toolsInterface.apply_language()
        self.toolsInterface._refresh_status()
        nav = self.navigationInterface
        nav.widget(self.convertInterface.objectName()).setText(tr("nav_convert"))
        nav.widget(self.toolsInterface.objectName()).setText(tr("nav_tools"))
        nav.widget("theme").setText(tr("nav_theme"))
        nav.widget("language").setText(tr("nav_language"))
        nav.widget("about").setText(tr("nav_about"))

    def initWindow(self) -> None:
        self.resize(920, 780)
        self.setMinimumSize(880, 640)
        self.setWindowIcon(QIcon(APP_ICON))
        self.setWindowTitle(APP_TITLE)

        try:
            self.setMicaEffectEnabled(True)
        except Exception:
            pass

        desktop = QApplication.screens()[0].availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

    def _show_about(self) -> None:
        box = MessageBox(APP_TITLE, tr("about_content"), self)
        box.yesButton.setText(tr("btn_ok"))
        box.cancelButton.hide()
        box.exec()


def _apply_tool_overrides() -> None:
    """Export persisted manual tool paths into the env the core looks up."""
    for env_name, item in ((EXIFTOOL_ENV, app_cfg.exiftoolPath), (DNGLAB_ENV, app_cfg.dnglabPath)):
        value = qconfig.get(item)
        if value and os.path.isfile(value):
            os.environ[env_name] = value
        else:
            os.environ.pop(env_name, None)


def run_app(argv: Optional[List[str]] = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationDisplayName(APP_TITLE)

    config_path = os.path.join(
        os.path.expanduser("~"), ".config", "fujifilm-converter", "config.json"
    )
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    qconfig.load(config_path, app_cfg)
    _apply_tool_overrides()
    t.set_language(qconfig.get(app_cfg.language))

    setTheme(Theme.AUTO)
    setThemeColor("#0078D4")
    window = MainWindow()
    window.show()
    return app.exec()


def main(argv: Optional[List[str]] = None) -> int:
    return run_app(argv)


if __name__ == "__main__":
    raise SystemExit(main())