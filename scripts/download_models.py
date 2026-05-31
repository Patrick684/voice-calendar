"""预下载 Paraformer 模型文件到本地目录，供 PyInstaller 打包使用

用法:
    python scripts/download_models.py

此脚本会将 paraformer-zh 和 fsmn-vad 模型下载到 models/ 目录，
之后 PyInstaller 可以将其打包进安装程序。
"""

import sys
import shutil
from pathlib import Path

# 确保项目根在 sys.path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

MODELS_DIR = PROJECT_ROOT / "models"


def download_paraformer():
    """下载 Paraformer ASR 模型和 FSMN-VAD 模型"""
    try:
        from funasr import AutoModel
    except ImportError:
        print("错误: funasr 未安装。请运行: pip install funasr")
        sys.exit(1)

    paraformer_dir = MODELS_DIR / "paraformer-zh"
    vad_dir = MODELS_DIR / "fsmn-vad"

    if paraformer_dir.exists() and any(paraformer_dir.iterdir()):
        print(f"[跳过] Paraformer 模型已存在: {paraformer_dir}")
    else:
        print("[下载] 正在下载 Paraformer-zh 模型（约 350MB）...")
        paraformer_dir.mkdir(parents=True, exist_ok=True)
        # 使用 modelscope 直接下载到指定目录
        try:
            from modelscope.hub.snapshot_download import snapshot_download

            snapshot_download(
                "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
                local_dir=str(paraformer_dir),
            )
            print(f"[完成] Paraformer 模型已下载到: {paraformer_dir}")
        except ImportError:
            # 如果 modelscope 不可用，通过 funasr 触发下载后复制缓存
            print("[备选] 使用 funasr 触发模型下载...")
            model = AutoModel(model="paraformer-zh", device="cpu", disable_update=True)
            # funasr 缓存位置
            _copy_funasr_cache("paraformer-zh", paraformer_dir)
            del model
            print(f"[完成] Paraformer 模型已缓存到: {paraformer_dir}")

    if vad_dir.exists() and any(vad_dir.iterdir()):
        print(f"[跳过] FSMN-VAD 模型已存在: {vad_dir}")
    else:
        print("[下载] 正在下载 FSMN-VAD 模型（约 40MB）...")
        vad_dir.mkdir(parents=True, exist_ok=True)
        try:
            from modelscope.hub.snapshot_download import snapshot_download

            snapshot_download(
                "iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
                local_dir=str(vad_dir),
            )
            print(f"[完成] FSMN-VAD 模型已下载到: {vad_dir}")
        except ImportError:
            print("[备选] 使用 funasr 触发 VAD 模型下载...")
            model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad", device="cpu", disable_update=True)
            _copy_funasr_cache("fsmn-vad", vad_dir)
            del model
            print(f"[完成] FSMN-VAD 模型已缓存到: {vad_dir}")


def _copy_funasr_cache(model_name: str, target_dir: Path):
    """从 funasr/modelscope 缓存中复制模型文件到目标目录"""
    import os

    # ModelScope 默认缓存路径
    cache_base = Path(os.environ.get("MODELSCOPE_CACHE", Path.home() / ".cache" / "modelscope"))
    hub_dir = cache_base / "hub"

    # 搜索匹配的模型目录
    found = None
    if hub_dir.exists():
        for d in hub_dir.iterdir():
            if model_name.replace("-", "") in d.name.replace("-", "").replace("_", ""):
                found = d
                break

    if found and found.exists():
        print(f"  从缓存复制: {found} -> {target_dir}")
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(found, target_dir)
    else:
        print(f"  警告: 未在缓存中找到 {model_name} 模型，请手动下载")


def verify_models():
    """验证所有必需模型文件是否存在"""
    print("\n--- 模型验证 ---")
    all_ok = True

    # 检查 intent_classifier
    intent_dir = MODELS_DIR / "intent_classifier"
    if intent_dir.exists() and (intent_dir / "model.safetensors").exists():
        size_mb = (intent_dir / "model.safetensors").stat().st_size / 1024 / 1024
        print(f"  [OK] intent_classifier ({size_mb:.1f} MB)")
    else:
        print("  [缺失] intent_classifier - 请先训练模型")
        all_ok = False

    # 检查 paraformer-zh
    para_dir = MODELS_DIR / "paraformer-zh"
    if para_dir.exists() and any(para_dir.glob("*.bin")) or any(para_dir.glob("*.pt")):
        total = sum(f.stat().st_size for f in para_dir.rglob("*") if f.is_file())
        print(f"  [OK] paraformer-zh ({total / 1024 / 1024:.1f} MB)")
    elif para_dir.exists() and any(para_dir.iterdir()):
        total = sum(f.stat().st_size for f in para_dir.rglob("*") if f.is_file())
        print(f"  [OK] paraformer-zh ({total / 1024 / 1024:.1f} MB)")
    else:
        print("  [缺失] paraformer-zh")
        all_ok = False

    # 检查 fsmn-vad
    vad_dir = MODELS_DIR / "fsmn-vad"
    if vad_dir.exists() and any(vad_dir.iterdir()):
        total = sum(f.stat().st_size for f in vad_dir.rglob("*") if f.is_file())
        print(f"  [OK] fsmn-vad ({total / 1024 / 1024:.1f} MB)")
    else:
        print("  [缺失] fsmn-vad")
        all_ok = False

    if all_ok:
        print("\n所有模型就绪，可以进行打包！")
    else:
        print("\n部分模型缺失，打包前请确保所有模型已下载。")

    return all_ok


if __name__ == "__main__":
    print("=" * 50)
    print("  语音日历工具 - 模型下载工具")
    print("=" * 50)
    print()

    download_paraformer()
    verify_models()
