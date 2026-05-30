"""批量模拟语音测试 - 读取 voice_test_scripts.txt 的台词，直接喂给规则引擎"""

import sys
import io
import re
import os

# 强制 UTF-8 输出（解决 Windows 终端中文乱码）
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from command.rule_engine import RuleEngine

engine = RuleEngine()

# 读取台词文件
script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice_test_scripts.txt")
with open(script_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 解析台词
test_cases = []
current_section = ""
for line in lines:
    line = line.strip()
    # 检测分组标题 (中文数字序号)
    if re.match(r"^[一二三四五六七八九十百千]+、", line):
        current_section = line
        continue
    # 检测测试台词
    match = re.match(r"\[(轻量|LLM|边界)\]\s+(.+)", line)
    if match:
        level = match.group(1)
        text = match.group(2)
        # 去掉行尾注释 (#后面的内容)
        if "#" in text:
            text = text[: text.index("#")].strip()
        # 跳过标注说明行（如 "= 规则引擎应能正确处理"）
        if text.startswith("= ") or text.startswith("="):
            continue
        test_cases.append((current_section, level, text))

# 统计
stats = {"pass": 0, "fail": 0, "expected_fail": 0, "boundary": 0}
results_by_section = {}

print("=" * 80)
print("  语音台词批量测试 - 规则引擎解析")
print("=" * 80)
print()

prev_section = ""
for section, level, text in test_cases:
    if section != prev_section:
        sep = "\u2500" * 80
        print(f"\n{sep}")
        print(f"  {section}")
        print(sep)
        prev_section = section
        if section and section not in results_by_section:
            results_by_section[section] = {"pass": 0, "fail": 0, "total": 0}

    # 解析
    result = engine.parse(text)
    cmd = result.command_type.value
    time_str = result.time.strftime("%m-%d %H:%M") if result.time else "N/A"
    title = result.title or ""
    conf = result.confidence
    rrule = result.recurrence_rule or ""
    end_str = result.end_time.strftime("%H:%M") if result.end_time else ""

    # 判断结果
    if level == "LLM":
        # LLM 专属台词，轻量预期失败或部分解析
        tag = "LLM"
        stats["expected_fail"] += 1
    elif level == "边界":
        tag = "EDGE"
        stats["boundary"] += 1
    else:
        # 轻量模式应该正确解析
        # 基本判定逻辑
        is_ok = False
        if "删除" in section or "否定" in section:
            is_ok = cmd == "delete_event" and conf > 0
        elif "查询" in section:
            is_ok = cmd == "query_event" and conf > 0
        elif "修改" in section:
            is_ok = cmd == "update_event" and conf > 0
        elif "循环" in section:
            is_ok = cmd == "add_event" and rrule != "" and conf > 0
        elif "过去" in section:
            # 过去日期查询或记录
            is_ok = cmd in ("query_event", "add_event") and conf > 0
        elif "非日历" in section:
            is_ok = cmd == "unknown"
        else:
            # 添加事件相关
            is_ok = cmd == "add_event" and conf > 0 and title != ""

        if is_ok:
            tag = "OK"
            stats["pass"] += 1
            if section:
                results_by_section[section]["pass"] += 1
        else:
            tag = "FAIL"
            stats["fail"] += 1
            if section:
                results_by_section[section]["fail"] += 1
        if section:
            results_by_section[section]["total"] += 1

    # 输出
    duration_info = f" -> {end_str}" if end_str else ""
    rrule_info = f" [R:{rrule}]" if rrule else ""
    print(f"  [{tag:4s}] '{text}'")
    print(f"         => {cmd} | {time_str}{duration_info} | '{title}'{rrule_info} (conf={conf:.1f})")

# 汇总
print()
print("=" * 80)
print("  测试汇总")
print("=" * 80)
print(f"  轻量模式:  {stats['pass']} PASS / {stats['fail']} FAIL")
print(f"  LLM专属:   {stats['expected_fail']} 条 (预期轻量无法完美处理)")
print(f"  边界测试:  {stats['boundary']} 条")
print()

if results_by_section:
    print("  分组详情 (仅轻量模式):")
    for section, data in results_by_section.items():
        if data["total"] > 0:
            rate = data["pass"] / data["total"] * 100
            status = "ALL PASS" if data["fail"] == 0 else f"{data['fail']} FAIL"
            print(f"    {section[:20]:20s}  {data['pass']}/{data['total']} ({rate:.0f}%) {status}")

print()
if stats["fail"] > 0:
    print(f"  *** {stats['fail']} 条轻量台词解析失败，需要排查 ***")
else:
    print("  *** 轻量模式全部通过! ***")
