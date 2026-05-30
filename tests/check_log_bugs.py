# -*- coding: utf-8 -*-
"""检查交互日志中的 bug 是否已修复"""

import sys

sys.path.insert(0, ".")
from command.parser import CommandParser

p = CommandParser(llm_enabled=False)

cases = [
    # (input_text, expected_type, expected_title, expected_recurrence)
    # 循环事件
    ("这周每天下午两点都要午睡", "add_event", "午睡", "FREQ=DAILY"),
    ("下周每天早上十点都要起床", "add_event", "起床", "FREQ=DAILY"),
    ("下个月每周五下午四点健身", "add_event", "健身", "FREQ=WEEKLY;BYDAY=FR"),
    ("下周每天早上七点起床打卡", "add_event", "起床打卡", "FREQ=DAILY"),
    ("每天早上七点起床打卡", "add_event", "起床打卡", "FREQ=DAILY"),
    ("每周五下午四点健身", "add_event", "健身", "FREQ=WEEKLY;BYDAY=FR"),
    ("每周六下午五点健身", "add_event", "健身", "FREQ=WEEKLY;BYDAY=SA"),
    ("每个工作日早上九点打卡", "add_event", "打卡", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"),
    # 删除/查询 不应产生额外 add_event
    ("删除今天的所有事件", "delete_event", None, ""),
    ("删除明天的所有事件", "delete_event", None, ""),
    ("查看本周所有安排", "query_event", None, ""),
    ("查看本周的所有安排", "query_event", None, ""),
    # 时间格式
    ("下个月1号上午9点年度总结会", "add_event", "年度总结会", ""),
    ("下个月1号上午十点年度总结会", "add_event", "年度总结会", ""),
    # 优先级前缀
    ("重要的后天晚上8点家庭聚餐", "add_event", "家庭聚餐", ""),
    ("紧急的今天下午两点项目评审会", "add_event", "项目评审会", ""),
    # 标题清理
    ("今天开会 大概是下午两点", "add_event", "开会", ""),
    ("明天下午三点半和客户谈合作", "add_event", "和客户谈合作", ""),
    ("下周一上午十点公司团建", "add_event", "公司团建", ""),
    # ASR 同音纠错
    ("山除后天的鸭鱼", "delete_event", None, ""),
    ("山图下周一的所有事件", "delete_event", None, ""),
]

passed = 0
failed = 0

for text, exp_type, exp_title, exp_rec in cases:
    results = p.parse_multiple(text)

    # Check
    ok = False
    if exp_type in ("delete_event", "query_event"):
        # 不能有额外的 add_event，且第一个结果类型正确
        if results and results[0].command_type.value == exp_type:
            # 检查是否有多余的 add_event
            spurious = [r for r in results if r.command_type.value == "add_event"]
            ok = len(spurious) == 0
    else:
        # add_event: 只应有1个结果，title和recurrence匹配
        matching = [r for r in results if r.command_type.value == "add_event"]
        if len(matching) == 1:
            r = matching[0]
            title_ok = (exp_title is None) or (r.title == exp_title)
            rec_ok = (not exp_rec) or (r.recurrence_rule == exp_rec)
            ok = title_ok and rec_ok

    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1

    if not ok:
        print(f"  [FAIL] '{text}'")
        print(f"         期望: type={exp_type}, title={exp_title}, rec={exp_rec}")
        print(f"         实际: {[(r.command_type.value, r.title, r.recurrence_rule) for r in results]}")
    else:
        print(
            f"  [PASS] '{text}' => {results[0].command_type.value}, title='{results[0].title}', rec='{results[0].recurrence_rule}'"
        )

print(f"\n结果: {passed} 通过, {failed} 失败 (共 {passed + failed} 个)")
