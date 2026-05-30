"""测试 Ollama 冷启动延迟和 LLM 解析"""

import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["NO_PROXY"] = "localhost,127.0.0.1"

from urllib import request

# 1. 预热测试（首次调用，模型加载到 VRAM）
print("=" * 50)
print("1. 预热测试（模型冷启动）")
print("=" * 50)

payload = json.dumps(
    {
        "model": "qwen2.5:3b",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "options": {"num_predict": 5},
    }
).encode()

req = request.Request(
    "http://localhost:11434/api/chat",
    data=payload,
    headers={"Content-Type": "application/json"},
)
opener = request.build_opener(request.ProxyHandler({}))

t0 = time.time()
resp = opener.open(req, timeout=120)
data = json.loads(resp.read())
cold_time = time.time() - t0
print(f"冷启动耗时: {cold_time:.1f}s")
print(f"响应: {data.get('message', {}).get('content', '')[:50]}")
print()

# 2. 热启动测试（模型已在 VRAM）
print("=" * 50)
print("2. 热启动测试")
print("=" * 50)

from command.llm_parser import LLMParser

parser = LLMParser(timeout=5.0)  # 热启动用 5s 应该够了
parser._available = True  # 跳过检测（已确认可用）

test_cases = [
    "明天下午三点开会",
    "后天上午十点面试还有下午三点去健身",
    "取消明天的会议",
]

for text in test_cases:
    t0 = time.time()
    results = parser.parse(text)
    elapsed = time.time() - t0
    if results:
        for r in results:
            print(f"  [{elapsed:.2f}s] {text} -> {r.command_type.value}: '{r.title}'")
    else:
        print(f"  [{elapsed:.2f}s] {text} -> None (LLM失败)")
