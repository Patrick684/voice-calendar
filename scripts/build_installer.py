"""一键构建 Windows 安装程序

用法:
    python scripts/build_installer.py          # 默认 CPU-only 构建（推荐，体积更小）
    python scripts/build_installer.py --gpu    # 包含 CUDA GPU 支持（体积更大）
    python scripts/build_installer.py --generate-addon  # GPU 构建后生成 CUDA addon zip
    python scripts/build_installer.py --skip-models  # 跳过模型下载（模型已存在时）

流程:
    1. 检查构建环境（PyInstaller、Inno Setup）
    2. 下载/验证模型文件
    3. 安装 CPU-only torch（如未指定 --gpu）
    4. 运行 PyInstaller 打包
    5. 运行 Inno Setup 生成安装程序
    6. 输出: dist/VoiceCalendar_Setup_1.0.0.exe

CUDA addon 构建:
    python scripts/build_installer.py --gpu --generate-addon
    生成: dist/cuda_addon_1.0.0.zip（上传到 GitHub Release 供用户下载）
"""

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"
SPEC_FILE = BUILD_DIR / "voice_calendar.spec"
ISS_FILE = BUILD_DIR / "installer.iss"

# 版本号（与 installer.iss 保持一致）
APP_VERSION = "1.0.0"

# Inno Setup 常见安装路径
INNO_SETUP_PATHS = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
    r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    r"C:\Program Files\Inno Setup 5\ISCC.exe",
]


class BuildError(Exception):
    """构建过程中的错误"""

    pass


def print_header(msg: str):
    """打印带分隔线的标题"""
    print(f"\n{'=' * 60}")
    print(f"  {msg}")
    print(f"{'=' * 60}\n")


def print_step(step: int, total: int, msg: str):
    """打印步骤信息"""
    print(f"  [{step}/{total}] {msg}")


def find_inno_setup() -> str | None:
    """查找 Inno Setup 编译器路径"""
    # 检查 PATH 中是否有 ISCC
    iscc = shutil.which("ISCC")
    if iscc:
        return iscc

    # 检查常见安装路径
    for path in INNO_SETUP_PATHS:
        if os.path.isfile(path):
            return path

    return None


def check_environment(gpu: bool = False) -> dict:
    """检查构建环境

    Returns:
        包含工具路径的字典
    """
    print_header("检查构建环境")
    env = {}

    # 1. Python
    print_step(1, 4, f"Python: {sys.version.split()[0]} ✓")

    # 2. PyInstaller
    try:
        result = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print_step(2, 4, f"PyInstaller: {version} ✓")
        else:
            raise FileNotFoundError
    except (FileNotFoundError, subprocess.CalledProcessError):
        print_step(2, 4, "PyInstaller: 未安装 ✗")
        print("    正在安装 PyInstaller...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            check=True,
        )
        print("    PyInstaller 安装完成 ✓")

    # 3. Inno Setup
    iscc_path = find_inno_setup()
    if iscc_path:
        print_step(3, 4, f"Inno Setup: {iscc_path} ✓")
        env["iscc"] = iscc_path
    else:
        print_step(3, 4, "Inno Setup: 未找到 ✗")
        print("    请从 https://jrsoftware.org/isinfo.php 下载安装 Inno Setup 6")
        print("    安装后重新运行此脚本")
        raise BuildError("Inno Setup 未安装")

    # 4. PyTorch
    try:
        import torch

        cuda_available = torch.cuda.is_available()
        torch_version = torch.__version__
        if gpu and cuda_available:
            print_step(4, 4, f"PyTorch: {torch_version} (CUDA ✓)")
        elif gpu and not cuda_available:
            print_step(4, 4, f"PyTorch: {torch_version} (CUDA 不可用，将使用 CPU)")
        else:
            print_step(4, 4, f"PyTorch: {torch_version} (CPU 模式)")
    except ImportError:
        print_step(4, 4, "PyTorch: 未安装")
        install_torch(gpu)

    return env


def install_torch(gpu: bool = False):
    """安装 PyTorch（CPU-only 或 GPU 版本）"""
    if gpu:
        print("    正在安装 PyTorch (GPU/CUDA)...")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "torch",
                "torchaudio",
                "--index-url",
                "https://download.pytorch.org/whl/cu121",
            ],
            check=True,
        )
    else:
        print("    正在安装 PyTorch (CPU-only, 体积更小)...")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "torch",
                "torchaudio",
                "--index-url",
                "https://download.pytorch.org/whl/cpu",
            ],
            check=True,
        )
    print("    PyTorch 安装完成 ✓")


def download_models(skip: bool = False):
    """下载并验证模型文件"""
    print_header("下载/验证模型文件")

    models_dir = PROJECT_ROOT / "models"

    # 检查 Paraformer 模型
    paraformer_dir = models_dir / "paraformer-zh"
    vad_dir = models_dir / "fsmn-vad"
    intent_dir = models_dir / "intent_classifier"

    if skip:
        # 仅验证是否存在
        missing = []
        if not paraformer_dir.exists():
            missing.append("paraformer-zh")
        if not vad_dir.exists():
            missing.append("fsmn-vad")
        if not intent_dir.exists():
            missing.append("intent_classifier")

        if missing:
            print(f"  警告: 以下模型缺失: {', '.join(missing)}")
            print("  请先运行: python scripts/download_models.py")
            raise BuildError(f"模型文件缺失: {', '.join(missing)}")
        else:
            print("  所有模型文件已就绪 ✓")
        return

    # 运行模型下载脚本
    download_script = PROJECT_ROOT / "scripts" / "download_models.py"
    if not download_script.exists():
        raise BuildError("模型下载脚本不存在: scripts/download_models.py")

    print("  运行模型下载脚本...")
    result = subprocess.run(
        [sys.executable, str(download_script)],
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        raise BuildError("模型下载失败")

    # 验证 intent_classifier
    if not intent_dir.exists():
        print("  警告: intent_classifier 模型需要单独训练")
        print("  如果尚未训练，请运行: python scripts/train_intent_classifier.py")

    print("  模型准备完成 ✓")


def run_pyinstaller(gpu: bool = False):
    """运行 PyInstaller 打包"""
    print_header("运行 PyInstaller 打包")

    if not SPEC_FILE.exists():
        raise BuildError(f"spec 文件不存在: {SPEC_FILE}")

    # 清理旧的打包输出
    output_dir = DIST_DIR / "VoiceCalendar"
    if output_dir.exists():
        print("  清理旧的打包输出...")
        shutil.rmtree(output_dir)

    # 设置环境变量控制 GPU/CPU 构建
    env = os.environ.copy()
    env["VOICE_CALENDAR_GPU_BUILD"] = "1" if gpu else "0"

    # 构建 PyInstaller 命令
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC_FILE),
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR / "pyinstaller_work"),
    ]

    print(f"  执行: {' '.join(cmd)}")
    print(f"  构建模式: {'GPU (CUDA)' if gpu else 'CPU-only'}")
    print("  （此步骤可能需要 5-10 分钟，请耐心等待...）\n")

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    if result.returncode != 0:
        raise BuildError("PyInstaller 打包失败")

    # 验证输出
    exe_path = output_dir / "VoiceCalendar.exe"
    if not exe_path.exists():
        raise BuildError(f"打包输出文件不存在: {exe_path}")

    # 如果是 CPU-only 构建，删除不必要的 CUDA DLL 以减小体积
    if not gpu:
        _cleanup_cuda_files(output_dir)

    # 计算目录大小
    total_size = sum(f.stat().st_size for f in output_dir.rglob("*") if f.is_file())
    size_mb = total_size / (1024 * 1024)
    print("\n  PyInstaller 打包完成 ✓")
    print(f"  输出目录: {output_dir}")
    print(f"  总大小: {size_mb:.0f} MB")


def _cleanup_cuda_files(output_dir: Path):
    """清理 CPU-only 构建中不需要的 CUDA 相关文件"""
    cuda_patterns = [
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

    removed_size = 0
    removed_count = 0

    for pattern in cuda_patterns:
        for f in output_dir.rglob(pattern):
            size = f.stat().st_size
            f.unlink()
            removed_size += size
            removed_count += 1

    if removed_count > 0:
        size_mb = removed_size / (1024 * 1024)
        print(f"  清理 CUDA 文件: 删除 {removed_count} 个文件, 节省 {size_mb:.0f} MB")


def generate_cuda_addon(output_dir: Path) -> Path:
    """从 GPU 构建输出中提取 CUDA 文件生成 addon zip

    Args:
        output_dir: PyInstaller 输出目录 (dist/VoiceCalendar)

    Returns:
        生成的 zip 文件路径
    """
    print_header("生成 CUDA Addon Zip")

    cuda_patterns = [
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

    # 收集所有 CUDA 相关文件
    cuda_files = []
    for pattern in cuda_patterns:
        cuda_files.extend(output_dir.rglob(pattern))

    if not cuda_files:
        raise BuildError("未找到 CUDA DLL 文件。确保使用 --gpu 模式构建。")

    # 创建 zip
    addon_zip = DIST_DIR / f"cuda_addon_{APP_VERSION}.zip"
    total_size = 0

    print(f"  找到 {len(cuda_files)} 个 CUDA 文件")
    print(f"  正在压缩到: {addon_zip}")

    with zipfile.ZipFile(str(addon_zip), "w", zipfile.ZIP_DEFLATED) as zf:
        for cuda_file in cuda_files:
            # 保持相对于 output_dir 的路径结构
            arcname = cuda_file.relative_to(output_dir)
            zf.write(str(cuda_file), str(arcname))
            total_size += cuda_file.stat().st_size

    zip_size = addon_zip.stat().st_size
    print(f"  原始大小: {total_size / (1024**3):.2f} GB")
    print(f"  压缩后: {zip_size / (1024**3):.2f} GB")
    print("\n  CUDA Addon 生成完成 ✓")
    print(f"  文件: {addon_zip}")
    print(f"  下一步: 上传到 GitHub Release v{APP_VERSION}")

    return addon_zip


def run_inno_setup(iscc_path: str):
    """运行 Inno Setup 生成安装程序"""
    print_header("生成安装程序")

    if not ISS_FILE.exists():
        raise BuildError(f"Inno Setup 脚本不存在: {ISS_FILE}")

    # 验证 PyInstaller 输出存在
    pyinstaller_output = DIST_DIR / "VoiceCalendar"
    if not pyinstaller_output.exists():
        raise BuildError(f"PyInstaller 输出不存在: {pyinstaller_output}")

    cmd = [iscc_path, str(ISS_FILE)]
    print(f"  执行: {' '.join(cmd)}")
    print("  （正在压缩和生成安装程序...）\n")

    result = subprocess.run(cmd, cwd=str(BUILD_DIR))
    if result.returncode != 0:
        raise BuildError("Inno Setup 编译失败")

    # 查找输出文件
    setup_files = list(DIST_DIR.glob("VoiceCalendar_Setup_*.exe"))
    if not setup_files:
        raise BuildError("未找到生成的安装程序")

    setup_file = setup_files[0]
    size_mb = setup_file.stat().st_size / (1024 * 1024)

    print("\n  安装程序生成完成 ✓")
    print(f"  文件: {setup_file}")
    print(f"  大小: {size_mb:.0f} MB")

    return setup_file


def main():
    parser = argparse.ArgumentParser(description="语音日历 Windows 安装程序构建工具")
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="包含 CUDA GPU 支持（默认仅 CPU，体积更小）",
    )
    parser.add_argument(
        "--skip-models",
        action="store_true",
        help="跳过模型下载（假设模型已存在）",
    )
    parser.add_argument(
        "--skip-pyinstaller",
        action="store_true",
        help="跳过 PyInstaller 步骤（仅运行 Inno Setup）",
    )
    parser.add_argument(
        "--generate-addon",
        action="store_true",
        help="GPU 构建后生成 CUDA addon zip（上传到 GitHub Release）",
    )
    args = parser.parse_args()

    print_header("语音日历 Windows 安装程序构建")
    print(f"  项目目录: {PROJECT_ROOT}")
    print(f"  构建模式: {'GPU (CUDA)' if args.gpu else 'CPU-only（推荐）'}")

    try:
        # Step 1: 检查环境
        env = check_environment(gpu=args.gpu)

        # Step 2: 下载/验证模型
        download_models(skip=args.skip_models)

        # Step 3: PyInstaller 打包
        if not args.skip_pyinstaller:
            run_pyinstaller(gpu=args.gpu)
        else:
            print_header("跳过 PyInstaller（使用现有输出）")

        # Step 4: Inno Setup 生成安装程序
        setup_file = run_inno_setup(env["iscc"])

        # Step 5: 生成 CUDA addon（仅 GPU 构建且指定 --generate-addon）
        addon_file = None
        if args.generate_addon:
            if not args.gpu:
                print("\n  警告: --generate-addon 需要搭配 --gpu 使用")
            else:
                output_dir = DIST_DIR / "VoiceCalendar"
                addon_file = generate_cuda_addon(output_dir)

        # 完成
        print_header("构建完成!")
        print(f"  安装程序: {setup_file}")
        if addon_file:
            print(f"  CUDA Addon: {addon_file}")
        print(f"  构建模式: {'GPU (CUDA)' if args.gpu else 'CPU-only'}")
        print()
        print("  下一步:")
        print("  1. 双击安装程序测试安装流程")
        print("  2. 验证安装后的应用能正常运行")
        print("  3. 发布安装程序给用户")

    except BuildError as e:
        print(f"\n  ✗ 构建失败: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n  构建已取消")
        sys.exit(1)


if __name__ == "__main__":
    main()
