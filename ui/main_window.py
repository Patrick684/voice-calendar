"""主窗口 - 日历视图 + 事件列表 + 语音面板 + 拖拽排序"""

import calendar as cal_mod
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Optional, Callable, List, Dict

import customtkinter as ctk

from calendar_pkg.event import CalendarEvent
from calendar_pkg.manager import CalendarManager
from calendar_pkg.stats import StatsEngine
from calendar_pkg.achievement import AchievementEngine
from ui.voice_panel import VoicePanel, VoiceState
from ui.event_dialog import EventDialog
from ui.stats_view import StatsView
from ui.time_dial import TimeDial

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
            "event": None, "source_date": None,
            "start_x": 0, "start_y": 0, "dragging": False,
        }
        self._day_cells: Dict[str, ctk.CTkButton] = {}  # date_str -> cell widget

        # 撤销栈
        self._undo_stack: deque = deque(maxlen=20)

        # 事件列表排序模式
        self._sort_mode = "time"  # "time" 或 "priority"

        # 当前选中的事件（用于拨盘）
        self._active_event: Optional[CalendarEvent] = None

        # 分类颜色（从配置获取，使用默认值）
        self._category_colors: Dict[str, str] = {
            "工作": "#2196F3", "健康": "#4CAF50", "学习": "#FF9800",
            "生活": "#9C27B0", "娱乐": "#E91E63", "社交": "#00BCD4",
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

        if self._stats_engine and self._achievement_engine:
            ctk.CTkButton(
                self._toolbar, text="📈 统计", width=80,
                command=self._open_stats,
            ).pack(side="right", padx=5, pady=8)

        ctk.CTkButton(
            self._toolbar, text="+ 添加事件", width=100,
            command=lambda: self._open_event_dialog(),
        ).pack(side="right", padx=5, pady=8)

        # 排序模式切换
        self._sort_btn = ctk.CTkButton(
            self._toolbar, text="⏱ 时间排序", width=100,
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
            width=40, height=40,
            fg_color=bg_color,
            hover_color="#2980b9",
            text_color=text_color,
            font=ctk.CTkFont(size=13, weight="bold" if is_today else "normal"),
            command=lambda d=date_str: self._on_date_click(d),
        )
        cell.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)

        # 拖拽放置目标（左键按下 + 移动阈值）
        cell.bind("<Enter>", lambda e, ds=date_str: self._on_drag_enter(ds))
        cell.bind("<Leave>", lambda e, ds=date_str: self._on_drag_leave(ds))
        cell.bind("<ButtonRelease-1>", lambda e, ds=date_str: self._on_drag_drop(ds))

        self._day_cells[date_str] = cell

    def _setup_event_list_for_date(self, date_str: str):
        """刷新指定日期的事件列表（支持排序模式）"""
        # 清空旧内容
        for widget in self._event_scroll.winfo_children():
            widget.destroy()

        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return

        events = self._manager.get_events_by_date(date)

        # 排序
        if self._sort_mode == "priority":
            events.sort(key=lambda e: (-e.priority, e.start_time))
        # 默认按时间排序（已由 storage 返回有序列表）

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

        # 显示时间拨盘
        self._update_time_dial()

    def _create_event_card(self, event: CalendarEvent):
        """创建事件卡片（含分类颜色条 + 左键拖拽）"""
        card = ctk.CTkFrame(self._event_scroll, corner_radius=8)
        card.pack(fill="x", pady=3)

        # 分类颜色条
        cat_color = self._category_colors.get(event.category, "#757575")
        color_bar = ctk.CTkFrame(card, width=4, fg_color=cat_color, corner_radius=2)
        color_bar.pack(side="left", fill="y", padx=(5, 0), pady=3)

        # 内容区
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True)

        time_str = "全天" if event.is_all_day else event.start_time.strftime("%H:%M")
        title_text = f"{time_str}  {event.title}"

        # 优先级标记
        priority_marker = ""
        if event.priority >= 2:
            priority_marker = " ❗"
        elif event.priority == 1:
            priority_marker = " ★"

        ctk.CTkLabel(
            content, text=title_text + priority_marker,
            font=ctk.CTkFont(size=13),
            anchor="w",
        ).pack(fill="x", padx=10, pady=(8, 2))

        if event.description:
            ctk.CTkLabel(
                content, text=event.description,
                font=ctk.CTkFont(size=11),
                text_color="gray",
                anchor="w",
                wraplength=250,
            ).pack(fill="x", padx=10, pady=(0, 5))

        # 分类 + 标签行
        info_parts = []
        if event.category:
            info_parts.append(f"[{event.category}]")
        if event.tags:
            info_parts.extend(f"[{t}]" for t in event.tags)
        if info_parts:
            ctk.CTkLabel(
                content, text="  ".join(info_parts),
                font=ctk.CTkFont(size=10),
                text_color=cat_color,
                anchor="w",
            ).pack(fill="x", padx=10, pady=(0, 5))

        # 选中事件 → 更新拨盘（单击左侧颜色条区域选中）
        color_bar.bind(
            "<Button-1>",
            lambda e, ev=event: self._select_event(ev),
        )

        # 左键拖拽（仅真实事件，移动阈值区分点击/拖拽）
        if event.id is not None:
            self._bind_drag_events(card, event)
            for child in card.winfo_children():
                self._bind_drag_events(child, event)
                for grandchild in child.winfo_children():
                    self._bind_drag_events(grandchild, event)
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
        widget.bind("<B1-Motion>", self._on_motion)
        widget.bind("<ButtonRelease-1>", lambda e, ev=event: self._on_release(e, ev))

    # ================================================================
    # 拖拽排序（左键 + 移动阈值）
    # ================================================================

    _DRAG_THRESHOLD = 5  # 像素阈值，超过才算拖拽

    def _on_press(self, event, cal_event: CalendarEvent):
        """左键按下 - 记录起始位置"""
        self._drag_data = {
            "event": cal_event,
            "source_date": cal_event.start_time.strftime("%Y-%m-%d"),
            "start_x": event.x_root,
            "start_y": event.y_root,
            "dragging": False,
        }

    def _on_motion(self, event):
        """左键拖拽中 - 超过阈值进入拖拽模式"""
        if self._drag_data.get("event") is None:
            return
        if not self._drag_data["dragging"]:
            dx = abs(event.x_root - self._drag_data["start_x"])
            dy = abs(event.y_root - self._drag_data["start_y"])
            if dx + dy < self._DRAG_THRESHOLD:
                return
            # 进入拖拽模式
            self._drag_data["dragging"] = True
            source_cell = self._day_cells.get(self._drag_data["source_date"])
            if source_cell:
                source_cell.configure(fg_color="#e67e22")

    def _on_release(self, event, cal_event: CalendarEvent):
        """左键释放 - 判断是点击还是拖拽"""
        if self._drag_data.get("dragging"):
            # 拖拽模式：放置已由 _on_drag_drop 处理
            self._drag_data = {
                "event": None, "source_date": None,
                "start_x": 0, "start_y": 0, "dragging": False,
            }
            self._refresh_calendar()
        else:
            # 点击模式：打开编辑对话框
            self._drag_data = {
                "event": None, "source_date": None,
                "start_x": 0, "start_y": 0, "dragging": False,
            }
            self._open_event_dialog(cal_event)

    def _on_drag_enter(self, date_str: str):
        """拖拽进入日期格子"""
        if not self._drag_data.get("dragging"):
            return
        cell = self._day_cells.get(date_str)
        if cell:
            cell.configure(fg_color="#27ae60")

    def _on_drag_leave(self, date_str: str):
        """拖拽离开日期格子"""
        if not self._drag_data.get("dragging"):
            return
        self._refresh_calendar()

    def _on_drag_drop(self, target_date_str: str):
        """拖拽放置到目标日期"""
        if not self._drag_data.get("dragging"):
            return

        cal_event = self._drag_data.get("event")
        if cal_event is None or cal_event.id is None:
            return

        source_date_str = self._drag_data["source_date"]
        if source_date_str == target_date_str:
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
            self._undo_stack.append({
                "event_id": cal_event.id,
                "old_start": cal_event.start_time,
                "old_end": cal_event.end_time,
            })

            self._manager.update_event(
                cal_event.id,
                start_time=new_start,
                end_time=new_end,
            )
            logger.info(
                f"拖拽移动: {cal_event.title} "
                f"{source_date_str} -> {target_date_str}"
            )
        except Exception as e:
            logger.error(f"拖拽失败: {e}")

        self._drag_data = {
            "event": None, "source_date": None,
            "start_x": 0, "start_y": 0, "dragging": False,
        }
        self._refresh_calendar()
        self._refresh_event_list()

    def _toggle_sort_mode(self):
        """切换排序模式"""
        if self._sort_mode == "time":
            self._sort_mode = "priority"
            self._sort_btn.configure(text="★ 优先级排序")
        else:
            self._sort_mode = "time"
            self._sort_btn.configure(text="⏱ 时间排序")
        self._refresh_event_list()

    def _on_undo(self, event=None):
        """Ctrl+Z 撤销上次拖拽/拨盘"""
        if not self._undo_stack:
            return
        action = self._undo_stack.pop()
        try:
            self._manager.update_event(
                action["event_id"],
                start_time=action["old_start"],
                end_time=action.get("old_end"),
            )
            logger.info(f"撤销: event_id={action['event_id']}")
            self._refresh_calendar()
            self._refresh_event_list()
        except Exception as e:
            logger.error(f"撤销失败: {e}")

    # ================================================================
    # 时间拨盘
    # ================================================================

    def _setup_time_dial(self):
        """在事件列表底部初始化时间拨盘"""
        self._time_dial = TimeDial(
            self._event_frame,
            on_time_change=self._on_time_dial_change,
        )
        # 默认隐藏，选中事件后显示
        self._time_dial_visible = False

    def _update_time_dial(self):
        """根据当前选中事件更新拨盘显示"""
        if not hasattr(self, '_time_dial'):
            self._setup_time_dial()

        if self._active_event and self._active_event.id is not None:
            if not self._time_dial_visible:
                self._time_dial.pack(fill="x", padx=10, pady=(0, 5))
                self._time_dial_visible = True
            self._time_dial.set_event(
                self._active_event.id,
                self._active_event.start_time,
            )
        else:
            if self._time_dial_visible:
                self._time_dial.pack_forget()
                self._time_dial_visible = False
            self._time_dial.clear()

    def _select_event(self, event: CalendarEvent):
        """选中事件，更新拨盘"""
        self._active_event = event
        self._update_time_dial()

    def _on_time_dial_change(self, hour: int, minute: int):
        """拨盘时间变更回调"""
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
        self._undo_stack.append({
            "event_id": self._active_event.id,
            "old_start": old_start,
            "old_end": self._active_event.end_time,
        })

        self._manager.update_event(
            self._active_event.id,
            start_time=new_start,
            end_time=new_end,
        )
        logger.info(
            f"拨盘调整: {self._active_event.title} → {hour:02d}:{minute:02d}"
        )
        self._refresh_event_list()

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

        EventDialog(
            self, event=event, on_save=on_save, on_delete=on_delete,
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

