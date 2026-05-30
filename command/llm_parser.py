"""基于本地 LLM 的指令解析器 — 一次调用完成多指令拆分 + 意图分类 + 槽位提取

设计原则:
- LLM 负责"理解"：多指令切分、意图判定、标题提取、时间表达提取
- TimeParser 负责"计算"：将 LLM 输出的相对时间文本转为精确 datetime
- RecurrenceResolver 负责"循环规则"：将 LLM 输出的循环描述转为 RRULE

这样 LLM 不需要知道今天的日期，避免日期计算错误。
"""

import json
import logging
import os
from datetime import datetime
from typing import List, Optional
from urllib import request, error as urlerror

from command.rule_engine import CommandType, ParsedCommand
from command.time_parser import TimeParser
from command.recurrence_resolver import RecurrenceResolver

# 绕过系统代理访问 localhost（避免 Clash 等代理拦截本地请求）
os.environ.setdefault("NO_PROXY", "localhost,127.0.0.1")
if "localhost" not in os.environ.get("NO_PROXY", ""):
    os.environ["NO_PROXY"] = os.environ.get("NO_PROXY", "") + ",localhost,127.0.0.1"

logger = logging.getLogger(__name__)

# LLM 系统提示词：要求一次性输出所有指令的结构化 JSON
_SYSTEM_PROMPT = """你是日历语音指令解析器。用户通过语音输入日历操作指令（无标点符号）。
请将输入拆分为独立指令，每条指令提取以下字段。

输出格式（严格 JSON 数组，不要输出任何其他内容）:
[{{
  "type": "add" | "delete" | "query" | "update",
  "title": "事件标题（核心动作/名称，去掉时间词和命令词）",
  "date": "日期表达（如 明天/后天/下周一/6月1号/下个月5号）或空字符串",
  "time": "时间表达（如 下午三点/晚上八点/上午十点/15:00）或空字符串",
  "recurrence": "循环规则（如 每天/每周五/每个工作日/每月1号）或空字符串",
  "priority": "普通" | "重要" | "紧急"
}}]

规则：
- add: 添加/安排事件，或隐式添加（有日期时间+事件标题即视为添加）
- delete: 删除/取消事件，包括"不X了"的否定表达
- query: 查看/查询日程/安排
- update: 修改/推迟/提前/挚到
- 一句话可能包含多条独立指令，必须全部拆分输出
- title 只保留事件核心描述，不要包含时间、日期、命令动词
- 如果是"删除所有事件"类指令，title 留空
- priority 默认为"普通"，仅当用户明确说"重要/紧急/必须"时才提升
- 重要：日期上下文继承——如果某条指令没有明确日期但前面的指令有，则继承前一条的日期。例如"明天早上8点起床下午3点开会"中，"下午3点开会"应继承"明天"。"""


class LLMParser:
    """基于本地 LLM 的指令解析器

    通过 Ollama API 调用本地部署的 LLM（如 Qwen2.5:3B），
    一次调用完成多指令拆分、意图分类和槽位提取。

    当 Ollama 不可用时优雅降级（返回 None，由上层回退到规则引擎）。
    """

    # 意图类型映射
    _TYPE_MAP = {
        "add": CommandType.ADD_EVENT,
        "delete": CommandType.DELETE_EVENT,
        "query": CommandType.QUERY_EVENT,
        "update": CommandType.UPDATE_EVENT,
    }

    # 优先级映射
    _PRIORITY_MAP = {
        "普通": 0,
        "重要": 1,
        "紧急": 2,
    }

    def __init__(
        self,
        model: str = "qwen2.5:3b",
        base_url: str = "http://localhost:11434",
        timeout: float = 5.0,
    ):
        """
        初始化 LLM 解析器

        Args:
            model: Ollama 模型名称
            base_url: Ollama API 地址
            timeout: 请求超时秒数（默认 5s，兆考冷启动场景）
        """
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._time_parser = TimeParser()
        self._recurrence_resolver = RecurrenceResolver()
        self._available: Optional[bool] = None  # None = 未检测

    @property
    def is_available(self) -> bool:
        """检查 Ollama 是否可用（首次调用时检测，缓存结果）"""
        if self._available is None:
            self._available = self._check_ollama()
        return self._available

    def reset_availability(self):
        """重置可用性状态（下次调用时重新检测）"""
        self._available = None

    def parse(self, text: str) -> Optional[List[ParsedCommand]]:
        """一次 LLM 调用完成多指令解析

        Args:
            text: 语音识别后的文本（无标点，已纠错）

        Returns:
            ParsedCommand 列表，或 None（LLM 不可用/调用失败时）
        """
        if not text or not text.strip():
            return None

        if not self.is_available:
            return None

        try:
            # 调用 LLM
            response = self._call_ollama(text)
            if response is None:
                return None

            # 解析 JSON 响应
            commands = self._parse_response(response, text)
            if commands:
                # 应用日期上下文继承（LLM 可能遗漏）
                commands = self._apply_date_inheritance(commands)
                logger.info(f"LLMParser: 成功解析 {len(commands)} 条指令")
            return commands

        except Exception as e:
            logger.warning(f"LLMParser: 解析异常 - {e}")
            return None

    def _call_ollama(self, text: str) -> Optional[str]:
        """调用 Ollama /api/chat 接口

        Args:
            text: 用户输入文本

        Returns:
            LLM 响应文本，失败返回 None
        """
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,  # 低温度保证输出稳定
                "num_predict": 256,  # 限制输出长度，加速生成
            },
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            # 绕过系统代理访问本地 Ollama
            opener = request.build_opener(request.ProxyHandler({}))
            with opener.open(req, timeout=self._timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("message", {}).get("content", "")

        except urlerror.URLError as e:
            logger.debug(f"LLMParser: Ollama 连接失败 - {e}")
            self._available = False  # 标记不可用，避免重复尝试
            return None
        except TimeoutError:
            logger.warning("LLMParser: Ollama 响应超时")
            return None
        except Exception as e:
            logger.warning(f"LLMParser: 调用异常 - {e}")
            return None

    def _parse_response(self, response: str, original_text: str) -> Optional[List[ParsedCommand]]:
        """解析 LLM 返回的 JSON 数组

        Args:
            response: LLM 原始响应文本
            original_text: 原始用户输入（用于填充 original_text 字段）

        Returns:
            ParsedCommand 列表，解析失败返回 None
        """
        # 提取 JSON 部分（处理 LLM 可能包裹的 markdown 代码块）
        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        # 尝试找到 JSON 数组
        json_str = json_str.strip()
        if not json_str.startswith("["):
            # 尝试从响应中提取数组部分
            start = json_str.find("[")
            end = json_str.rfind("]")
            if start >= 0 and end > start:
                json_str = json_str[start : end + 1]
            else:
                logger.warning(f"LLMParser: 响应中未找到 JSON 数组: {response[:100]}")
                return None

        try:
            items = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"LLMParser: JSON 解析失败 - {e}, 响应: {json_str[:200]}")
            return None

        if not isinstance(items, list) or not items:
            return None

        # 转换为 ParsedCommand 列表
        commands: List[ParsedCommand] = []
        for item in items:
            cmd = self._item_to_command(item, original_text)
            if cmd is not None:
                commands.append(cmd)

        return commands if commands else None

    def _item_to_command(self, item: dict, original_text: str) -> Optional[ParsedCommand]:
        """将单个 JSON 对象转换为 ParsedCommand

        LLM 提取文本级信息，TimeParser 计算精确时间。

        Args:
            item: LLM 输出的单条指令 JSON
            original_text: 原始输入文本

        Returns:
            ParsedCommand 或 None
        """
        if not isinstance(item, dict):
            return None

        # 1. 解析意图类型
        cmd_type = self._TYPE_MAP.get(item.get("type", ""), CommandType.UNKNOWN)
        if cmd_type == CommandType.UNKNOWN:
            return None

        # 2. 提取标题（应用口语清理）
        title = self._clean_title(item.get("title", "").strip())

        # 3. 解析时间（拼接 date + time 交给 TimeParser）
        date_expr = item.get("date", "").strip()
        time_expr = item.get("time", "").strip()
        time_text = f"{date_expr}{time_expr}".strip()

        parsed_time = None
        if time_text:
            parsed_time, _ = self._time_parser.parse(time_text)

        # 4. 解析循环规则
        recurrence_rule = ""
        recurrence_end = None
        recurrence_expr = item.get("recurrence", "").strip()
        if recurrence_expr:
            rec_result = self._recurrence_resolver.resolve(recurrence_expr)
            recurrence_rule = rec_result.rule
            recurrence_end = rec_result.end_time
            # 如果循环解析提供了 start_time 且主时间未解析成功，使用它
            if parsed_time is None and rec_result.start_time:
                parsed_time = rec_result.start_time

        # 5. 优先级
        priority = self._PRIORITY_MAP.get(item.get("priority", "普通"), 0)

        # 6. 如果有循环但主时间仍为 None，尝试从 time_expr 单独解析时间部分
        if parsed_time is None and time_expr:
            parsed_time, _ = self._time_parser.parse(time_expr)

        return ParsedCommand(
            command_type=cmd_type,
            title=title,
            time=parsed_time,
            end_time=None,
            priority=priority,
            recurrence_rule=recurrence_rule,
            recurrence_end=recurrence_end,
            original_text=original_text,
            confidence=0.9,  # LLM 解析的置信度较高
        )

    # 口语填充词（与 RuleEngine 保持一致）
    _ORAL_FILLERS = ["个", "了", "啊", "吧", "呢"]
    _ORAL_PREFIXES = ["去", "来", "得"]

    @classmethod
    def _clean_title(cls, title: str) -> str:
        """清理 LLM 返回的标题（去除口语填充词）

        例: "开个会" → "开会", "去买菜" → "买菜"
        """
        if not title:
            return title
        for filler in cls._ORAL_FILLERS:
            title = title.replace(filler, "")
        for prefix in cls._ORAL_PREFIXES:
            if title.startswith(prefix) and len(title) > len(prefix):
                title = title[len(prefix) :]
        return title.strip()

    def _check_ollama(self) -> bool:
        """检查 Ollama 服务是否在运行"""
        try:
            url = f"{self._base_url}/api/tags"
            # 使用 ProxyHandler 绕过代理
            opener = request.build_opener(request.ProxyHandler({}))
            req = request.Request(url, method="GET")
            with opener.open(req, timeout=1.0) as resp:
                if resp.status == 200:
                    logger.info("LLMParser: Ollama 服务可用")
                    return True
        except Exception:
            pass
        logger.info("LLMParser: Ollama 服务不可用，将使用规则引擎")
        return False

    def _apply_date_inheritance(self, commands: List[ParsedCommand]) -> List[ParsedCommand]:
        """后处理：日期上下文继承

        当 LLM 未正确处理日期继承时，检测并修复：
        如果一条指令的时间看起来默认到了"今天"但前一条在未来日期，
        则继承前一条的日期。
        """

        if len(commands) <= 1:
            return commands

        today = datetime.now().date()
        last_future_date = None  # 最近一条有明确未来日期的日期

        for i, cmd in enumerate(commands):
            if cmd.time is None:
                continue

            cmd_date = cmd.time.date()

            if cmd_date > today:
                # 这条有明确未来日期，记录
                last_future_date = cmd_date
            elif cmd_date == today and last_future_date is not None and i > 0:
                # 这条落在"今天"但前面有未来日期 → 可能是日期继承遗漏
                # 只对 ADD_EVENT 做修复（查询/删除不做假设）
                if cmd.command_type == CommandType.ADD_EVENT:
                    corrected_time = cmd.time.replace(
                        year=last_future_date.year,
                        month=last_future_date.month,
                        day=last_future_date.day,
                    )
                    commands[i] = ParsedCommand(
                        command_type=cmd.command_type,
                        title=cmd.title,
                        time=corrected_time,
                        end_time=cmd.end_time,
                        priority=cmd.priority,
                        recurrence_rule=cmd.recurrence_rule,
                        recurrence_end=cmd.recurrence_end,
                        original_text=cmd.original_text,
                        confidence=cmd.confidence,
                    )
                    logger.info(
                        f"LLMParser: 日期继承修复 '{cmd.title}' "
                        f"{cmd.time.strftime('%m-%d')} -> {corrected_time.strftime('%m-%d')}"
                    )

        return commands
