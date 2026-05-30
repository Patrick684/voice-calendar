"""快速验证 CommandRouter 路由逻辑（含 LLM 端到端）"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

logging.basicConfig(level=logging.INFO)

from command.parser import CommandParser

p = CommandParser(llm_enabled=True, llm_parser_model="qwen2.5:3b", llm_parser_timeout=5.0)

print(f"LLM Available: {p._llm_parser.is_available}")
print()

# 测试用例
cases = [
    # (输入, 预期指令数, 预期类型列表)
    # 简单指令（快速路径）
    ("删除后天上午酒店看牙医", 1, ["delete_event"]),
    ("上午十点面试", 1, ["add_event"]),
    ("查看明天的安排", 1, ["query_event"]),
    ("每天早上八点跑步", 1, ["add_event"]),
    ("明天下午三点开会", 1, ["add_event"]),
    # 多指令（LLM 路径或规则回退）
    ("明天下午三点不健身了上午十点面试后天上午十点的面试取消", None, None),  # LLM可能拆为2-3条，不严格检查
    ("后天上午十点开会还有下午三点面试", 2, ["add_event", "add_event"]),
    # 口语表达
    ("明天下午三点开个会", 1, ["add_event"]),
]

passed = 0
failed = 0

for text, expected_count, expected_types in cases:
    results = p.parse_multiple(text)
    actual_types = [r.command_type.value for r in results]

    # expected_count=None 表示不严格检查（LLM 可能有多种合理解读）
    if expected_count is None:
        passed += 1
        titles = [r.title for r in results]
        print(f"  [OK*] {text} -> {actual_types} titles={titles} (不严格)")
        continue

    ok_count = len(results) == expected_count
    ok_types = actual_types == expected_types

    if ok_count and ok_types:
        passed += 1
        titles = [r.title for r in results]
        print(f"  [OK] {text} -> {actual_types} titles={titles}")
    else:
        failed += 1
        print(f"  [FAIL] {text}")
        print(f"         Expected: {expected_count} cmds, {expected_types}")
        print(f"         Got:      {len(results)} cmds, {actual_types}")
        for r in results:
            print(f"           - {r.command_type.value}: '{r.title}' conf={r.confidence}")

print(f"\n{'=' * 50}")
print(f"Result: {passed} passed, {failed} failed")
if failed == 0:
    print("All routing tests passed!")
