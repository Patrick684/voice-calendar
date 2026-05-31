"""主窗口 - 日历视图 + 事件列表 + 语音面板 + 拖拽排序"""

import calendar as cal_mod
import logging
from collections import deque
from datetime import datetime
from typing import Optional, Callable, List, Dict

import customtkinter as ctk

from calendar_pkg.event import CalendarEvent
from calendar_pkg.manager import CalendarManager
from calendar_pkg.stats import StatsEngine
from calendar_pkg.achievement import AchievementEngine
from ui.voice_panel import VoicePanel, VoiceState
from ui.event_dialog import EventDialog
from ui.stats_view import StatsView
from ui.time_wheel import TimeWheel
from ui.query_window import QueryWindow
from ui.recycle_bin_window import RecycleBinWindow

logger = logging.getLogger(__name__)


class MainWindow(ctk.CTk):
    """语音日历工具主窗口

    布局：
    - 顶部：工具栏（语音按钮、添加事件、设置）
    - 左侧：月历视图
    - 右侧：当日事件列表
    - 底部：语音状态栏
    """

    def __init__(
        self,
        calendar_manager: CalendarManager,
        on_settings: Optional[Callable] = None,
        on_voice_start: Optional[Callable] = None,
        on_voice_stop: Optional[Callable] = None,
        stats_engine: Optional[StatsEngine] = None,
        achievement_engine: Optional[AchievementEngine] = None,
    ):
        """
        初始化主窗口

        Args:
            calendar_manager: 日历管理器实例
            on_settings: 设置按钮回调
            on_voice_start: 开始录音回调
            on_voice_stop: 停止录音回调
        """
        super().__init__()
        self._manager = calendar_manager
        self._on_settings = on_settings
        self._on_voice_start = on_voice_start
        self._on_voice_stop = on_voice_stop
        self._stats_engine = stats_engine
        self._achievement_engine = achievement_engine

        # 当前显示的年月
        self._view_year = datetime.now().year
        self._view_month = datetime.now().month
        self._selected_date = datetime.now()

        # 事件标记日期缓存
        self._event_dates: List[str] = []

        # 按钮录音即时状态标记（避免轮询延迟导致竞态）
        self._is_recording = False

        # 拖拽状态（左键 + 移动阈值）
        self._drag_data: Dict = {
            "event": None,
            "source_date": None,
            "start_x": 0,
            "start_y": 0,
            "dragging": False,
            "long_press_id": None,
        }
        self._day_cells: Dict[str, ctk.CTkButton] = {}  # date_str -> cell widget
        self._ghost = None  # 拖拽时的浮动幽灵卡片
        self._drag_hover_date: Optional[str] = None  # 拖拽悬停的日期
        self._drag_hover_timer = None  # 悬停高亮延迟定时器

        # 撤销栈
        self._undo_stack: deque = deque(maxlen=20)

        # 事件列表排序模式
        self._sort_mode = "time"  # "time" 或 "priority"

        # 当前选中的事件（用于拨盘）
        self._active_event: Optional[CalendarEvent] = None

        # 查询结果窗口引用
        self._query_window: Optional[QueryWindow] = None

        # 回收站窗口引用
        self._recycle_bin_window: Optional[RecycleBinWindow] = None

        # 单击延迟定时器（用于区分单击/双击）
        self._click_open_timer = None

        # 分类颜色（从配置获取，使用默认值）
        self._category_colors: Dict[str, str] = {
            "工作": "#2196F3",
            "健康": "#4CAF50",
            "学习": "#FF9800",
            "生活": "#9C27B0",
            "娱乐": "#E91E63",
            "社交": "#00BCD4",
            "其他": "#757575",
        }

        self._setup_window()
        self._setup_ui()
        self._refresh_calendar()
        self._refresh_event_list()

        # 绑定 Ctrl+Z 撤销
        self.bind("<Control-z>", self._on_undo)

    def _setup_window(self):
        """配置窗口属性"""
        self.title("语音日历工具")
        self.geometry("900x650")
        self.minsize(750, 550)

    def _setup_ui(self):
        """构建 UI 布局"""
        # 顶部工具栏
        self._toolbar = ctk.CTkFrame(self, height=50)
        self._toolbar.pack(fill="x", padx=10, pady=(10, 5))
        self._setup_toolbar()

        # 中间区域（左右分栏）
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="both", expand=True, padx=10, pady=5)
        self._content.grid_columnconfigure(0, weight=3)
        self._content.grid_columnconfigure(1, weight=2)
        self._content.grid_rowconfigure(0, weight=1)

        # 左侧：月历视图
        self._calendar_frame = ctk.CTkFrame(self._content)
        self._calendar_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self._setup_calendar_view()

        # 右侧：事件列表
        self._event_frame = ctk.CTkFrame(self._content)
        self._event_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        self._setup_event_list()

        # 底部：语音面板
        self._voice_panel = VoicePanel(
            self, on_voice_button=self._on_voice_click, on_recycle_bin=self._open_recycle_bin
        )
        self._voice_panel.pack(fill="x", padx=10, pady=(5, 10))

    def _setup_toolbar(self):
        """构建顶部工具栏"""
        # 左侧：月份导航
        self._prev_btn = ctk.CTkButton(
            self._toolbar,
            text="◀",
            width=35,
            command=self._prev_month,
        )
        self._prev_btn.pack(side="left", padx=(10, 5), pady=8)

        self._month_label = ctk.CTkLabel(
            self._toolbar,
            text="",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self._month_label.pack(side="left", padx=5, pady=8)

        self._next_btn = ctk.CTkButton(
            self._toolbar,
            text="▶",
            width=35,
            command=self._next_month,
        )
        self._next_btn.pack(side="left", padx=(5, 10), pady=8)

        self._today_btn = ctk.CTkButton(
            self._toolbar,
            text="今天",
            width=60,
            command=self._go_today,
        )
        self._today_btn.pack(side="left", padx=5, pady=8)

        # 右侧：功能按钮
        ctk.CTkButton(
            self._toolbar,
            text="⚙ 设置",
            width=80,
            command=self._open_settings,
        ).pack(side="right", padx=(5, 10), pady=8)

        if self._stats_engine and self._achievement_engine:
            ctk.CTkButton(
                self._toolbar,
                text="📈 统计",
                width=80,
                command=self._open_stats,
            ).pack(side="right", padx=5, pady=8)

        ctk.CTkButton(
            self._toolbar,
            text="+ 添加事件",
            width=100,
            command=lambda: self._open_event_dialog(),
        ).pack(side="right", padx=5, pady=8)

        # 排序模式切换
        self._sort_btn = ctk.CTkButton(
            self._toolbar,
            text="⏱ 时间排序",
            width=100,
            command=self._toggle_sort_mode,
        )
        self._sort_btn.pack(side="right", padx=5, pady=8)

    def _setup_calendar_view(self):
        """构建月历视图"""
        # 星期标题行
        self._weekday_frame = ctk.CTkFrame(self._calendar_frame, fg_color="transparent")
        self._weekday_frame.pack(fill="x", padx=10, pady=(10, 0))

        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        for i, day_name in enumerate(weekdays):
            ctk.CTkLabel(
                self._weekday_frame,
                text=day_name,
                font=ctk.CTkFont(size=12, weight="bold"),
                width=40,
            ).pack(side="left", expand=True)

        # 日期格子容器
        self._days_frame = ctk.CTkFrame(self._calendar_frame, fg_color="transparent")
        self._days_frame.pack(fill="both", expand=True, padx=10, pady=5)

    def _setup_event_list(self):
        """构建事件列表"""
        # 标题
        self._event_list_label = ctk.CTkLabel(
            self._event_frame,
            text="当日事件",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._event_list_label.pack(padx=10, pady=(10, 5), anchor="w")

        # 优先级关键词提示（仅优先级排序模式下显示）
        self._priority_hint_label = ctk.CTkLabel(
            self._event_frame,
            text='语音关键词:  "紧急" → 高优  |  "重要" → 中优',
            font=ctk.CTkFont(size=11),
            text_color="#888888",
        )
        # 初始隐藏（时间排序模式）
        self._priority_hint_label.pack_forget()

        # 事件滚动列表
        self._event_scroll = ctk.CTkScrollableFrame(self._event_frame)
        self._event_scroll.pack(fill="both", expand=True, padx=10, pady=5)

        # 空状态提示
        self._empty_label = ctk.CTkLabel(
            self._event_scroll,
            text="暂无事件\n\n点击「+ 添加事件」或\n使用语音指令创建",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )

    def _refresh_calendar(self):
        """刷新月历视图"""
        # 更新月份标签
        self._month_label.configure(text=f"{self._view_year}年 {self._view_month}月")

        # 获取有事件的日期
        self._event_dates = self._manager.get_month_event_dates(self._view_year, self._view_month)

        # 清空旧格子
        for widget in self._days_frame.winfo_children():
            widget.destroy()

        # 生成日历格子
        month_cal = cal_mod.monthcalendar(self._view_year, self._view_month)
        today = datetime.now()

        for week_idx, week in enumerate(month_cal):
            for day_idx, day in enumerate(week):
                if day == 0:
                    # 空白格子
                    ctk.CTkLabel(self._days_frame, text="").grid(
                        row=week_idx,
                        column=day_idx,
                        sticky="nsew",
                        padx=1,
                        pady=1,
                    )
                    continue

                date_str = f"{self._view_year:04d}-{self._view_month:02d}-{day:02d}"
                is_today = today.year == self._view_year and today.month == self._view_month and today.day == day
                is_selected = (
                    self._selected_date.year == self._view_year
                    and self._selected_date.month == self._view_month
                    and self._selected_date.day == day
                )
                has_event = date_str in self._event_dates

                self._create_day_cell(
                    week_idx,
                    day_idx,
                    day,
                    date_str,
                    is_today,
                    is_selected,
                    has_event,
                )

            # 配置行权重
            self._days_frame.grid_rowconfigure(week_idx, weight=1)

        # 配置列权重
        for col in range(7):
            self._days_frame.grid_columnconfigure(col, weight=1)

    def _create_day_cell(
        self,
        row,
        col,
        day,
        date_str,
        is_today,
        is_selected,
        has_event,
    ):
        """创建单个日期格子（支持拖拽放置）"""
        bg_color = "#f0f0f0"
        text_color = "#333333"

        if is_selected:
            bg_color = "#3498db"
            text_color = "white"
        elif is_today:
            bg_color = "#2ecc71"
            text_color = "white"

        cell = ctk.CTkButton(
            self._days_frame,
            text=str(day) + (" •" if has_event else ""),
            width=40,
            height=40,
            fg_color=bg_color,
            hover_color="#2980b9",
            text_color=text_color,
            font=ctk.CTkFont(size=13, weight="bold" if is_today else "normal"),
            command=lambda d=date_str: self._on_date_click(d),
        )
        cell.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)

        self._day_cells[date_str] = cell

    # 优先级分组定义：(priority_value, label, color)
    _PRIORITY_GROUPS = [
        (2, "❗ 紧急", "#e74c3c"),
        (1, "★ 重要", "#e67e22"),
        (0, "○ 普通", "#95a5a6"),
    ]

    def _setup_event_list_for_date(self, date_str: str, keep_scroll: bool = False):
        """刷新指定日期的事件列表（支持排序模式）"""
        # 记录当前滚动位置
        scroll_pos = 0.0
        if keep_scroll:
            try:
                scroll_pos = self._event_scroll._parent_canvas.yview()[0]
            except Exception:
                pass

        # 清空旧内容
        for widget in self._event_scroll.winfo_children():
            widget.destroy()

        # 清空分组 widget 引用 和 卡片索引
        self._priority_group_widgets = {}
        self._event_card_widgets = {}

        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return

        events = self._manager.get_events_by_date(date)

        # 排序
        if self._sort_mode == "priority":
            events.sort(key=lambda e: (-e.priority, e.start_time))
        # 默认按时间排序（已由 storage 返回有序列表）

        self._event_list_label.configure(text=f"{date_str} 的事件 ({len(events)})")

        if not events:
            self._empty_label = ctk.CTkLabel(
                self._event_scroll,
                text="暂无事件",
                font=ctk.CTkFont(size=12),
                text_color="gray",
            )
            self._empty_label.pack(pady=20)
            return

        if self._sort_mode == "priority":
            self._render_priority_groups(events)
        else:
            for event in events:
                self._create_event_card(event)

        # 恢复滚动位置（必须在卡片创建后执行）
        if keep_scroll:
            self.after(20, lambda: self._restore_scroll(scroll_pos))
        else:
            try:
                self._event_scroll._parent_canvas.yview_moveto(0)
            except Exception:
                pass

    def _restore_scroll(self, pos: float):
        """延迟恢复滚动位置（等待 canvas 更新 scroll region）"""
        try:
            self._event_scroll._parent_canvas.yview_moveto(pos)
        except Exception:
            pass

    # 卡片高亮动画参数
    _FLASH_COLOR = "#2ecc71"  # 绿色高亮（与今天日期格同色）
    _FLASH_STEPS = [  # (fg_color, delay_ms)
        (_FLASH_COLOR, 200),
        (None, 150),  # None = 恢复默认
        (_FLASH_COLOR, 200),
        (None, 0),
    ]

    def _scroll_to_card(self, event_id: int):
        """滚动事件列表使目标卡片可见"""
        card = self._event_card_widgets.get(event_id)
        if not card or not card.winfo_exists():
            return
        try:
            canvas = self._event_scroll._parent_canvas
            canvas.update_idletasks()
            # 卡片相对于滚动容器内部 frame 的 y 位置
            card_y = card.winfo_y()
            scroll_height = canvas.winfo_height()
            # bbox[3] 是滚动区域总高度
            bbox = canvas.bbox("all")
            if not bbox:
                return
            total_height = bbox[3] - bbox[1]
            if total_height <= scroll_height:
                return  # 内容不超出视口，无需滚动
            # 计算目标位置（卡片置于视口上 1/3 处）
            target_pos = max(0.0, (card_y - scroll_height / 3) / total_height)
            target_pos = min(target_pos, 1.0)
            canvas.yview_moveto(target_pos)
        except Exception:
            pass

    def _flash_card(self, event_id: int):
        """对指定事件卡片执行闪烁高亮动画"""
        # 先滚动到卡片位置
        self._scroll_to_card(event_id)
        card = self._event_card_widgets.get(event_id)
        if not card or not card.winfo_exists():
            return
        # 记录原始颜色
        try:
            original_color = card.cget("fg_color")
        except Exception:
            original_color = ("gray86", "gray17")

        def step(idx):
            if not card.winfo_exists():
                return
            if idx >= len(self._FLASH_STEPS):
                return
            color, delay = self._FLASH_STEPS[idx]
            card.configure(fg_color=color if color else original_color)
            if delay > 0:
                self.after(delay, lambda: step(idx + 1))
            else:
                # 最后一步，确保恢复
                card.configure(fg_color=original_color)

        step(0)

    def _render_priority_groups(self, events):
        """按优先级分组渲染事件列表（含分组标题）"""
        # 将事件按优先级归类
        grouped = {}
        for event in events:
            # priority >= 2 归入紧急，1=重要，0=普通
            level = min(event.priority, 2)
            grouped.setdefault(level, []).append(event)

        for priority_val, label, color in self._PRIORITY_GROUPS:
            group_events = grouped.get(priority_val, [])

            # 分组标题（即使无事件也显示，方便拖入）
            header = ctk.CTkFrame(self._event_scroll, fg_color="transparent", height=28)
            header.pack(fill="x", pady=(8, 2), padx=5)
            header.pack_propagate(False)

            # 左侧色块
            ctk.CTkFrame(header, width=4, fg_color=color, corner_radius=2).pack(side="left", fill="y", padx=(0, 8))

            # 分组文字
            ctk.CTkLabel(
                header,
                text=f"{label} ({len(group_events)})",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=color,
            ).pack(side="left", anchor="w")

            # 记录分组 widget 供拖拽判定使用
            self._priority_group_widgets[priority_val] = header

            # 渲染组内事件卡片
            for event in group_events:
                self._create_event_card(event)

    def _create_event_card(self, event: CalendarEvent):
        """创建事件卡片（紧凑布局 + 描述自适应高度）"""
        card = ctk.CTkFrame(self._event_scroll, corner_radius=2)
        card.pack(fill="x", pady=2)
        # 索引卡片
        if event.id is not None:
            self._event_card_widgets[event.id] = card

        # 无描述时固定高度，有描述时自适应
        if not event.description:
            card.configure(height=36)
            card.pack_propagate(False)

        # 分类颜色条（height=1 避免默认 250px，fill=y 自适应卡片高度）
        cat_color = self._category_colors.get(event.category, "#757575")
        ctk.CTkFrame(card, width=4, height=1, fg_color=cat_color, corner_radius=2).pack(
            side="left", fill="y", padx=(2, 0), pady=2
        )

        # 第一行容器（标题 + 分类在同一行）
        row = ctk.CTkFrame(card, fg_color="transparent", height=18, corner_radius=0)
        if not event.description:
            # 无描述时 expand=True 使 row 垂直居中于 36px 卡片
            row.pack(side="top", fill="x", expand=True)
        else:
            row.pack(side="top", fill="x", pady=(1, 0))
        row.pack_propagate(False)

        # 时间 + 标题 + 优先级
        time_str = "全天" if event.is_all_day else event.start_time.strftime("%H:%M")
        if not event.is_all_day and event.end_time and event.end_time != event.start_time:
            duration_min = event.duration_minutes
            if duration_min > 0:
                time_str += f"-{event.end_time.strftime('%H:%M')}"

        priority_marker = ""
        if event.priority >= 2:
            priority_marker = " ❗"
        elif event.priority == 1:
            priority_marker = " ★"

        title_text = f"{time_str}  {event.title}{priority_marker}"
        ctk.CTkLabel(
            row,
            text=title_text,
            font=ctk.CTkFont(size=14),
            anchor="w",
            height=16,
        ).pack(side="left", padx=(8, 0), fill="y")

        # 分类标签（同行右侧）
        if event.category:
            ctk.CTkLabel(
                row,
                text=event.category,
                font=ctk.CTkFont(size=12),
                text_color=cat_color,
                height=16,
            ).pack(side="right", padx=(0, 8), fill="y")

        # 描述行（有描述时显示，单行紧凑/多行自动扩展）
        if event.description:
            ctk.CTkLabel(
                card,
                text=event.description,
                font=ctk.CTkFont(size=12),
                text_color="#888888",
                anchor="w",
                wraplength=240,
            ).pack(side="top", fill="x", padx=(14, 0), pady=(0, 1))

        # 右键菜单（快捷编辑）
        if event.id is not None:
            self._bind_context_menu(card, event)
            for child in card.winfo_children():
                self._bind_context_menu(child, event)
                for grandchild in child.winfo_children():
                    self._bind_context_menu(grandchild, event)

        # 左键拖拽 + 双击描述（仅真实事件）
        if event.id is not None:
            self._bind_drag_events(card, event)
            self._bind_double_click(card, event)
            for child in card.winfo_children():
                self._bind_drag_events(child, event)
                self._bind_double_click(child, event)
                for grandchild in child.winfo_children():
                    self._bind_drag_events(grandchild, event)
                    self._bind_double_click(grandchild, event)
        else:
            # 虚拟循环实例只能点击编辑
            card.bind("<Button-1>", lambda e, ev=event: self._open_event_dialog(ev))
            for child in card.winfo_children():
                child.bind("<Button-1>", lambda e, ev=event: self._open_event_dialog(ev))
                for grandchild in child.winfo_children():
                    grandchild.bind("<Button-1>", lambda e, ev=event: self._open_event_dialog(ev))

    def _bind_drag_events(self, widget, event: CalendarEvent):
        """绑定左键拖拽事件（带移动阈值）"""
        widget.bind("<ButtonPress-1>", lambda e, ev=event: self._on_press(e, ev))

    def _bind_double_click(self, widget, event: CalendarEvent):
        """绑定双击事件（添加/编辑描述）"""
        widget.bind("<Double-Button-1>", lambda e, ev=event: self._on_double_click_desc(ev))

    def _on_double_click_desc(self, cal_event: CalendarEvent):
        """双击卡片 — 弹出描述输入框"""
        # 取消单击延迟开编辑对话框
        if hasattr(self, "_click_open_timer") and self._click_open_timer:
            self.after_cancel(self._click_open_timer)
            self._click_open_timer = None

        dialog = ctk.CTkInputDialog(
            text=f"为「{cal_event.title}」修改描述：",
            title="修改描述",
        )
        # 预填充已有描述（_entry 是延迟创建的，需等 widget 就绪）
        if cal_event.description:
            dialog.after(200, lambda: dialog._entry.insert(0, cal_event.description))

        result = dialog.get_input()
        if result is not None:
            # 空字符串表示清空描述
            desc = result.strip() if result.strip() else None
            self._manager.update_event(cal_event.id, description=desc)
            logger.info(f"描述更新: {cal_event.title} → {desc}")
            self._setup_event_list_for_date(cal_event.start_time.strftime("%Y-%m-%d"), keep_scroll=True)

    def _bind_context_menu(self, widget, event: CalendarEvent):
        """绑定右键菜单"""
        widget.bind("<Button-3>", lambda e, ev=event: self._show_context_menu(e, ev))

    def _show_context_menu(self, event, cal_event: CalendarEvent):
        """显示右键快捷编辑菜单"""
        import tkinter as tk

        menu = tk.Menu(self, tearoff=0)

        # 优先级子菜单
        priority_menu = tk.Menu(menu, tearoff=0)
        priority_labels = [("普通", 0), ("★ 重要", 1), ("❗ 紧急", 2), ("❗❗ 最高", 3)]
        for label, level in priority_labels:
            marker = "✓ " if cal_event.priority == level else "   "
            priority_menu.add_command(
                label=marker + label,
                command=lambda e=cal_event, p=level: self._quick_set_priority(e, p),
            )
        menu.add_cascade(label="优先级", menu=priority_menu)

        # 分类子菜单
        category_menu = tk.Menu(menu, tearoff=0)
        categories = ["工作", "健康", "学习", "生活", "娱乐", "社交", "其他"]
        for cat in categories:
            marker = "✓ " if cal_event.category == cat else "   "
            category_menu.add_command(
                label=marker + cat,
                command=lambda e=cal_event, c=cat: self._quick_set_category(e, c),
            )
        menu.add_cascade(label="分类", menu=category_menu)

        menu.add_separator()
        menu.add_command(label="编辑详情...", command=lambda: self._open_event_dialog(cal_event))
        menu.add_command(
            label="删除",
            command=lambda: self._quick_delete(cal_event),
        )

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _quick_set_priority(self, cal_event: CalendarEvent, priority: int):
        """快捷设置优先级"""
        if cal_event.id is None:
            return
        self._manager.update_event(cal_event.id, priority=priority)
        logger.info(f"快捷设置优先级: {cal_event.title} → {priority}")
        self._setup_event_list_for_date(cal_event.start_time.strftime("%Y-%m-%d"), keep_scroll=True)

    def _quick_set_category(self, cal_event: CalendarEvent, category: str):
        """快捷设置分类"""
        if cal_event.id is None:
            return
        self._manager.update_event(cal_event.id, category=category)
        logger.info(f"快捷设置分类: {cal_event.title} → {category}")
        self._setup_event_list_for_date(cal_event.start_time.strftime("%Y-%m-%d"), keep_scroll=True)

    def _quick_delete(self, cal_event: CalendarEvent):
        """快捷删除事件"""
        if cal_event.id is None:
            return
        self._manager.delete_event(cal_event.id)
        logger.info(f"快捷删除: {cal_event.title}")
        self._setup_event_list_for_date(cal_event.start_time.strftime("%Y-%m-%d"), keep_scroll=True)
        self._refresh_calendar()

    # ================================================================
    # 拖拽排序（左键 + 移动阈值 + 浮动幽灵卡片）
    # ================================================================

    _DRAG_THRESHOLD = 5  # 像素阈值，超过才算拖拽
    _GHOST_NORMAL_SIZE = (200, 55)  # 幽灵卡片正常大小
    _GHOST_SHRINK_SIZE = (140, 38)  # 缩小后大小

    def _on_press(self, event, cal_event: CalendarEvent):
        """左键按下 - 记录起始位置，绑定全局拖拽事件，启动长按定时器"""
        self._drag_data = {
            "event": cal_event,
            "source_date": cal_event.start_time.strftime("%Y-%m-%d"),
            "start_x": event.x_root,
            "start_y": event.y_root,
            "dragging": False,
            "long_press_id": None,
        }
        # 启动长按定时器（500ms）
        self._drag_data["long_press_id"] = self.after(500, lambda: self._on_long_press(event, cal_event))
        # 绑定全局事件（确保在离开原始 widget 后仍能捕获运动和释放）
        self._drag_motion_id = self.bind_all("<B1-Motion>", self._on_motion, add="+")
        self._drag_release_id = self.bind_all("<ButtonRelease-1>", self._on_global_release, add="+")

    def _on_motion(self, event):
        """左键拖拽中 - 超过阈值进入拖拽模式，创建幽灵卡片跟随鼠标"""
        if self._drag_data.get("event") is None:
            return
        if not self._drag_data["dragging"]:
            dx = abs(event.x_root - self._drag_data["start_x"])
            dy = abs(event.y_root - self._drag_data["start_y"])
            if dx + dy < self._DRAG_THRESHOLD:
                return
            # 取消长按定时器
            if self._drag_data.get("long_press_id"):
                self.after_cancel(self._drag_data["long_press_id"])
                self._drag_data["long_press_id"] = None
            # 进入拖拽模式
            self._drag_data["dragging"] = True
            source_cell = self._day_cells.get(self._drag_data["source_date"])
            if source_cell:
                source_cell.configure(fg_color="#e67e22")
            # 创建幽灵卡片
            self._create_drag_ghost(self._drag_data["event"], event.x_root, event.y_root)
        else:
            # 拖拽进行中：更新幽灵卡片位置
            if hasattr(self, "_ghost") and self._ghost:
                self._ghost.geometry(f"+{event.x_root + 12}+{event.y_root + 12}")
                # 检测是否在事件卡片区域外（靠近日历区域时缩小）
                if self._is_outside_card_area(event):
                    w, h = self._GHOST_SHRINK_SIZE
                else:
                    w, h = self._GHOST_NORMAL_SIZE
                self._ghost.geometry(f"{w}x{h}+{event.x_root + 12}+{event.y_root + 12}")
            # 主动检测鼠标悬停的日期格子（<Enter>/<Leave> 在全局拖拽时不触发）
            self._detect_drag_hover(event)
            # 优先级排序模式下检测分组悬停高亮
            self._detect_priority_group_hover(event)

    def _on_global_release(self, event):
        """全局释放处理（先解绑全局事件，再判断放置目标）"""
        # 解绑全局事件
        try:
            self.unbind_all("<B1-Motion>")
            self.unbind_all("<ButtonRelease-1>")
        except Exception:
            pass

        if not self._drag_data.get("event"):
            return

        # 取消长按定时器
        if self._drag_data.get("long_press_id"):
            self.after_cancel(self._drag_data["long_press_id"])
            self._drag_data["long_press_id"] = None

        # 如果长按已经触发了时间滚轮，直接清理状态
        if self._drag_data.get("long_press_fired"):
            self._drag_data = {
                "event": None,
                "source_date": None,
                "start_x": 0,
                "start_y": 0,
                "dragging": False,
                "long_press_id": None,
            }
            return

        cal_event = self._drag_data["event"]

        if self._drag_data.get("dragging"):
            # 销毁幽灵卡片
            self._destroy_drag_ghost()
            # 清除悬停高亮
            self._clear_drag_hover()
            # 清除优先级分组高亮
            self._clear_priority_hover()

            # 优先级排序模式下：检查是否释放在事件列表区域（调整优先级）
            if self._sort_mode == "priority" and self._try_priority_drop(event, cal_event):
                self._drag_data = {
                    "event": None,
                    "source_date": None,
                    "start_x": 0,
                    "start_y": 0,
                    "dragging": False,
                    "long_press_id": None,
                }
                return

            # 拖拽模式：检查释放位置是否在日期格子上
            dropped = False
            for date_str, cell in self._day_cells.items():
                try:
                    cell.update_idletasks()
                    x1 = cell.winfo_rootx()
                    y1 = cell.winfo_rooty()
                    x2 = x1 + cell.winfo_width()
                    y2 = y1 + cell.winfo_height()
                    if x1 <= event.x_root <= x2 and y1 <= event.y_root <= y2:
                        self._on_drag_drop(date_str)
                        dropped = True
                        break
                except Exception:
                    continue

            if not dropped:
                # 没有放在日期格子上，撤销拖拽状态
                self._refresh_calendar()

            self._drag_data = {
                "event": None,
                "source_date": None,
                "start_x": 0,
                "start_y": 0,
                "dragging": False,
                "long_press_id": None,
            }
        else:
            # 点击模式（非拖拽、非长按）- 延迟打开编辑对话框（给双击时间取消）
            self._drag_data = {
                "event": None,
                "source_date": None,
                "start_x": 0,
                "start_y": 0,
                "dragging": False,
                "long_press_id": None,
            }
            self._click_open_timer = self.after(300, lambda ev=cal_event: self._open_event_dialog(ev))

    def _create_drag_ghost(self, cal_event: CalendarEvent, x: int, y: int):
        """创建跟随鼠标的浮动幽灵卡片"""
        import tkinter as tk

        self._ghost = tk.Toplevel(self)
        self._ghost.overrideredirect(True)
        self._ghost.attributes("-alpha", 0.85)
        self._ghost.attributes("-topmost", True)
        w, h = self._GHOST_NORMAL_SIZE
        self._ghost.geometry(f"{w}x{h}+{x + 12}+{y + 12}")
        self._ghost.configure(bg="#34495e", highlightthickness=0, bd=0)

        # 简化卡片内容
        time_str = "全天" if cal_event.is_all_day else cal_event.start_time.strftime("%H:%M")
        title = cal_event.title
        if len(title) > 12:
            title = title[:12] + "..."

        frame = tk.Frame(self._ghost, bg="#34495e", padx=8, pady=6, highlightthickness=0, bd=0)
        frame.pack(fill="both", expand=True)

        # 分类颜色条
        cat_color = self._category_colors.get(cal_event.category, "#757575")
        tk.Frame(frame, bg=cat_color, width=3, highlightthickness=0, bd=0).pack(side="left", fill="y", padx=(0, 6))

        # 文字内容
        text_frame = tk.Frame(frame, bg="#34495e", highlightthickness=0, bd=0)
        text_frame.pack(side="left", fill="both", expand=True)
        tk.Label(
            text_frame,
            text=f"{time_str}  {title}",
            bg="#34495e",
            fg="white",
            font=("Microsoft YaHei UI", 10),
            anchor="w",
            highlightthickness=0,
            bd=0,
        ).pack(anchor="w")
        tk.Label(
            text_frame,
            text="拖拽到目标日期释放",
            bg="#34495e",
            fg="#95a5a6",
            font=("Microsoft YaHei UI", 8),
            anchor="w",
            highlightthickness=0,
            bd=0,
        ).pack(anchor="w")

    def _destroy_drag_ghost(self):
        """销毁幽灵卡片"""
        if hasattr(self, "_ghost") and self._ghost:
            try:
                self._ghost.destroy()
            except Exception:
                pass
            self._ghost = None

    def _is_outside_card_area(self, event) -> bool:
        """检测鼠标是否在事件卡片区域外（靠近日历区域时返回 True）"""
        try:
            # 事件列表区域的屏幕坐标
            self._event_frame.update_idletasks()
            ef_x1 = self._event_frame.winfo_rootx()
            ef_x2 = ef_x1 + self._event_frame.winfo_width()
            ef_y1 = self._event_frame.winfo_rooty()
            ef_y2 = ef_y1 + self._event_frame.winfo_height()
            # 鼠标不在事件列表区域内
            return not (ef_x1 <= event.x_root <= ef_x2 and ef_y1 <= event.y_root <= ef_y2)
        except Exception:
            return False

    def _detect_drag_hover(self, event):
        """主动检测拖拽时鼠标悬停的日期格子（替代 <Enter>/<Leave>）

        停留 150ms 后高亮目标日期格子，离开时恢复。
        """
        if not self._drag_data.get("dragging"):
            return

        # 遍历日期格子，检测鼠标在哪个格子上
        hovered_date = None
        for date_str, cell in self._day_cells.items():
            try:
                x1 = cell.winfo_rootx()
                y1 = cell.winfo_rooty()
                x2 = x1 + cell.winfo_width()
                y2 = y1 + cell.winfo_height()
                if x1 <= event.x_root <= x2 and y1 <= event.y_root <= y2:
                    hovered_date = date_str
                    break
            except Exception:
                continue

        # 跳过源日期
        if hovered_date == self._drag_data.get("source_date"):
            hovered_date = None

        # 与上一次悬停位置比较
        if hovered_date == self._drag_hover_date:
            return  # 没变化，无需处理

        # 离开旧格子 → 恢复颜色
        if self._drag_hover_date:
            self._restore_cell_color(self._drag_hover_date)
            # 取消尚未触发的高亮定时器
            if self._drag_hover_timer:
                self.after_cancel(self._drag_hover_timer)
                self._drag_hover_timer = None

        # 进入新格子 → 延迟 150ms 后高亮
        self._drag_hover_date = hovered_date
        if hovered_date:
            self._drag_hover_timer = self.after(150, lambda ds=hovered_date: self._highlight_hover_cell(ds))

    def _highlight_hover_cell(self, date_str: str):
        """延迟后高亮悬停的目标日期格子"""
        # 再次确认仍在拖拽中且悬停位置没变
        if not self._drag_data.get("dragging"):
            return
        if self._drag_hover_date != date_str:
            return
        cell = self._day_cells.get(date_str)
        if cell:
            cell.configure(fg_color="#3498db", text_color="white")

    def _restore_cell_color(self, date_str: str):
        """恢复单个日期格子的原始颜色"""
        cell = self._day_cells.get(date_str)
        if not cell:
            return
        today = datetime.now()
        try:
            day_num = int(date_str.split("-")[2])
        except (IndexError, ValueError):
            day_num = 0
        is_today = today.year == self._view_year and today.month == self._view_month and today.day == day_num
        is_selected = self._selected_date.strftime("%Y-%m-%d") == date_str
        if is_selected:
            bg = "#3498db"
            fg = "white"
        elif is_today:
            bg = "#2ecc71"
            fg = "white"
        else:
            bg = "#f0f0f0"
            fg = "#333333"
        cell.configure(fg_color=bg, text_color=fg)

    def _clear_drag_hover(self):
        """清除拖拽悬停状态"""
        if self._drag_hover_timer:
            self.after_cancel(self._drag_hover_timer)
            self._drag_hover_timer = None
        if self._drag_hover_date:
            self._restore_cell_color(self._drag_hover_date)
            self._drag_hover_date = None

    # ================================================================
    # 优先级拖拽调整
    # ================================================================

    def _try_priority_drop(self, event, cal_event: CalendarEvent) -> bool:
        """尝试将卡片释放到优先级分组区域，成功则修改优先级并返回 True"""
        if not hasattr(self, "_priority_group_widgets") or not self._priority_group_widgets:
            return False

        # 检测释放坐标落在哪个分组标题所属区域
        target_priority = self._detect_priority_group_at(event.x_root, event.y_root)
        if target_priority is None:
            return False

        # 与当前优先级相同则不修改
        current_level = min(cal_event.priority, 2)
        if target_priority == current_level:
            return False

        # 记录撤销
        self._undo_stack.append(
            {
                "event_id": cal_event.id,
                "old_start": cal_event.start_time,
                "old_end": cal_event.end_time,
                "old_priority": cal_event.priority,
            }
        )

        # 更新优先级
        self._manager.update_event(cal_event.id, priority=target_priority)
        logger.info(f"优先级调整: {cal_event.title} {current_level} -> {target_priority}")

        # 刷新视图
        self.navigate_to_date(cal_event.start_time)
        return True

    def _detect_priority_group_at(self, root_x: int, root_y: int):
        """根据绝对坐标判断落在哪个优先级分组区域内

        分组区域定义：每个分组标题到下一个分组标题之间的区域属于该组。
        """
        if not hasattr(self, "_priority_group_widgets") or not self._priority_group_widgets:
            return None

        # 先检查是否在事件列表滚动区域内
        try:
            scroll_x = self._event_scroll.winfo_rootx()
            scroll_y = self._event_scroll.winfo_rooty()
            scroll_x2 = scroll_x + self._event_scroll.winfo_width()
            scroll_y2 = scroll_y + self._event_scroll.winfo_height()
            if not (scroll_x <= root_x <= scroll_x2 and scroll_y <= root_y <= scroll_y2):
                return None
        except Exception:
            return None

        # 根据 y 坐标确定所属分组
        # 各分组标题的 y 坐标（从上到下：紧急 → 重要 → 普通）
        group_positions = []
        for priority_val, header in self._priority_group_widgets.items():
            try:
                hy = header.winfo_rooty()
                group_positions.append((hy, priority_val))
            except Exception:
                continue

        if not group_positions:
            return None

        # 按 y 坐标排序
        group_positions.sort(key=lambda x: x[0])

        # 找到释放点落在哪两个标题之间
        target = group_positions[-1][1]  # 默认最后一组
        for i, (gy, pv) in enumerate(group_positions):
            if root_y < gy:
                # 在第一个标题上方 → 归入第一组
                target = group_positions[max(0, i - 1)][1] if i > 0 else group_positions[0][1]
                break
            target = pv

        return target

    def _detect_priority_group_hover(self, event):
        """拖拽期间检测鼠标悬停的优先级分组并高亮"""
        if self._sort_mode != "priority":
            return
        if not hasattr(self, "_priority_group_widgets") or not self._priority_group_widgets:
            return

        hovered = self._detect_priority_group_at(event.x_root, event.y_root)

        # 与上次相同则不处理
        prev = getattr(self, "_priority_hover_group", None)
        if hovered == prev:
            return

        # 恢复上一个高亮
        if prev is not None and prev in self._priority_group_widgets:
            self._priority_group_widgets[prev].configure(fg_color="transparent")

        self._priority_hover_group = hovered

        # 高亮新的分组标题
        if hovered is not None and hovered in self._priority_group_widgets:
            # 用分组对应颜色的浅色版本作为高亮背景
            color_map = {2: "#fadbd8", 1: "#fdebd0", 0: "#eaeded"}
            self._priority_group_widgets[hovered].configure(fg_color=color_map.get(hovered, "#eaeded"))

    def _clear_priority_hover(self):
        """清除优先级分组悬停高亮"""
        prev = getattr(self, "_priority_hover_group", None)
        if prev is not None and hasattr(self, "_priority_group_widgets"):
            if prev in self._priority_group_widgets:
                self._priority_group_widgets[prev].configure(fg_color="transparent")
        self._priority_hover_group = None

    def _on_drag_drop(self, target_date_str: str):
        """拖拽放置到目标日期（含高亮确认动画）"""
        if not self._drag_data.get("dragging"):
            return

        cal_event = self._drag_data.get("event")
        if cal_event is None or cal_event.id is None:
            return

        source_date_str = self._drag_data["source_date"]
        if source_date_str == target_date_str:
            self._refresh_calendar()
            return

        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
            new_start = cal_event.start_time.replace(
                year=target_date.year,
                month=target_date.month,
                day=target_date.day,
            )
            new_end = None
            if cal_event.end_time:
                new_end = cal_event.end_time.replace(
                    year=target_date.year,
                    month=target_date.month,
                    day=target_date.day,
                )

            # 记录撤销信息
            self._undo_stack.append(
                {
                    "event_id": cal_event.id,
                    "old_start": cal_event.start_time,
                    "old_end": cal_event.end_time,
                }
            )

            self._manager.update_event(
                cal_event.id,
                start_time=new_start,
                end_time=new_end,
            )
            logger.info(f"拖拽移动: {cal_event.title} {source_date_str} -> {target_date_str}")
        except Exception as e:
            logger.error(f"拖拽失败: {e}")

        self._drag_data = {
            "event": None,
            "source_date": None,
            "start_x": 0,
            "start_y": 0,
            "dragging": False,
            "long_press_id": None,
        }

        # 导航到目标日期 + 高亮确认动画（金色闪烁 800ms）
        self.navigate_to_date(target_date)
        cell = self._day_cells.get(target_date_str)
        if cell:
            cell.configure(fg_color="#f1c40f", text_color="#2c3e50")
            self.after(800, self._refresh_calendar)

    def _toggle_sort_mode(self):
        """切换排序模式"""
        if self._sort_mode == "time":
            self._sort_mode = "priority"
            self._sort_btn.configure(text="★ 优先级排序")
            self._priority_hint_label.pack(
                padx=10,
                pady=(0, 5),
                anchor="w",
                after=self._event_list_label,
            )
        else:
            self._sort_mode = "time"
            self._sort_btn.configure(text="⏱ 时间排序")
            self._priority_hint_label.pack_forget()
        self._refresh_event_list()

    def _on_undo(self, event=None):
        """Ctrl+Z 撤销上次拖拽/拨盘/优先级调整"""
        if not self._undo_stack:
            return
        action = self._undo_stack.pop()
        try:
            update_kwargs = {
                "start_time": action["old_start"],
                "end_time": action.get("old_end"),
            }
            if "old_priority" in action:
                update_kwargs["priority"] = action["old_priority"]
            self._manager.update_event(action["event_id"], **update_kwargs)
            logger.info(f"撤销: event_id={action['event_id']}")
            self._refresh_calendar()
            self._refresh_event_list()
        except Exception as e:
            logger.error(f"撤销失败: {e}")

    # ================================================================
    # 长按时间调整（纵向滚轮弹窗）
    # ================================================================

    def _on_long_press(self, event, cal_event: CalendarEvent):
        """长按触发 - 弹出时间滚轮小窗"""
        # 确认仍在按下状态（未进入拖拽、未释放）
        if self._drag_data.get("dragging"):
            return
        if self._drag_data.get("event") != cal_event:
            return

        # 清除长按标记（避免释放时重复处理）
        self._drag_data["long_press_id"] = None
        self._drag_data["long_press_fired"] = True

        # 解绑全局事件（长按已触发，不再需要拖拽/释放检测）
        try:
            self.unbind_all("<B1-Motion>")
            self.unbind_all("<ButtonRelease-1>")
        except Exception:
            pass

        # 仅非全天事件可调整时间
        if cal_event.is_all_day or cal_event.id is None:
            return

        # 弹出时间滚轮
        self._active_event = cal_event
        hour = cal_event.start_time.hour
        minute = cal_event.start_time.minute

        # 定位在鼠标附近
        x = event.x_root + 15
        y = event.y_root + 15

        TimeWheel(
            self,
            hour=hour,
            minute=minute,
            on_time_confirm=self._on_time_wheel_confirm,
            x=x,
            y=y,
        )

    def _on_time_wheel_confirm(self, hour: int, minute: int):
        """时间滚轮确认回调"""
        if self._active_event is None or self._active_event.id is None:
            return

        old_start = self._active_event.start_time
        new_start = old_start.replace(hour=hour, minute=minute, second=0, microsecond=0)

        new_end = None
        if self._active_event.end_time:
            # 保持时长不变
            duration = self._active_event.end_time - old_start
            new_end = new_start + duration

        # 记录撤销
        self._undo_stack.append(
            {
                "event_id": self._active_event.id,
                "old_start": old_start,
                "old_end": self._active_event.end_time,
            }
        )

        self._manager.update_event(
            self._active_event.id,
            start_time=new_start,
            end_time=new_end,
        )
        logger.info(f"时间滚轮调整: {self._active_event.title} → {hour:02d}:{minute:02d}")
        # 导航到事件所在日期（刷新视图显示更新后的时间）
        self.navigate_to_date(new_start)
        self._active_event = None

    # ================================================================
    # 事件处理
    # ================================================================

    def _on_date_click(self, date_str: str):
        """日期格子点击"""
        try:
            self._selected_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return
        self._refresh_calendar()
        self._setup_event_list_for_date(date_str)

    def _prev_month(self):
        """上一个月"""
        if self._view_month == 1:
            self._view_month = 12
            self._view_year -= 1
        else:
            self._view_month -= 1
        self._refresh_calendar()

    def _next_month(self):
        """下一个月"""
        if self._view_month == 12:
            self._view_month = 1
            self._view_year += 1
        else:
            self._view_month += 1
        self._refresh_calendar()

    def _go_today(self):
        """跳转今天"""
        today = datetime.now()
        self._view_year = today.year
        self._view_month = today.month
        self._selected_date = today
        self._refresh_calendar()
        self._setup_event_list_for_date(today.strftime("%Y-%m-%d"))

    def _open_settings(self):
        """打开设置"""
        if self._on_settings:
            self._on_settings()

    def _open_stats(self):
        """打开统计与成就视图"""
        if self._stats_engine and self._achievement_engine:
            StatsView(
                self,
                stats_engine=self._stats_engine,
                achievement_engine=self._achievement_engine,
            )

    def _open_event_dialog(self, event: Optional[CalendarEvent] = None):
        """打开事件编辑对话框"""

        def on_save(data: dict):
            if event and event.id:
                # 编辑模式
                self._manager.update_event(event.id, **data)
                logger.info(f"事件已更新: {data['title']}")
                target_date = data.get("start_time")
                if target_date:
                    self.navigate_to_date(target_date, highlight_event_id=event.id)
                else:
                    self._refresh_calendar()
                    self._refresh_event_list()
            else:
                # 添加模式
                new_event = self._manager.add_event(**data)
                logger.info(f"事件已添加: {data['title']}")
                # 导航到事件所在日期并高亮卡片
                target_date = data.get("start_time")
                if target_date:
                    self.navigate_to_date(target_date, highlight_event_id=new_event.id)
                else:
                    self._refresh_calendar()
                    self._refresh_event_list()

        def on_delete(event_id: int):
            title = self._manager.delete_event(event_id)
            if title:
                logger.info(f"事件已删除: {title}")
            self._refresh_calendar()
            self._refresh_event_list()

        EventDialog(
            self,
            event=event,
            on_save=on_save,
            on_delete=on_delete,
            default_date=self._selected_date,
        )

    def _on_voice_click(self):
        """语音按钮点击 - 切换录音/停止（使用即时标记避免轮询竞态）"""
        if self._is_recording:
            self._is_recording = False
            if self._on_voice_stop:
                self._on_voice_stop()
        else:
            self._is_recording = True
            if self._on_voice_start:
                self._on_voice_start()

    def _refresh_event_list(self):
        """刷新当前选中日期的事件列表"""
        date_str = self._selected_date.strftime("%Y-%m-%d")
        self._setup_event_list_for_date(date_str)

    # ================================================================
    # 外部接口
    # ================================================================

    def set_voice_state(self, state: VoiceState, message: str = ""):
        """更新语音面板状态，同步录音标记"""
        if state == VoiceState.RECORDING:
            self._is_recording = True
        elif state in (VoiceState.IDLE, VoiceState.SUCCESS, VoiceState.ERROR):
            self._is_recording = False
        self._voice_panel.set_state(state, message)

    def show_voice_result(self, text: str):
        """显示语音识别结果"""
        self._voice_panel.set_result(text)

    def navigate_to_date(self, target_date: datetime, highlight_event_id: int = None):
        """导航到指定日期并刷新视图（公共接口）

        自动切换年月、选中目标日期、刷新日历和事件列表。
        可选高亮指定事件卡片。
        """
        self._view_year = target_date.year
        self._view_month = target_date.month
        self._selected_date = target_date
        self._refresh_calendar()
        self._refresh_event_list()
        # 延迟高亮目标卡片（等待卡片渲染完成）
        if highlight_event_id is not None:
            self.after(30, lambda: self._flash_card(highlight_event_id))

    def refresh_all(self):
        """刷新所有视图"""
        self._refresh_calendar()
        self._refresh_event_list()

    def show_query_window(self, title: str, events: list):
        """打开或复用查询结果窗口（贴主窗口左侧）"""
        if self._query_window and self._query_window.winfo_exists():
            self._query_window.update_results(title, events)
            self._query_window.focus()
        else:
            self._query_window = QueryWindow(self, title, events)
        # 定位到主窗口左侧贴边
        self._position_query_window()

    def _position_query_window(self):
        """将查询窗口定位到主窗口左侧贴边"""
        if not self._query_window or not self._query_window.winfo_exists():
            return
        self.update_idletasks()
        x = self.winfo_x() - 290
        y = self.winfo_y()
        h = self.winfo_height()
        # 防止窗口跑到屏幕外
        if x < 0:
            x = 0
        self._query_window.geometry(f"280x{h}+{x}+{y}")

    # ================================================================
    # 回收站
    # ================================================================

    def _open_recycle_bin(self):
        """打开回收站窗口"""
        events = self._manager.get_deleted_events()
        if self._recycle_bin_window and self._recycle_bin_window.winfo_exists():
            self._recycle_bin_window.refresh(events)
            self._recycle_bin_window.focus()
        else:
            self._recycle_bin_window = RecycleBinWindow(
                self,
                events,
                on_restore=self._on_restore_event,
                on_hard_delete=self._on_hard_delete_event,
                on_clear_all=self._on_clear_all_deleted,
            )

    def _on_restore_event(self, event_id: int):
        """恢复已删除事件并导航到该事件日期"""
        self._manager.restore_event(event_id)
        logger.info(f"回收站恢复事件: id={event_id}")
        # 导航到恢复事件所在日期并高亮卡片
        event = self._manager.get_event(event_id)
        if event:
            self.navigate_to_date(event.start_time, highlight_event_id=event_id)
        else:
            self._refresh_calendar()
            self._refresh_event_list()

    def _on_hard_delete_event(self, event_id: int):
        """彻底删除事件"""
        self._manager.hard_delete_event(event_id)
        logger.info(f"回收站彻底删除: id={event_id}")

    def _on_clear_all_deleted(self):
        """一键清空回收站"""
        count = self._manager.clear_all_deleted()
        logger.info(f"回收站一键清空: {count} 条")
        if self._recycle_bin_window and self._recycle_bin_window.winfo_exists():
            self._recycle_bin_window.refresh([])

    def show_reminder(self, event: CalendarEvent):
        """显示事件提醒弹窗"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("事件提醒")
        dialog.geometry("350x150")
        dialog.attributes("-topmost", True)

        time_str = event.start_time.strftime("%H:%M")
        ctk.CTkLabel(
            dialog,
            text=f"⏰ 提醒: {event.title}",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=(15, 5))
        ctk.CTkLabel(
            dialog,
            text=f"时间: {time_str}",
            font=ctk.CTkFont(size=13),
        ).pack()
        ctk.CTkButton(
            dialog,
            text="知道了",
            width=80,
            command=dialog.destroy,
        ).pack(pady=15)
