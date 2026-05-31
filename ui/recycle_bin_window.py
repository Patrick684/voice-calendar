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
        on_clear_all: Optional[Callable] = None,
    ):
        super().__init__(master)

        self.title("回收站")
        self.geometry("320x450")
        self.resizable(False, True)
        self.attributes("-topmost", True)

        self._on_restore = on_restore
        self._on_hard_delete = on_hard_delete
        self._on_clear_all = on_clear_all
        self._sort_mode = "delete_time"  # "delete_time" | "event_date"
        self._events = events
        self._card_widgets: dict[int, ctk.CTkFrame] = {}  # event_id -> card widget

        self._build_ui()
        # 延迟渲染，先让窗口显示出来
        self.after(10, lambda: self._render_events(events))

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        """构建窗口 UI"""
        # 顶部栏（标题 + 清空按钮）
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(12, 0))

        self._title_label = ctk.CTkLabel(
            header,
            text="🗑 回收站",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._title_label.pack(side="left")

        # 右上角清空按钮
        self._clear_btn = ctk.CTkButton(
            header,
            text="清空",
            width=50,
            height=24,
            font=ctk.CTkFont(size=11),
            fg_color="#c0392b",
            hover_color="#e74c3c",
            command=self._do_clear_all,
        )
        self._clear_btn.pack(side="right")

        # 提示
        ctk.CTkLabel(
            self,
            text="已删除的事件会保留 30 天",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(padx=10, anchor="w", pady=(4, 0))

        # 排序切换栏
        sort_frame = ctk.CTkFrame(self, fg_color="transparent")
        sort_frame.pack(fill="x", padx=10, pady=(4, 0))

        self._sort_delete_btn = ctk.CTkButton(
            sort_frame,
            text="按删除时间",
            width=70,
            height=22,
            font=ctk.CTkFont(size=10),
            command=lambda: self._switch_sort("delete_time"),
        )
        self._sort_delete_btn.pack(side="left", padx=(0, 4))

        self._sort_event_btn = ctk.CTkButton(
            sort_frame,
            text="按事件日期",
            width=70,
            height=22,
            font=ctk.CTkFont(size=10),
            fg_color="transparent",
            text_color="gray",
            hover_color=("#e0e0e0", "#3a3a3a"),
            command=lambda: self._switch_sort("event_date"),
        )
        self._sort_event_btn.pack(side="left")

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

    def _switch_sort(self, mode: str):
        """切换排序模式"""
        if mode == self._sort_mode:
            return
        self._sort_mode = mode
        # 更新按钮样式（选中状态）
        if mode == "delete_time":
            self._sort_delete_btn.configure(
                fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"],
                text_color=ctk.ThemeManager.theme["CTkButton"]["text_color"],
            )
            self._sort_event_btn.configure(fg_color="transparent", text_color="gray")
        else:
            self._sort_event_btn.configure(
                fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"],
                text_color=ctk.ThemeManager.theme["CTkButton"]["text_color"],
            )
            self._sort_delete_btn.configure(fg_color="transparent", text_color="gray")
        self._render_events(self._events)

    def _render_events(self, events: list):
        """渲染已删除事件列表（按当前排序模式分组）"""
        self._events = events
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

        # 排序 + 分组
        if self._sort_mode == "delete_time":
            # 按删除时间倒序（已由 storage 返回），按删除日期分组
            sorted_events = events
            current_group = None
            for event in sorted_events:
                group_key = event.deleted_at[:10] if event.deleted_at else "未知"
                if group_key != current_group:
                    current_group = group_key
                    ctk.CTkLabel(
                        self._scroll_frame,
                        text=f"──── 删除于 {current_group} ────",
                        font=ctk.CTkFont(size=11),
                        text_color="#666666",
                    ).pack(fill="x", pady=(6, 2))
                self._create_event_card(event)
        else:
            # 按事件日期排序
            sorted_events = sorted(events, key=lambda e: e.start_time)
            current_group = None
            for event in sorted_events:
                group_key = event.start_time.strftime("%Y-%m-%d")
                if group_key != current_group:
                    current_group = group_key
                    ctk.CTkLabel(
                        self._scroll_frame,
                        text=f"────── {current_group} ──────",
                        font=ctk.CTkFont(size=11),
                        text_color="#666666",
                    ).pack(fill="x", pady=(6, 2))
                self._create_event_card(event)

    def _create_event_card(self, event: CalendarEvent):
        """创建回收站事件卡片（含恢复/删除按钮）"""
        card = ctk.CTkFrame(self._scroll_frame, corner_radius=4)
        card.pack(fill="x", pady=3)
        # 记录卡片引用
        if event.id is not None:
            self._card_widgets[event.id] = card

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
        """恢复事件（局部移除卡片，不全量重建）"""
        self._remove_card(event_id)
        if self._on_restore:
            self._on_restore(event_id)

    def _do_hard_delete(self, event_id: int):
        """彻底删除事件（局部移除卡片，不全量重建）"""
        self._remove_card(event_id)
        if self._on_hard_delete:
            self._on_hard_delete(event_id)

    def _remove_card(self, event_id: int):
        """局部移除单张卡片并更新计数"""
        card = self._card_widgets.pop(event_id, None)
        if card:
            card.destroy()
        self._events = [e for e in self._events if e.id != event_id]
        self._title_label.configure(text=f"\ud83d\uddd1 \u56de\u6536\u7ad9 ({len(self._events)})")
        # 如果清空了，显示空状态
        if not self._events:
            for widget in self._scroll_frame.winfo_children():
                widget.destroy()
            ctk.CTkLabel(
                self._scroll_frame,
                text="\u56de\u6536\u7ad9\u4e3a\u7a7a",
                font=ctk.CTkFont(size=12),
                text_color="gray",
            ).pack(pady=30)

    def _do_clear_all(self):
        """一键清空回收站"""
        if self._on_clear_all:
            self._on_clear_all()

    def refresh(self, events: list):
        """刷新事件列表（外部调用时全量重建）"""
        self._card_widgets.clear()
        self._render_events(events)

    def _on_close(self):
        """关闭窗口"""
        self.destroy()
