"""回收站窗口 - 显示已删除事件，支持恢复和彻底删除"""

import customtkinter as ctk
from typing import Callable, Optional

from calendar_pkg.event import CalendarEvent


CATEGORY_COLORS = {
    "工作": "#2196F3",
    "健康": "#4CAF50",
    "学习": "#FF9800",
    "生活": "#9C27B0",
    "娱乐": "#E91E63",
    "社交": "#00BCD4",
    "其他": "#757575",
}


class RecycleBinWindow(ctk.CTkToplevel):
    """回收站窗口"""

    def __init__(
        self,
        master,
        events: list,
        on_restore: Optional[Callable] = None,
        on_hard_delete: Optional[Callable] = None,
    ):
        super().__init__(master)

        self.title("回收站")
        self.geometry("320x450")
        self.resizable(False, True)
        self.attributes("-topmost", True)

        self._on_restore = on_restore
        self._on_hard_delete = on_hard_delete

        self._build_ui()
        self._render_events(events)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        """构建窗口 UI"""
        # 标题
        self._title_label = ctk.CTkLabel(
            self,
            text="🗑 回收站",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._title_label.pack(padx=10, pady=(12, 6), anchor="w")

        # 提示
        ctk.CTkLabel(
            self,
            text="已删除的事件会保留 30 天",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(padx=10, anchor="w")

        # 事件滚动列表
        self._scroll_frame = ctk.CTkScrollableFrame(self)
        self._scroll_frame.pack(fill="both", expand=True, padx=8, pady=(8, 8))

        # 底部按钮
        ctk.CTkButton(
            self,
            text="关闭",
            width=80,
            height=28,
            command=self._on_close,
        ).pack(pady=(0, 10))

    def _render_events(self, events: list):
        """渲染已删除事件列表"""
        for widget in self._scroll_frame.winfo_children():
            widget.destroy()

        self._title_label.configure(text=f"🗑 回收站 ({len(events)})")

        if not events:
            ctk.CTkLabel(
                self._scroll_frame,
                text="回收站为空",
                font=ctk.CTkFont(size=12),
                text_color="gray",
            ).pack(pady=30)
            return

        for event in events:
            self._create_event_card(event)

    def _create_event_card(self, event: CalendarEvent):
        """创建回收站事件卡片（含恢复/删除按钮）"""
        card = ctk.CTkFrame(self._scroll_frame, corner_radius=4)
        card.pack(fill="x", pady=3)

        # 颜色条
        cat_color = CATEGORY_COLORS.get(event.category, "#757575")
        ctk.CTkFrame(card, width=4, height=1, fg_color=cat_color, corner_radius=2).pack(
            side="left", fill="y", padx=(3, 0), pady=3
        )

        # 内容区
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=3)

        # 标题行
        time_str = "全天" if event.is_all_day else event.start_time.strftime("%m-%d %H:%M")
        ctk.CTkLabel(
            content,
            text=f"{time_str}  {event.title}",
            font=ctk.CTkFont(size=12),
            anchor="w",
        ).pack(side="top", fill="x")

        # 分类
        if event.category:
            ctk.CTkLabel(
                content,
                text=event.category,
                font=ctk.CTkFont(size=10),
                text_color=cat_color,
                anchor="w",
            ).pack(side="top", fill="x")

        # 操作按钮区
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="right", padx=(0, 6), pady=3)

        # 恢复按钮
        ctk.CTkButton(
            btn_frame,
            text="恢复",
            width=44,
            height=22,
            font=ctk.CTkFont(size=10),
            fg_color="#27ae60",
            hover_color="#2ecc71",
            command=lambda eid=event.id: self._do_restore(eid),
        ).pack(side="top", pady=(0, 2))

        # 彻底删除按钮
        ctk.CTkButton(
            btn_frame,
            text="删除",
            width=44,
            height=22,
            font=ctk.CTkFont(size=10),
            fg_color="#c0392b",
            hover_color="#e74c3c",
            command=lambda eid=event.id: self._do_hard_delete(eid),
        ).pack(side="top")

    def _do_restore(self, event_id: int):
        """恢复事件"""
        if self._on_restore:
            self._on_restore(event_id)

    def _do_hard_delete(self, event_id: int):
        """彻底删除事件"""
        if self._on_hard_delete:
            self._on_hard_delete(event_id)

    def refresh(self, events: list):
        """刷新事件列表"""
        self._render_events(events)

    def _on_close(self):
        """关闭窗口"""
        self.destroy()
