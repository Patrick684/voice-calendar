"""主窗口 - 日历视图 + 事件列表 + 语音面板"""

import calendar as cal_mod
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, List

import customtkinter as ctk

from calendar.event import CalendarEvent
from calendar.manager import CalendarManager
from ui.voice_panel import VoicePanel, VoiceState
from ui.event_dialog import EventDialog

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

        # 当前显示的年月
        self._view_year = datetime.now().year
        self._view_month = datetime.now().month
        self._selected_date = datetime.now()

        # 事件标记日期缓存
        self._event_dates: List[str] = []

        self._setup_window()
        self._setup_ui()
        self._refresh_calendar()
        self._refresh_event_list()

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
            self, on_voice_button=self._on_voice_click
        )
        self._voice_panel.pack(fill="x", padx=10, pady=(5, 10))

    def _setup_toolbar(self):
        """构建顶部工具栏"""
        # 左侧：月份导航
        self._prev_btn = ctk.CTkButton(
            self._toolbar, text="◀", width=35,
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
            self._toolbar, text="▶", width=35,
            command=self._next_month,
        )
        self._next_btn.pack(side="left", padx=(5, 10), pady=8)

        self._today_btn = ctk.CTkButton(
            self._toolbar, text="今天", width=60,
            command=self._go_today,
        )
        self._today_btn.pack(side="left", padx=5, pady=8)

        # 右侧：功能按钮
        ctk.CTkButton(
            self._toolbar, text="⚙ 设置", width=80,
            command=self._open_settings,
        ).pack(side="right", padx=(5, 10), pady=8)

        ctk.CTkButton(
            self._toolbar, text="+ 添加事件", width=100,
            command=lambda: self._open_event_dialog(),
        ).pack(side="right", padx=5, pady=8)

    def _setup_calendar_view(self):
        """构建月历视图"""
        # 星期标题行
        self._weekday_frame = ctk.CTkFrame(self._calendar_frame, fg_color="transparent")
        self._weekday_frame.pack(fill="x", padx=10, pady=(10, 0))

        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        for i, day_name in enumerate(weekdays):
            ctk.CTkLabel(
                self._weekday_frame, text=day_name,
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
            self._event_frame, text="当日事件",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._event_list_label.pack(padx=10, pady=(10, 5), anchor="w")

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
        self._month_label.configure(
            text=f"{self._view_year}年 {self._view_month}月"
        )

        # 获取有事件的日期
        self._event_dates = self._manager.get_month_event_dates(
            self._view_year, self._view_month
        )

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
                        row=week_idx, column=day_idx, sticky="nsew",
                        padx=1, pady=1,
                    )
                    continue

                date_str = f"{self._view_year:04d}-{self._view_month:02d}-{day:02d}"
                is_today = (
                    today.year == self._view_year
                    and today.month == self._view_month
                    and today.day == day
                )
                is_selected = (
                    self._selected_date.year == self._view_year
                    and self._selected_date.month == self._view_month
                    and self._selected_date.day == day
                )
                has_event = date_str in self._event_dates

                self._create_day_cell(
                    week_idx, day_idx, day, date_str,
                    is_today, is_selected, has_event,
                )

            # 配置行权重
            self._days_frame.grid_rowconfigure(week_idx, weight=1)

        # 配置列权重
        for col in range(7):
            self._days_frame.grid_columnconfigure(col, weight=1)

    def _create_day_cell(
        self, row, col, day, date_str,
        is_today, is_selected, has_event,
    ):
        """创建单个日期格子"""
        bg_color = "transparent"
        text_color = "white"

        if is_selected:
            bg_color = "#3498db"
        elif is_today:
            bg_color = "#2ecc71"

        cell = ctk.CTkButton(
            self._days_frame,
            text=str(day) + (" •" if has_event else ""),
            width=40, height=40,
            fg_color=bg_color,
            hover_color="#2980b9",
            text_color=text_color,
            font=ctk.CTkFont(size=13, weight="bold" if is_today else "normal"),
            command=lambda d=date_str: self._on_date_click(d),
        )
        cell.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)

    def _setup_event_list_for_date(self, date_str: str):
        """刷新指定日期的事件列表"""
        # 清空旧内容
        for widget in self._event_scroll.winfo_children():
            widget.destroy()

        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return

        events = self._manager.get_events_by_date(date)
        self._event_list_label.configure(
            text=f"{date_str} 的事件 ({len(events)})"
        )

        if not events:
            self._empty_label = ctk.CTkLabel(
                self._event_scroll,
                text="暂无事件",
                font=ctk.CTkFont(size=12),
                text_color="gray",
            )
            self._empty_label.pack(pady=20)
            return

        for event in events:
            self._create_event_card(event)

    def _create_event_card(self, event: CalendarEvent):
        """创建事件卡片"""
        card = ctk.CTkFrame(self._event_scroll, corner_radius=8)
        card.pack(fill="x", pady=3)

        time_str = "全天" if event.is_all_day else event.start_time.strftime("%H:%M")
        title_text = f"{time_str}  {event.title}"

        ctk.CTkLabel(
            card, text=title_text,
            font=ctk.CTkFont(size=13),
            anchor="w",
        ).pack(fill="x", padx=10, pady=(8, 2))

        if event.description:
            ctk.CTkLabel(
                card, text=event.description,
                font=ctk.CTkFont(size=11),
                text_color="gray",
                anchor="w",
                wraplength=250,
            ).pack(fill="x", padx=10, pady=(0, 5))

        if event.tags:
            tags_text = "  ".join(f"[{t}]" for t in event.tags)
            ctk.CTkLabel(
                card, text=tags_text,
                font=ctk.CTkFont(size=10),
                text_color="#3498db",
                anchor="w",
            ).pack(fill="x", padx=10, pady=(0, 5))

        # 点击编辑
        card.bind("<Button-1>", lambda e, ev=event: self._open_event_dialog(ev))
        for child in card.winfo_children():
            child.bind("<Button-1>", lambda e, ev=event: self._open_event_dialog(ev))

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

    def _open_event_dialog(self, event: Optional[CalendarEvent] = None):
        """打开事件编辑对话框"""
        def on_save(data: dict):
            if event and event.id:
                # 编辑模式
                self._manager.update_event(event.id, **data)
                logger.info(f"事件已更新: {data['title']}")
            else:
                # 添加模式
                self._manager.add_event(**data)
                logger.info(f"事件已添加: {data['title']}")
            self._refresh_calendar()
            self._refresh_event_list()

        def on_delete(event_id: int):
            title = self._manager.delete_event(event_id)
            if title:
                logger.info(f"事件已删除: {title}")
            self._refresh_calendar()
            self._refresh_event_list()

        EventDialog(self, event=event, on_save=on_save, on_delete=on_delete)

    def _on_voice_click(self):
        """语音按钮点击"""
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
        """更新语音面板状态"""
        self._voice_panel.set_state(state, message)

    def show_voice_result(self, text: str):
        """显示语音识别结果"""
        self._voice_panel.set_result(text)

    def refresh_all(self):
        """刷新所有视图"""
        self._refresh_calendar()
        self._refresh_event_list()

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
            dialog, text="知道了", width=80,
            command=dialog.destroy,
        ).pack(pady=15)

