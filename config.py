"""语音日历工具配置管理模块"""

import json
import os
from pathlib import Path
from typing import Any, Optional


class Config:
    """应用配置管理器，支持持久化存储"""

    DEFAULT_CONFIG = {
        # 快捷键设置
        "hotkey": "right alt",
        "hotkey_mode": "hold",  # hold: 按住录音, toggle: 切换录音
        # 语音识别设置
        "model_size": "small",
        "language": "zh",
        "beam_size": 5,
        "compute_type": "int8",  # int8, float16, float32
        # 音频设置
        "sample_rate": 16000,
        "audio_device": None,  # None 表示使用默认设备
        # 日历设置
        "default_reminder_minutes": 15,  # 默认提前提醒分钟数
        "week_start_day": 0,  # 0=周一, 6=周日
        "calendar_view": "month",  # month/week/day
        # 提醒设置
        "reminder_enabled": True,
        "reminder_sound": True,
        "reminder_notification": True,
        # LLM 设置（可选，用于语音指令兜底解析）
        "llm_enabled": False,
        "llm_provider": "ollama",  # ollama/openai
        "llm_model": "qwen2.5:7b",
        "llm_base_url": "http://localhost:11434",
        # UI 设置
        "theme": "system",  # system, light, dark
        "start_minimized": False,
        "show_notifications": True,
        # 热词设置
        "hotwords": [],
        "hotword_weight": 1.5,
        "hotword_max_count": 30,
        # 后处理设置
        "text_correction": True,  # 中文同音字纠错
        "punctuation_optimization": True,
        # 历史记录设置
        "history_enabled": True,
        "history_max_records": 500,
    }

    def __init__(self, config_dir: Optional[str] = None):
        if config_dir is None:
            config_dir = os.path.join(
                os.environ.get("APPDATA", os.path.expanduser("~")), "VoiceCalendar"
            )
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
    def calendar_db_path(self) -> str:
        """日历 SQLite 数据库路径"""
        return str(self.config_dir / "calendar.db")
