"""验证新增的时间解析功能：时段扩展 + 模糊日期词"""

import sys

sys.path.insert(0, ".")

from command.time_parser import TimeParser
from command.parser import CommandParser

tp = TimeParser()
cp = CommandParser()

print("=" * 60)
print("测试 TimeParser 新增时段词（清晨/深夜/午夜/黎明）")
print("=" * 60)

cases_period = [
    ("清晨七点跑步", "跑步", 7),
    ("深夜十一点看电影", "看电影", 23),
    ("黎明五点出发", "出发", 5),
    ("清晨开会", "开会", 6),  # 清晨默认6点
    ("深夜加班", "加班", 23),  # 深夜默认23点
    ("黎明起床", "起床", 5),  # 黎明默认5点
]

pass_count = 0
fail_count = 0

for text, expect_title, expect_hour in cases_period:
    result_time, remaining = tp.parse(text)
    title = remaining.strip()
    ok_time = result_time is not None and result_time.hour == expect_hour
    ok_title = expect_title in title
    if ok_time and ok_title:
        print(f"  [PASS] '{text}' => {result_time.strftime('%H:%M')}, title='{title}'")
        pass_count += 1
    else:
        print(
            f"  [FAIL] '{text}' => time={result_time}, title='{title}' (expect hour={expect_hour}, title含'{expect_title}')"
        )
        fail_count += 1

print()
print("=" * 60)
print("测试 TimeParser 模糊日期词（月底/月初/月末/年底/年初/周末）")
print("=" * 60)

cases_fuzzy = [
    ("月底交报告", "交报告", True),
    ("月初开会", "开会", True),
    ("月末汇总", "汇总", True),
    ("年底总结", "总结", True),
    ("年初计划", "计划", True),
    ("周末聚餐", "聚餐", True),
    ("周末下午三点聚餐", "聚餐", True),
]

for text, expect_title, expect_has_time in cases_fuzzy:
    result_time, remaining = tp.parse(text)
    title = remaining.strip()
    ok_time = (result_time is not None) == expect_has_time
    ok_title = expect_title in title
    if ok_time and ok_title:
        time_str = result_time.strftime("%Y-%m-%d %H:%M") if result_time else "None"
        print(f"  [PASS] '{text}' => {time_str}, title='{title}'")
        pass_count += 1
    else:
        print(
            f"  [FAIL] '{text}' => time={result_time}, title='{title}' (expect has_time={expect_has_time}, title含'{expect_title}')"
        )
        fail_count += 1

print()
print("=" * 60)
print("测试 CommandParser 端到端（新时间词 + 事件添加）")
print("=" * 60)

cases_e2e = [
    ("清晨七点跑步", "add_event", "跑步"),
    ("月底交报告", "add_event", "交报告"),
    ("周末聚餐", "add_event", "聚餐"),
    ("年底总结会", "add_event", "总结会"),
    ("深夜十一点看球赛", "add_event", "看球赛"),
]

for text, expect_type, expect_title in cases_e2e:
    results = cp.parse_multiple(text)
    if results:
        r = results[0]
        ok_type = r.command_type.value == expect_type
        ok_title = expect_title in r.title
        if ok_type and ok_title:
            time_str = r.time.strftime("%m-%d %H:%M") if r.time else "None"
            print(f"  [PASS] '{text}' => {r.command_type.value}, title='{r.title}', time={time_str}")
            pass_count += 1
        else:
            print(
                f"  [FAIL] '{text}' => type={r.command_type.value}, title='{r.title}' (expect {expect_type}, '{expect_title}')"
            )
            fail_count += 1
    else:
        print(f"  [FAIL] '{text}' => 无结果 (expect {expect_type})")
        fail_count += 1

print()
print("=" * 60)
print("测试纯时间词不触发 add_event")
print("=" * 60)

pure_time_cases = ["月底", "月初", "年底", "周末", "清晨", "深夜"]
for text in pure_time_cases:
    results = cp.parse_multiple(text)
    if not results:
        print(f"  [PASS] '{text}' => 空结果（正确过滤纯时间）")
        pass_count += 1
    else:
        print(f"  [FAIL] '{text}' => {results[0].command_type.value} (应返回空)")
        fail_count += 1

print()
print(f"结果: {pass_count} 通过, {fail_count} 失败 (共 {pass_count + fail_count} 个)")
