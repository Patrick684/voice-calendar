"""全局快捷键管理模块 - 使用 keyboard 库监听全局按键"""

import logging
import time
import threading
import winsound
from typing import Callable, Optional

import keyboard

logger = logging.getLogger(__name__)


class HotkeyManager:
    """全局快捷键管理器，支持按住录音和切换录音两种模式"""

    # 提示音频率 (Hz) 和时长 (ms)
    BEEP_START_FREQ = 880
    BEEP_START_DURATION = 100
    BEEP_STOP_FREQ = 440
    BEEP_STOP_DURATION = 100

    # 需要扫描码过滤的按键及其有效扫描码集合
    # Windows 下 keyboard 库无法可靠区分左右修饰键，通过扫描码解决
    SCAN_CODE_FILTERS = {
        "right alt": {312},  # 右Alt: scan code 56 + extended flag = 312
        "left alt": {56},  # 左Alt: scan code 56
        "right ctrl": {285},  # 右Ctrl: scan code 29 + extended flag = 285
        "left ctrl": {29},  # 左Ctrl: scan code 29
        "right shift": {54},  # 右Shift: scan code 54
        "left shift": {42},  # 左Shift: scan code 42
    }

    # 左右键扫描码相同时，回退到 event.name 判断
    AMBIGUOUS_SCAN_CODES = {
        56: {"right alt", "left alt"},  # Alt 键共用扫描码 56
        29: {"right ctrl", "left ctrl"},  # Ctrl 键共用扫描码 29
    }

    def __init__(
        self,
        hotkey: str = "right alt",
        mode: str = "hold",
        on_start: Optional[Callable[[], None]] = None,
        on_stop: Optional[Callable[[], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
    ):
        """
        初始化快捷键管理器

        Args:
            hotkey: 快捷键名称 (如 "right alt", "f4" 等)
            mode: 触发模式 "hold"(按住) 或 "toggle"(切换)
            on_start: 开始录音回调
            on_stop: 停止录音回调
            on_cancel: 取消录音回调
        """
        self.hotkey = hotkey
        self.mode = mode
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_cancel = on_cancel

        self._active = False
        self._recording = False
        self._press_time: float = 0
        self._registered = False

        # 防抖设置
        self._min_hold_duration = 0.15  # 最短按住时间（秒），防止误触
        self._debounce_lock = threading.Lock()

        # 启动保护：注册后短暂忽略事件，避免 keyboard 库的合成事件误触
        self._ready_time: float = 0

    @property
    def is_recording(self) -> bool:
        return self._recording

    def register(self):
        """注册全局快捷键"""
        if self._registered:
            return

        if self.mode == "hold":
            keyboard.on_press_key(self.hotkey, self._on_key_press)
            keyboard.on_release_key(self.hotkey, self._on_key_release)
        else:  # toggle 模式
            keyboard.add_hotkey(self.hotkey, self._on_toggle)

        self._registered = True
        # 启动保护：注册后 0.5 秒内忽略所有事件，避免 keyboard 库合成事件误触
        self._ready_time = time.time() + 0.5
        self._active = True

    def unregister(self):
        """注销全局快捷键"""
        if not self._registered:
            return

        try:
            if self.mode == "hold":
                keyboard.unhook_all()
            else:
                keyboard.remove_hotkey(self.hotkey)
        except Exception:
            pass

        self._registered = False
        self._active = False

    def _is_target_key(self, event) -> bool:
        """
        检查事件是否是目标按键（通过扫描码过滤，解决左右修饰键混淆问题）

        keyboard 库在 Windows 下对左右 Alt/Ctrl/Shift 的区分不可靠，
        通过检查硬件扫描码可以精确过滤。
        """
        hotkey_lower = self.hotkey.lower()
        valid_codes = self.SCAN_CODE_FILTERS.get(hotkey_lower)

        if valid_codes is None:
            # 不需要扫描码过滤的按键（如 F4、F9 等）
            return True

        scan_code = getattr(event, "scan_code", None)
        event_name = getattr(event, "name", "").lower()

        if scan_code is None:
            return True  # 无扫描码信息时不拦截

        # 检查扫描码是否匹配
        is_match = scan_code in valid_codes

        # 当扫描码与左右键都相同时（无 extended flag），回退到 event.name 判断
        if not is_match:
            ambiguous_keys = self.AMBIGUOUS_SCAN_CODES.get(scan_code)
            if ambiguous_keys and hotkey_lower in ambiguous_keys:
                is_match = event_name == hotkey_lower
                if not is_match:
                    logger.debug(
                        f"扫描码模糊过滤: scan_code={scan_code}, name={event_name}, 期望={hotkey_lower}"
                    )
                return is_match

        if not is_match:
            logger.debug(
                f"扫描码过滤: scan_code={scan_code}, 期望={valid_codes}, key={event_name}"
            )
        return is_match

    def _on_key_press(self, event):
        """按住模式 - 按键按下处理"""
        if not self._active:
            return

        # 扫描码过滤：排除左 Alt 等混淆按键
        if not self._is_target_key(event):
            return

        # 启动保护期内忽略事件
        if time.time() < self._ready_time:
            return

        with self._debounce_lock:
            if self._recording:
                return

            self._press_time = time.time()
            self._recording = True

        # 播放开始提示音
        self._play_beep(self.BEEP_START_FREQ, self.BEEP_START_DURATION)

        if self.on_start:
            self.on_start()

    def _on_key_release(self, event):
        """按住模式 - 按键释放处理"""
        if not self._active or not self._recording:
            return

        # 扫描码过滤：排除左 Alt 等混淆按键
        if not self._is_target_key(event):
            return

        # 启动保护期内忽略事件
        if time.time() < self._ready_time:
            return

        with self._debounce_lock:
            hold_duration = time.time() - self._press_time

            if hold_duration < self._min_hold_duration:
                # 按住时间太短，取消录音
                self._recording = False
                if self.on_cancel:
                    self.on_cancel()
                return

            self._recording = False

        # 播放停止提示音
        self._play_beep(self.BEEP_STOP_FREQ, self.BEEP_STOP_DURATION)

        if self.on_stop:
            self.on_stop()

    def _on_toggle(self):
        """切换模式 - 按键切换处理"""
        if not self._active:
            return

        if self._recording:
            self._recording = False
            self._play_beep(self.BEEP_STOP_FREQ, self.BEEP_STOP_DURATION)
            if self.on_stop:
                self.on_stop()
        else:
            self._recording = True
            self._play_beep(self.BEEP_START_FREQ, self.BEEP_START_DURATION)
            if self.on_start:
                self.on_start()

    def cancel_recording(self):
        """手动取消当前录音"""
        if self._recording:
            self._recording = False
            if self.on_cancel:
                self.on_cancel()

    @staticmethod
    def _play_beep(frequency: int, duration: int):
        """播放提示音（异步）"""
        try:
            # 使用线程避免阻塞
            threading.Thread(
                target=winsound.Beep,
                args=(frequency, duration),
                daemon=True,
            ).start()
        except Exception:
            pass

    def change_hotkey(self, new_hotkey: str, new_mode: Optional[str] = None):
        """
        更改快捷键

        Args:
            new_hotkey: 新的快捷键
            new_mode: 新的触发模式（可选）
        """
        was_registered = self._registered
        if was_registered:
            self.unregister()

        self.hotkey = new_hotkey
        if new_mode:
            self.mode = new_mode

        if was_registered:
            self.register()

    def set_active(self, active: bool):
        """设置快捷键是否激活"""
        self._active = active
