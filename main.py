"""语音日历工具主程序 - 集成语音识别与日历管理的桌面应用"""

import os
import json
import logging
import threading
import queue
from pathlib import Path
from typing import Optional

# 配置 HuggingFace 国内镜像
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from config import Config
from audio.recorder import AudioRecorder
from engine.whisper_engine import WhisperEngine
from engine.paraformer_engine import ParaformerEngine
from engine.hotword_manager import HotwordManager
from engine.punctuation_processor import PunctuationProcessor
from engine.punctuation_restorer import PunctuationRestorer
from engine.post_processor import PostProcessor
from engine.text_corrector import TextCorrector
from hotkey.hotkey_manager import HotkeyManager
from calendar_pkg.manager import CalendarManager
from calendar_pkg.reminder import ReminderScheduler
from calendar_pkg.stats import StatsEngine
from calendar_pkg.achievement import AchievementEngine
from command.parser import CommandParser, CommandType
from command.completion import CommandCompleter
from ui.main_window import MainWindow
from ui.settings_window import SettingsWindow
from ui.voice_panel import VoiceState
from ui.tray import SystemTray
from ui.notification import ToastNotifier
from sounds.generate_sounds import ensure_sounds

# 应用主题配置
import customtkinter as ctk

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("VoiceCalendar")


class VoiceCalendarApp:
    """语音日历工具主应用

    集成语音识别流水线、日历管理和 GUI 界面。
    """

    def __init__(self):
        # 初始化配置
        self.config = Config()

        # 线程通信
        self._task_queue: queue.Queue = queue.Queue()
        self._result_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        # 窗口引用
        self._settings_window: Optional[SettingsWindow] = None
        self._main_window: Optional[MainWindow] = None

        # 系统托盘与通知
        self._tray: Optional[SystemTray] = None
        self._notifier: Optional[ToastNotifier] = None

        # 确保音效文件存在
        ensure_sounds(self.config.sounds_dir)

        # 初始化各模块
        self._init_modules()

    def _init_modules(self):
        """初始化所有子模块"""
        logger.info("正在初始化各模块...")

        # 检查是否有手动放置的 CUDA addon 待安装
        self._check_pending_cuda_addon()

        # 日历管理器
        self._calendar = CalendarManager(
            db_path=self.config.calendar_db_path,
            default_reminder_minutes=self.config.get("default_reminder_minutes", 15),
        )
        # 启动时自动补充循环事件实例
        self._calendar.expand_recurring_events()

        # 语音识别引擎（根据配置选择 Paraformer 或 Whisper）
        asr_engine = self.config.get("asr_engine", "paraformer")
        asr_device = self.config.get("asr_device", "cuda:0")
        if asr_engine == "paraformer":
            self._asr = ParaformerEngine(
                device=asr_device,
                cache_dir=str(self.config.model_cache_dir),
            )
            logger.info(f"ASR 引擎: Paraformer (device={self._asr.device})")
        else:
            self._asr = WhisperEngine(
                model_size=self.config.get("model_size", "small"),
                compute_type=self.config.get("compute_type", "int8"),
                cache_dir=str(self.config.model_cache_dir),
            )
            logger.info("ASR 引擎: Whisper (CPU)")

        # 后处理链
        self._text_corrector = TextCorrector()
        self._punctuation_restorer = PunctuationRestorer()
        self._punctuation_processor = PunctuationProcessor()
        self._post_processor = PostProcessor()

        # 热词管理
        self._hotword_manager = HotwordManager(hotword_file=str(self.config.hotword_file))

        # 录音器
        self._recorder = AudioRecorder(
            sample_rate=self.config.get("sample_rate", 16000),
            device=self.config.get("audio_device"),
        )

        # 快捷键
        self._hotkey = HotkeyManager(
            hotkey=self.config.get("hotkey", "right alt"),
            mode=self.config.get("hotkey_mode", "hold"),
            on_start=self._on_record_start,
            on_stop=self._on_record_stop,
            on_cancel=self._on_record_cancel,
        )

        # 指令解析器
        self._command_parser = CommandParser(
            llm_enabled=self.config.get("llm_enabled", False),
            llm_provider=self.config.get("llm_provider", "ollama"),
            llm_model=self.config.get("llm_model", "qwen2.5:7b"),
            llm_base_url=self.config.get("llm_base_url", "http://localhost:11434"),
            llm_parser_model=self.config.get("llm_parser_model", "qwen2.5:3b"),
            llm_parser_timeout=self.config.get("llm_parser_timeout", 2.0),
        )

        # 指令补全器
        self._completer = CommandCompleter()

        # 统计与成就引擎
        self._stats_engine = StatsEngine(self._calendar.storage)
        self._achievement_engine = AchievementEngine(
            self._stats_engine,
            save_path=str(self.config.data_dir / "achievements.json")
            if hasattr(self.config, "data_dir")
            else "achievements.json",
        )

        # 提醒调度器
        self._reminder = ReminderScheduler(
            calendar_manager=self._calendar,
            on_reminder=self._on_reminder_triggered,
            reminder_sounds=self.config.get("reminder_sounds", {}),
            dnd_enabled=self.config.get("dnd_enabled", False),
            dnd_start=self.config.get("dnd_start", "22:00"),
            dnd_end=self.config.get("dnd_end", "07:00"),
        )

        logger.info("模块初始化完成")

    def _check_pending_cuda_addon(self):
        """检查是否有手动放置的 CUDA addon zip 待安装"""
        try:
            from utils.torch_manager import check_manual_addon, install_cuda_addon

            zip_path = check_manual_addon()
            if zip_path:
                logger.info(f"检测到待安装的 CUDA addon: {zip_path}")
                success = install_cuda_addon(zip_path)
                if success:
                    self.config.set("asr_device", "cuda:0")
                    logger.info("CUDA addon 自动安装完成")
                else:
                    logger.warning("CUDA addon 自动安装失败")
        except Exception as e:
            logger.debug(f"CUDA addon 检查跳过: {e}")

    def run(self):
        """启动应用"""
        logger.info("语音日历工具启动")

        # 加载 Whisper 模型（后台线程）
        self._worker_thread = threading.Thread(target=self._load_model_worker, daemon=True, name="ModelLoader")
        self._worker_thread.start()

        # 注册快捷键
        self._hotkey.register()

        # 初始化 Toast 通知器
        self._notifier = ToastNotifier(
            app_id="语音日历",
            sounds_dir=self.config.sounds_dir,
        )

        # 创建主窗口
        self._main_window = MainWindow(
            calendar_manager=self._calendar,
            on_settings=self._open_settings,
            on_voice_start=self._on_record_start,
            on_voice_stop=self._on_record_stop,
            stats_engine=self._stats_engine,
            achievement_engine=self._achievement_engine,
        )
        self._main_window.protocol("WM_DELETE_WINDOW", self._on_close)

        # 启动系统托盘
        self._tray = SystemTray(
            on_open=self._on_tray_open,
            on_quit=self._on_quit,
        )
        self._tray.start()

        # 如果配置了启动时最小化，直接隐藏窗口
        if self.config.get("start_minimized", False):
            self._main_window.withdraw()

        # 启动提醒调度器（在主窗口创建之后，避免时序问题）
        if self.config.get("reminder_enabled", True):
            self._reminder.start()

        # 启动结果轮询
        self._poll_results()

        # 启动主循环
        self._main_window.mainloop()

    def _load_model_worker(self):
        """后台线程：加载 Whisper 模型"""
        try:
            logger.info("正在加载语音识别模型...")
            self._asr.load_model()
            logger.info("模型加载完成")
        except Exception as e:
            logger.error(f"模型加载失败: {e}")

    # ================================================================
    # 语音录音回调
    # ================================================================

    def _on_record_start(self):
        """开始录音"""
        logger.info("开始录音")
        self._recorder.start_recording()
        self._result_queue.put(("voice_state", VoiceState.RECORDING, ""))

    def _on_record_stop(self):
        """停止录音，送入识别流水线"""
        logger.info("停止录音")
        audio = self._recorder.stop_recording()
        if audio is None:
            self._result_queue.put(("voice_state", VoiceState.IDLE, ""))
            return

        duration = self._recorder.get_audio_duration(audio)
        if duration < 0.1:
            logger.info("音频过短，忽略")
            self._result_queue.put(("voice_state", VoiceState.IDLE, ""))
            return

        self._result_queue.put(("voice_state", VoiceState.PROCESSING, ""))

        # 在 worker 线程中执行识别+解析
        threading.Thread(
            target=self._process_audio,
            args=(audio,),
            daemon=True,
            name="SpeechWorker",
        ).start()

    def _on_record_cancel(self):
        """取消录音"""
        logger.info("取消录音")
        self._recorder.cancel_recording()
        self._result_queue.put(("voice_state", VoiceState.IDLE, ""))

    # ================================================================
    # 语音处理流水线
    # ================================================================

    def _process_audio(self, audio):
        """处理录音：识别 → 后处理 → 指令解析 → 执行

        Args:
            audio: numpy 音频数组
        """
        try:
            # 1. 语音识别
            initial_prompt = self._hotword_manager.build_initial_prompt()
            text = self._asr.transcribe(
                audio,
                language=self.config.get("language", "zh"),
                initial_prompt=initial_prompt,
                beam_size=self.config.get("beam_size", 5),
            )

            if not text:
                self._result_queue.put(("voice_state", VoiceState.ERROR, "未识别到语音"))
                self._wake_ui()
                return

            # 2. 后处理链
            # 解析路径：仅文本纠错（无标点，避免标点错误干扰拆分）
            parse_text = self._run_text_correction(text)
            # 展示路径：含标点恢复（给用户看）
            display_text = self._run_post_process(text)
            logger.info(f"识别结果: {display_text}")
            self._result_queue.put(("voice_result", display_text, None))
            self._wake_ui()

            # 3. 指令解析（使用无标点的纠错文本，支持多指令拆分）
            commands = self._command_parser.parse_multiple(parse_text)
            logger.info(f"指令解析: 识别到 {len(commands)} 条指令")

            if not commands:
                self._result_queue.put(("voice_state", VoiceState.ERROR, "未识别到有效指令"))
                self._wake_ui()
                return

            # 4. 执行指令（多条添加指令批量收集反馈）
            add_results = []  # 收集添加事件的结果
            for cmd in commands:
                extra = []
                if cmd.recurrence_rule:
                    extra.append(f"rec={cmd.recurrence_rule}")
                if cmd.priority > 0:
                    pri_labels = {1: "重要", 2: "紧急", 3: "紧急+重要"}
                    extra.append(f"pri={pri_labels.get(cmd.priority, cmd.priority)}")
                if cmd.end_time:
                    extra.append(f"end={cmd.end_time.strftime('%H:%M')}")
                extra_str = f" [{', '.join(extra)}]" if extra else ""
                logger.info(f"执行指令: type={cmd.command_type.value}, title='{cmd.title}'{extra_str}")
                if cmd.command_type == CommandType.ADD_EVENT:
                    result = self._execute_add_event_batch(cmd)
                    if result:
                        add_results.append(result)
                else:
                    self._execute_command(cmd)

            # 批量反馈添加结果
            if add_results:
                self._send_batch_add_feedback(add_results)

            # 唤醒UI立即处理指令执行结果
            self._wake_ui()

            # 5. 记录到交互日志（用于回放测试和模型训练）
            for cmd in commands:
                self._log_interaction(text, cmd)

        except Exception as e:
            logger.error(f"语音处理失败: {e}", exc_info=True)
            self._result_queue.put(("voice_state", VoiceState.ERROR, str(e)))
            self._wake_ui()

    def _log_interaction(self, text: str, cmd):
        """将语音交互记录追加到日志文件（用于回放测试和模型训练）

        Args:
            text: 原始语音文本
            cmd: 解析后的指令结果
        """
        log_file = Path("tests/interaction_log.jsonl")
        entry = {
            "text": text,
            "label": cmd.command_type.value,
            "expected_title": cmd.title,
            "expected_recurrence": cmd.recurrence_rule or "",
            "confidence": cmd.confidence,
            "note": "自动记录",
            "accepted": True,
        }
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"交互日志写入失败: {e}")

    def _run_post_process(self, text: str) -> str:
        """执行后处理链（用于 UI 展示，含标点恢复）

        Args:
            text: 原始识别文本（无标点）

        Returns:
            处理后的文本（含标点，适合展示）
        """
        text = self._run_text_correction(text)

        # 标点恢复（仅用于展示，解析路径不使用）
        if self.config.get("punctuation_optimization", True):
            text = self._punctuation_restorer.restore(text)
            text = self._punctuation_processor.process(text)

        return text

    def _run_text_correction(self, text: str) -> str:
        """执行文本纠错（不含标点恢复，用于解析路径）

        Args:
            text: 原始识别文本（无标点）

        Returns:
            纠错后的纯文本（无标点）
        """
        # 繁转简
        try:
            import zhconv

            text = zhconv.convert(text, "zh-cn")
        except ImportError:
            pass

        # 同音纠错
        if self.config.get("text_correction", True):
            text = self._text_corrector.correct(text)

        return text

    # ================================================================
    # 指令执行
    # ================================================================

    def _execute_command(self, command):
        """执行解析后的日历指令

        Args:
            command: ParsedCommand 对象
        """
        cmd_type = command.command_type

        if cmd_type == CommandType.ADD_EVENT:
            self._execute_add_event(command)
        elif cmd_type == CommandType.DELETE_EVENT:
            self._execute_delete_event(command)
        elif cmd_type == CommandType.QUERY_EVENT:
            self._execute_query_event(command)
        elif cmd_type == CommandType.UPDATE_EVENT:
            self._execute_update_event(command)
        else:
            self._result_queue.put(("voice_state", VoiceState.ERROR, f"无法理解指令: {command.original_text}"))

    def _execute_add_event(self, command):
        """执行添加事件"""
        # 使用补全器检查并补全不完整信息
        check = self._completer.check_completeness(command)
        if not check["complete"]:
            logger.info(f"指令不完整: {check['suggestion']}")
            command = self._completer.complete_command(command)

        new_event = self._calendar.add_event(
            title=command.title,
            start_time=command.time,
            end_time=getattr(command, "end_time", None),
            priority=getattr(command, "priority", 0),
            recurrence_rule=getattr(command, "recurrence_rule", ""),
            recurrence_end=getattr(command, "recurrence_end", None),
        )
        time_str = command.time.strftime("%m月%d日 %H:%M")
        msg = f"已添加: {command.title} ({time_str})"
        logger.info(msg)

        # 检查成就解锁
        new_achievements = self._achievement_engine.check_achievements()
        if new_achievements:
            ach_names = ", ".join(a["name"] for a in new_achievements)
            msg += f" | 🏆 解锁成就: {ach_names}"
            logger.info(f"成就解锁: {ach_names}")

        self._result_queue.put(("command_executed", msg, "add", command.time, new_event.id))

    def _execute_add_event_batch(self, command):
        """执行添加事件并返回结果（不直接发送反馈，用于批量收集）

        Returns:
            (msg, event_time, event_id) 元组，失败返回 None
        """
        try:
            check = self._completer.check_completeness(command)
            if not check["complete"]:
                logger.info(f"指令不完整: {check['suggestion']}")
                command = self._completer.complete_command(command)

            new_event = self._calendar.add_event(
                title=command.title,
                start_time=command.time,
                end_time=getattr(command, "end_time", None),
                priority=getattr(command, "priority", 0),
                recurrence_rule=getattr(command, "recurrence_rule", ""),
                recurrence_end=getattr(command, "recurrence_end", None),
            )
            time_str = command.time.strftime("%m月%d日 %H:%M")
            msg = f"{command.title} ({time_str})"
            logger.info(f"已添加: {msg}")
            return (msg, command.time, new_event.id)
        except Exception as e:
            logger.error(f"添加事件失败: {e}")
            return None

    def _send_batch_add_feedback(self, add_results):
        """发送批量添加事件的合并反馈

        Args:
            add_results: [(msg, event_time, event_id), ...] 列表
        """
        # 检查成就解锁
        achievement_msg = ""
        new_achievements = self._achievement_engine.check_achievements()
        if new_achievements:
            ach_names = ", ".join(a["name"] for a in new_achievements)
            achievement_msg = f" | \U0001f3c6 解锁成就: {ach_names}"
            logger.info(f"成就解锁: {ach_names}")

        if len(add_results) == 1:
            # 单条事件：保持原格式
            msg, event_time, event_id = add_results[0]
            full_msg = f"已添加: {msg}{achievement_msg}"
            self._result_queue.put(("command_executed", full_msg, "add", event_time, event_id))
        else:
            # 多条事件：合并反馈
            lines = [f"已添加 {len(add_results)} 个事件:"]
            for msg, _, _ in add_results:
                lines.append(f"  · {msg}")
            full_msg = "\n".join(lines) + achievement_msg
            # 导航到最后一个事件
            _, last_time, last_id = add_results[-1]
            self._result_queue.put(("command_executed", full_msg, "add", last_time, last_id))

    def _execute_delete_event(self, command):
        """执行删除事件（查找匹配的事件并删除）"""
        if command.time:
            events = self._calendar.get_events_by_date(command.time)
        elif command.title:
            events = self._calendar.search_events(command.title)
        else:
            events = []

        if not events:
            msg = "未找到匹配的事件"
            self._result_queue.put(("voice_state", VoiceState.ERROR, msg))
            return

        # 标题为空表示删除所有匹配事件（如“删除今天的所有事件”）
        if not command.title and command.time:
            deleted_count = 0
            for event in events:
                if self._calendar.delete_event(event.id):
                    deleted_count += 1
            date_str = command.time.strftime("%m月%d日")
            msg = f"已删除 {date_str} 的 {deleted_count} 个事件"
            self._result_queue.put(("command_executed", msg, "delete", None))
        else:
            # 删除第一个匹配的事件
            title = self._calendar.delete_event(events[0].id)
            if title:
                msg = f"已删除: {title}"
                self._result_queue.put(("command_executed", msg, "delete", None))
            else:
                self._result_queue.put(("voice_state", VoiceState.ERROR, "删除失败"))

    def _execute_query_event(self, command):
        """执行查询事件"""
        if command.time:
            events = self._calendar.get_events_by_date(command.time)
            date_str = command.time.strftime("%m月%d日")
        else:
            events = self._calendar.get_today_events()
            date_str = "今天"

        if events:
            event_list = CalendarManager.format_event_list(events)
            msg = f"{date_str}有 {len(events)} 个事件:\n{event_list}"
        else:
            msg = f"{date_str}没有事件"

        self._result_queue.put(("command_executed", msg, "query", (date_str, events)))

    def _execute_update_event(self, command):
        """执行修改事件

        解析层提供:
        - command.title: 事件名称（用于搜索）
        - command.time: 目标时间（绝对调整）或 None（相对偏移）
        - command.end_time: 源时间（用于定位事件所在日期）
        - command.original_text: 原始文本（用于提取偏移量）
        """
        from datetime import timedelta

        title = command.title
        target_time = command.time  # 目标时间（绝对）
        source_time = command.end_time  # 源时间（用于定位事件）

        if not title and not target_time and not source_time:
            self._result_queue.put(("voice_state", VoiceState.ERROR, "无法识别要修改的事件"))
            return

        # 搜索匹配事件: title 精确匹配 → 源时间日期匹配 → 目标时间日期匹配
        candidates = []
        if title:
            candidates = self._calendar.search_events(title)
            # 如果有源时间，用它缩小范围
            if candidates and source_time:
                date_filtered = [e for e in candidates if e.start_time.date() == source_time.date()]
                if date_filtered:
                    candidates = date_filtered

        if not candidates and source_time:
            candidates = self._calendar.get_events_by_date(source_time)
            # 如果有标题，进一步筛选
            if candidates and title:
                title_filtered = [e for e in candidates if title in e.title]
                if title_filtered:
                    candidates = title_filtered

        if not candidates and target_time:
            candidates = self._calendar.get_events_by_date(target_time)

        if not candidates:
            self._result_queue.put(
                ("voice_state", VoiceState.ERROR, f"未找到匹配的事件: {title or command.original_text}")
            )
            return

        # 多个候选时选时间最近的（未来优先）
        from datetime import datetime as dt

        now = dt.now()
        candidates.sort(key=lambda e: (0 if e.start_time >= now else 1, abs((e.start_time - now).total_seconds())))
        target_event = candidates[0]

        # 确定更新内容
        update_kwargs = {}
        original_text = command.original_text

        # 判断相对/绝对模式
        is_relative = any(
            kw in original_text for kw in ["推迟", "延后", "往后推", "向后推", "提前", "向前推", "往前推"]
        )

        if is_relative:
            # 相对偏移：从原文提取偏移量
            offset_minutes = self._parse_relative_offset(original_text, default=60)
            if any(kw in original_text for kw in ["提前", "向前推", "往前推"]):
                offset_minutes = -offset_minutes
            new_start = target_event.start_time + timedelta(minutes=offset_minutes)
            update_kwargs["start_time"] = new_start
            if target_event.end_time and target_event.end_time != target_event.start_time:
                update_kwargs["end_time"] = target_event.end_time + timedelta(minutes=offset_minutes)
        elif target_time:
            # 绝对时间更新
            if target_time.hour == 0 and target_time.minute == 0:
                # 目标时间只有日期，保留原事件时分
                new_start = target_time.replace(
                    hour=target_event.start_time.hour, minute=target_event.start_time.minute
                )
            else:
                new_start = target_time
            update_kwargs["start_time"] = new_start
            if target_event.end_time and target_event.end_time != target_event.start_time:
                duration = target_event.end_time - target_event.start_time
                update_kwargs["end_time"] = new_start + duration
        else:
            self._result_queue.put(("voice_state", VoiceState.ERROR, "无法确定修改内容"))
            return

        # 执行更新
        updated = self._calendar.update_event(target_event.id, **update_kwargs)
        if updated:
            new_time_str = update_kwargs["start_time"].strftime("%m月%d日 %H:%M")
            msg = f"已修改: {target_event.title} → {new_time_str}"
            logger.info(msg)
            self._result_queue.put(("command_executed", msg, "update", None))
        else:
            self._result_queue.put(("voice_state", VoiceState.ERROR, "修改失败"))

    @staticmethod
    def _parse_relative_offset(text: str, default: int = 60) -> int:
        """从文本中提取相对偏移量（分钟）

        支持: "N个小时", "N小时", "N分钟", "半小时"
        默认返回 default 分钟
        """
        import re

        # 半小时
        if "半小时" in text or "半天" in text:
            if "半天" in text:
                return 720
            return 30

        # N个小时 / N小时
        m = re.search(r"(\d+)\s*个?小时", text)
        if m:
            return int(m.group(1)) * 60

        # N分钟
        m = re.search(r"(\d+)\s*分钟?", text)
        if m:
            return int(m.group(1))

        # 中文数字
        cn_nums = {"一": 1, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        m = re.search(r"([一两三四五六七八九十]+)\s*个?小时", text)
        if m:
            cn = m.group(1)
            num = cn_nums.get(cn, 1)
            return num * 60

        m = re.search(r"([一两三四五六七八九十]+)\s*分钟?", text)
        if m:
            cn = m.group(1)
            num = cn_nums.get(cn, default)
            return num

        return default

    def _execute_update_event(self, command):
        """执行修改事件

        解析层提供:
        - command.title: 事件名称（用于搜索）
        - command.time: 目标时间（绝对调整）或 None（相对偏移）
        - command.end_time: 源时间（用于定位事件所在日期）
        - command.original_text: 原始文本（用于提取偏移量）
        """
        from datetime import timedelta

        title = command.title
        target_time = command.time  # 目标时间（绝对）
        source_time = command.end_time  # 源时间（用于定位事件）

        if not title and not target_time and not source_time:
            self._result_queue.put(("voice_state", VoiceState.ERROR, "无法识别要修改的事件"))
            return

        # 搜索匹配事件: title 精确匹配 → 源时间日期匹配 → 目标时间日期匹配
        candidates = []
        if title:
            candidates = self._calendar.search_events(title)
            # 如果有源时间，用它缩小范围
            if candidates and source_time:
                date_filtered = [e for e in candidates if e.start_time.date() == source_time.date()]
                if date_filtered:
                    candidates = date_filtered

        if not candidates and source_time:
            candidates = self._calendar.get_events_by_date(source_time)
            # 如果有标题，进一步筛选
            if candidates and title:
                title_filtered = [e for e in candidates if title in e.title]
                if title_filtered:
                    candidates = title_filtered

        if not candidates and target_time:
            candidates = self._calendar.get_events_by_date(target_time)

        if not candidates:
            self._result_queue.put(
                ("voice_state", VoiceState.ERROR, f"未找到匹配的事件: {title or command.original_text}")
            )
            return

        # 多个候选时选时间最近的（未来优先）
        from datetime import datetime as dt

        now = dt.now()
        candidates.sort(key=lambda e: (0 if e.start_time >= now else 1, abs((e.start_time - now).total_seconds())))
        target_event = candidates[0]

        # 确定更新内容
        update_kwargs = {}
        original_text = command.original_text

        # 判断相对/绝对模式
        is_relative = any(
            kw in original_text for kw in ["推迟", "延后", "往后推", "向后推", "提前", "向前推", "往前推"]
        )

        if is_relative:
            # 相对偏移：从原文提取偏移量
            offset_minutes = self._parse_relative_offset(original_text, default=60)
            if any(kw in original_text for kw in ["提前", "向前推", "往前推"]):
                offset_minutes = -offset_minutes
            new_start = target_event.start_time + timedelta(minutes=offset_minutes)
            update_kwargs["start_time"] = new_start
            if target_event.end_time and target_event.end_time != target_event.start_time:
                update_kwargs["end_time"] = target_event.end_time + timedelta(minutes=offset_minutes)
        elif target_time:
            # 绝对时间更新
            if target_time.hour == 0 and target_time.minute == 0:
                # 目标时间只有日期，保留原事件时分
                new_start = target_time.replace(
                    hour=target_event.start_time.hour, minute=target_event.start_time.minute
                )
            else:
                new_start = target_time
            update_kwargs["start_time"] = new_start
            if target_event.end_time and target_event.end_time != target_event.start_time:
                duration = target_event.end_time - target_event.start_time
                update_kwargs["end_time"] = new_start + duration
        else:
            self._result_queue.put(("voice_state", VoiceState.ERROR, "无法确定修改内容"))
            return

        # 执行更新
        updated = self._calendar.update_event(target_event.id, **update_kwargs)
        if updated:
            new_time_str = update_kwargs["start_time"].strftime("%m月%d日 %H:%M")
            msg = f"已修改: {target_event.title} → {new_time_str}"
            logger.info(msg)
            self._result_queue.put(("command_executed", msg, "update"))
        else:
            self._result_queue.put(("voice_state", VoiceState.ERROR, "修改失败"))

    @staticmethod
    def _parse_relative_offset(text: str, default: int = 60) -> int:
        """从文本中提取相对偏移量（分钟）

        支持: "N个小时", "N小时", "N分钟", "半小时"
        默认返回 default 分钟
        """
        import re

        # 半小时
        if "半小时" in text or "半天" in text:
            if "半天" in text:
                return 720
            return 30

        # N个小时 / N小时
        m = re.search(r"(\d+)\s*个?小时", text)
        if m:
            return int(m.group(1)) * 60

        # N分钟
        m = re.search(r"(\d+)\s*分钟?", text)
        if m:
            return int(m.group(1))

        # 中文数字
        cn_nums = {"一": 1, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        m = re.search(r"([一两三四五六七八九十]+)\s*个?小时", text)
        if m:
            cn = m.group(1)
            num = cn_nums.get(cn, 1)
            return num * 60

        m = re.search(r"([一两三四五六七八九十]+)\s*分钟?", text)
        if m:
            cn = m.group(1)
            num = cn_nums.get(cn, default)
            return num

        return default

    # ================================================================
    # UI 回调与更新
    # ================================================================

    def _poll_results(self):
        """轮询结果队列，在主线程中更新 UI"""
        try:
            while not self._result_queue.empty():
                result = self._result_queue.get_nowait()
                self._handle_result(result)
        except queue.Empty:
            pass
        # 每 100ms 轮询一次（保底，实际通过 _wake_ui 即时触发）
        if self._main_window:
            self._main_window.after(100, self._poll_results)

    def _wake_ui(self):
        """从任意线程唤醒主线程立即处理队列

        解决 Windows 下窗口未获焦时 after() 回调延迟的问题。
        tkinter 的 after() 在 CPython 中是线程安全的（通过 Tcl 事件队列）。
        """
        try:
            if self._main_window:
                self._main_window.after(1, self._poll_results)
        except Exception:
            pass

    def _handle_result(self, result: tuple):
        """处理结果队列中的消息

        Args:
            result: (消息类型, 数据1, 数据2) 元组
        """
        msg_type = result[0]

        if msg_type == "voice_state":
            state, message = result[1], result[2]
            self._main_window.set_voice_state(state, message)

        elif msg_type == "voice_result":
            text = result[1]
            self._main_window.show_voice_result(text)

        elif msg_type == "command_executed":
            message = result[1]
            cmd_action = result[2] if len(result) > 2 else None
            event_time = result[3] if len(result) > 3 else None
            event_id = result[4] if len(result) > 4 else None
            if cmd_action == "query" and event_time:
                # 查询指令：仅打开独立窗口，不在反馈区输出
                query_title, query_events = event_time
                self._main_window.show_query_window(query_title, query_events)
                self._main_window.set_voice_state(VoiceState.IDLE)
            else:
                self._main_window.show_voice_result(message)
                self._main_window.set_voice_state(VoiceState.SUCCESS, message)
                # 添加事件后导航到对应日期并高亮卡片
                if cmd_action == "add" and event_time:
                    self._main_window.navigate_to_date(event_time, highlight_event_id=event_id)
                else:
                    self._main_window.refresh_all()

        elif msg_type == "reminder":
            event = result[1]
            self._main_window.show_reminder(event)

    def _open_settings(self):
        """打开设置窗口"""
        if self._settings_window and self._settings_window.winfo_exists():
            self._settings_window.focus()
            return

        self._settings_window = SettingsWindow(
            self._main_window,
            config=self.config,
            on_settings_changed=self._on_settings_changed,
        )

    def _on_settings_changed(self, changes: dict):
        """配置变更回调"""
        if "hotkey" in changes or "hotkey_mode" in changes:
            self._hotkey.change_hotkey(
                self.config.get("hotkey", "right alt"),
                self.config.get("hotkey_mode", "hold"),
            )

        if "model_size" in changes and hasattr(self._asr, "change_model"):
            threading.Thread(
                target=self._asr.change_model,
                args=(changes["model_size"],),
                daemon=True,
            ).start()

        if "llm_enabled" in changes:
            self._command_parser.enable_llm(changes["llm_enabled"])

    def _on_reminder_triggered(self, event):
        """提醒触发回调 - 发送 Toast 通知 + 显示弹窗 + 可选音效"""
        logger.info(f"提醒触发: {event.title}")

        # Toast 通知（始终有效，不依赖主窗口）
        if self._notifier:
            self._notifier.show_reminder(event)

        # 音效（如果启用）
        if self.config.get("reminder_sound", False) and self._notifier:
            sound = self._reminder.get_sound_for_category(event.category)
            self._notifier.play_sound(sound)

        # 始终显示自定义弹窗（topmost 独立窗口，不受主窗口可见性影响）
        try:
            if self._main_window:
                self._result_queue.put(("reminder", event, None))
        except Exception:
            pass

    def _on_close(self):
        """关闭窗口 -> 最小化到托盘或退出"""
        if self.config.get("minimize_to_tray", True):
            logger.info("窗口最小化到系统托盘")
            self._main_window.withdraw()
        else:
            self._on_quit()

    def _on_tray_open(self):
        """从托盘恢复窗口"""
        if self._main_window:
            self._main_window.after(0, self._restore_window)

    def _restore_window(self):
        """在主线程中恢复窗口"""
        self._main_window.deiconify()
        self._main_window.lift()
        self._main_window.focus_force()

    def _on_quit(self):
        """真正退出应用"""
        logger.info("应用退出")
        self._hotkey.unregister()
        self._reminder.stop()
        self._recorder.cancel_recording()
        self._stop_event.set()
        if self._tray:
            self._tray.stop()
        if self._main_window:
            self._main_window.withdraw()  # 立即隐藏窗口
            self._main_window.quit()  # 停止 mainloop
        # 直接终止进程，避免 CustomTkinter 的 TclError
        import os

        os._exit(0)


def main():
    """程序入口"""
    app = VoiceCalendarApp()
    app.run()


if __name__ == "__main__":
    main()
