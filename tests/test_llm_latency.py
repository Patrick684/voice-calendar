"""测试 LLM (qwen2.5:3b via Ollama) 热启动延迟"""

import json
import time
import os
from urllib import request

os.environ["NO_PROXY"] = "localhost,127.0.0.1"

SYSTEM_PROMPT = """你是日历语音指令解析器。用户通过语音输入日历操作指令（无标点符号）。
请将输入拆分为独立指令，每条指令提取以下字段。

输出格式（严格 JSON 数组，不要输出任何其他内容）:
[{
  "type": "add" | "delete" | "query" | "update",
  "title": "事件标题",
  "date": "日期表达或空字符串",
  "time": "时间表达或空字符串",
  "recurrence": "循环规则或空字符串",
  "priority": "普通"
}]

规则：
- add: 添加/安排事件，或隐式添加（有日期时间+事件标题即视为添加）
- delete: 删除/取消事件，包括"不X了"的否定表达
- query: 查看/查询日程
- update: 修改/推迟/提前
- title 只保留事件核心描述，不含时间、日期、命令动词"""

test_cases = [
    "明天下午三点开会",
    "后天上午十点面试还有下午三点去健身",
    "取消明天的会议",
    "把后天的会改到下午四点",
    "下周一上午十点开会下午两点面试晚上八点跑步",
    "帮我安排明天下午三点的团队会议",
    "每周五下午三点开周会",
    "不去健身了",
]

opener = request.build_opener(request.ProxyHandler({}))
results = []

print("=" * 60)
print("LLM 延迟测试 (qwen2.5:3b, 热启动)")
print("=" * 60)
print()

for text in test_cases:
    payload = json.dumps(
        {
            "model": "qwen2.5:3b",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 256,
            },
        }
    ).encode("utf-8")

    req = request.Request(
        "http://localhost:11434/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    t0 = time.time()
    try:
        resp = opener.open(req, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - t0
        content = data.get("message", {}).get("content", "")
        # 尝试解析 JSON 验证格式
        try:
            parsed = json.loads(content)
            summary = json.dumps(parsed, ensure_ascii=False)[:80]
        except json.JSONDecodeError:
            summary = content[:80]

        status = "OK" if elapsed < 1.0 else "SLOW"
        print(f"  [{elapsed:.2f}s] [{status}] '{text}'")
        print(f"         -> {summary}")
        results.append(elapsed)
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [{elapsed:.2f}s] [ERR] '{text}' -> {e}")
        results.append(elapsed)
    print()

print("=" * 60)
print("统计")
print("=" * 60)
print(f"  样本数: {len(results)}")
print(f"  平均延迟: {sum(results) / len(results):.2f}s")
print(f"  最小延迟: {min(results):.2f}s")
print(f"  最大延迟: {max(results):.2f}s")
print(f"  < 1s 占比: {sum(1 for r in results if r < 1.0)}/{len(results)}")
print(f"  < 0.5s 占比: {sum(1 for r in results if r < 0.5)}/{len(results)}")
