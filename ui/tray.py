"""系统托盘模块 - 应用最小化到系统托盘时的常驻图标"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


class SystemTray:
    """系统托盘图标管理器

    使用 pystray 在系统托盘中显示图标，支持右键菜单。
    托盘运行在独立线程中，不阻塞主线程。
    """

    def __init__(
        self,
        on_open: Callable[[], None],
        on_quit: Callable[[], None],
        icon_path: Optional[str] = None,
    ):
        """
        Args:
            on_open: 点击"打开主窗口"的回调
            on_quit: 点击"退出"的回调
            icon_path: 可选的图标文件路径（.ico/.png）
        """
        self._on_open = on_open
        self._on_quit = on_quit
        self._icon_path = icon_path
        self._icon = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """启动系统托盘图标（在独立线程中运行）"""
        import pystray
        from pystray import MenuItem as Item

        image = self._load_or_create_icon()

        menu = pystray.Menu(
            Item("打开主窗口", self._handle_open, default=True),
            pystray.Menu.SEPARATOR,
            Item("退出", self._handle_quit),
        )

        self._icon = pystray.Icon(
            name="VoiceCalendar",
            icon=image,
            title="语音日历",
            menu=menu,
        )

        # 在独立线程运行 pystray 事件循环
        self._thread = threading.Thread(
            target=self._icon.run,
            daemon=False,
            name="SystemTray",
        )
        self._thread.start()
        logger.info("系统托盘已启动")

    def stop(self):
        """停止并销毁托盘图标"""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
        logger.info("系统托盘已停止")

    @property
    def is_running(self) -> bool:
        """托盘是否在运行"""
        return self._thread is not None and self._thread.is_alive()

    def _handle_open(self, icon=None, item=None):
        """处理'打开主窗口'菜单点击"""
        try:
            self._on_open()
        except Exception as e:
            logger.error(f"打开主窗口失败: {e}")

    def _handle_quit(self, icon=None, item=None):
        """处理'退出'菜单点击"""
        try:
            self._on_quit()
        except Exception as e:
            logger.error(f"退出应用失败: {e}")

    def _load_or_create_icon(self) -> Image.Image:
        """加载图标文件或程序化生成一个日历图标"""
        if self._icon_path:
            try:
                return Image.open(self._icon_path)
            except Exception:
                logger.warning(f"无法加载图标: {self._icon_path}，使用默认图标")

        return self._create_calendar_icon()

    @staticmethod
    def _create_calendar_icon() -> Image.Image:
        """程序化生成一个简单的日历图标 (64x64)"""
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 日历主体 - 白色圆角矩形
        draw.rounded_rectangle(
            [4, 10, 60, 60],
            radius=6,
            fill=(255, 255, 255, 255),
            outline=(100, 100, 100, 255),
            width=2,
        )

        # 日历顶部 - 蓝色条
        draw.rounded_rectangle(
            [4, 10, 60, 24],
            radius=6,
            fill=(46, 134, 193, 255),
        )
        # 覆盖底部圆角
        draw.rectangle([4, 18, 60, 24], fill=(46, 134, 193, 255))

        # 日历挂钩
        draw.rectangle([18, 6, 22, 16], fill=(80, 80, 80, 255))
        draw.rectangle([42, 6, 46, 16], fill=(80, 80, 80, 255))

        # 日期格子线条
        for y in [32, 42, 52]:
            draw.line([(12, y), (52, y)], fill=(200, 200, 200, 255), width=1)
        for x in [22, 32, 42]:
            draw.line([(x, 26), (x, 58)], fill=(200, 200, 200, 255), width=1)

        # 标记今天 - 小红点
        draw.ellipse([34, 44, 42, 52], fill=(231, 76, 60, 255))

        return img
