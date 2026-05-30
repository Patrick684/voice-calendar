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
        """创建事件卡片（风格与主窗口一致）"""
        card = ctk.CTkFrame(self._scroll_frame, corner_radius=8)
        card.pack(fill="x", pady=3)

        # 分类颜色条
        cat_color = CATEGORY_COLORS.get(event.category, "#757575")
        color_bar = ctk.CTkFrame(card, width=4, fg_color=cat_color, corner_radius=2)
        color_bar.pack(side="left", fill="y", padx=(5, 0), pady=3)

        # 内容区
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True)

        # 时间文本
        time_str = "全天" if event.is_all_day else event.start_time.strftime("%H:%M")
        duration_tag = ""
        if not event.is_all_day and event.end_time and event.end_time != event.start_time:
            duration_min = event.duration_minutes
            if duration_min > 0:
                time_str += f"-{event.end_time.strftime('%H:%M')}"
                if duration_min >= 60:
                    h = int(duration_min // 60)
                    m = int(duration_min % 60)
                    duration_tag = f" ({h}h{m}min)" if m else f" ({h}h)"
                else:
                    duration_tag = f" ({int(duration_min)}min)"

        title_text = f"{time_str}{duration_tag}  {event.title}"

        # 优先级标记
        priority_marker = ""
        if event.priority >= 2:
            priority_marker = " ❗"
        elif event.priority == 1:
            priority_marker = " ★"

        ctk.CTkLabel(
            content,
            text=title_text + priority_marker,
            font=ctk.CTkFont(size=12),
            anchor="w",
            wraplength=220,
        ).pack(fill="x", padx=8, pady=(6, 2))

        # 日期行（查询窗口需要显示日期，因为可能跨日）
        date_str = event.start_time.strftime("%m/%d")
        ctk.CTkLabel(
            content,
            text=date_str,
            font=ctk.CTkFont(size=10),
            text_color="#888888",
            anchor="w",
        ).pack(fill="x", padx=8, pady=(0, 2))

        # 描述
        if event.description:
            ctk.CTkLabel(
                content,
                text=event.description,
                font=ctk.CTkFont(size=10),
                text_color="gray",
                anchor="w",
                wraplength=220,
            ).pack(fill="x", padx=8, pady=(0, 4))

        # 分类 + 标签
        info_parts = []
        if event.category:
            info_parts.append(f"[{event.category}]")
        if event.tags:
            info_parts.extend(f"[{t}]" for t in event.tags)
        if info_parts:
            ctk.CTkLabel(
                content,
                text="  ".join(info_parts),
                font=ctk.CTkFont(size=10),
                text_color=cat_color,
                anchor="w",
            ).pack(fill="x", padx=8, pady=(0, 5))

    def _on_close(self):
        """关闭窗口"""
        self.destroy()
