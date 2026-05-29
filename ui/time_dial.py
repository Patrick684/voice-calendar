"""时间拨盘 - 24 小时水平标尺 + 半小时吸附 + 拖拽精调"""

import logging
from datetime import datetime
from typing import Optional, Callable

import customtkinter as ctk
import tkinter as tk

logger = logging.getLogger(__name__)


class TimeDial(ctk.CTkFrame):
    """时间拨盘组件

    水平 24 小时标尺，半小时刻度吸附，拖拽调整事件时间。
    选中事件后在事件列表底部展开。
    """

    # 布局常量
    _SLOT_WIDTH = 28  # 每个半小时的像素宽度
    _TOTAL_SLOTS = 48  # 24h × 2 = 48 个半小时
    _HEIGHT = 80  # 组件总高度
    _TICK_TOP = 25  # 刻度线顶部 Y
    _HANDLE_Y = 20  # 滑块中心 Y
    _HANDLE_W = 12  # 滑块宽度
    _HANDLE_H = 30  # 滑块高度
    _LABEL_Y = 55  # 小时标签 Y

    def __init__(
        self,
        master,
        on_time_change: Optional[Callable[[int, int], None]] = None,
        **kwargs,
    ):
        """
        Args:
            master: 父组件
            on_time_change: 时间变更回调 (hour, minute)
        """
        super().__init__(master, height=self._HEIGHT, **kwargs)
        self._on_time_change = on_time_change

        # 当前时间（半小时精度）
        self._current_slot = 28  # 默认 14:00
        self._event_id: Optional[int] = None

        # 拖拽状态
        self._dragging = False
        self._hover_slot = -1

        self._setup_canvas()
        self._draw()

    def _setup_canvas(self):
        """创建 Canvas"""
        total_width = self._TOTAL_SLOTS * self._SLOT_WIDTH
        self._canvas = tk.Canvas(
            self,
            width=total_width,
            height=self._HEIGHT,
            highlightthickness=0,
            bg="#f5f5f5",
        )
        self._canvas.pack(fill="x", expand=True)

        # 绑定鼠标事件
        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_motion)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Motion>", self._on_hover)
        self._canvas.bind("<Leave>", self._on_leave)

    def _draw(self):
        """绘制标尺"""
        c = self._canvas
        c.delete("all")
        sw = self._SLOT_WIDTH

        # 背景渐变效果（工作时间浅色高亮）
        # 工作时间 8:00-18:00 (slot 16-36)
        c.create_rectangle(
            16 * sw,
            0,
            36 * sw,
            self._HEIGHT,
            fill="#e8f5e9",
            outline="",
        )

        # 刻度线
        for i in range(self._TOTAL_SLOTS + 1):
            x = i * sw
            if i % 2 == 0:
                # 整点：长刻度
                c.create_line(x, self._TICK_TOP, x, self._TICK_TOP + 15, fill="#666", width=2)
            else:
                # 半点：短刻度
                c.create_line(x, self._TICK_TOP + 5, x, self._TICK_TOP + 15, fill="#aaa", width=1)

        # 小时标签
        for h in range(24):
            x = h * 2 * sw
            label = f"{h:02d}"
            c.create_text(
                x + sw,
                self._LABEL_Y,
                text=label,
                fill="#555",
                font=("Consolas", 9),
            )

        # Hover 高亮
        if 0 <= self._hover_slot < self._TOTAL_SLOTS and not self._dragging:
            hx = self._hover_slot * sw
            c.create_rectangle(
                hx,
                self._TICK_TOP - 5,
                hx + sw,
                self._TICK_TOP + 20,
                fill="#bbdefb",
                outline="",
                stipple="gray25",
            )

        # 滑块
        slot = self._current_slot
        sx = slot * sw
        # 滑块主体
        c.create_rectangle(
            sx - self._HANDLE_W // 2,
            self._HANDLE_Y,
            sx + self._HANDLE_W // 2,
            self._HANDLE_Y + self._HANDLE_H,
            fill="#1976D2",
            outline="#0D47A1",
            width=2,
            tags="handle",
        )
        # 滑块上方时间标签
        hour = slot // 2
        minute = (slot % 2) * 30
        time_text = f"{hour:02d}:{minute:02d}"
        c.create_text(
            sx,
            self._HANDLE_Y - 8,
            text=time_text,
            fill="#1976D2",
            font=("Consolas", 10, "bold"),
            tags="handle_label",
        )

    def set_event(self, event_id: Optional[int], start_time: datetime):
        """设置当前事件（显示其时间位置）

        Args:
            event_id: 事件 ID（None 表示无选中）
            start_time: 事件开始时间
        """
        self._event_id = event_id
        if event_id is not None:
            slot = start_time.hour * 2 + (1 if start_time.minute >= 30 else 0)
            self._current_slot = max(0, min(slot, self._TOTAL_SLOTS - 1))
        self._draw()

    def clear(self):
        """清除选中状态"""
        self._event_id = None
        self._draw()

    def _x_to_slot(self, x: int) -> int:
        """将鼠标 X 坐标转换为 slot 索引"""
        slot = round(x / self._SLOT_WIDTH)
        return max(0, min(slot, self._TOTAL_SLOTS - 1))

    def _slot_to_time(self, slot: int) -> tuple:
        """slot → (hour, minute)"""
        return slot // 2, (slot % 2) * 30

    # ================================================================
    # 鼠标事件
    # ================================================================

    def _on_press(self, event):
        """按下"""
        if self._event_id is None:
            return
        slot = self._x_to_slot(event.x)
        # 只有点击在滑块附近才开始拖拽
        if abs(slot - self._current_slot) <= 1:
            self._dragging = True

    def _on_motion(self, event):
        """拖拽中"""
        if not self._dragging:
            return
        slot = self._x_to_slot(event.x)
        if slot != self._current_slot:
            self._current_slot = slot
            self._draw()

    def _on_release(self, event):
        """释放"""
        if self._dragging:
            self._dragging = False
            hour, minute = self._slot_to_time(self._current_slot)
            if self._on_time_change and self._event_id is not None:
                self._on_time_change(hour, minute)
            logger.info(f"拨盘调整: {hour:02d}:{minute:02d}")
        self._draw()

    def _on_hover(self, event):
        """悬停"""
        slot = self._x_to_slot(event.x)
        if slot != self._hover_slot:
            self._hover_slot = slot
            self._draw()

    def _on_leave(self, event):
        """离开"""
        self._hover_slot = -1
        self._draw()
