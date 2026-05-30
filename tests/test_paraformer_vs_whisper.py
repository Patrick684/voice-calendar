"""Paraformer vs Whisper 对比测试

测试方式：
1. 用 Windows SAPI TTS 合成中文测试音频（日历场景台词）
2. 分别用 Whisper 和 Paraformer 识别
3. 对比准确率（CER）和延迟

依赖：pip install pyttsx3 funasr faster-whisper soundfile
"""

import sys
import io
import os
import time
import wave
import tempfile
import numpy as np
from pathlib import Path

# 强制 UTF-8 输出
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 配置 HuggingFace 国内镜像
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ========== 测试台词（日历场景高频指令） ==========
TEST_CASES = [
    "明天下午三点开会",
    "后天上午十点看牙医",
    "帮我安排下周一的团队会议",
    "删除明天的会议",
    "今天晚上八点跑步",
    "每周五下午四点健身",
    "把明天的会改到后天",
    "这周有哪些日程",
    "提醒我后天晚上七点吃药",
    "大后天下午两点面试",
    "取消下周三的客户会面",
    "三天后上午九点出发",
    "月底交报告",
    "帮我记明天早上九点去银行办事",
    "每天早上七点起床打卡",
]


def calculate_cer(reference: str, hypothesis: str) -> float:
    """计算字符错误率 (Character Error Rate)"""
    # 简单编辑距离计算
    ref = list(reference.replace(" ", ""))
    hyp = list(hypothesis.replace(" ", ""))

    d = [[0] * (len(hyp) + 1) for _ in range(len(ref) + 1)]
    for i in range(len(ref) + 1):
        d[i][0] = i
    for j in range(len(hyp) + 1):
        d[0][j] = j

    for i in range(1, len(ref) + 1):
        for j in range(1, len(hyp) + 1):
            if ref[i - 1] == hyp[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                d[i][j] = min(
                    d[i - 1][j] + 1,  # 删除
                    d[i][j - 1] + 1,  # 插入
                    d[i - 1][j - 1] + 1,  # 替换
                )

    return d[len(ref)][len(hyp)] / max(len(ref), 1)


# ========== TTS 合成音频 ==========
def synthesize_audio_batch(texts: list, audio_dir: Path) -> list:
    """用 Windows SAPI TTS 批量合成中文语音为 WAV 文件"""
    import pyttsx3

    engine = pyttsx3.init()
    # 设置中文语音
    voices = engine.getProperty("voices")
    zh_voice = None
    for v in voices:
        if "chinese" in v.name.lower() or "zh" in v.id.lower() or "huihui" in v.name.lower():
            zh_voice = v
            break
    if zh_voice:
        engine.setProperty("voice", zh_voice.id)
        print(f"  TTS 语音: {zh_voice.name}")
    else:
        print("  TTS 语音: 默认（未找到中文语音）")

    engine.setProperty("rate", 150)  # 语速适中

    audio_files = []
    for i, text in enumerate(texts):
        audio_path = str(audio_dir / f"test_{i:02d}.wav")
        engine.save_to_file(text, audio_path)
        audio_files.append(audio_path)

    engine.runAndWait()
    return audio_files


def load_audio_file(filepath: str, target_sr: int = 16000) -> np.ndarray:
    """加载 WAV 音频文件为 numpy 数组 (16kHz, mono, float32)"""
    with wave.open(filepath, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_data = wf.readframes(n_frames)

    # 转为 numpy
    if sampwidth == 2:
        audio = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        audio = np.frombuffer(raw_data, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        audio = np.frombuffer(raw_data, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0

    # 立体声转单声道
    if n_channels > 1:
        audio = audio.reshape(-1, n_channels).mean(axis=1)

    # 重采样到 16kHz
    if framerate != target_sr:
        ratio = target_sr / framerate
        new_length = int(len(audio) * ratio)
        indices = np.linspace(0, len(audio) - 1, new_length)
        audio = np.interp(indices, np.arange(len(audio)), audio)

    return audio.astype(np.float32)


# ========== Whisper 引擎测试 ==========
def test_whisper(audio_files: list, test_texts: list) -> dict:
    """用 faster-whisper 测试识别"""
    print("\n" + "=" * 60)
    print("  Whisper (faster-whisper, small, int8, CPU)")
    print("=" * 60)

    from faster_whisper import WhisperModel

    # 使用本地缓存的模型
    cache_dir = os.path.join(os.environ.get("APPDATA", ""), "VoiceCalendar", "models")
    t0 = time.time()
    model = WhisperModel("small", device="cpu", compute_type="int8", download_root=cache_dir)
    load_time = time.time() - t0
    print(f"  模型加载耗时: {load_time:.2f}s")

    results = []
    total_time = 0

    for i, (audio_path, ref_text) in enumerate(zip(audio_files, test_texts)):
        audio = load_audio_file(audio_path)

        t0 = time.time()
        segments, _ = model.transcribe(
            audio,
            language="zh",
            beam_size=5,
            vad_filter=True,
            initial_prompt="普通话，简体。语音日历助手，添加删除修改查询日程。",
        )
        text = "".join([s.text for s in segments]).strip()
        elapsed = time.time() - t0
        total_time += elapsed

        # 去除标点进行比较
        import unicodedata

        clean_text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("P")).strip()

        cer = calculate_cer(ref_text, clean_text)
        status = "OK" if cer == 0 else f"CER={cer:.0%}"
        results.append({"ref": ref_text, "hyp": clean_text, "cer": cer, "time": elapsed})

        print(f"  [{i + 1:2d}] {status:>8s} | {elapsed:.2f}s | '{ref_text}' → '{clean_text}'")

    avg_cer = np.mean([r["cer"] for r in results])
    avg_time = total_time / len(results)
    perfect = sum(1 for r in results if r["cer"] == 0)

    print(f"\n  {'─' * 50}")
    print(f"  平均 CER: {avg_cer:.1%}")
    print(f"  完全正确: {perfect}/{len(results)} ({perfect / len(results):.0%})")
    print(f"  平均延迟: {avg_time:.2f}s/条")
    print(f"  总耗时:   {total_time:.2f}s")

    return {"results": results, "avg_cer": avg_cer, "avg_time": avg_time, "perfect": perfect}


# ========== Paraformer 引擎测试 ==========
def test_paraformer(audio_files: list, test_texts: list) -> dict:
    """用 FunASR Paraformer 测试识别"""
    print("\n" + "=" * 60)
    print("  Paraformer (FunASR, paraformer-zh)")
    print("=" * 60)

    from funasr import AutoModel

    t0 = time.time()
    # GPU 模式（不加载 punc_model，项目已有独立标点恢复模块）
    model = AutoModel(
        model="paraformer-zh",
        vad_model="fsmn-vad",
        device="cuda:0",
        disable_update=True,
    )
    load_time = time.time() - t0
    print(f"  模型加载耗时: {load_time:.2f}s (CUDA)")

    results = []
    total_time = 0

    for i, (audio_path, ref_text) in enumerate(zip(audio_files, test_texts)):
        t0 = time.time()
        res = model.generate(input=audio_path)
        elapsed = time.time() - t0
        total_time += elapsed

        # Paraformer 返回格式
        if res and len(res) > 0:
            text = res[0].get("text", "") if isinstance(res[0], dict) else str(res[0])
        else:
            text = ""

        # 去除标点进行比较
        import unicodedata

        clean_text = "".join(ch for ch in text if not unicodedata.category(ch).startswith("P")).strip()

        cer = calculate_cer(ref_text, clean_text)
        status = "OK" if cer == 0 else f"CER={cer:.0%}"
        results.append({"ref": ref_text, "hyp": clean_text, "cer": cer, "time": elapsed})

        print(f"  [{i + 1:2d}] {status:>8s} | {elapsed:.2f}s | '{ref_text}' → '{clean_text}'")

    avg_cer = np.mean([r["cer"] for r in results])
    avg_time = total_time / len(results)
    perfect = sum(1 for r in results if r["cer"] == 0)

    print(f"\n  {'─' * 50}")
    print(f"  平均 CER: {avg_cer:.1%}")
    print(f"  完全正确: {perfect}/{len(results)} ({perfect / len(results):.0%})")
    print(f"  平均延迟: {avg_time:.2f}s/条")
    print(f"  总耗时:   {total_time:.2f}s")

    return {"results": results, "avg_cer": avg_cer, "avg_time": avg_time, "perfect": perfect}


# ========== 主流程 ==========
def main():
    print("=" * 60)
    print("  Paraformer vs Whisper 对比测试")
    print("  测试场景：中文日历语音指令（Windows SAPI TTS 合成音频）")
    print("=" * 60)

    # 1. 合成测试音频
    audio_dir = Path(tempfile.mkdtemp(prefix="asr_test_"))
    print(f"\n  音频缓存目录: {audio_dir}")
    print(f"  正在合成 {len(TEST_CASES)} 条测试音频...")

    audio_files = synthesize_audio_batch(TEST_CASES, audio_dir)

    # 验证文件生成
    valid_files = []
    valid_texts = []
    for i, (f, t) in enumerate(zip(audio_files, TEST_CASES)):
        if Path(f).exists() and Path(f).stat().st_size > 100:
            valid_files.append(f)
            valid_texts.append(t)
            print(f"    [{i + 1:2d}/{len(TEST_CASES)}] OK '{t}'")
        else:
            print(f"    [{i + 1:2d}/{len(TEST_CASES)}] SKIP '{t}' (文件生成失败)")

    if not valid_files:
        print("  ERROR: 没有成功生成任何音频文件！")
        return

    audio_files = valid_files
    test_texts = valid_texts
    print(f"  合成完成！有效文件: {len(audio_files)}/{len(TEST_CASES)}")

    # 2. Paraformer 测试（必须先加载，避免 CTranslate2 cuDNN 符号冲突）
    paraformer_results = test_paraformer(audio_files, test_texts)

    # 3. Whisper 测试（CPU 模式，不受影响）
    whisper_results = test_whisper(audio_files, test_texts)

    # 4. 对比汇总
    print("\n" + "=" * 60)
    print("  对比汇总")
    print("=" * 60)
    print(f"  {'指标':<12s} | {'Whisper':>10s} | {'Paraformer':>10s} | {'优胜'}")
    print(f"  {'─' * 50}")

    w_cer = whisper_results["avg_cer"]
    p_cer = paraformer_results["avg_cer"]
    winner_cer = "Paraformer" if p_cer < w_cer else ("Whisper" if w_cer < p_cer else "平局")
    print(f"  {'平均CER':<10s} | {w_cer:>9.1%} | {p_cer:>9.1%} | {winner_cer}")

    w_perfect = whisper_results["perfect"]
    p_perfect = paraformer_results["perfect"]
    winner_p = "Paraformer" if p_perfect > w_perfect else ("Whisper" if w_perfect > p_perfect else "平局")
    print(f"  {'完全正确':<9s} | {w_perfect:>7d}/{len(TEST_CASES)} | {p_perfect:>7d}/{len(TEST_CASES)} | {winner_p}")

    w_time = whisper_results["avg_time"]
    p_time = paraformer_results["avg_time"]
    winner_t = "Paraformer" if p_time < w_time else ("Whisper" if w_time < p_time else "平局")
    print(f"  {'平均延迟':<9s} | {w_time:>8.2f}s | {p_time:>8.2f}s | {winner_t}")

    print(f"\n  {'─' * 50}")
    print("  结论: ", end="")
    if p_cer <= w_cer and p_time <= w_time:
        print("Paraformer 全面优于 Whisper（准确率更高 + 速度更快）")
    elif p_cer < w_cer:
        print(f"Paraformer 准确率更高 (CER {w_cer:.1%} → {p_cer:.1%})")
    elif p_time < w_time:
        print(f"Paraformer 速度更快 ({w_time:.2f}s → {p_time:.2f}s)")
    else:
        print("Whisper 表现更好，建议保留当前方案")

    # 5. 逐条对比（仅显示差异）
    print("\n  差异详情（仅显示两者结果不同的条目）:")
    print(f"  {'─' * 50}")
    diff_count = 0
    for i, (w, p) in enumerate(zip(whisper_results["results"], paraformer_results["results"])):
        if w["hyp"] != p["hyp"]:
            diff_count += 1
            print(f"  [{i + 1:2d}] 原文: '{w['ref']}'")
            print(f"       Whisper:    '{w['hyp']}' (CER={w['cer']:.0%})")
            print(f"       Paraformer: '{p['hyp']}' (CER={p['cer']:.0%})")
            print()

    if diff_count == 0:
        print("  无差异，两者结果完全一致")
    else:
        print(f"  共 {diff_count} 条结果存在差异")


if __name__ == "__main__":
    main()
