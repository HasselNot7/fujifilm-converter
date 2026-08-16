# 打包说明（Windows）

## 前置条件

- Windows 10/11
- Python 3.8+，已安装依赖：

```sh
python3 -m pip install -e ".[gui]"   # PySide6 + PySide6-Fluent-Widgets
python3 -m pip install pyinstaller pillow
```

## 一键打包

```sh
pyinstaller --noconfirm --clean FujifilmConverter.spec
```

产物在 `dist/FujifilmConverter/`（onedir 模式）。整个文件夹直接复制给别人即可，双击 `FujifilmConverter.exe` 启动，**对方无需安装 Python 或任何环境**。

## spec 已配置的内容

- `--windowed`：无控制台窗口
- `collect_all('qfluentwidgets')`：打包 Fluent 组件资源
- `collect_data_files('fujifilm_converter.gui')`：打包界面 QSS 和应用图标
- `icon='packaging/fujifilm-converter.ico'`：exe 图标
- 入口脚本 `packaging/gui_entry.py` 调用 `fujifilm_converter.gui.app:main`

## 注意事项

- exiftool / dnglab **不打包进 exe**，由程序内置的「工具安装」页面在运行时下载到用户缓存目录
- 首次启动时杀毒软件可能扫描 10~30 秒，窗口打开较慢属正常现象
- onedir 体积约 150MB；如需单文件可改 `--onefile`（启动更慢、更易被杀毒软件误报，不推荐）

## 更新图标

1. 用 256×256 以上、透明背景的 PNG 生成多尺寸 ICO：

```python
from PIL import Image
Image.open("logo.png").convert("RGBA").save(
    "fujifilm-converter.ico",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
```

2. 覆盖 `packaging/fujifilm-converter.ico`
3. 窗口标题栏图标同步替换 `src/fujifilm_converter/gui/resource/images/app.png`
4. 重新打包

## 验证

启动 `dist/FujifilmConverter/FujifilmConverter.exe`，确认：

- 标题栏显示「Fujifilm Converter」，图标正确
- 转换页 / 工具页正常打开，主题与语言切换正常
- 转换一张照片、安装 exiftool 均可用
