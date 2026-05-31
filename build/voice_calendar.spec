# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec 文件 - 语音日历工具打包配置

用法:
    pyinstaller build/voice_calendar.spec

前置条件:
    1. 已运行 scripts/download_models.py 下载模型
    2. 已运行 scripts/generate_icon.py 生成图标
"""

import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(PROJECT_ROOT))

# 收集数据文件
datas = []

# 模型文件
models_dir = PROJECT_ROOT / "models"
if (models_dir / "intent_classifier").exists():
    datas.append((str(models_dir / "intent_classifier"), "models/intent_classifier"))
if (models_dir / "paraformer-zh").exists():
    datas.append((str(models_dir / "paraformer-zh"), "models/paraformer-zh"))
if (models_dir / "fsmn-vad").exists():
    datas.append((str(models_dir / "fsmn-vad"), "models/fsmn-vad"))

# 音效文件
sounds_dir = PROJECT_ROOT / "sounds"
if sounds_dir.exists():
    for wav in sounds_dir.glob("*.wav"):
        datas.append((str(wav), "sounds"))

# 图标
icon_path = PROJECT_ROOT / "assets" / "icon.ico"
if icon_path.exists():
    datas.append((str(icon_path), "assets"))

# CustomTkinter 主题文件（必须包含）
import customtkinter

ctk_path = Path(customtkinter.__file__).parent
datas.append((str(ctk_path), "customtkinter"))

block_cipher = None

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # FunASR 及其依赖
        "funasr",
        "funasr.auto",
        "funasr.models",
        "funasr.utils",
        "funasr.register",
        # PyTorch
        "torch",
        "torch.nn",
        "torch.cuda",
        "torch.backends",
        "torch.backends.cudnn",
        # Transformers (意图分类)
        "transformers",
        "transformers.models",
        "transformers.models.bert",
        "transformers.models.bert.modeling_bert",
        "transformers.models.bert.tokenization_bert",
        "transformers.models.bert.tokenization_bert_fast",
        # GUI
        "customtkinter",
        "PIL",
        "PIL._tkinter_finder",
        "pystray",
        "pystray._win32",
        # 系统集成
        "sounddevice",
        "keyboard",
        "keyboard._winkeyboard",
        "winotify",
        "plyer",
        "plyer.platforms.win",
        "plyer.platforms.win.notification",
        # 科学计算
        "numpy",
        "sklearn",
        "sklearn.utils",
        "sklearn.utils._cython_blas",
        # 其他
        "zhconv",
        "pypinyin",
        "dateutil",
        "dateutil.parser",
        "json",
        "sqlite3",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大型包
        "matplotlib",
        "scipy",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
        "setuptools",
        "pip",
        # 排除训练相关
        "tensorboard",
        "torch.utils.tensorboard",
        "torch.distributed",
        "torch.testing",
        "torch.utils.bottleneck",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VoiceCalendar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
    # UAC 管理员权限（全局热键需要）
    uac_admin=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VoiceCalendar",
)
