"""LLM 兜底指令解析 - 当规则引擎无法识别时使用大模型解析

支持两种 LLM 后端:
- Ollama: 本地部署（默认）
- OpenAI 兼容 API: 远程服务
"""

import json
import logging
from datetime import datetime
from typing import Optional
from urllib import request, error as urlerror

from command.rule_engine import CommandType, ParsedCommand

logger = logging.getLogger(__name__)

# LLM 系统提示词：要求输出结构化 JSON
SYSTEM_PROMPT = """你是一个日历语音指令解析助手。用户会通过语音说出日历操作指令，请解析并返回 JSON 格式结果。

输出格式（严格 JSON，不要包含其他内容）：
{
  "command_type": "add_event" | "delete_event" | "query_event" | "update_event",
  "title": "事件标题（如有）",
  "time": "ISO 8601 格式时间（如有，根据当前时间推算）",
  "end_time": "结束时间（如有）"
}

当前时间: {current_time}

规则：
- add_event: 用户想要添加/创建/安排一个新事件
- delete_event: 用户想要删除/取消一个事件
- query_event: 用户想要查看/查询日程安排
- update_event: 用户想要修改/调整一个事件
- 如果无法识别意图，command_type 返回 "unknown"
- time 字段根据用户说的时间推算，格式为 YYYY-MM-DDTHH:MM:SS
- title 是事件的核心描述，去掉时间相关词汇"""


class LLMFallback:
    """LLM 兜底指令解析器"""

    def __init__(
        self,
        provider: str = "ollama",
        model: str = "qwen2.5:7b",
        base_url: str = "http://localhost:11434",
        timeout: int = 30,
    ):
        """
        初始化 LLM 解析器

        Args:
            provider: LLM 提供商 (ollama / openai)
            model: 模型名称
            base_url: API 地址
            timeout: 请求超时秒数
        """
        self._provider = provider
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def parse(self, text: str) -> Optional[ParsedCommand]:
        """使用 LLM 解析指令

        Args:
            text: 语音识别后的文本

        Returns:
            ParsedCommand 或 None（解析失败时）
        """
        try:
            response = self._call_llm(text)
            if response is None:
                return None
            return self._parse_response(response, text)
        except Exception as e:
            logger.error(f"LLM 解析失败: {e}")
            return None

    def _call_llm(self, text: str) -> Optional[str]:
        """调用 LLM API

        Args:
            text: 用户输入文本

        Returns:
            LLM 返回的文本，失败时返回 None
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        system_msg = SYSTEM_PROMPT.format(current_time=current_time)

        if self._provider == "ollama":
            return self._call_ollama(system_msg, text)
        elif self._provider == "openai":
            return self._call_openai(system_msg, text)
        else:
            logger.error(f"不支持的 LLM 提供商: {self._provider}")
            return None

    def _call_ollama(self, system_msg: str, user_msg: str) -> Optional[str]:
        """调用 Ollama API"""
        url = f"{self._base_url}/api/chat"
        payload = json.dumps(
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                "stream": False,
                "options": {"temperature": 0.1},
            }
        ).encode("utf-8")

        req = request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("message", {}).get("content")
        except urlerror.URLError as e:
            logger.warning(f"Ollama 连接失败: {e}（请确保 Ollama 服务已启动）")
            return None

    def _call_openai(self, system_msg: str, user_msg: str) -> Optional[str]:
        """调用 OpenAI 兼容 API"""
        url = f"{self._base_url}/v1/chat/completions"
        payload = json.dumps(
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.1,
            }
        ).encode("utf-8")

        req = request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except (urlerror.URLError, KeyError, IndexError) as e:
            logger.warning(f"OpenAI API 调用失败: {e}")
            return None

    def _parse_response(self, response: str, original_text: str) -> Optional[ParsedCommand]:
        """解析 LLM 返回的 JSON

        Args:
            response: LLM 返回的文本
            original_text: 原始用户输入

        Returns:
            ParsedCommand 或 None
        """
        # 尝试提取 JSON 块
        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(f"LLM 返回非 JSON 格式: {response[:200]}")
            return None

        # 映射 command_type
        cmd_type_str = data.get("command_type", "unknown")
        try:
            cmd_type = CommandType(cmd_type_str)
        except ValueError:
            cmd_type = CommandType.UNKNOWN

        # 解析时间
        parsed_time = self._parse_iso_time(data.get("time"))
        end_time = self._parse_iso_time(data.get("end_time"))

        return ParsedCommand(
            command_type=cmd_type,
            title=data.get("title", ""),
            time=parsed_time,
            end_time=end_time,
            original_text=original_text,
            confidence=0.7 if cmd_type != CommandType.UNKNOWN else 0.0,
        )

    @staticmethod
    def _parse_iso_time(time_str) -> Optional[datetime]:
        """解析 ISO 8601 时间字符串"""
        if not time_str:
            return None
        try:
            return datetime.fromisoformat(time_str)
        except (ValueError, TypeError):
            return None
