"""查询结果独立展示窗口

语音 query 指令唤起，贴主窗口左侧显示事件卡片列表。
"""

import customtkinter as ctk

from calendar_pkg.event import CalendarEvent


# 分类颜色映射（与主窗口保持一致）
CATEGORY_COLORS = {
    "工作": "#2196F3",
    "健康": "#4CAF50",
    "学习": "#FF9800",
    "生活": "#9C27B0",
    "娱乐": "#E91E63",
    "社交": "#00BCD4",
    "其他": "#757575",
}

WINDOW_WIDTH = 280


class QueryWindow(ctk.CTkToplevel):
    """查询结果展示窗口（贴主窗口左侧）"""

    def __init__(self, master, title: str, events: list):
        super().__init__(master)

        self.title(f"查询: {title}")
        self.resizable(False, True)
        self.attributes("-topmost", True)

        # 设置窗口大小
        master_h = master.winfo_height() or 600
        self.geometry(f"{WINDOW_WIDTH}x{master_h}")

        self._build_ui()
        self.update_results(title, events)

        # 窗口关闭协议
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        """构建窗口 UI 骨架"""
        # 顶部标题
        self._title_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._title_label.pack(padx=10, pady=(12, 6), anchor="w")

        # 事件滚动列表
        self._scroll_frame = ctk.CTkScrollableFrame(self)
        self._scroll_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # 底部关闭按钮
        ctk.CTkButton(
            self,
            text="关闭",
            width=80,
            height=28,
            command=self._on_close,
        ).pack(pady=(0, 10))

    def update_results(self, title: str, events: list):
        """更新窗口内容（支持复用窗口）"""
        self.title(f"查询: {title}")
        self._title_label.configure(text=f"{title} — {len(events)} 个事件")

        # 清空旧内容
        for widget in self._scroll_frame.winfo_children():
            widget.destroy()

        if not events:
            ctk.CTkLabel(
                self._scroll_frame,
                text="暂无事件",
                font=ctk.CTkFont(size=12),
                text_color="gray",
            ).pack(pady=30)
            return

        for event in events:
            self._create_event_card(event)

    def _create_event_card(self, event: CalendarEvent):
        """创建紧凑事件卡片（仅展示时间、标题、类别、优先级）"""
        card = ctk.CTkFrame(self._scroll_frame, corner_radius=6, height=36)
        card.pack(fill="x", pady=2)
        card.pack_propagate(False)

        # 分类颜色条
        cat_color = CATEGORY_COLORS.get(event.category, "#757575")
        ctk.CTkFrame(card, width=4, fg_color=cat_color, corner_radius=2).pack(
            side="left", fill="y", padx=(4, 0), pady=4
        )

        # 时间
        time_str = "全天" if event.is_all_day else event.start_time.strftime("%H:%M")
        ctk.CTkLabel(
            card,
            text=time_str,
            font=ctk.CTkFont(size=11),
            text_color="#888888",
            width=40,
        ).pack(side="left", padx=(6, 4), pady=4)

        # 优先级标记（独立带颜色标签）
        if event.priority >= 2:
            ctk.CTkLabel(
                card,
                text="❗",
                font=ctk.CTkFont(size=12),
                text_color="#e74c3c",
            ).pack(side="left", padx=(2, 0), pady=4)
        elif event.priority == 1:
            ctk.CTkLabel(
                card,
                text="★",
                font=ctk.CTkFont(size=12),
                text_color="#e67e22",
            ).pack(side="left", padx=(2, 0), pady=4)

        # 标题
        title = event.title
        if len(title) > 14:
            title = title[:14] + "..."
        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=12),
            anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=(4, 4), pady=4)

        # 分类标签（右侧）
        if event.category:
            ctk.CTkLabel(
                card,
                text=event.category,
                font=ctk.CTkFont(size=10),
                text_color=cat_color,
            ).pack(side="right", padx=(0, 8), pady=4)

    def _on_close(self):
        """关闭窗口"""
        self.destroy()
