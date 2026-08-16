"""
PySide6 desktop GUI for fujifilm-converter built with PySide6-Fluent-Widgets.

The window is organized into fluent cards: input files, camera identity,
conversion options, and a live log area. Conversion and tool checks run on a
background QThread so the UI stays responsive.
"""

from __future__ import annotations

import sys
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    FluentIcon,
    HeaderCardWidget,
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
    SubtitleLabel,
    SwitchButton,
    TextBrowser,
    setTheme,
    setThemeColor,
    Theme,
)

from ..cameras import list_presets
from ..core import collect_input_paths, process_inputs, print_status
from .worker import Worker

APP_TITLE = "Fujifilm Converter"
APP_ICON = ":/qfluentwidgets/images/logo.png"


class InputCard(HeaderCardWidget):
    """Card for choosing RAW/DNG files or directories."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("输入文件 / 文件夹")
        self.setBorderRadius(8)

        self.listWidget = ListWidget(self)
        self.addFileButton = PushButton("添加文件", self)
        self.addFolderButton = PushButton("添加文件夹", self)
        self.removeButton = PushButton("移除选中", self)
        self.clearButton = PushButton("清空", self)

        self.addFileButton.setIcon(FluentIcon.DOCUMENT)
        self.addFolderButton.setIcon(FluentIcon.FOLDER)
        self.listWidget.setMinimumHeight(140)

        buttonLayout = QHBoxLayout()
        buttonLayout.setContentsMargins(0, 0, 0, 0)
        buttonLayout.setSpacing(8)
        buttonLayout.addWidget(self.addFileButton)
        buttonLayout.addWidget(self.addFolderButton)
        buttonLayout.addStretch(1)
        buttonLayout.addWidget(self.removeButton)
        buttonLayout.addWidget(self.clearButton)

        self.viewLayout.addWidget(self.listWidget, 1)
        self.viewLayout.addLayout(buttonLayout)

        self.addFileButton.clicked.connect(self._add_files)
        self.addFolderButton.clicked.connect(self._add_folder)
        self.removeButton.clicked.connect(self._remove_selected)
        self.clearButton.clicked.connect(self.listWidget.clear)

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
        self.presetCombo.setFixedWidth(220)
        self.presetCombo.setCurrentText("fuji")

        self.customSwitch = SwitchButton("自定义相机身份", self)
        self.makeEdit = LineEdit(self)
        self.modelEdit = LineEdit(self)
        self.ucmEdit = LineEdit(self)

        self.makeEdit.setPlaceholderText("Make（如 FUJIFILM）")
        self.modelEdit.setPlaceholderText("Model（如 GFX100II）")
        self.ucmEdit.setPlaceholderText("UniqueCameraModel（如 Fujifilm GFX 100 II）")
        self.makeEdit.setClearButtonEnabled(True)
        self.modelEdit.setClearButtonEnabled(True)
        self.ucmEdit.setClearButtonEnabled(True)

        customRow = QHBoxLayout()
        customRow.setContentsMargins(0, 0, 0, 0)
        customRow.addWidget(self.customSwitch)
        customRow.addStretch(1)

        self.viewLayout.addWidget(BodyLabel("预设：只需选一个简单的名字", self))
        self.viewLayout.addWidget(self.presetCombo)
        self.viewLayout.addSpacing(8)
        self.viewLayout.addLayout(customRow)
        self.viewLayout.addWidget(self.makeEdit)
        self.viewLayout.addWidget(self.modelEdit)
        self.viewLayout.addWidget(self.ucmEdit)

        self._update_custom_enabled(False)
        self.customSwitch.checkedChanged.connect(self._update_custom_enabled)

    def _update_custom_enabled(self, enabled: bool) -> None:
        self.makeEdit.setEnabled(enabled)
        self.modelEdit.setEnabled(enabled)
        self.ucmEdit.setEnabled(enabled)
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

        self.archiveSwitch = SwitchButton("转换后归档原始 RAW", self)
        self.skipSwitch = SwitchButton("跳过 RAW→DNG 转换（输入须已是 DNG）", self)
        self.backupSwitch = SwitchButton("保留 exiftool 备份文件", self)
        self.archiveDirEdit = LineEdit(self)

        self.archiveSwitch.setChecked(True)
        self.archiveDirEdit.setText("originals")
        self.archiveDirEdit.setPlaceholderText("归档目录名（默认 originals）")
        self.archiveDirEdit.setFixedWidth(220)
        self.archiveDirEdit.setClearButtonEnabled(True)

        archiveRow = QHBoxLayout()
        archiveRow.setContentsMargins(0, 0, 0, 0)
        archiveRow.addWidget(self.archiveSwitch)
        archiveRow.addStretch(1)
        archiveRow.addWidget(BodyLabel("归档目录：", self))
        archiveRow.addWidget(self.archiveDirEdit)

        self.viewLayout.addLayout(archiveRow)
        self.viewLayout.addWidget(self.skipSwitch)
        self.viewLayout.addWidget(self.backupSwitch)

        self.archiveSwitch.checkedChanged.connect(self.archiveDirEdit.setEnabled)
        self.archiveDirEdit.setEnabled(self.archiveSwitch.isChecked())


class ConvertInterface(ScrollArea):
    """Main page: inputs, options, actions and the live log."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = QWidget(self)

        self.inputCard = InputCard(self)
        self.cameraCard = CameraCard(list_presets(), self)
        self.optionCard = OptionCard(self)
        self.logBrowser = TextBrowser(self)
        self.progressBar = ProgressBar(self)
        self.checkButton = PushButton("检测外部工具", self)
        self.startButton = PrimaryPushButton("开始转换", self)

        self.checkButton.setIcon(FluentIcon.ROBOT)
        self.startButton.setIcon(FluentIcon.PLAY)
        self.progressBar.setRange(0, 100)
        self.progressBar.setValue(0)

        logCard = HeaderCardWidget(self)
        logCard.setTitle("运行日志")
        logCard.setBorderRadius(8)
        logCard.viewLayout.addWidget(self.logBrowser)
        logCard.viewLayout.addWidget(self.progressBar)

        actionLayout = QHBoxLayout()
        actionLayout.setContentsMargins(0, 0, 0, 0)
        actionLayout.addWidget(self.checkButton)
        actionLayout.addStretch(1)
        actionLayout.addWidget(self.startButton)

        self.vBoxLayout = QVBoxLayout(self.view)
        self.vBoxLayout.setContentsMargins(0, 0, 10, 30)
        self.vBoxLayout.setSpacing(10)
        self.vBoxLayout.addWidget(self.inputCard, 0, Qt.AlignTop)
        self.vBoxLayout.addWidget(self.cameraCard, 0, Qt.AlignTop)
        self.vBoxLayout.addWidget(self.optionCard, 0, Qt.AlignTop)
        self.vBoxLayout.addLayout(actionLayout)
        self.vBoxLayout.addWidget(logCard, 1)

        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setObjectName("convertInterface")
        self.enableTransparentBackground()

        self.checkButton.clicked.connect(self._check_tools)
        self.startButton.clicked.connect(self._start)

        self._worker: Optional[Worker] = None
        self._check_mode = False
        self._total = 0
        self._done = 0

    def _show_info(self, content: str, level: str = "info") -> None:
        parent = self.window() or self
        if level == "success":
            InfoBar.success("提示", content, isClosable=True, duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=parent)
        elif level == "warning":
            InfoBar.warning("提示", content, isClosable=True, duration=5000, position=InfoBarPosition.TOP_RIGHT, parent=parent)
        else:
            InfoBar.error("错误", content, isClosable=True, duration=6000, position=InfoBarPosition.TOP_RIGHT, parent=parent)

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

    def _on_finished(self, result) -> None:
        self._set_running(False)
        if self._check_mode:
            self._show_info("工具检测完成，请查看日志。", "success")
            return
        count = len(result) if isinstance(result, list) else self._done
        self.progressBar.setValue(100)
        self.logBrowser.append(f"处理完成，共 {count} 个文件。")
        self._show_info(f"处理完成，共 {count} 个文件。", "success")

    def _on_failed(self, exc: str) -> None:
        self._set_running(False)
        self.logBrowser.append(f"错误：{exc}")
        self._show_info(exc, "error")


class MainWindow(MSFluentWindow):
    def __init__(self):
        super().__init__()
        self.convertInterface = ConvertInterface(self)

        self.initNavigation()
        self.initWindow()

    def initNavigation(self) -> None:
        self.addSubInterface(self.convertInterface, FluentIcon.PHOTO, "转换")
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
        self.resize(860, 740)
        self.setWindowIcon(QIcon(APP_ICON))
        self.setWindowTitle(APP_TITLE)

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
    setTheme(Theme.AUTO)
    setThemeColor("#0078D4")
    window = MainWindow()
    window.show()
    return app.exec()


def main(argv: Optional[List[str]] = None) -> int:
    return run_app(argv)


if __name__ == "__main__":
    raise SystemExit(main())