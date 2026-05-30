"""诊断交互日志中记录的 bug"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from command.parser import CommandParser
from command.rule_engine import RuleEngine
from command.time_parser import TimeParser
from command.recurrence_resolver import RecurrenceResolver

print("=" * 60)
print("1. 循环事件 recurrence 检测")
print("=" * 60)

tp = TimeParser()
rr = RecurrenceResolver()
re_engine = RuleEngine()

# 检查 TimeParser 对 "下个月下午四点健身" 的行为
t, r = tp.parse("下个月下午四点健身")
print(f"  TimeParser('下个月下午四点健身') => time={t}, remaining=[{r}]")

t, r = tp.parse("下个月")
print(f"  TimeParser('下个月') => time={t}, remaining=[{r}]")

# 检查 RuleEngine 直接解析
result = re_engine.parse("下个月每周五下午四点健身")
print(
    f"  RuleEngine('下个月每周五下午四点健身') => type={result.command_type.value}, title=[{result.title}], rec=[{result.recurrence_rule}]"
)

result = re_engine.parse("这个月每周五下午四点健身")
print(
    f"  RuleEngine('这个月每周五下午四点健身') => type={result.command_type.value}, title=[{result.title}], rec=[{result.recurrence_rule}]"
)

print()
print("=" * 60)
print("2. parse_multiple 路由测试")
print("=" * 60)

p = CommandParser(llm_enabled=False, intent_model_enabled=False)

cases = [
    "下个月每周五下午四点健身",
    "这个月每周五下午四点健身",
    "这周每天下午两点都要午睡",
    "下周每天早上十点都要起床",
    "删除今天的所有事件",
    "查看本周所有安排",
    "下个月1号上午9点年度总结会",
    "明天上午十点去银行删掉上周的购物提醒每周二下午一点学英语",
]

for text in cases:
    results = p.parse_multiple(text)
    print(f"  '{text}'")
    for r in results:
        time_str = r.time.strftime("%m-%d %H:%M") if r.time else "None"
        print(f"    -> {r.command_type.value}: title=[{r.title}] rec=[{r.recurrence_rule}] time={time_str}")
    if not results:
        print("    -> (空)")
    print()

print("=" * 60)
print("3. 日志中记录的已知问题")
print("=" * 60)

problem_cases = [
    # (输入, 期望类型, 期望标题, 期望循环)
    ("这周每天下午两点都要午睡", "add_event", "午睡", "FREQ=DAILY"),
    ("下个月每周五下午四点健身", "add_event", "健身", "FREQ=WEEKLY;BYDAY=FR"),
    ("删除今天的所有事件", "delete_event", "", ""),
    ("查看本周所有安排", "query_event", "", ""),
    ("下个月1号上午9点年度总结会", "add_event", "年度总结会", ""),
]

passed = 0
failed = 0
for text, exp_type, exp_title, exp_rec in problem_cases:
    results = p.parse_multiple(text)
    if not results:
        print(f"  [FAIL] '{text}' => 空结果")
        failed += 1
        continue
    r = results[0]
    ok = True
    issues = []
    if r.command_type.value != exp_type:
        issues.append(f"type: got {r.command_type.value}, expected {exp_type}")
        ok = False
    if exp_title and r.title != exp_title:
        issues.append(f"title: got [{r.title}], expected [{exp_title}]")
        ok = False
    if r.recurrence_rule != exp_rec:
        issues.append(f"rec: got [{r.recurrence_rule}], expected [{exp_rec}]")
        ok = False
    if ok:
        print(f"  [OK] '{text}' => {r.command_type.value}, title=[{r.title}], rec=[{r.recurrence_rule}]")
        passed += 1
    else:
        print(f"  [FAIL] '{text}' => {'; '.join(issues)}")
        failed += 1

print(f"\n结果: {passed} 通过, {failed} 失败")
