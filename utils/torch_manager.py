"""PyTorch 版本管理器 - CUDA/CPU 模式检测与切换

提供以下功能:
- 检测当前 PyTorch 运行模式（CPU / CUDA）
- 从 GitHub Release 下载 CUDA addon 组件
- 安装/卸载 CUDA addon（DLL 文件管理）
- 手动安装兜底方案
"""

import logging
import zipfile
from pathlib import Path
from typing import Callable, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from config import get_app_dir

logger = logging.getLogger(__name__)

# 应用版本（与 installer.iss 一致）
APP_VERSION = "1.0.0"

# GitHub Release 下载地址模板
GITHUB_REPO = "Patrick684/voice-calendar"
GITHUB_RELEASE_URL = f"https://github.com/{GITHUB_REPO}/releases/download/v{{version}}/cuda_addon_{{version}}.zip"

# CUDA DLL 文件匹配模式（用于检测和清理）
CUDA_DLL_PATTERNS = [
    "cudnn*.dll",
    "cublas*.dll",
    "cublasLt*.dll",
    "cufft*.dll",
    "curand*.dll",
    "cusolver*.dll",
    "cusparse*.dll",
    "nvrtc*.dll",
    "nvinfer*.dll",
    "torch_cuda*.dll",
    "c10_cuda.dll",
    "caffe2_nvrtc.dll",
]

# CUDA addon 预估大小（用于 UI 显示）
CUDA_ADDON_ESTIMATED_SIZE = "约 2 GB"

# addon zip 文件名
ADDON_ZIP_FILENAME = f"cuda_addon_{APP_VERSION}.zip"


def detect_torch_mode() -> str:
    """检测当前 PyTorch 是否支持 CUDA

    Returns:
        "cuda" 如果 CUDA 可用且相关 DLL 存在
        "cpu" 否则
    """
    try:
        import torch

        if not torch.cuda.is_available():
            return "cpu"

        # 额外检查：打包模式下验证 CUDA DLL 是否存在
        if getattr(import_module_sys(), "frozen", False):
            app_dir = get_app_dir()
            cuda_dlls = _find_cuda_dlls(app_dir)
            if not cuda_dlls:
                return "cpu"

        return "cuda"
    except Exception:
        return "cpu"


def import_module_sys():
    """延迟导入 sys 模块"""
    import sys

    return sys


def is_cuda_addon_installed() -> bool:
    """检查 CUDA addon 是否已安装（通过检测关键 DLL）"""
    app_dir = get_app_dir()
    cuda_dlls = _find_cuda_dlls(app_dir)
    return len(cuda_dlls) > 0


def get_cuda_addon_size() -> str:
    """获取 CUDA addon 的预估下载大小"""
    return CUDA_ADDON_ESTIMATED_SIZE


def get_download_url(version: str = APP_VERSION) -> str:
    """获取 CUDA addon 的下载 URL"""
    return GITHUB_RELEASE_URL.format(version=version)


def get_manual_download_url() -> str:
    """获取 GitHub Release 页面 URL（手动下载兜底）"""
    return f"https://github.com/{GITHUB_REPO}/releases/tag/v{APP_VERSION}"


def get_addon_zip_path() -> Path:
    """获取 addon zip 应放置的本地路径"""
    return get_app_dir() / ADDON_ZIP_FILENAME


def check_manual_addon() -> Optional[Path]:
    """检查用户是否手动放置了 cuda_addon.zip

    Returns:
        zip 文件路径（如果存在且有效），否则 None
    """
    zip_path = get_addon_zip_path()
    if zip_path.exists() and zipfile.is_zipfile(str(zip_path)):
        return zip_path
    return None


def download_cuda_addon(
    on_progress: Optional[Callable[[int, int], None]] = None,
    on_status: Optional[Callable[[str], None]] = None,
) -> Path:
    """从 GitHub Release 下载 CUDA addon zip

    Args:
        on_progress: 进度回调 (downloaded_bytes, total_bytes)
        on_status: 状态文本回调

    Returns:
        下载完成的 zip 文件路径

    Raises:
        RuntimeError: 下载失败
    """
    url = get_download_url()
    zip_path = get_addon_zip_path()
    temp_path = zip_path.with_suffix(".zip.downloading")

    if on_status:
        on_status("正在连接 GitHub...")

    try:
        req = Request(url, headers={"User-Agent": "VoiceCalendar-Updater"})
        response = urlopen(req, timeout=30)

        total_size = int(response.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 1024 * 1024  # 1MB chunks

        if on_status:
            size_str = f"{total_size / (1024**3):.1f} GB" if total_size > 0 else "未知大小"
            on_status(f"正在下载 CUDA 组件（{size_str}）...")

        with open(temp_path, "wb") as f:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if on_progress and total_size > 0:
                    on_progress(downloaded, total_size)

        # 验证 zip 文件完整性
        if not zipfile.is_zipfile(str(temp_path)):
            temp_path.unlink(missing_ok=True)
            raise RuntimeError("下载的文件不是有效的 zip 压缩包")

        # 重命名为最终文件
        if zip_path.exists():
            zip_path.unlink()
        temp_path.rename(zip_path)

        if on_status:
            on_status("下载完成")

        logger.info(f"CUDA addon 下载完成: {zip_path}")
        return zip_path

    except HTTPError as e:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"下载失败 (HTTP {e.code}): {e.reason}") from e
    except URLError as e:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"网络连接失败: {e.reason}") from e
    except OSError as e:
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"文件写入失败: {e}") from e


def install_cuda_addon(
    zip_path: Optional[Path] = None,
    on_status: Optional[Callable[[str], None]] = None,
) -> bool:
    """安装 CUDA addon（解压 DLL 到应用目录）

    Args:
        zip_path: addon zip 文件路径（None 则使用默认路径）
        on_status: 状态回调

    Returns:
        True 如果安装成功
    """
    if zip_path is None:
        zip_path = get_addon_zip_path()

    if not zip_path.exists():
        raise FileNotFoundError(f"CUDA addon 文件不存在: {zip_path}")

    app_dir = get_app_dir()

    if on_status:
        on_status("正在安装 CUDA 组件...")

    try:
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            # 解压所有文件到应用目录
            zf.extractall(str(app_dir))

        # 安装完成后删除 zip 文件
        zip_path.unlink(missing_ok=True)

        if on_status:
            on_status("CUDA 组件安装完成，重启应用后生效")

        logger.info("CUDA addon 安装完成")
        return True

    except (zipfile.BadZipFile, OSError) as e:
        if on_status:
            on_status(f"安装失败: {e}")
        logger.error(f"CUDA addon 安装失败: {e}")
        return False


def remove_cuda_addon(
    on_status: Optional[Callable[[str], None]] = None,
) -> bool:
    """卸载 CUDA addon（删除 CUDA DLL 文件）

    Args:
        on_status: 状态回调

    Returns:
        True 如果卸载成功
    """
    app_dir = get_app_dir()
    cuda_dlls = _find_cuda_dlls(app_dir)

    if not cuda_dlls:
        if on_status:
            on_status("未检测到 CUDA 组件")
        return True

    if on_status:
        on_status("正在移除 CUDA 组件...")

    removed_count = 0
    removed_size = 0

    for dll_path in cuda_dlls:
        try:
            size = dll_path.stat().st_size
            dll_path.unlink()
            removed_count += 1
            removed_size += size
        except OSError as e:
            logger.warning(f"无法删除 {dll_path}: {e}")

    size_mb = removed_size / (1024 * 1024)
    msg = f"已移除 {removed_count} 个 CUDA 文件，释放 {size_mb:.0f} MB 空间"

    if on_status:
        on_status(msg + "。重启应用后生效")

    logger.info(msg)
    return True


def get_cuda_addon_disk_usage() -> str:
    """获取已安装 CUDA addon 的磁盘占用"""
    app_dir = get_app_dir()
    cuda_dlls = _find_cuda_dlls(app_dir)
    total_size = sum(f.stat().st_size for f in cuda_dlls)

    if total_size == 0:
        return "未安装"
    elif total_size < 1024 * 1024 * 1024:
        return f"{total_size / (1024 * 1024):.0f} MB"
    else:
        return f"{total_size / (1024**3):.1f} GB"


def _find_cuda_dlls(app_dir: Path) -> list[Path]:
    """在应用目录中查找所有 CUDA DLL 文件"""
    cuda_dlls = []
    for pattern in CUDA_DLL_PATTERNS:
        cuda_dlls.extend(app_dir.rglob(pattern))
    return cuda_dlls
