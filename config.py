"""语音日历工具配置管理模块"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional


def get_app_dir() -> Path:
    """获取应用根目录（兼容开发模式和 PyInstaller 打包模式）"""
    if getattr(sys, "frozen", False):
        # PyInstaller --onedir 模式: exe 所在目录
        return Path(sys.executable).parent
    return Path(__file__).parent


class Config:
    """应用配置管理器，支持持久化存储"""

    DEFAULT_CONFIG = {
        # 快捷键设置
        "hotkey": "right alt",
        "hotkey_mode": "hold",  # hold: 按住录音, toggle: 切换录音
        # 语音识别设置
        "asr_engine": "paraformer",  # paraformer / whisper
        "asr_device": "cuda:0",  # cuda:0 / cpu
        "torch_mode": "auto",  # auto / cpu / cuda（auto=自动检测）
        "model_size": "small",
        "language": "zh",
        "beam_size": 5,
        "compute_type": "int8",  # int8, float16, float32
        # 音频设置
        "sample_rate": 16000,
        "audio_device": None,  # None 表示使用默认设备
        # 日历设置
        "default_reminder_minutes": 30,  # 默认提前提醒分钟数
        "week_start_day": 0,  # 0=周一, 6=周日
        "calendar_view": "month",  # month/week/day
        # 提醒设置
        "reminder_enabled": True,
        "reminder_sound": False,  # 提示音默认关闭
        "reminder_notification": True,
        # 个性化提醒音效（按事件分类）
        "reminder_sounds": {
            "工作": "bell.wav",
            "健康": "chime.wav",
            "学习": "soft.wav",
            "默认": "default.wav",
        },
        # 免打扰时段
        "dnd_enabled": False,
        "dnd_start": "22:00",  # 免打扰开始时间
        "dnd_end": "07:00",  # 免打扰结束时间
        # LLM 设置（可选，用于语音指令兜底解析）
        "llm_enabled": False,
        "llm_provider": "ollama",  # ollama/openai
        "llm_model": "qwen2.5:7b",
        "llm_base_url": "http://localhost:11434",
        # LLMParser 设置（新版智能路由核心）
        "llm_parser_model": "qwen2.5:3b",  # 本地 LLM 模型
        "llm_parser_timeout": 5.0,  # LLM 超时秒数（兆考首次加载延迟）
        # 意图分类模型设置（可选，替换关键词意图匹配）
        "intent_model_enabled": True,
        "intent_model_path": "models/intent_classifier",
        "intent_confidence_threshold": 0.8,
        # 系统托盘与后台设置
        "minimize_to_tray": True,  # 关闭窗口时最小化到托盘
        "autostart": True,  # 开机自动启动
        # UI 设置
        "theme": "system",  # system, light, dark
        "start_minimized": False,  # 启动时最小化到托盘
        "show_notifications": True,
        # 热词设置
        "hotwords": [],
        "hotword_weight": 1.5,
        "hotword_max_count": 30,
        # 后处理设置
        "text_correction": True,  # 中文同音字纠错
        "punctuation_optimization": True,
        # 事件分类颜色映射
        "category_colors": {
            "工作": "#2196F3",
            "健康": "#4CAF50",
            "学习": "#FF9800",
            "生活": "#9C27B0",
            "娱乐": "#E91E63",
            "社交": "#00BCD4",
            "其他": "#757575",
        },
        # 历史记录设置
        "history_enabled": True,
        "history_max_records": 500,
    }

    def __init__(self, config_dir: Optional[str] = None):
        if config_dir is None:
            config_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "VoiceCalendar")
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.config_dir / "config.json"
        self._config = dict(self.DEFAULT_CONFIG)
        self._load()

    def _load(self):
        """从文件加载配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._config.update(saved)
            except (json.JSONDecodeError, IOError):
                pass

    def save(self):
        """保存配置到文件"""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"保存配置失败: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        """设置配置项并自动保存"""
        self._config[key] = value
        self.save()

    def reset(self, key: Optional[str] = None):
        """重置配置项为默认值"""
        if key:
            if key in self.DEFAULT_CONFIG:
                self._config[key] = self.DEFAULT_CONFIG[key]
        else:
            self._config = dict(self.DEFAULT_CONFIG)
        self.save()

    @property
    def model_cache_dir(self) -> Path:
        """模型缓存目录"""
        cache_dir = self.config_dir / "models"
        cache_dir.mkdir(exist_ok=True)
        return cache_dir

    @property
    def hotword_file(self) -> Path:
        """热词文件路径"""
        return self.config_dir / "hotwords.json"

    @property
    def rules_file(self) -> Path:
        """后处理规则文件路径"""
        return self.config_dir / "post_rules.json"

    @property
    def history_file(self) -> Path:
        """识别历史文件路径"""
        return self.config_dir / "history.json"

    @property
    def sounds_dir(self) -> Path:
        """音效文件目录"""
        sounds = self.config_dir / "sounds"
        sounds.mkdir(exist_ok=True)
        return sounds

    @property
    def calendar_db_path(self) -> str:
        """日历 SQLite 数据库路径"""
        return str(self.config_dir / "calendar.db")
