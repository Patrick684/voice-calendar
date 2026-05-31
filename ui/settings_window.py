"""设置窗口 - 语音日历工具的配置界面"""

import logging
import threading
import customtkinter as ctk

from config import Config
from utils.autostart import is_autostart_enabled, set_autostart
from utils.torch_manager import (
    detect_torch_mode,
    download_cuda_addon,
    get_cuda_addon_size,
    get_manual_download_url,
    install_cuda_addon,
    remove_cuda_addon,
    check_manual_addon,
)

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
        self.geometry("520x580")
        self.resizable(False, False)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._setup_ui()

        # 延迟加载设置，确保 CTkToplevel 窗口和组件完全渲染后再填充值
        self.after(150, self._load_settings)

        # 居中显示
        self.update_idletasks()
        x = master.winfo_x() + (master.winfo_width() - 520) // 2
        y = master.winfo_y() + (master.winfo_height() - 580) // 2
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
        self._hotkey_combo = ctk.CTkComboBox(
            tab,
            variable=self._hotkey_var,
            width=200,
            values=["right alt", "right ctrl", "right shift", "f4", "f8", "f9"],
        )
        self._hotkey_combo.grid(row=0, column=1, sticky="w", **pad)

        # 触发模式
        ctk.CTkLabel(tab, text="触发方式:").grid(row=1, column=0, sticky="w", **pad)
        self._mode_var = ctk.StringVar()
        self._mode_combo = ctk.CTkComboBox(
            tab,
            variable=self._mode_var,
            width=200,
            values=["hold", "toggle"],
        )
        self._mode_combo.grid(row=1, column=1, sticky="w", **pad)

        # 主题
        ctk.CTkLabel(tab, text="主题:").grid(row=2, column=0, sticky="w", **pad)
        self._theme_var = ctk.StringVar()
        self._theme_combo = ctk.CTkComboBox(
            tab,
            variable=self._theme_var,
            width=200,
            values=["system", "light", "dark"],
            command=self._on_theme_changed,
        )
        self._theme_combo.grid(row=2, column=1, sticky="w", **pad)

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

        # ASR 引擎
        ctk.CTkLabel(tab, text="识别引擎:").grid(row=0, column=0, sticky="w", **pad)
        self._engine_var = ctk.StringVar()
        self._engine_combo = ctk.CTkComboBox(
            tab,
            variable=self._engine_var,
            width=200,
            values=["Paraformer (推荐)", "Whisper"],
            command=self._on_engine_changed,
        )
        self._engine_combo.grid(row=0, column=1, sticky="w", **pad)

        # 计算设备 - 状态显示 + 切换按钮
        ctk.CTkLabel(tab, text="计算设备:").grid(row=1, column=0, sticky="w", **pad)
        self._device_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self._device_frame.grid(row=1, column=1, sticky="w", **pad)

        self._device_status_label = ctk.CTkLabel(
            self._device_frame,
            text="检测中...",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._device_status_label.pack(side="left", padx=(0, 10))

        self._device_switch_btn = ctk.CTkButton(
            self._device_frame,
            text="切换",
            width=180,
            height=28,
            font=ctk.CTkFont(size=12),
            command=self._on_device_switch,
        )
        self._device_switch_btn.pack(side="left")

        # 保留隐藏的 device_var 用于保存配置
        self._device_var = ctk.StringVar()

        # Whisper 模型大小（仅 Whisper 引擎显示）
        self._model_size_label = ctk.CTkLabel(tab, text="Whisper 模型:")
        self._model_size_label.grid(row=2, column=0, sticky="w", **pad)
        self._model_var = ctk.StringVar()
        self._model_size_combo = ctk.CTkComboBox(
            tab,
            variable=self._model_var,
            width=200,
            values=["tiny", "base", "small", "medium"],
        )
        self._model_size_combo.grid(row=2, column=1, sticky="w", **pad)

        # 计算精度（仅 Whisper）
        self._compute_label = ctk.CTkLabel(tab, text="计算精度:")
        self._compute_label.grid(row=3, column=0, sticky="w", **pad)
        self._compute_var = ctk.StringVar()
        self._compute_combo = ctk.CTkComboBox(
            tab,
            variable=self._compute_var,
            width=200,
            values=["int8", "float16", "float32"],
        )
        self._compute_combo.grid(row=3, column=1, sticky="w", **pad)

        # 识别语言
        ctk.CTkLabel(tab, text="识别语言:").grid(row=4, column=0, sticky="w", **pad)
        self._lang_var = ctk.StringVar()
        self._lang_combo = ctk.CTkComboBox(
            tab,
            variable=self._lang_var,
            width=200,
            values=["zh", "en", "ja"],
        )
        self._lang_combo.grid(row=4, column=1, sticky="w", **pad)

        # 同音纠错
        self._correction_var = ctk.BooleanVar()
        ctk.CTkCheckBox(
            tab,
            text="启用同音纠错",
            variable=self._correction_var,
        ).grid(row=5, column=1, sticky="w", **pad)

    def _create_calendar_tab(self):
        """日历设置选项卡"""
        tab = self._tabview.add("日历")
        pad = {"padx": 15, "pady": 8}

        # 默认提醒
        ctk.CTkLabel(tab, text="默认提醒:").grid(row=0, column=0, sticky="w", **pad)
        self._reminder_var = ctk.StringVar()
        self._reminder_combo = ctk.CTkComboBox(
            tab,
            variable=self._reminder_var,
            width=200,
            values=["5", "10", "15", "30", "60"],
        )
        self._reminder_combo.grid(row=0, column=1, sticky="w", **pad)

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
        self._week_start_combo = ctk.CTkComboBox(
            tab,
            variable=self._week_start_var,
            width=200,
            values=["周一", "周日"],
        )
        self._week_start_combo.grid(row=3, column=1, sticky="w", **pad)

        # 分隔线
        ctk.CTkLabel(tab, text="─" * 40, text_color="gray60").grid(
            row=4, column=0, columnspan=2, sticky="we", padx=15, pady=(12, 4)
        )

        # 最小化到托盘
        self._minimize_tray_var = ctk.BooleanVar()
        ctk.CTkCheckBox(
            tab,
            text="关闭窗口时最小化到系统托盘",
            variable=self._minimize_tray_var,
        ).grid(row=5, column=1, sticky="w", **pad)

        # 开机自启
        self._autostart_var = ctk.BooleanVar()
        ctk.CTkCheckBox(
            tab,
            text="开机自动启动",
            variable=self._autostart_var,
        ).grid(row=6, column=1, sticky="w", **pad)

        # 启动时最小化
        self._start_minimized_var = ctk.BooleanVar()
        ctk.CTkCheckBox(
            tab,
            text="启动时最小化到托盘",
            variable=self._start_minimized_var,
        ).grid(row=7, column=1, sticky="w", **pad)

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
        self._llm_provider_combo = ctk.CTkComboBox(
            tab,
            variable=self._llm_provider_var,
            width=200,
            values=["ollama", "openai"],
        )
        self._llm_provider_combo.grid(row=1, column=1, sticky="w", **pad)

        # 模型
        ctk.CTkLabel(tab, text="模型名称:").grid(row=2, column=0, sticky="w", **pad)
        self._llm_model_var = ctk.StringVar()
        self._llm_model_entry = ctk.CTkEntry(
            tab,
            textvariable=self._llm_model_var,
            width=200,
        )
        self._llm_model_entry.grid(row=2, column=1, sticky="w", **pad)

        # API 地址
        ctk.CTkLabel(tab, text="API 地址:").grid(row=3, column=0, sticky="w", **pad)
        self._llm_url_var = ctk.StringVar()
        self._llm_url_entry = ctk.CTkEntry(
            tab,
            textvariable=self._llm_url_var,
            width=200,
        )
        self._llm_url_entry.grid(row=3, column=1, sticky="w", **pad)

    def _load_settings(self):
        """从 Config 加载设置到 UI"""
        c = self._config
        # 基本设置 - 直接调用组件 .set() 确保显示正确
        hotkey = c.get("hotkey", "right alt")
        self._hotkey_combo.set(hotkey)
        mode = c.get("hotkey_mode", "hold")
        self._mode_combo.set(mode)
        theme = c.get("theme", "system")
        self._theme_combo.set(theme)
        self._notify_var.set(c.get("show_notifications", True))
        # 语音识别
        engine = c.get("asr_engine", "paraformer")
        engine_display = "Paraformer (推荐)" if engine == "paraformer" else "Whisper"
        self._engine_combo.set(engine_display)
        # 计算设备状态
        self._update_device_status()
        self._model_size_combo.set(c.get("model_size", "small"))
        self._compute_combo.set(c.get("compute_type", "int8"))
        self._lang_combo.set(c.get("language", "zh"))
        self._correction_var.set(c.get("text_correction", True))
        self._on_engine_changed(engine_display)
        # 日历
        self._reminder_combo.set(str(c.get("default_reminder_minutes", 30)))
        self._reminder_enabled_var.set(c.get("reminder_enabled", True))
        self._reminder_sound_var.set(c.get("reminder_sound", False))
        week_start = c.get("week_start_day", 0)
        self._week_start_combo.set("周一" if week_start == 0 else "周日")
        self._minimize_tray_var.set(c.get("minimize_to_tray", True))
        self._autostart_var.set(is_autostart_enabled())
        self._start_minimized_var.set(c.get("start_minimized", False))
        # LLM
        self._llm_enabled_var.set(c.get("llm_enabled", False))
        self._llm_provider_combo.set(c.get("llm_provider", "ollama"))
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
        # 语音识别
        engine_display = self._engine_var.get()
        changes["asr_engine"] = (
            "paraformer" if "推荐" in engine_display or "Paraformer" in engine_display else "whisper"
        )
        # 设备配置根据当前实际模式设置
        current_mode = detect_torch_mode()
        changes["asr_device"] = "cuda:0" if current_mode == "cuda" else "cpu"
        changes["model_size"] = self._model_var.get()
        changes["compute_type"] = self._compute_var.get()
        changes["language"] = self._lang_var.get()
        changes["text_correction"] = self._correction_var.get()

        try:
            changes["default_reminder_minutes"] = int(self._reminder_var.get())
        except ValueError:
            changes["default_reminder_minutes"] = 30

        changes["reminder_enabled"] = self._reminder_enabled_var.get()
        changes["reminder_sound"] = self._reminder_sound_var.get()
        changes["week_start_day"] = 0 if self._week_start_var.get() == "周一" else 6
        changes["minimize_to_tray"] = self._minimize_tray_var.get()
        changes["start_minimized"] = self._start_minimized_var.get()
        changes["llm_enabled"] = self._llm_enabled_var.get()
        changes["llm_provider"] = self._llm_provider_var.get()
        changes["llm_model"] = self._llm_model_var.get()
        changes["llm_base_url"] = self._llm_url_var.get()

        # 批量写入
        for key, value in changes.items():
            c.set(key, value)

        # 处理开机自启（通过注册表，不存在 config 中）
        autostart_enabled = self._autostart_var.get()
        set_autostart(autostart_enabled)
        c.set("autostart", autostart_enabled)

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

    def _on_engine_changed(self, value):
        """切换 ASR 引擎时显示/隐藏 Whisper 专属选项"""
        is_whisper = "Whisper" in value and "推荐" not in value
        if is_whisper:
            self._model_size_label.grid()
            self._model_size_combo.grid()
            self._compute_label.grid()
            self._compute_combo.grid()
        else:
            self._model_size_label.grid_remove()
            self._model_size_combo.grid_remove()
            self._compute_label.grid_remove()
            self._compute_combo.grid_remove()

    # ─── 设备切换相关方法 ───────────────────────────────────────────

    def _update_device_status(self):
        """更新计算设备状态显示"""
        mode = detect_torch_mode()
        if mode == "cuda":
            self._device_status_label.configure(
                text="GPU 模式 (CUDA)",
                text_color="#4CAF50",
            )
            self._device_switch_btn.configure(
                text="切换到 CPU 模式",
                fg_color="#757575",
            )
            self._device_var.set("GPU (cuda)")
        else:
            self._device_status_label.configure(
                text="CPU 模式",
                text_color="#2196F3",
            )
            addon_size = get_cuda_addon_size()
            self._device_switch_btn.configure(
                text=f"升级到 GPU 模式（需下载{addon_size}）",
                fg_color="#2196F3",
            )
            self._device_var.set("CPU")

    def _on_device_switch(self):
        """处理设备切换按钮点击"""
        mode = detect_torch_mode()
        if mode == "cuda":
            self._confirm_switch_to_cpu()
        else:
            self._confirm_switch_to_gpu()

    def _confirm_switch_to_cpu(self):
        """确认切换到 CPU 模式"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("切换到 CPU 模式")
        dialog.geometry("400x180")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        # 居中
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 400) // 2
        y = self.winfo_y() + (self.winfo_height() - 180) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            dialog,
            text="确认切换到 CPU 模式？\n\n将移除 CUDA 组件并释放约 2GB 磁盘空间。\n切换后需要重启应用生效。",
            font=ctk.CTkFont(size=13),
            justify="center",
        ).pack(expand=True, padx=20, pady=(20, 10))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 15))

        def do_switch():
            dialog.destroy()
            remove_cuda_addon(on_status=lambda msg: logger.info(msg))
            self._config.set("asr_device", "cpu")
            self._update_device_status()
            self._show_restart_hint()

        ctk.CTkButton(btn_frame, text="确认切换", width=100, command=do_switch).pack(side="right", padx=5)
        ctk.CTkButton(btn_frame, text="取消", width=100, fg_color="gray", command=dialog.destroy).pack(
            side="right", padx=5
        )

    def _confirm_switch_to_gpu(self):
        """确认并开始下载 CUDA 组件"""
        # 先检查是否有手动放置的 addon
        manual_zip = check_manual_addon()
        if manual_zip:
            self._install_from_local(manual_zip)
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("升级到 GPU 模式")
        dialog.geometry("480x280")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        # 居中
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 480) // 2
        y = self.winfo_y() + (self.winfo_height() - 280) // 2
        dialog.geometry(f"+{x}+{y}")

        addon_size = get_cuda_addon_size()

        self._gpu_dialog = dialog
        self._gpu_status_label = ctk.CTkLabel(
            dialog,
            text=f"需要下载 CUDA 组件（{addon_size}）\n\n下载完成后将自动安装，需重启应用生效。\n请确保网络连接稳定。",
            font=ctk.CTkFont(size=13),
            justify="center",
        )
        self._gpu_status_label.pack(expand=True, padx=20, pady=(20, 5))

        self._gpu_progress = ctk.CTkProgressBar(dialog, width=400)
        self._gpu_progress.pack(padx=20, pady=5)
        self._gpu_progress.set(0)

        self._gpu_progress_label = ctk.CTkLabel(dialog, text="", font=ctk.CTkFont(size=11))
        self._gpu_progress_label.pack(padx=20, pady=(0, 5))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 15))

        self._gpu_confirm_btn = ctk.CTkButton(btn_frame, text="开始下载", width=100, command=self._start_gpu_download)
        self._gpu_confirm_btn.pack(side="right", padx=5)

        self._gpu_cancel_btn = ctk.CTkButton(btn_frame, text="取消", width=100, fg_color="gray", command=dialog.destroy)
        self._gpu_cancel_btn.pack(side="right", padx=5)

        # 手动下载链接
        manual_url = get_manual_download_url()
        self._gpu_manual_label = ctk.CTkLabel(
            dialog,
            text=f"下载失败？手动下载: {manual_url}",
            font=ctk.CTkFont(size=10),
            text_color="gray60",
        )
        self._gpu_manual_label.pack(padx=20, pady=(0, 10))

    def _start_gpu_download(self):
        """开始后台下载 CUDA addon"""
        self._gpu_confirm_btn.configure(state="disabled", text="下载中...")
        self._gpu_cancel_btn.configure(state="disabled")

        def on_progress(downloaded, total):
            progress = downloaded / total if total > 0 else 0
            downloaded_mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            # 在主线程更新 UI
            self.after(
                0,
                lambda: self._update_gpu_progress(progress, f"{downloaded_mb:.0f} / {total_mb:.0f} MB"),
            )

        def on_status(msg):
            self.after(0, lambda: self._gpu_status_label.configure(text=msg))

        def download_task():
            try:
                zip_path = download_cuda_addon(on_progress=on_progress, on_status=on_status)
                # 下载完成，安装
                self.after(0, lambda: self._gpu_status_label.configure(text="正在安装 CUDA 组件..."))
                success = install_cuda_addon(zip_path)
                if success:
                    self.after(0, self._on_gpu_install_success)
                else:
                    self.after(0, lambda: self._on_gpu_install_failed("安装失败：zip 文件解压出错"))
            except RuntimeError as exc:
                error_msg = str(exc)
                self.after(0, lambda: self._on_gpu_install_failed(error_msg))

        thread = threading.Thread(target=download_task, daemon=True)
        thread.start()

    def _update_gpu_progress(self, progress: float, text: str):
        """更新下载进度条"""
        try:
            self._gpu_progress.set(progress)
            self._gpu_progress_label.configure(text=text)
        except Exception:
            pass

    def _on_gpu_install_success(self):
        """GPU 组件安装成功"""
        try:
            self._gpu_status_label.configure(
                text="CUDA 组件安装完成！\n重启应用后生效。",
                text_color="#4CAF50",
            )
            self._gpu_progress.set(1.0)
            self._gpu_progress_label.configure(text="完成")
            self._gpu_confirm_btn.configure(state="normal", text="确定", command=self._gpu_dialog.destroy)
            self._gpu_cancel_btn.pack_forget()
            self._config.set("asr_device", "cuda:0")
            self._update_device_status()
        except Exception:
            pass

    def _on_gpu_install_failed(self, error_msg: str):
        """GPU 组件安装失败"""
        try:
            manual_url = get_manual_download_url()
            self._gpu_status_label.configure(
                text=f"下载失败: {error_msg}\n\n"
                f"您可以手动下载 CUDA 组件:\n{manual_url}\n\n"
                "下载后将 zip 文件放入应用安装目录，\n重启应用将自动安装。",
                text_color="#F44336",
                font=ctk.CTkFont(size=12),
            )
            self._gpu_confirm_btn.configure(state="normal", text="关闭", command=self._gpu_dialog.destroy)
            self._gpu_cancel_btn.pack_forget()
        except Exception:
            pass

    def _install_from_local(self, zip_path):
        """从本地文件安装 CUDA addon"""
        success = install_cuda_addon(zip_path)
        if success:
            self._config.set("asr_device", "cuda:0")
            self._update_device_status()
            self._show_restart_hint()

    def _show_restart_hint(self):
        """显示重启提示"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("提示")
        dialog.geometry("300x120")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 300) // 2
        y = self.winfo_y() + (self.winfo_height() - 120) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            dialog,
            text="设置已更改，重启应用后生效。",
            font=ctk.CTkFont(size=13),
        ).pack(expand=True, padx=20, pady=(20, 10))

        ctk.CTkButton(dialog, text="确定", width=80, command=dialog.destroy).pack(pady=(0, 15))
