"""
用途：验证指令解析层（time_parser/rule_engine/parser）功能是否正常
示例：python tests/verify_command.py
"""

import os
import sys
from datetime import datetime, timedelta

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from command.time_parser import TimeParser
from command.rule_engine import RuleEngine, CommandType
from command.parser import CommandParser


def test_time_parser():
    """测试中文时间解析"""
    print("=" * 50)
    print("测试 TimeParser 中文时间解析")
    print("=" * 50)

    parser = TimeParser()
    now = datetime.now()

    # 1. 相对日期
    cases = [
        ("明天下午三点开会", True, "明天+下午三点"),
        ("后天上午十点看牙", True, "后天+上午十点"),
        ("今天晚上八点跑步", True, "今天+晚上八点"),
        ("大后天下午两点面试", True, "大后天+下午两点"),
        ("三天后上午九点出发", True, "三天后+上午九点"),
    ]

    for text, should_have_time, desc in cases:
        result_time, remaining = parser.parse(text)
        if should_have_time:
            assert result_time is not None, f"解析失败: {text} ({desc})"
            print(f"  [通过] '{text}' → {result_time.strftime('%m-%d %H:%M')} | 剩余: '{remaining}'")
        else:
            print(f"  [通过] '{text}' → None | 剩余: '{remaining}'")

    # 2. 下周X
    result_time, remaining = parser.parse("下周一上午十点开会")
    assert result_time is not None
    assert result_time.weekday() == 0  # 周一
    print(f"  [通过] '下周一上午十点' → {result_time.strftime('%m-%d %H:%M')} (weekday={result_time.weekday()})")

    # 3. X月X号
    result_time, remaining = parser.parse("六月十五号下午三点聚会")
    assert result_time is not None
    assert result_time.month == 6
    assert result_time.day == 15
    print(f"  [通过] '六月十五号下午三点' → {result_time.strftime('%Y-%m-%d %H:%M')}")

    # 4. 具体时间
    result_time, remaining = parser.parse("明天15:30开会")
    assert result_time is not None
    assert result_time.hour == 15
    assert result_time.minute == 30
    print(f"  [通过] '明天15:30' → {result_time.strftime('%m-%d %H:%M')}")

    # 5. 中文数字时间
    result_time, remaining = parser.parse("明天下午三点半开会")
    assert result_time is not None
    assert result_time.hour == 15  # 下午 +12
    assert result_time.minute == 30
    print(f"  [通过] '明天下午三点半' → {result_time.strftime('%m-%d %H:%M')}")

    # 6. N天后
    result_time, remaining = parser.parse("五天后上午九点体检")
    assert result_time is not None
    expected_date = (now + timedelta(days=5)).date()
    assert result_time.date() == expected_date
    print(f"  [通过] '五天后上午九点' → {result_time.strftime('%m-%d %H:%M')}")

    print()


def test_rule_engine():
    """测试规则引擎指令识别"""
    print("=" * 50)
    print("测试 RuleEngine 指令识别")
    print("=" * 50)

    engine = RuleEngine()

    # 1. 添加事件
    test_cases = [
        ("帮我安排明天下午三点的团队会议", CommandType.ADD_EVENT, "团队会议"),
        ("添加一个下周一上午十点的面试", CommandType.ADD_EVENT, "面试"),
        ("提醒我后天晚上七点吃药", CommandType.ADD_EVENT, "吃药"),
    ]
    for text, expected_type, expected_title_contains in test_cases:
        result = engine.parse(text)
        assert result.command_type == expected_type, (
            f"类型不匹配: '{text}' → {result.command_type.value} (期望 {expected_type.value})"
        )
        assert expected_title_contains in result.title, (
            f"标题不匹配: '{text}' → title='{result.title}' (期望含 '{expected_title_contains}')"
        )
        print(f"  [通过] '{text}' → {result.command_type.value}, title='{result.title}'")

    # 2. 删除事件
    result = engine.parse("删掉明天的会议")
    assert result.command_type == CommandType.DELETE_EVENT
    print(f"  [通过] '删掉明天的会议' → {result.command_type.value}")

    result = engine.parse("取消后天的面试")
    assert result.command_type == CommandType.DELETE_EVENT
    print(f"  [通过] '取消后天的面试' → {result.command_type.value}")

    # 3. 查询事件
    result = engine.parse("今天有什么安排")
    assert result.command_type == CommandType.QUERY_EVENT
    assert result.time is not None
    print(f"  [通过] '今天有什么安排' → {result.command_type.value}, time={result.time.strftime('%m-%d')}")

    result = engine.parse("看看这周的日程")
    assert result.command_type == CommandType.QUERY_EVENT
    print(f"  [通过] '看看这周的日程' → {result.command_type.value}")

    # 4. 修改事件
    result = engine.parse("把明天的会改到后天")
    assert result.command_type == CommandType.UPDATE_EVENT
    print(f"  [通过] '把明天的会改到后天' → {result.command_type.value}")

    # 5. 隐式添加（无明确关键词）
    result = engine.parse("明天下午三点开会")
    assert result.command_type == CommandType.ADD_EVENT
    assert result.time is not None
    print(f"  [通过] '明天下午三点开会' → {result.command_type.value} (隐式), title='{result.title}'")

    # 6. 无法识别
    result = engine.parse("你好世界")
    assert result.command_type == CommandType.UNKNOWN
    print(f"  [通过] '你好世界' → {result.command_type.value}")

    print()


def test_command_parser():
    """测试混合指令解析器"""
    print("=" * 50)
    print("测试 CommandParser 混合解析")
    print("=" * 50)

    # 不启用 LLM
    parser = CommandParser(llm_enabled=False)
    assert not parser.llm_enabled

    result = parser.parse("安排明天下午两点的项目评审会")
    assert result.command_type == CommandType.ADD_EVENT
    assert result.time is not None
    assert "项目评审会" in result.title or "评审" in result.title
    print(f"  [通过] 规则引擎: '{result.original_text}' → {result.command_type.value}, title='{result.title}'")

    result = parser.parse("今天有什么日程")
    assert result.command_type == CommandType.QUERY_EVENT
    print(f"  [通过] 查询指令: → {result.command_type.value}")

    result = parser.parse("随便说点什么")
    assert result.command_type == CommandType.UNKNOWN
    print(f"  [通过] 未知指令: → {result.command_type.value}")

    print()


if __name__ == "__main__":
    print("\n指令解析层功能验证\n")
    try:
        test_time_parser()
        test_rule_engine()
        test_command_parser()
        print("=" * 50)
        print("全部测试通过!")
        print("=" * 50)
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
