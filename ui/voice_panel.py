"""语音输入状态面板 - 显示录音/识别状态和结果"""

import customtkinter as ctk
from enum import Enum
from typing import Optional, Callable


class VoiceState(Enum):
    """语音输入状态"""

    IDLE = "idle"  # 就绪
    RECORDING = "recording"  # 录音中
    PROCESSING = "processing"  # 识别中
    SUCCESS = "success"  # 识别完成
    ERROR = "error"  # 识别失败


class VoicePanel(ctk.CTkFrame):
    """语音输入状态面板

    显示在窗口底部，实时反馈语音输入的当前状态和识别结果。
    """

    # 状态颜色配置
    STATE_COLORS = {
        VoiceState.IDLE: ("#2ecc71", "就绪 - 按住快捷键说话"),
        VoiceState.RECORDING: ("#e74c3c", "录音中..."),
        VoiceState.PROCESSING: ("#3498db", "识别中..."),
        VoiceState.SUCCESS: ("#27ae60", "识别完成"),
        VoiceState.ERROR: ("#e74c3c", "识别失败"),
    }

    def __init__(
        self,
        master,
        on_voice_button: Optional[Callable] = None,
        **kwargs,
    ):
        """
        初始化语音面板

        Args:
            master: 父组件
            on_voice_button: 语音按钮点击回调
        """
        super().__init__(master, height=80, **kwargs)
        self._on_voice_button = on_voice_button
        self._state = VoiceState.IDLE
        self._setup_ui()

    def _setup_ui(self):
        """构建 UI 组件"""
        self.grid_columnconfigure(1, weight=1)

        # 左侧：语音按钮
        self._voice_btn = ctk.CTkButton(
            self,
            text="🎤 语音输入",
            width=120,
            height=50,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_voice_click,
        )
        self._voice_btn.grid(row=0, column=0, padx=(10, 10), pady=10, sticky="w")

        # 中间：状态指示 + 结果显示
        self._status_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._status_frame.grid(row=0, column=1, padx=5, pady=10, sticky="ew")
        self._status_frame.grid_columnconfigure(0, weight=1)

        # 状态标签（带颜色指示）
        self._state_indicator = ctk.CTkLabel(
            self._status_frame,
            text="● 就绪",
            font=ctk.CTkFont(size=12),
            text_color="#2ecc71",
            anchor="w",
        )
        self._state_indicator.grid(row=0, column=0, sticky="w")

        # 识别结果文本
        self._result_label = ctk.CTkLabel(
            self._status_frame,
            text="按住快捷键或点击按钮开始语音输入",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
            wraplength=500,
        )
        self._result_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

    def set_state(self, state: VoiceState, message: str = ""):
        """更新面板状态

        Args:
            state: 新的语音状态
            message: 附加消息（如识别结果或错误信息）
        """
        self._state = state
        color, default_text = self.STATE_COLORS.get(state, ("#95a5a6", ""))
        display_text = message if message else default_text

        self._state_indicator.configure(
            text=f"● {display_text}",
            text_color=color,
        )

        if state == VoiceState.RECORDING:
            self._voice_btn.configure(text="⏹ 停止录音")
        else:
            self._voice_btn.configure(text="🎤 语音输入")

        if state == VoiceState.SUCCESS and message:
            self._result_label.configure(text=message, text_color="white")
        elif state == VoiceState.ERROR and message:
            self._result_label.configure(text=f"错误: {message}", text_color="#e74c3c")
        elif state == VoiceState.RECORDING:
            self._result_label.configure(text="正在录音，请说话...", text_color="gray")
        elif state == VoiceState.PROCESSING:
            self._result_label.configure(text="正在识别语音...", text_color="gray")
        else:
            self._result_label.configure(text="按住快捷键或点击按钮开始语音输入", text_color="gray")

    def set_result(self, text: str):
        """设置识别结果文本

        Args:
            text: 识别结果
        """
        self.set_state(VoiceState.SUCCESS, text)

    def _on_voice_click(self):
        """语音按钮点击"""
        if self._on_voice_button:
            self._on_voice_button()
