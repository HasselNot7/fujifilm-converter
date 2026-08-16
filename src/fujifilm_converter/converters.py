"""
RAW / DNG converter discovery and execution, plus tool installation.

Handles finding Adobe DNG Converter or dnglab, performing the RAW → DNG
conversion step, and installing missing helpers (exiftool / dnglab) into a
per-user cache directory so no admin rights are needed on Windows.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from typing import Tuple, Optional

from . import log

RAW_EXTENSIONS = {
    "arw", "cr2", "cr3", "nef", "nrw", "raf", "orf", "rw2", "pef", "srw",
    "dng", "raw", "rwl", "3fr", "iiq", "mef", "mrw", "erf", "kdc", "dcr", "gpr",
}

ADOBE_DNG_CONVERTER_PATHS = {
    "Darwin": "/Applications/Adobe DNG Converter.app/Contents/MacOS/Adobe DNG Converter",
    "Windows": r"C:\Program Files\Adobe\Adobe DNG Converter\Adobe DNG Converter.exe",
}

EXIFTOOL_VERSION_URL = "https://exiftool.org/ver.txt"
EXIFTOOL_DOWNLOAD_URL = "https://sourceforge.net/projects/exiftool/files/exiftool-{version}_{bit}.zip/download"
EXIFTOOL_TARBALL_URL = "https://sourceforge.net/projects/exiftool/files/Image-ExifTool-{version}.tar.gz/download"
DNGTAB_RELEASES_URL = "https://api.github.com/repos/dnglab/dnglab/releases/latest"


def file_extension(path: str) -> str:
    return os.path.splitext(path)[1].lstrip(".").lower()


def is_raw_file(path: str) -> bool:
    return file_extension(path) in RAW_EXTENSIONS


def is_dng_file(path: str) -> bool:
    return file_extension(path) == "dng"


def cache_dir() -> str:
    path = os.environ.get("FUJI_CONVERT_CACHE") or os.path.expanduser("~/.cache/fujifilm-converter")
    os.makedirs(path, exist_ok=True)
    return path


def find_executable(name: str) -> Optional[str]:
    found = shutil.which(name)
    if found:
        return found
    ext = ".exe" if os.name == "nt" else ""
    cache = cache_dir()
    candidates = [
        os.path.join(cache, name + ext),
        os.path.join(cache, name, name + ext),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


EXIFTOOL_ENV = "FUJIFILM_EXIFTOOL"
DNGLAB_ENV = "FUJIFILM_DNGLAB"


def is_valid_exiftool(path: str) -> bool:
    """True when the file can be used as exiftool (Windows needs exiftool_files beside it)."""
    return bool(path) and os.path.isfile(path) and _exiftool_install_valid(path)


def is_valid_dnglab(path: str) -> bool:
    return bool(path) and os.path.isfile(path)


def env_exiftool() -> Optional[str]:
    value = os.environ.get(EXIFTOOL_ENV)
    if is_valid_exiftool(value or ""):
        return value
    return None


def env_dnglab() -> Optional[str]:
    value = os.environ.get(DNGLAB_ENV)
    if is_valid_dnglab(value or ""):
        return value
    return None


def find_adobe_dng_converter() -> Optional[str]:
    custom = os.environ.get("ADOBE_DNG_CONVERTER")
    if custom and os.path.isfile(custom):
        return custom

    system = platform.system()
    default_path = ADOBE_DNG_CONVERTER_PATHS.get(system)
    if default_path and os.path.isfile(default_path):
        return default_path
    return None


def find_dng_converter() -> Tuple[Optional[str], Optional[str]]:
    """Return (converter_type, path) or (None, None)."""
    custom = env_dnglab()
    if custom:
        return ("dnglab", custom)

    adobe = find_adobe_dng_converter()
    if adobe:
        return ("adobe", adobe)

    dnglab = find_executable("dnglab")
    if dnglab:
        return ("dnglab", dnglab)

    # Auto-download portable dnglab binary if missing (makes install closer to one-click)
    dnglab = _ensure_dnglab()
    if dnglab:
        return ("dnglab", dnglab)

    return (None, None)


def _cached_dnglab() -> Optional[str]:
    bin_path = os.path.join(cache_dir(), "dnglab" + (".exe" if os.name == "nt" else ""))
    if os.path.isfile(bin_path):
        return bin_path
    return None


def _ensure_dnglab() -> Optional[str]:
    """Download the portable dnglab binary into the cache. Returns path or None."""
    cached = _cached_dnglab()
    if cached:
        return cached

    system = platform.system()
    machine = platform.machine().lower()
    is_zip = False

    if system == "Darwin":
        if "arm" in machine or "aarch" in machine:
            asset = "dnglab-macos-arm64"
        else:
            return None
        download_name = "dnglab_download.zip"
        is_zip = True
    elif system == "Windows":
        asset = "dnglab-win-x64"
        download_name = "dnglab_download.zip"
        is_zip = True
    elif system == "Linux":
        asset = "dnglab_linux_aarch64" if ("aarch" in machine or "arm" in machine) else "dnglab_linux_x64"
        download_name = "dnglab_download"
    else:
        return None

    log.info("dnglab not found, downloading portable binary...")
    try:
        with urllib.request.urlopen(DNGTAB_RELEASES_URL, timeout=30) as resp:
            release = json.load(resp)

        download_url = None
        for a in release.get("assets", []):
            if asset in a.get("name", ""):
                download_url = a["browser_download_url"]
                break

        if not download_url:
            log.info("Could not find matching dnglab asset for this platform.")
            return None

        download_path = os.path.join(cache_dir(), download_name)
        _download_file(download_url, download_path)

        bin_path = os.path.join(cache_dir(), "dnglab" + (".exe" if os.name == "nt" else ""))
        if is_zip:
            with zipfile.ZipFile(download_path) as zf:
                target = None
                for member in zf.namelist():
                    if member.endswith("/"):
                        continue
                    base = os.path.basename(member)
                    if base.lower().startswith("dnglab"):
                        target = member
                        break
                if target is None:
                    log.info("Could not find the dnglab executable inside the archive.")
                    os.remove(download_path)
                    return None
                zf.extract(target, cache_dir())
                extracted = os.path.join(cache_dir(), target)
                if os.path.normpath(extracted) != os.path.normpath(bin_path):
                    os.rename(extracted, bin_path)
            os.remove(download_path)
        else:
            os.rename(download_path, bin_path)

        if os.name != "nt":
            os.chmod(bin_path, 0o755)
        log.info(f"Downloaded dnglab to {bin_path}")
        return bin_path
    except Exception as e:
        log.info(f"Failed to auto-download dnglab: {e}")
        return None


def find_dnglab() -> Optional[str]:
    return env_dnglab() or find_executable("dnglab") or _cached_dnglab()


def _download_file(url: str, dest: str) -> None:
    """Stream a download to dest, logging progress in 10% steps."""
    log.info(f"Downloading {url}")
    tmp = dest + ".part"
    request = urllib.request.Request(url, headers={"User-Agent": "fujifilm-converter"})
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            last_pct = -1
            with open(tmp, "wb") as fh:
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        if pct != last_pct and pct % 10 == 0:
                            last_pct = pct
                            log.info(f"  download {pct}%")
    finally:
        if os.path.exists(tmp):
            os.replace(tmp, dest)


def _run_install(command: list[str], timeout: int = 600) -> None:
    """Run a package-manager install, streaming output, raising on failure."""
    log.info(f"[install] {' '.join(command)}")
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    try:
        for line in proc.stdout:
            log.info(line.rstrip("\r\n"))
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError(f"安装命令超时：{' '.join(command)}")
    if proc.returncode != 0:
        raise RuntimeError(f"安装命令失败（退出码 {proc.returncode}）：{' '.join(command)}")


def exiftool_binary_path() -> str:
    return os.path.join(cache_dir(), "exiftool", "exiftool" + (".exe" if os.name == "nt" else ""))


def _exiftool_install_valid(path: str) -> bool:
    """On Windows the exe needs its exiftool_files support dir beside it."""
    if os.name != "nt":
        return True
    return os.path.isdir(os.path.join(os.path.dirname(path), "exiftool_files"))


def find_exiftool() -> Optional[str]:
    custom = env_exiftool()
    if custom:
        return custom
    found = find_executable("exiftool")
    if found and _exiftool_install_valid(found):
        return found
    cached = exiftool_binary_path()
    if os.path.isfile(cached) and _exiftool_install_valid(cached):
        return cached
    return None


def _latest_exiftool_version() -> Optional[str]:
    try:
        with urllib.request.urlopen(EXIFTOOL_VERSION_URL, timeout=30) as resp:
            return resp.read().decode("utf-8", "replace").strip() or None
    except Exception as e:
        log.info(f"Failed to fetch the latest exiftool version: {e}")
        return None


def _install_exiftool_windows() -> str:
    version = _latest_exiftool_version()
    if not version:
        raise RuntimeError("无法获取 exiftool 最新版本号，请稍后重试")
    url = EXIFTOOL_DOWNLOAD_URL.format(version=version, bit="64")
    archive = os.path.join(cache_dir(), f"exiftool-{version}_64.zip")
    _download_file(url, archive)

    tmp_dir = os.path.join(cache_dir(), "exiftool_extract_tmp")
    if os.path.isdir(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(tmp_dir)
    finally:
        os.remove(archive)

    # The zip nests everything under a top-level folder. The exe must sit
    # next to its exiftool_files support directory, so move both together.
    exe_src = None
    files_src = None
    for root, dirs, files in os.walk(tmp_dir):
        if exe_src is None:
            for name in files:
                if name.lower().startswith("exiftool") and name.lower().endswith(".exe"):
                    exe_src = os.path.join(root, name)
                    break
        if files_src is None and "exiftool_files" in dirs:
            files_src = os.path.join(root, "exiftool_files")
        if exe_src and files_src:
            break

    if exe_src is None or files_src is None:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError("下载内容中未找到 exiftool 可执行文件或 exiftool_files 目录")

    extract_dir = os.path.join(cache_dir(), "exiftool")
    if os.path.isdir(extract_dir):
        shutil.rmtree(extract_dir)
    os.makedirs(extract_dir)

    bin_path = exiftool_binary_path()
    shutil.move(exe_src, bin_path)
    shutil.move(files_src, os.path.join(extract_dir, "exiftool_files"))
    shutil.rmtree(tmp_dir, ignore_errors=True)

    log.info(f"exiftool installed to {bin_path}")
    return bin_path


def _install_exiftool_portable() -> str:
    """macOS/Linux: portable Perl distribution wrapped in a small launcher."""
    version = _latest_exiftool_version()
    if not version:
        raise RuntimeError("无法获取 exiftool 最新版本号，请稍后重试")

    perl = find_executable("perl")
    if not perl:
        raise RuntimeError("未找到 perl（macOS/Linux 一般自带），无法安装便携版 exiftool")

    url = EXIFTOOL_TARBALL_URL.format(version=version)
    archive = os.path.join(cache_dir(), f"Image-ExifTool-{version}.tar.gz")
    _download_file(url, archive)

    extract_dir = os.path.join(cache_dir(), "exiftool")
    os.makedirs(extract_dir, exist_ok=True)
    try:
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(extract_dir)
    finally:
        os.remove(archive)

    root = None
    for name in os.listdir(extract_dir):
        if name.startswith("Image-ExifTool-"):
            root = os.path.join(extract_dir, name)
            break
    if not root:
        raise RuntimeError("下载内容中未找到 exiftool 源码目录")

    lib_dir = os.path.join(root, "lib")
    script = os.path.join(root, "exiftool")
    if not os.path.isfile(script):
        raise RuntimeError("下载内容中未找到 exiftool 脚本")

    bin_path = exiftool_binary_path()
    launcher = f"#!/bin/sh\nexec {perl} -I '{lib_dir}' '{script}' \"$@\"\n"
    with open(bin_path, "w", encoding="utf-8") as fh:
        fh.write(launcher)
    os.chmod(bin_path, 0o755)
    log.info(f"exiftool installed to {bin_path}")
    return bin_path


def install_exiftool() -> str:
    existing = find_exiftool()
    if existing:
        log.info(f"exiftool 已存在：{existing}")
        return existing

    system = platform.system()
    if system == "Windows":
        return _install_exiftool_windows()
    if system == "Darwin":
        try:
            return _install_exiftool_portable()
        except Exception as exc:
            raise RuntimeError(
                f"exiftool 自动安装失败：{exc}\n请手动执行：brew install exiftool"
            ) from exc
    if system == "Linux":
        try:
            return _install_exiftool_portable()
        except Exception as exc:
            raise RuntimeError(
                f"exiftool 自动安装失败：{exc}\n请手动执行：sudo apt-get install exiftool"
            ) from exc
    raise RuntimeError(f"不支持的平台：{system}")


def install_dnglab() -> str:
    existing = find_dnglab()
    if existing:
        log.info(f"dnglab 已存在：{existing}")
        return existing

    downloaded = _ensure_dnglab()
    if downloaded:
        return downloaded

    system = platform.system()
    if system == "Darwin":
        if find_executable("brew"):
            _run_install(["brew", "install", "dnglab"])
            found = find_dnglab()
            if found:
                return found
        raise RuntimeError("dnglab 安装失败，请手动执行：brew install dnglab")
    raise RuntimeError("dnglab 自动安装失败，请手动安装，或安装 Adobe DNG Converter")


def ensure_dir(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(path)


def cached_exiftool_install() -> Optional[str]:
    """Return the cache-managed exiftool directory if present (valid or not)."""
    target = os.path.join(cache_dir(), "exiftool")
    if os.path.exists(target):
        return target
    return None


def uninstall_exiftool() -> str:
    """Remove the cache-managed portable exiftool install. System installs are untouched."""
    target = os.path.join(cache_dir(), "exiftool")
    if os.path.isdir(target):
        shutil.rmtree(target, ignore_errors=True)
    elif os.path.isfile(target):
        os.remove(target)
    log.info(f"exiftool 已卸载：{target}")
    return target


def uninstall_dnglab() -> str:
    """Remove the cache-managed portable dnglab binary. System installs are untouched."""
    bin_path = os.path.join(cache_dir(), "dnglab" + (".exe" if os.name == "nt" else ""))
    if os.path.isfile(bin_path):
        os.remove(bin_path)
    log.info(f"dnglab 已卸载：{bin_path}")
    return bin_path


def run_command(command: list[str], label: str) -> subprocess.CompletedProcess:
    """Run a command, stream its output through log.info, raise on failure."""
    log.info(f"[{label}] {' '.join(command)}")
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    for line in proc.stdout:
        log.info(line.rstrip("\r\n"))
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {proc.returncode}")
    return subprocess.CompletedProcess(command, proc.returncode)


def expected_dng_path(raw_path: str) -> str:
    return os.path.splitext(raw_path)[0] + ".dng"


def find_converted_dng(raw_path: str) -> Optional[str]:
    base = os.path.splitext(raw_path)[0]
    for ext in (".dng", ".DNG"):
        candidate = base + ext
        if os.path.isfile(candidate):
            return candidate
    return None


def convert_raw_to_dng(raw_path: str, converter_type: str, converter_path: str, output_dir: Optional[str] = None) -> str:
    if output_dir:
        output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)
    else:
        output_dir = os.path.dirname(os.path.abspath(raw_path))

    base = os.path.splitext(os.path.basename(raw_path))[0]
    expected = os.path.join(output_dir, base + ".dng")

    if converter_type == "adobe":
        run_command(
            [converter_path, "-fl", "-mp", "-d", output_dir, raw_path],
            "RAW to DNG (Adobe DNG Converter)",
        )
    elif converter_type == "dnglab":
        run_command(
            [converter_path, "convert", "-f", raw_path, expected],
            "RAW to DNG (dnglab)",
        )
    else:
        raise RuntimeError("No RAW to DNG converter found")

    if os.path.isfile(expected):
        return expected
    dng_path = find_converted_dng(raw_path)
    if not dng_path:
        raise RuntimeError(f"DNG output not found for {raw_path}")
    return dng_path


def print_converter_status() -> None:
    converter_type, converter_path = find_dng_converter()
    exiftool = find_exiftool()
    log.info(f"exiftool: {'found' if exiftool else 'missing (install from https://exiftool.org/ or brew/apt)'}")
    if converter_path:
        log.info(f"RAW converter: {converter_type} ({converter_path})")
    else:
        log.info("RAW converter: missing (will try to auto-download dnglab; or install Adobe DNG Converter)")
