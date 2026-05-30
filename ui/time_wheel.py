"""纵向滚轮时间选择器 - 双拨盘（时+分）弹出小窗

设计参考手机计时器/密码锁：两个并列纵向拨盘，
用户可通过上下拖拽或鼠标滚轮修改时间。
长按事件卡片后弹出在鼠标位置旁。
"""

import logging
import tkinter as tk
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class TimeWheel(tk.Toplevel):
    """纵向滚轮时间选择器弹窗

    两个并列 Canvas 分别渲染时(0-23)和分(0-59)，
    支持鼠标拖拽滚动和滚轮快速调整。
    窗口外点击自动关闭并保存。
    """

    # 布局常量
    _WHEEL_WIDTH = 60  # 每个轮的宽度
    _WHEEL_HEIGHT = 120  # 每个轮的高度
    _ITEM_HEIGHT = 36  # 每个数字的行高
    _VISIBLE_ITEMS = 3  # 可见项数（中间高亮）
    _COLON_WIDTH = 24  # 冒号区域宽度

    def __init__(
        self,
        master,
        hour: int = 12,
        minute: int = 0,
        on_time_confirm: Optional[Callable[[int, int], None]] = None,
        x: int = 0,
        y: int = 0,
    ):
        """
        Args:
            master: 父窗口
            hour: 初始小时 (0-23)
            minute: 初始分钟 (0-59)
            on_time_confirm: 确认回调 (hour, minute)
            x, y: 弹出位置（屏幕坐标）
        """
        super().__init__(master)
        self._on_time_confirm = on_time_confirm
        self._hour = hour
        self._minute = minute

        # 拖拽状态
        self._drag_start_y = 0
        self._drag_target = None  # "hour" or "minute"
        self._drag_offset = 0.0

        self._setup_window(x, y)
        self._setup_ui()
        self._redraw_all()

        # 窗口外点击关闭
        self.bind("<FocusOut>", self._on_focus_out)
        self.after(100, self._bind_global_click)

    def _setup_window(self, x: int, y: int):
        """配置窗口属性"""
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        total_w = self._WHEEL_WIDTH * 2 + self._COLON_WIDTH + 20
        total_h = self._WHEEL_HEIGHT + 40  # 额外空间给确认按钮
        self.geometry(f"{total_w}x{total_h}+{x}+{y}")
        self.configure(bg="#2c3e50")
        # 圆角阴影效果（通过透明度模拟）
        self.attributes("-alpha", 0.95)

    def _setup_ui(self):
        """构建 UI"""
        # 标题
        tk.Label(
            self,
            text="调整时间",
            bg="#2c3e50",
            fg="#ecf0f1",
            font=("Microsoft YaHei UI", 9),
        ).pack(pady=(4, 2))

        # 拨盘容器
        wheel_frame = tk.Frame(self, bg="#2c3e50")
        wheel_frame.pack(fill="both", expand=True, padx=8)

        # 小时轮
        self._hour_canvas = tk.Canvas(
            wheel_frame,
            width=self._WHEEL_WIDTH,
            height=self._WHEEL_HEIGHT,
            bg="#34495e",
            highlightthickness=0,
        )
        self._hour_canvas.pack(side="left", padx=(0, 2))

        # 冒号
        colon_label = tk.Label(
            wheel_frame,
            text=":",
            bg="#2c3e50",
            fg="#ecf0f1",
            font=("Consolas", 20, "bold"),
        )
        colon_label.pack(side="left", padx=2)

        # 分钟轮
        self._minute_canvas = tk.Canvas(
            wheel_frame,
            width=self._WHEEL_WIDTH,
            height=self._WHEEL_HEIGHT,
            bg="#34495e",
            highlightthickness=0,
        )
        self._minute_canvas.pack(side="left", padx=(2, 0))

        # 绑定事件 - 小时轮
        self._hour_canvas.bind("<ButtonPress-1>", lambda e: self._on_wheel_press(e, "hour"))
        self._hour_canvas.bind("<B1-Motion>", lambda e: self._on_wheel_drag(e, "hour"))
        self._hour_canvas.bind("<ButtonRelease-1>", lambda e: self._on_wheel_release(e, "hour"))
        self._hour_canvas.bind("<MouseWheel>", lambda e: self._on_wheel_scroll(e, "hour"))

        # 绑定事件 - 分钟轮
        self._minute_canvas.bind("<ButtonPress-1>", lambda e: self._on_wheel_press(e, "minute"))
        self._minute_canvas.bind("<B1-Motion>", lambda e: self._on_wheel_drag(e, "minute"))
        self._minute_canvas.bind("<ButtonRelease-1>", lambda e: self._on_wheel_release(e, "minute"))
        self._minute_canvas.bind("<MouseWheel>", lambda e: self._on_wheel_scroll(e, "minute"))

        # 确认按钮
        btn_frame = tk.Frame(self, bg="#2c3e50")
        btn_frame.pack(fill="x", padx=8, pady=(2, 6))
        confirm_btn = tk.Button(
            btn_frame,
            text="确认",
            bg="#27ae60",
            fg="white",
            font=("Microsoft YaHei UI", 9),
            relief="flat",
            cursor="hand2",
            command=self._on_confirm,
        )
        confirm_btn.pack(fill="x")

    def _redraw_all(self):
        """重绘两个拨盘"""
        self._redraw_wheel(self._hour_canvas, self._hour, 24)
        self._redraw_wheel(self._minute_canvas, self._minute, 60)

    def _redraw_wheel(self, canvas: tk.Canvas, value: int, max_val: int):
        """绘制单个拨盘

        Args:
            canvas: 目标 Canvas
            value: 当前值
            max_val: 最大值（24 或 60）
        """
        canvas.delete("all")
        w = self._WHEEL_WIDTH
        h = self._WHEEL_HEIGHT
        item_h = self._ITEM_HEIGHT
        center_y = h // 2

        # 中间选中区域高亮背景
        sel_y1 = center_y - item_h // 2
        sel_y2 = center_y + item_h // 2
        canvas.create_rectangle(0, sel_y1, w, sel_y2, fill="#1abc9c", outline="")

        # 上下渐变遮罩线
        canvas.create_line(0, sel_y1, w, sel_y1, fill="#16a085", width=1)
        canvas.create_line(0, sel_y2, w, sel_y2, fill="#16a085", width=1)

        # 绘制可见数字（中间 + 上下各 1-2 个）
        visible_range = self._VISIBLE_ITEMS // 2 + 1
        for offset in range(-visible_range, visible_range + 1):
            item_val = (value + offset) % max_val
            y = center_y + offset * item_h

            if y < -item_h or y > h + item_h:
                continue

            # 根据离中心距离设置样式
            if offset == 0:
                # 当前选中值（大字白色）
                font = ("Consolas", 18, "bold")
                color = "white"
            elif abs(offset) == 1:
                # 相邻值（中等字灰色）
                font = ("Consolas", 14)
                color = "#bdc3c7"
            else:
                # 远处值（小字暗灰）
                font = ("Consolas", 11)
                color = "#7f8c8d"

            text = f"{item_val:02d}"
            canvas.create_text(w // 2, y, text=text, font=font, fill=color)

    def _on_wheel_press(self, event, target: str):
        """拨盘按下"""
        self._drag_start_y = event.y
        self._drag_target = target
        self._drag_offset = 0.0

    def _on_wheel_drag(self, event, target: str):
        """拨盘拖拽中 - 上下拖拽改变值"""
        if self._drag_target != target:
            return

        dy = self._drag_start_y - event.y  # 向上拖 = 正值 = 数值增大
        self._drag_offset += dy
        self._drag_start_y = event.y

        # 累计超过一个 item 高度时触发值变更
        threshold = self._ITEM_HEIGHT * 0.6
        while abs(self._drag_offset) >= threshold:
            if self._drag_offset > 0:
                self._change_value(target, 1)
                self._drag_offset -= threshold
            else:
                self._change_value(target, -1)
                self._drag_offset += threshold

        self._redraw_all()

    def _on_wheel_release(self, event, target: str):
        """拨盘释放"""
        self._drag_target = None
        self._drag_offset = 0.0
        self._redraw_all()

    def _on_wheel_scroll(self, event, target: str):
        """鼠标滚轮调整"""
        # Windows: event.delta > 0 = 向上滚 = 值增大
        delta = 1 if event.delta > 0 else -1
        self._change_value(target, delta)
        self._redraw_all()

    def _change_value(self, target: str, delta: int):
        """修改时/分值"""
        if target == "hour":
            self._hour = (self._hour + delta) % 24
        elif target == "minute":
            self._minute = (self._minute + delta) % 60

    def _on_confirm(self):
        """确认按钮"""
        if self._on_time_confirm:
            self._on_time_confirm(self._hour, self._minute)
        logger.info(f"时间滚轮确认: {self._hour:02d}:{self._minute:02d}")
        self.destroy()

    def _on_focus_out(self, event=None):
        """失去焦点时保存并关闭"""
        # 延迟检查，避免内部控件切换焦点误触发
        self.after(150, self._check_focus)

    def _check_focus(self):
        """检查焦点是否真的离开了窗口"""
        try:
            focus_widget = self.focus_get()
            if focus_widget is None or not str(focus_widget).startswith(str(self)):
                self._on_confirm()
        except Exception:
            self._on_confirm()

    def _bind_global_click(self):
        """绑定全局点击检测（点击窗口外关闭）"""
        self.bind_all("<Button-1>", self._on_global_click, add="+")
        self.focus_force()

    def _on_global_click(self, event):
        """全局点击检测"""
        try:
            # 检查点击是否在本窗口内
            x = self.winfo_rootx()
            y = self.winfo_rooty()
            w = self.winfo_width()
            h = self.winfo_height()
            if not (x <= event.x_root <= x + w and y <= event.y_root <= y + h):
                self.unbind_all("<Button-1>")
                self._on_confirm()
        except Exception:
            pass
