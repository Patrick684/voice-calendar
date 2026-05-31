"""Toast 通知与音效播放模块

使用 winotify 发送 Windows 原生 Toast 通知（屏幕右下角），
使用 winsound 播放 .wav 提示音。
"""

from __future__ import annotations

import logging
import threading
import winsound
from datetime import datetime
from pathlib import Path
from typing import Optional

from calendar_pkg.event import CalendarEvent

logger = logging.getLogger(__name__)


class ToastNotifier:
    """Windows Toast 通知管理器

    - 发送事件提醒通知到 Windows 通知中心
    - 异步播放 .wav 音效文件
    """

    def __init__(
        self,
        app_id: str = "VoiceCalendar",
        icon_path: Optional[str] = None,
        sounds_dir: Optional[Path] = None,
    ):
        """
        Args:
            app_id: Windows 通知的应用标识
            icon_path: 通知图标路径（.ico/.png）
            sounds_dir: 音效文件目录
        """
        self._app_id = app_id
        self._icon_path = icon_path
        self._sounds_dir = sounds_dir

    def show_reminder(self, event: CalendarEvent):
        """发送事件提醒的 Toast 通知

        Args:
            event: 要提醒的日历事件
        """
        try:
            from winotify import Notification, audio

            # 计算剩余时间
            now = datetime.now()
            diff = event.start_time - now
            minutes_left = max(0, int(diff.total_seconds() / 60))
            if minutes_left > 0:
                time_hint = f"还有 {minutes_left} 分钟"
            else:
                time_hint = "已到时间"

            time_str = event.start_time.strftime("%m月%d日 %H:%M")

            # 构建通知正文
            body = f"时间: {time_str} ({time_hint})"
            if event.category:
                body += f"\n分类: {event.category}"

            toast = Notification(
                app_id=self._app_id,
                title=f"\u23f0 {event.title}",
                msg=body,
                duration="short",
            )

            # 设置图标
            if self._icon_path and Path(self._icon_path).exists():
                toast.set_audio(audio.Default, loop=False)
                toast.icon = self._icon_path

            # 不使用 winotify 内置音效（我们有自己的音效系统）
            toast.set_audio(audio.Silent, loop=False)

            toast.show()
            logger.info(f"Toast 通知已发送: {event.title}")

        except ImportError:
            logger.warning("winotify 未安装，无法发送 Toast 通知")
        except Exception as e:
            logger.error(f"发送 Toast 通知失败: {e}")

    def play_sound(self, sound_file: str):
        """异步播放提示音

        Args:
            sound_file: 音效文件名（如 "bell.wav"）
        """
        if not self._sounds_dir:
            logger.warning("未配置音效目录，跳过播放")
            return

        filepath = self._sounds_dir / sound_file
        if not filepath.exists():
            # 回退到默认音效
            filepath = self._sounds_dir / "default.wav"
            if not filepath.exists():
                logger.warning(f"音效文件不存在: {sound_file}")
                return

        # 在独立线程中异步播放，避免阻塞
        thread = threading.Thread(
            target=self._play_wav,
            args=(str(filepath),),
            daemon=True,
            name="SoundPlayer",
        )
        thread.start()

    @staticmethod
    def _play_wav(filepath: str):
        """使用 winsound 播放 .wav 文件"""
        try:
            winsound.PlaySound(filepath, winsound.SND_FILENAME)
        except Exception as e:
            logger.error(f"播放音效失败: {e}")
