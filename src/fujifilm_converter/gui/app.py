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

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QFrame, QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ComboBox,
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

from ..cameras import list_presets
from ..converters import (
    cache_dir,
    find_adobe_dng_converter,
    find_dnglab,
    find_exiftool,
    install_dnglab,
    install_exiftool,
)
from ..core import collect_input_paths, process_inputs, print_status
from .style import StyleSheet
from .worker import Worker

APP_TITLE = "Fujifilm Converter"
APP_ICON = ":/qfluentwidgets/images/logo.png"


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


class InputCard(HeaderCardWidget):
    """Card for choosing RAW/DNG files or directories."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("输入文件 / 文件夹")
        self.setBorderRadius(8)

        self.countBadge = InfoBadge.info(0, self)
        self.listWidget = ListWidget(self)
        self.listPanel = QFrame(self)
        self.listPanel.setObjectName("listPanel")
        self.addFileButton = PushButton("添加文件", self, FluentIcon.DOCUMENT)
        self.addFolderButton = PushButton("添加文件夹", self, FluentIcon.FOLDER)
        self.removeButton = PushButton("移除选中", self)
        self.clearButton = PushButton("清空", self)

        panelLayout = QVBoxLayout(self.listPanel)
        panelLayout.setContentsMargins(2, 2, 2, 2)
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
        contentLayout.addLayout(buttonLayout)
        self.viewLayout.addLayout(contentLayout, 1)

        self.addFileButton.clicked.connect(self._add_files)
        self.addFolderButton.clicked.connect(self._add_folder)
        self.removeButton.clicked.connect(self._remove_selected)
        self.clearButton.clicked.connect(self._clear)
        self.listWidget.model().rowsInserted.connect(self._update_count)
        self.listWidget.model().rowsRemoved.connect(self._update_count)

    def _update_count(self) -> None:
        self.countBadge.setText(str(self.listWidget.count()))

    def _clear(self) -> None:
        self.listWidget.clear()

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self.window(),
            "选择 RAW / DNG 文件",
            "",
            "RAW / DNG 文件 (*.arw *.cr2 *.cr3 *.nef *.nrw *.raf *.orf *.rw2 *.pef *.srw *.dng *.raw *.rwl *.3fr *.iiq *.mef *.mrw *.erf *.kdc *.dcr *.gpr);;所有文件 (*.*)",
        )
        self._add_paths(paths)

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self.window(), "选择照片目录")
        if folder:
            self._add_paths([folder])

    def _add_paths(self, paths: List[str]) -> None:
        existing = {self.listWidget.item(i).text() for i in range(self.listWidget.count())}
        for path in paths:
            if path not in existing:
                self.listWidget.addItem(path)

    def _remove_selected(self) -> None:
        for item in self.listWidget.selectedItems():
            self.listWidget.takeItem(self.listWidget.row(item))

    def paths(self) -> List[str]:
        return [self.listWidget.item(i).text() for i in range(self.listWidget.count())]


class CameraCard(HeaderCardWidget):
    """Card for choosing the camera identity (preset or custom)."""

    def __init__(self, presets: List[str], parent=None):
        super().__init__(parent)
        self.setTitle("相机身份")
        self.setBorderRadius(8)

        self.presetCombo = ComboBox(self)
        self.presetCombo.addItems(presets)
        self.presetCombo.setCurrentText("fuji")
        self.presetCombo.setMinimumWidth(200)

        self.customSwitch = SwitchButton(self)
        self.makeEdit = LineEdit(self)
        self.modelEdit = LineEdit(self)
        self.ucmEdit = LineEdit(self)

        self.makeEdit.setPlaceholderText("Make（如 FUJIFILM）")
        self.modelEdit.setPlaceholderText("Model（如 GFX100II）")
        self.ucmEdit.setPlaceholderText("UniqueCameraModel（如 Fujifilm GFX 100 II）")
        self.makeEdit.setClearButtonEnabled(True)
        self.modelEdit.setClearButtonEnabled(True)
        self.ucmEdit.setClearButtonEnabled(True)

        presetRow = QHBoxLayout()
        presetRow.setContentsMargins(0, 0, 0, 0)
        presetRow.setSpacing(12)
        presetRow.addWidget(StrongBodyLabel("预设", self))
        presetRow.addWidget(self.presetCombo, 1)
        presetRow.addStretch(1)

        hint = CaptionLabel("选择 Lightroom 已支持的预设，多数情况默认 fuji 即可解锁富士胶片模拟", self)
        hint.setTextColor(QColor(96, 96, 96), QColor(216, 216, 216))
        hint.setWordWrap(True)

        customRow = QHBoxLayout()
        customRow.setContentsMargins(0, 0, 0, 0)
        customRow.setSpacing(12)
        customRow.addWidget(StrongBodyLabel("自定义相机身份", self))
        customRow.addStretch(1)
        customRow.addWidget(self.customSwitch)

        customHint = CaptionLabel("需要完整填写 Make、Model、UniqueCameraModel 三项", self)
        customHint.setTextColor(QColor(96, 96, 96), QColor(216, 216, 216))
        customHint.setWordWrap(True)
        customHint.setVisible(False)

        contentLayout = QVBoxLayout()
        contentLayout.setContentsMargins(0, 0, 0, 0)
        contentLayout.setSpacing(10)
        contentLayout.addLayout(presetRow)
        contentLayout.addWidget(hint)
        contentLayout.addLayout(customRow)
        contentLayout.addWidget(customHint)
        contentLayout.addWidget(self.makeEdit)
        contentLayout.addWidget(self.modelEdit)
        contentLayout.addWidget(self.ucmEdit)
        self.viewLayout.addLayout(contentLayout, 1)

        self._customHint = customHint
        self._update_custom_enabled(False)
        self.customSwitch.checkedChanged.connect(self._update_custom_enabled)

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
        self.setTitle("转换选项")
        self.setBorderRadius(8)

        self.archiveSwitch = SwitchButton(self)
        self.skipSwitch = SwitchButton(self)
        self.backupSwitch = SwitchButton(self)
        self.archiveDirEdit = LineEdit(self)

        self.archiveSwitch.setChecked(True)
        self.archiveDirEdit.setText("originals")
        self.archiveDirEdit.setPlaceholderText("归档目录名（默认 originals）")
        self.archiveDirEdit.setMinimumWidth(140)
        self.archiveDirEdit.setClearButtonEnabled(True)
        self._contentLayout = None

        self._add_row("转换后归档原始 RAW", "原始照片会移动到归档目录", self.archiveSwitch, self.archiveDirEdit, "归档目录：")
        self._add_row("跳过 RAW→DNG 转换", "输入文件必须已经是 DNG", self.skipSwitch, None, None)
        self._add_row("保留 exiftool 备份文件", "会额外生成 *_original 文件", self.backupSwitch, None, None)

        self.archiveSwitch.checkedChanged.connect(self.archiveDirEdit.setEnabled)
        self.archiveDirEdit.setEnabled(self.archiveSwitch.isChecked())

    def _add_row(self, title: str, description: str, switch: SwitchButton, extra: Optional[LineEdit], extraLabel: Optional[str]) -> None:
        labelLayout = QVBoxLayout()
        labelLayout.setContentsMargins(0, 0, 0, 0)
        labelLayout.setSpacing(2)
        labelLayout.addWidget(StrongBodyLabel(title, self))
        desc = CaptionLabel(description, self)
        desc.setTextColor(QColor(96, 96, 96), QColor(216, 216, 216))
        desc.setWordWrap(True)
        labelLayout.addWidget(desc)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        row.addLayout(labelLayout, 1)
        if extra is not None and extraLabel:
            row.addWidget(CaptionLabel(extraLabel, self))
            row.addWidget(extra)
        row.addWidget(switch)

        if self._contentLayout is None:
            self._contentLayout = QVBoxLayout()
            self._contentLayout.setContentsMargins(0, 0, 0, 0)
            self._contentLayout.setSpacing(14)
            self.viewLayout.addLayout(self._contentLayout, 1)
        self._contentLayout.addLayout(row)


class ConvertInterface(InterfaceBase):
    """Main page: inputs, options, actions and the live log."""

    def __init__(self, parent=None):
        super().__init__(
            "convertInterface",
            "照片转换",
            "把任意相机的 RAW/DNG 照片处理成 Lightroom 能识别的富士机型，解锁胶片模拟",
            parent,
        )

        self.inputCard = InputCard(self)
        self.cameraCard = CameraCard(list_presets(), self)
        self.optionCard = OptionCard(self)
        self.logBrowser = TextBrowser(self)
        self.logBrowser.setObjectName("logBrowser")
        self.progressBar = ProgressBar(self)
        self.checkButton = PushButton("检测外部工具", self, FluentIcon.ROBOT)
        self.startButton = PrimaryPushButton("开始转换", self, FluentIcon.PLAY)

        self.header.addActionButton(self.checkButton)
        self.header.addActionButton(self.startButton)
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)

        logCard = HeaderCardWidget(self)
        logCard.setTitle("运行日志")
        logCard.setBorderRadius(8)
        logContent = QVBoxLayout()
        logContent.setContentsMargins(0, 0, 0, 0)
        logContent.setSpacing(12)
        logContent.addWidget(self.logBrowser, 1)
        logContent.addWidget(self.progressBar)
        logCard.viewLayout.addLayout(logContent, 1)

        self.vBoxLayout.addWidget(self.inputCard)
        self.vBoxLayout.addWidget(self.cameraCard)
        self.vBoxLayout.addWidget(self.optionCard)
        self.vBoxLayout.addWidget(logCard, 1)

        StyleSheet.CONVERT_INTERFACE.apply(self)

        self.checkButton.clicked.connect(self._check_tools)
        self.startButton.clicked.connect(self._start)

        self._worker: Optional[Worker] = None
        self._check_mode = False
        self._total = 0
        self._done = 0
        self._stateToolTip: Optional[StateToolTip] = None

    def _show_info(self, content: str, level: str = "info") -> None:
        parent = self.window() or self
        if level == "success":
            InfoBar.success("提示", content, isClosable=True, duration=4000, position=InfoBarPosition.BOTTOM_RIGHT, parent=parent)
        elif level == "warning":
            InfoBar.warning("提示", content, isClosable=True, duration=5000, position=InfoBarPosition.BOTTOM_RIGHT, parent=parent)
        else:
            InfoBar.error("错误", content, isClosable=True, duration=6000, position=InfoBarPosition.BOTTOM_RIGHT, parent=parent)

    def _show_state(self, title: str, content: str) -> None:
        if self._stateToolTip is None:
            self._stateToolTip = StateToolTip(title, content, self)
            self._stateToolTip.move(max(0, (self.width() - 360) // 2), self.header.height() + 8)
        else:
            self._stateToolTip.setTitle(title)
            self._stateToolTip.setContent(content)
            self._stateToolTip.setState(False)
        self._stateToolTip.show()

    def _hide_state(self) -> None:
        if self._stateToolTip is not None:
            self._stateToolTip.hide()

    def _set_running(self, running: bool) -> None:
        self.checkButton.setEnabled(not running)
        self.startButton.setEnabled(not running)
        self.startButton.setText("处理中…" if running else "开始转换")
        self.progressBar.setValue(0)
        self._done = 0

    def _collect_inputs(self) -> List[str]:
        return collect_input_paths(self.inputCard.paths())

    def _camera_args(self):
        return self.cameraCard.camera_args()

    def _validate(self):
        if not self.inputCard.paths():
            self._show_info("请先添加输入文件或文件夹。", "warning")
            return None
        preset, make, model, ucm = self._camera_args()
        if (make or model or ucm) and not (make and model and ucm):
            self._show_info("自定义相机身份需要完整填写 Make、Model、UniqueCameraModel 三项。", "warning")
            return None
        try:
            files = self._collect_inputs()
        except (FileNotFoundError, RuntimeError) as exc:
            self._show_info(str(exc), "warning")
            return None
        if not files:
            self._show_info("没有找到支持的 RAW / DNG 文件。", "warning")
            return None
        return preset, make, model, ucm, files

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
        self.logBrowser.clear()
        self.logBrowser.append(f"共发现 {self._total} 个文件，开始处理…")
        self._show_state("正在转换", f"共 {self._total} 个文件，开始处理…")

        self._worker = Worker(
            process_inputs,
            files,
            preset=preset,
            archive_raw=self.optionCard.archiveSwitch.isChecked(),
            skip_raw_conversion=self.optionCard.skipSwitch.isChecked(),
            archive_dir=self.optionCard.archiveDirEdit.text().strip() or "originals",
            keep_exif_backup=self.optionCard.backupSwitch.isChecked(),
            make=make,
            model=model,
            uniquecameramodel=ucm,
        )
        self._connect_worker()

    def _check_tools(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._check_mode = True
        self._total = 0
        self._set_running(True)
        self.logBrowser.clear()
        self.logBrowser.append("检测外部工具…")
        self._show_state("检测外部工具", "正在检查 exiftool 与 RAW 转换器…")
        self._worker = Worker(print_status)
        self._connect_worker()

    def _connect_worker(self) -> None:
        self._worker.log_line.connect(self._on_log_line)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_log_line(self, msg: str) -> None:
        self.logBrowser.append(msg)
        if self._total and msg.startswith("Done: "):
            self._done += 1
            self.progressBar.setValue(int(self._done * 100 / self._total))
            if self._stateToolTip is not None:
                self._stateToolTip.setContent(f"已处理 {self._done} / {self._total} 个文件")

    def _on_finished(self, result) -> None:
        self._set_running(False)
        if self._check_mode:
            self._hide_state()
            self._show_info("工具检测完成，请查看日志。", "success")
            return
        count = len(result) if isinstance(result, list) else self._done
        self.progressBar.setValue(100)
        self.logBrowser.append(f"处理完成，共 {count} 个文件。")
        if self._stateToolTip is not None:
            self._stateToolTip.setContent(f"处理完成，共 {count} 个文件")
            self._stateToolTip.setState(True)
        QTimer.singleShot(2500, self._hide_state)
        self._show_info(f"处理完成，共 {count} 个文件。", "success")

    def _on_failed(self, exc: str) -> None:
        self._set_running(False)
        self._hide_state()
        self.logBrowser.append(f"错误：{exc}")
        self._show_info(exc, "error")


class ToolStatusCard(CardWidget):
    """A single row showing one helper tool's install status and an install button."""

    def __init__(self, icon, name: str, description: str, parent=None):
        super().__init__(parent)
        self.iconWidget = IconWidget(icon, self)
        self.titleLabel = StrongBodyLabel(name, self)
        self.descriptionLabel = CaptionLabel(description, self)
        self.successBadge = InfoBadge.success("已安装", self)
        self.errorBadge = InfoBadge.error("未安装", self)
        self.statusLabel = CaptionLabel("未检测", self)
        self.installButton = PrimaryPushButton("安装", self)
        self.installButton.setIcon(FluentIcon.DOWNLOAD)
        self.installButton.setFixedWidth(110)

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
        self.hBoxLayout.addWidget(self.installButton, 0, Qt.AlignVCenter)

    def set_status(self, text: str, installed: bool) -> None:
        self.statusLabel.setText(text)
        self.successBadge.setVisible(installed)
        self.errorBadge.setVisible(not installed)
        self.installButton.setText("已安装" if installed else "安装")
        self.installButton.setEnabled(not installed)


class ToolsInterface(InterfaceBase):
    """Page for installing/checking the external helper tools (exiftool, dnglab)."""

    def __init__(self, parent=None):
        super().__init__(
            "toolsInterface",
            "工具安装",
            "一键自动安装 exiftool 与 dnglab，按当前系统选择对应版本，无需管理员权限",
            parent,
        )

        self.exifCard = ToolStatusCard(FluentIcon.PHOTO, "ExifTool", "读写照片 EXIF 元数据的必需工具", self)
        self.dnglabCard = ToolStatusCard(FluentIcon.CLOUD_DOWNLOAD, "dnglab", "开源的 RAW→DNG 转换器（便携版）", self)
        self.refreshButton = PushButton("重新检测", self, FluentIcon.SYNC)
        self.installAllButton = PrimaryPushButton("全部安装", self, FluentIcon.DOWNLOAD)
        self.logBrowser = TextBrowser(self)
        self.logBrowser.setObjectName("logBrowser")
        self.progressBar = ProgressBar(self)

        self.header.addActionButton(self.refreshButton)
        self.header.addActionButton(self.installAllButton)
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)

        installCard = HeaderCardWidget(self)
        installCard.setTitle("外部工具")
        installCard.setBorderRadius(8)
        info = CaptionLabel(
            f"当前平台：{platform.system()} / {platform.machine()}　·　安装目录：{cache_dir()}",
            self,
        )
        info.setTextColor(QColor(96, 96, 96), QColor(216, 216, 216))
        info.setWordWrap(True)
        installContent = QVBoxLayout()
        installContent.setContentsMargins(0, 0, 0, 0)
        installContent.setSpacing(10)
        installContent.addWidget(self.exifCard)
        installContent.addWidget(self.dnglabCard)
        installContent.addWidget(info)
        installCard.viewLayout.addLayout(installContent, 1)

        logCard = HeaderCardWidget(self)
        logCard.setTitle("安装日志")
        logCard.setBorderRadius(8)
        logContent = QVBoxLayout()
        logContent.setContentsMargins(0, 0, 0, 0)
        logContent.setSpacing(12)
        logContent.addWidget(self.logBrowser, 1)
        logContent.addWidget(self.progressBar)
        logCard.viewLayout.addLayout(logContent, 1)

        self.vBoxLayout.addWidget(installCard)
        self.vBoxLayout.addWidget(logCard, 1)

        StyleSheet.TOOLS_INTERFACE.apply(self)

        self.exifCard.installButton.clicked.connect(self._install_exiftool)
        self.dnglabCard.installButton.clicked.connect(self._install_dnglab)
        self.refreshButton.clicked.connect(self._refresh_status)
        self.installAllButton.clicked.connect(self._install_all)

        self._worker: Optional[Worker] = None
        self._queue: Optional[List[str]] = None
        self._stateToolTip: Optional[StateToolTip] = None

        self._refresh_status()

    def _show_info(self, content: str, level: str = "info") -> None:
        parent = self.window() or self
        if level == "success":
            InfoBar.success("提示", content, isClosable=True, duration=4000, position=InfoBarPosition.BOTTOM_RIGHT, parent=parent)
        elif level == "warning":
            InfoBar.warning("提示", content, isClosable=True, duration=5000, position=InfoBarPosition.BOTTOM_RIGHT, parent=parent)
        else:
            InfoBar.error("错误", content, isClosable=True, duration=6000, position=InfoBarPosition.BOTTOM_RIGHT, parent=parent)

    def _show_state(self, title: str, content: str) -> None:
        if self._stateToolTip is None:
            self._stateToolTip = StateToolTip(title, content, self)
            self._stateToolTip.move(max(0, (self.width() - 360) // 2), self.header.height() + 8)
        else:
            self._stateToolTip.setTitle(title)
            self._stateToolTip.setContent(content)
            self._stateToolTip.setState(False)
        self._stateToolTip.show()

    def _hide_state(self) -> None:
        if self._stateToolTip is not None:
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
        self.progressBar.setValue(0)

    def _refresh_status(self) -> None:
        exif = find_exiftool()
        if exif:
            self.exifCard.set_status(f"已安装：{exif}", True)
        else:
            self.exifCard.set_status("未安装", False)

        dng = find_dnglab()
        if dng:
            self.dnglabCard.set_status(f"已安装：{dng}", True)
        else:
            adobe = find_adobe_dng_converter()
            text = f"未安装（已检测到 Adobe DNG Converter：{adobe}）" if adobe else "未安装"
            self.dnglabCard.set_status(text, False)

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

    def _install_all(self) -> None:
        if not self._ensure_idle():
            return
        missing = []
        if find_exiftool() is None:
            missing.append("exiftool")
        if find_dnglab() is None:
            missing.append("dnglab")
        if not missing:
            self._show_info("所有工具都已安装。", "success")
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
        self.logBrowser.append(f"正在安装 {name}…")
        self._show_state("正在安装", f"{name} 正在下载并安装到缓存目录…")
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
        if self._stateToolTip is not None:
            self._stateToolTip.setContent("工具安装完成")
            self._stateToolTip.setState(True)
        QTimer.singleShot(2500, self._hide_state)
        self._show_info("安装完成，请查看日志。", "success")


class MainWindow(MSFluentWindow):
    def __init__(self):
        super().__init__()
        self.convertInterface = ConvertInterface(self)
        self.toolsInterface = ToolsInterface(self)

        self.initNavigation()
        self.initWindow()

    def initNavigation(self) -> None:
        self.addSubInterface(self.convertInterface, FluentIcon.PHOTO, "转换")
        self.addSubInterface(self.toolsInterface, FluentIcon.CONNECT, "工具安装")
        self.navigationInterface.addItem(
            routeKey="theme",
            icon=FluentIcon.CONSTRACT,
            text="切换主题",
            onClick=lambda: toggleTheme(True),
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )
        self.navigationInterface.addItem(
            routeKey="about",
            icon=FluentIcon.INFO,
            text="关于",
            onClick=self._show_about,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )
        self.navigationInterface.setCurrentItem(self.convertInterface.objectName())

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
        box = MessageBox(
            APP_TITLE,
            "把任意相机的 RAW/DNG 照片处理成 Lightroom 能识别的富士机型，"
            "从而选出富士的胶片模拟。\n\n"
            "转换前请确保已安装 exiftool，以及 dnglab 或 Adobe DNG Converter。",
            self,
        )
        box.yesButton.setText("确定")
        box.cancelButton.hide()
        box.exec()


def run_app(argv: Optional[List[str]] = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationDisplayName(APP_TITLE)

    config_path = os.path.join(
        os.path.expanduser("~"), ".config", "fujifilm-converter", "config.json"
    )
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    qconfig.load(config_path)

    setTheme(Theme.AUTO)
    setThemeColor("#0078D4")
    window = MainWindow()
    window.show()
    return app.exec()


def main(argv: Optional[List[str]] = None) -> int:
    return run_app(argv)


if __name__ == "__main__":
    raise SystemExit(main())