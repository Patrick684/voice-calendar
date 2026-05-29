"""设置窗口 - 语音日历工具的配置界面"""

import logging
import customtkinter as ctk

from config import Config

logger = logging.getLogger(__name__)


class SettingsWindow(ctk.CTkToplevel):
    """设置窗口

    提供语音日历工具的所有配置选项，包括：
    - 基本设置（快捷键、主题）
    - 语音识别（模型、语言）
    - 日历设置（提醒、默认视图）
    - LLM 设置（可选的兜底解析）
    """

    def __init__(
        self,
        master,
        config: Config,
        on_settings_changed=None,
    ):
        """
        初始化设置窗口

        Args:
            master: 父窗口
            config: 配置管理器
            on_settings_changed: 配置变更回调
        """
        super().__init__(master)
        self._config = config
        self._on_changed = on_settings_changed

        self.title("设置")
        self.geometry("520x520")
        self.resizable(False, False)
        self.transient(master)

        self._setup_ui()
        self._load_settings()

        # 居中显示
        self.update_idletasks()
        x = master.winfo_x() + (master.winfo_width() - 520) // 2
        y = master.winfo_y() + (master.winfo_height() - 520) // 2
        self.geometry(f"+{x}+{y}")

    def _setup_ui(self):
        """构建选项卡 UI"""
        self._tabview = ctk.CTkTabview(self)
        self._tabview.pack(fill="both", expand=True, padx=10, pady=10)

        self._create_basic_tab()
        self._create_engine_tab()
        self._create_calendar_tab()
        self._create_llm_tab()

        # 底部按钮
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text="保存",
            width=100,
            command=self._save_and_close,
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            btn_frame,
            text="取消",
            width=100,
            fg_color="gray",
            command=self.destroy,
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            btn_frame,
            text="恢复默认",
            width=100,
            fg_color="#e67e22",
            command=self._reset_settings,
        ).pack(side="left", padx=5)

    def _create_basic_tab(self):
        """基本设置选项卡"""
        tab = self._tabview.add("基本设置")
        pad = {"padx": 15, "pady": 8}

        # 快捷键
        ctk.CTkLabel(tab, text="录音快捷键:").grid(row=0, column=0, sticky="w", **pad)
        self._hotkey_var = ctk.StringVar()
        ctk.CTkComboBox(
            tab,
            variable=self._hotkey_var,
            width=200,
            values=["right alt", "right ctrl", "right shift", "f4", "f8", "f9"],
        ).grid(row=0, column=1, sticky="w", **pad)

        # 触发模式
        ctk.CTkLabel(tab, text="触发方式:").grid(row=1, column=0, sticky="w", **pad)
        self._mode_var = ctk.StringVar()
        ctk.CTkComboBox(
            tab,
            variable=self._mode_var,
            width=200,
            values=["hold", "toggle"],
        ).grid(row=1, column=1, sticky="w", **pad)

        # 主题
        ctk.CTkLabel(tab, text="主题:").grid(row=2, column=0, sticky="w", **pad)
        self._theme_var = ctk.StringVar()
        ctk.CTkComboBox(
            tab,
            variable=self._theme_var,
            width=200,
            values=["system", "light", "dark"],
            command=self._on_theme_changed,
        ).grid(row=2, column=1, sticky="w", **pad)

        # 通知
        self._notify_var = ctk.BooleanVar()
        ctk.CTkCheckBox(
            tab,
            text="显示系统通知",
            variable=self._notify_var,
        ).grid(row=3, column=1, sticky="w", **pad)

    def _create_engine_tab(self):
        """语音识别选项卡"""
        tab = self._tabview.add("语音识别")
        pad = {"padx": 15, "pady": 8}

        # 模型大小
        ctk.CTkLabel(tab, text="识别模型:").grid(row=0, column=0, sticky="w", **pad)
        self._model_var = ctk.StringVar()
        ctk.CTkComboBox(
            tab,
            variable=self._model_var,
            width=200,
            values=["tiny", "base", "small", "medium"],
        ).grid(row=0, column=1, sticky="w", **pad)

        # 计算精度
        ctk.CTkLabel(tab, text="计算精度:").grid(row=1, column=0, sticky="w", **pad)
        self._compute_var = ctk.StringVar()
        ctk.CTkComboBox(
            tab,
            variable=self._compute_var,
            width=200,
            values=["int8", "float16", "float32"],
        ).grid(row=1, column=1, sticky="w", **pad)

        # 语言
        ctk.CTkLabel(tab, text="识别语言:").grid(row=2, column=0, sticky="w", **pad)
        self._lang_var = ctk.StringVar()
        ctk.CTkComboBox(
            tab,
            variable=self._lang_var,
            width=200,
            values=["zh", "en", "ja"],
        ).grid(row=2, column=1, sticky="w", **pad)

        # 同音纠错
        self._correction_var = ctk.BooleanVar()
        ctk.CTkCheckBox(
            tab,
            text="启用同音纠错",
            variable=self._correction_var,
        ).grid(row=3, column=1, sticky="w", **pad)

    def _create_calendar_tab(self):
        """日历设置选项卡"""
        tab = self._tabview.add("日历")
        pad = {"padx": 15, "pady": 8}

        # 默认提醒
        ctk.CTkLabel(tab, text="默认提醒:").grid(row=0, column=0, sticky="w", **pad)
        self._reminder_var = ctk.StringVar()
        ctk.CTkComboBox(
            tab,
            variable=self._reminder_var,
            width=200,
            values=["5", "10", "15", "30", "60"],
        ).grid(row=0, column=1, sticky="w", **pad)

        # 提醒开关
        self._reminder_enabled_var = ctk.BooleanVar()
        ctk.CTkCheckBox(
            tab,
            text="启用事件提醒",
            variable=self._reminder_enabled_var,
        ).grid(row=1, column=1, sticky="w", **pad)

        # 提醒声音
        self._reminder_sound_var = ctk.BooleanVar()
        ctk.CTkCheckBox(
            tab,
            text="提醒时播放声音",
            variable=self._reminder_sound_var,
        ).grid(row=2, column=1, sticky="w", **pad)

        # 周起始日
        ctk.CTkLabel(tab, text="周起始日:").grid(row=3, column=0, sticky="w", **pad)
        self._week_start_var = ctk.StringVar()
        ctk.CTkComboBox(
            tab,
            variable=self._week_start_var,
            width=200,
            values=["周一", "周日"],
        ).grid(row=3, column=1, sticky="w", **pad)

    def _create_llm_tab(self):
        """LLM 设置选项卡"""
        tab = self._tabview.add("LLM (可选)")
        pad = {"padx": 15, "pady": 8}

        # LLM 开关
        self._llm_enabled_var = ctk.BooleanVar()
        ctk.CTkCheckBox(
            tab,
            text="启用 LLM 兜底解析",
            variable=self._llm_enabled_var,
        ).grid(row=0, column=1, sticky="w", **pad)

        # 提供商
        ctk.CTkLabel(tab, text="LLM 提供商:").grid(row=1, column=0, sticky="w", **pad)
        self._llm_provider_var = ctk.StringVar()
        ctk.CTkComboBox(
            tab,
            variable=self._llm_provider_var,
            width=200,
            values=["ollama", "openai"],
        ).grid(row=1, column=1, sticky="w", **pad)

        # 模型
        ctk.CTkLabel(tab, text="模型名称:").grid(row=2, column=0, sticky="w", **pad)
        self._llm_model_var = ctk.StringVar()
        ctk.CTkEntry(
            tab,
            variable=self._llm_model_var,
            width=200,
        ).grid(row=2, column=1, sticky="w", **pad)

        # API 地址
        ctk.CTkLabel(tab, text="API 地址:").grid(row=3, column=0, sticky="w", **pad)
        self._llm_url_var = ctk.StringVar()
        ctk.CTkEntry(
            tab,
            variable=self._llm_url_var,
            width=200,
        ).grid(row=3, column=1, sticky="w", **pad)

    def _load_settings(self):
        """从 Config 加载设置到 UI"""
        c = self._config
        self._hotkey_var.set(c.get("hotkey", "right alt"))
        self._mode_var.set(c.get("hotkey_mode", "hold"))
        self._theme_var.set(c.get("theme", "system"))
        self._notify_var.set(c.get("show_notifications", True))
        self._model_var.set(c.get("model_size", "small"))
        self._compute_var.set(c.get("compute_type", "int8"))
        self._lang_var.set(c.get("language", "zh"))
        self._correction_var.set(c.get("text_correction", True))
        self._reminder_var.set(str(c.get("default_reminder_minutes", 15)))
        self._reminder_enabled_var.set(c.get("reminder_enabled", True))
        self._reminder_sound_var.set(c.get("reminder_sound", True))
        week_start = c.get("week_start_day", 0)
        self._week_start_var.set("周一" if week_start == 0 else "周日")
        self._llm_enabled_var.set(c.get("llm_enabled", False))
        self._llm_provider_var.set(c.get("llm_provider", "ollama"))
        self._llm_model_var.set(c.get("llm_model", "qwen2.5:7b"))
        self._llm_url_var.set(c.get("llm_base_url", "http://localhost:11434"))

    def _save_and_close(self):
        """保存设置并关闭窗口"""
        c = self._config
        changes = {}

        changes["hotkey"] = self._hotkey_var.get()
        changes["hotkey_mode"] = self._mode_var.get()
        changes["theme"] = self._theme_var.get()
        changes["show_notifications"] = self._notify_var.get()
        changes["model_size"] = self._model_var.get()
        changes["compute_type"] = self._compute_var.get()
        changes["language"] = self._lang_var.get()
        changes["text_correction"] = self._correction_var.get()

        try:
            changes["default_reminder_minutes"] = int(self._reminder_var.get())
        except ValueError:
            changes["default_reminder_minutes"] = 15

        changes["reminder_enabled"] = self._reminder_enabled_var.get()
        changes["reminder_sound"] = self._reminder_sound_var.get()
        changes["week_start_day"] = 0 if self._week_start_var.get() == "周一" else 6
        changes["llm_enabled"] = self._llm_enabled_var.get()
        changes["llm_provider"] = self._llm_provider_var.get()
        changes["llm_model"] = self._llm_model_var.get()
        changes["llm_base_url"] = self._llm_url_var.get()

        # 批量写入
        for key, value in changes.items():
            c.set(key, value)

        logger.info("设置已保存")

        if self._on_changed:
            self._on_changed(changes)

        self.destroy()

    def _reset_settings(self):
        """恢复默认设置"""
        self._config.reset()
        self._load_settings()
        logger.info("设置已恢复默认值")

    def _on_theme_changed(self, value):
        """主题实时切换"""
        ctk.set_appearance_mode(value)
