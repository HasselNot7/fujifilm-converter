"""
Minimal zh/en translation layer for the GUI.

All user-visible strings go through tr(). Static widgets are re-populated by
each widget's apply_language() when the language changes; dynamic strings
(statuses, dialogs, log lines) pick up the new language automatically.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

LANGUAGES = ("zh", "en")

_TABLE: Dict[str, Dict[str, str]] = {
    "zh": {
        # window / navigation
        "nav_convert": "转换",
        "nav_tools": "工具安装",
        "nav_theme": "主题",
        "nav_language": "语言",
        "nav_about": "关于",
        "btn_ok": "确定",
        "btn_cancel": "取消",
        # input card
        "input_title": "输入文件 / 文件夹",
        "btn_add_files": "添加文件",
        "btn_add_folder": "添加文件夹",
        "btn_remove_selected": "移除选中",
        "btn_clear": "清空",
        "dlg_open_files": "选择 RAW / DNG 文件",
        "dlg_file_filter": "RAW / DNG 文件 (*.arw *.cr2 *.cr3 *.nef *.nrw *.raf *.orf *.rw2 *.pef *.srw *.dng *.raw *.rwl *.3fr *.iiq *.mef *.mrw *.erf *.kdc *.dcr *.gpr);;所有文件 (*.*)",
        "dlg_open_folder": "选择照片目录",
        # camera card
        "camera_title": "相机身份",
        "ph_make": "Make（如 FUJIFILM）",
        "ph_model": "Model（如 GFX100II）",
        "ph_ucm": "UniqueCameraModel（如 Fujifilm GFX 100 II）",
        "label_preset": "预设",
        "hint_preset": "选择 Lightroom 已支持的预设，多数情况默认 fuji 即可解锁富士胶片模拟",
        "label_custom": "自定义相机身份",
        "hint_custom": "需要完整填写 Make、Model、UniqueCameraModel 三项",
        # options card
        "options_title": "转换选项",
        "ph_archive_dir": "归档目录名（默认 originals）",
        "opt_archive": "转换后归档原始 RAW",
        "opt_archive_desc": "原始照片会移动到归档目录",
        "label_archive_dir": "归档目录：",
        "opt_skip": "跳过 RAW→DNG 转换",
        "opt_skip_desc": "输入文件必须已经是 DNG",
        "opt_backup": "保留 exiftool 备份文件",
        "opt_backup_desc": "会额外生成 *_original 文件",
        # convert page
        "convert_title": "照片转换",
        "convert_subtitle": "把任意相机的 RAW/DNG 照片处理成 Lightroom 能识别的富士机型，解锁胶片模拟",
        "btn_check_tools": "检测外部工具",
        "btn_start": "开始转换",
        "btn_processing": "处理中…",
        "log_title": "运行日志",
        "info_title": "提示",
        "error_title": "错误",
        "warn_no_inputs": "请先添加输入文件或文件夹。",
        "warn_custom_incomplete": "自定义相机身份需要完整填写 Make、Model、UniqueCameraModel 三项。",
        "warn_no_supported": "没有找到支持的 RAW / DNG 文件。",
        "log_found_files": "共发现 {n} 个文件，开始处理…",
        "state_converting": "正在转换",
        "state_checking": "检测外部工具",
        "state_checking_content": "正在检查 exiftool 与 RAW 转换器…",
        "state_processed": "已处理 {done} / {total} 个文件",
        "msg_check_done": "工具检测完成，请查看日志。",
        "log_done": "处理完成，共 {n} 个文件。",
        "state_done_content": "处理完成，共 {n} 个文件",
        "log_error": "错误：{exc}",
        # tool status card
        "badge_installed": "已安装",
        "badge_missing": "未安装",
        "status_unknown": "未检测",
        "btn_install": "安装",
        "btn_uninstall": "卸载",
        "btn_manual": "手动指定",
        "menu_pick_path": "选择路径…",
        "menu_clear_path": "清除手动路径",
        "exif_desc": "读写照片 EXIF 元数据的必需工具",
        "dnglab_desc": "开源的 RAW→DNG 转换器（便携版）",
        # tools page
        "tools_title": "工具安装",
        "tools_subtitle": "一键自动安装 exiftool 与 dnglab，按当前系统选择对应版本，无需管理员权限",
        "btn_refresh": "重新检测",
        "btn_install_all": "全部安装",
        "tools_card_title": "外部工具",
        "tools_info": "当前平台：{system} / {machine}　·　安装目录：{dir}",
        "log_install_title": "安装日志",
        "status_manual": "手动指定：{path}",
        "status_installed": "已安装：{path}",
        "status_missing": "未安装",
        "status_manual_invalid": "（手动路径无效，请重新选择或清除）",
        "status_manual_invalid_short": "手动路径无效，请重新选择或清除",
        "status_adobe": "未安装（已检测到 Adobe DNG Converter：{path}）",
        "msg_invalid_tool": "所选文件不是可用的工具（exiftool 需与其 exiftool_files 目录放在一起）。",
        "msg_manual_set": "已设置手动路径：{path}",
        "msg_manual_cleared": "已清除手动路径，恢复自动检测。",
        "dlg_pick_exif": "选择 ExifTool 可执行文件",
        "dlg_pick_dnglab": "选择 dnglab 可执行文件",
        "file_filter_exec": "可执行文件 (*.exe);;所有文件 (*)",
        "file_filter_all": "所有文件 (*)",
        "msg_no_cached_exif": "缓存目录中没有可卸载的 ExifTool。",
        "msg_no_cached_dnglab": "缓存目录中没有可卸载的 dnglab。",
        "dlg_confirm_uninstall": "确认卸载",
        "dlg_confirm_uninstall_body": "确定要卸载 {name} 吗？\n\n将删除：{target}",
        "log_uninstalling": "正在卸载 {name}…",
        "state_uninstalling": "正在卸载",
        "state_uninstalling_content": "{name} 正在从缓存目录中移除…",
        "msg_uninstalled": "{name} 已卸载。",
        "msg_all_installed": "所有工具都已安装。",
        "log_installing": "正在安装 {name}…",
        "state_installing": "正在安装",
        "state_installing_content": "{name} 正在下载并安装到缓存目录…",
        "state_install_done": "工具安装完成",
        "msg_install_done": "安装完成，请查看日志。",
        # about
        "about_content": (
            "把任意相机的 RAW/DNG 照片处理成 Lightroom 能识别的富士机型，"
            "从而选出富士的胶片模拟。\n\n"
            "转换前请确保已安装 exiftool，以及 dnglab 或 Adobe DNG Converter。"
        ),
    },
    "en": {
        "nav_convert": "Convert",
        "nav_tools": "Tools",
        "nav_theme": "Theme",
        "nav_language": "English",
        "nav_about": "About",
        "btn_ok": "OK",
        "btn_cancel": "Cancel",
        "input_title": "Input Files / Folders",
        "btn_add_files": "Add Files",
        "btn_add_folder": "Add Folder",
        "btn_remove_selected": "Remove Selected",
        "btn_clear": "Clear",
        "dlg_open_files": "Select RAW / DNG Files",
        "dlg_file_filter": "RAW / DNG Files (*.arw *.cr2 *.cr3 *.nef *.nrw *.raf *.orf *.rw2 *.pef *.srw *.dng *.raw *.rwl *.3fr *.iiq *.mef *.mrw *.erf *.kdc *.dcr *.gpr);;All Files (*.*)",
        "dlg_open_folder": "Select Photo Folder",
        "camera_title": "Camera Identity",
        "ph_make": "Make (e.g. FUJIFILM)",
        "ph_model": "Model (e.g. GFX100II)",
        "ph_ucm": "UniqueCameraModel (e.g. Fujifilm GFX 100 II)",
        "label_preset": "Preset",
        "hint_preset": "Pick a preset Lightroom already supports; the default \"fuji\" unlocks Fujifilm film simulations",
        "label_custom": "Custom Camera Identity",
        "hint_custom": "Make, Model and UniqueCameraModel must all be filled in",
        "options_title": "Conversion Options",
        "ph_archive_dir": "Archive folder name (default: originals)",
        "opt_archive": "Archive Original RAW after Conversion",
        "opt_archive_desc": "Originals are moved into the archive folder",
        "label_archive_dir": "Archive folder:",
        "opt_skip": "Skip RAW→DNG Conversion",
        "opt_skip_desc": "Inputs must already be DNG",
        "opt_backup": "Keep exiftool Backup Files",
        "opt_backup_desc": "Generates extra *_original files",
        "convert_title": "Photo Conversion",
        "convert_subtitle": "Process RAW/DNG photos from any camera into Fujifilm models Lightroom recognizes, unlocking film simulations",
        "btn_check_tools": "Check Tools",
        "btn_start": "Start Conversion",
        "btn_processing": "Processing…",
        "log_title": "Run Log",
        "info_title": "Notice",
        "error_title": "Error",
        "warn_no_inputs": "Add input files or folders first.",
        "warn_custom_incomplete": "Custom camera identity requires Make, Model and UniqueCameraModel.",
        "warn_no_supported": "No supported RAW / DNG files found.",
        "log_found_files": "Found {n} files, starting…",
        "state_converting": "Converting",
        "state_checking": "Checking Tools",
        "state_checking_content": "Checking exiftool and the RAW converter…",
        "state_processed": "Processed {done} / {total} files",
        "msg_check_done": "Tool check finished, see the log.",
        "log_done": "Done, {n} files processed.",
        "state_done_content": "Done, {n} files processed",
        "log_error": "Error: {exc}",
        "badge_installed": "Installed",
        "badge_missing": "Not Installed",
        "status_unknown": "Not Checked",
        "btn_install": "Install",
        "btn_uninstall": "Uninstall",
        "btn_manual": "Manual Path",
        "menu_pick_path": "Choose Path…",
        "menu_clear_path": "Clear Manual Path",
        "exif_desc": "Required tool for reading/writing photo EXIF metadata",
        "dnglab_desc": "Open-source RAW→DNG converter (portable)",
        "tools_title": "Tool Setup",
        "tools_subtitle": "One-click install of exiftool and dnglab with the right build for this OS, no admin rights needed",
        "btn_refresh": "Re-check",
        "btn_install_all": "Install All",
        "tools_card_title": "External Tools",
        "tools_info": "Platform: {system} / {machine} · Install folder: {dir}",
        "log_install_title": "Install Log",
        "status_manual": "Manual: {path}",
        "status_installed": "Installed: {path}",
        "status_missing": "Not Installed",
        "status_manual_invalid": " (manual path invalid — pick again or clear)",
        "status_manual_invalid_short": "Manual path invalid — pick again or clear",
        "status_adobe": "Not installed (found Adobe DNG Converter: {path})",
        "msg_invalid_tool": "The selected file is not a usable tool (exiftool needs its exiftool_files folder beside it).",
        "msg_manual_set": "Manual path set: {path}",
        "msg_manual_cleared": "Manual path cleared, auto-detection restored.",
        "dlg_pick_exif": "Select ExifTool Executable",
        "dlg_pick_dnglab": "Select dnglab Executable",
        "file_filter_exec": "Executable (*.exe);;All Files (*)",
        "file_filter_all": "All Files (*)",
        "msg_no_cached_exif": "No cached ExifTool to uninstall.",
        "msg_no_cached_dnglab": "No cached dnglab to uninstall.",
        "dlg_confirm_uninstall": "Confirm Uninstall",
        "dlg_confirm_uninstall_body": "Uninstall {name}?\n\nWill delete: {target}",
        "log_uninstalling": "Uninstalling {name}…",
        "state_uninstalling": "Uninstalling",
        "state_uninstalling_content": "Removing {name} from the cache folder…",
        "msg_uninstalled": "{name} uninstalled.",
        "msg_all_installed": "All tools are already installed.",
        "log_installing": "Installing {name}…",
        "state_installing": "Installing",
        "state_installing_content": "Downloading and installing {name} to the cache folder…",
        "state_install_done": "Tools Installed",
        "msg_install_done": "Installation finished, see the log.",
        "about_content": (
            "Process RAW/DNG photos from any camera into Fujifilm models "
            "Lightroom recognizes, so Fujifilm film simulations become available.\n\n"
            "Make sure exiftool is installed, plus dnglab or Adobe DNG Converter, "
            "before converting."
        ),
    },
}


class Translator:
    def __init__(self) -> None:
        self._lang = "zh"
        self._listeners: List[Callable[[], None]] = []

    @property
    def lang(self) -> str:
        return self._lang

    def set_language(self, lang: Optional[str]) -> None:
        if lang not in _TABLE or lang == self._lang:
            return
        self._lang = lang
        for fn in self._listeners:
            fn()

    def toggle(self) -> str:
        self.set_language("en" if self._lang == "zh" else "zh")
        return self._lang

    def on_change(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def tr(self, key: str, **kwargs) -> str:
        text = _TABLE.get(self._lang, {}).get(key) or _TABLE["zh"].get(key) or key
        return text.format(**kwargs) if kwargs else text


t = Translator()
tr = t.tr
