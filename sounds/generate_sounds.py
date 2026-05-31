"""生成默认提醒音效文件

使用 Python 标准库 wave + struct 程序化合成短提示音 .wav 文件。
运行方式: python sounds/generate_sounds.py
或在应用启动时自动调用 ensure_sounds() 检查并生成。
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 44100
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit


def _generate_tone(frequency: float, duration: float, volume: float = 0.5) -> "list[int]":
    """生成单频正弦波采样数据"""
    num_samples = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(num_samples):
        t = i / SAMPLE_RATE
        # 带衰减包络
        envelope = 1.0 - (i / num_samples) * 0.7
        value = volume * envelope * math.sin(2 * math.pi * frequency * t)
        samples.append(int(value * 32767))
    return samples


def _generate_bell(duration: float = 0.8, volume: float = 0.5) -> "list[int]":
    """生成铃声音效 - 双频叠加 + 快速衰减"""
    num_samples = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(num_samples):
        t = i / SAMPLE_RATE
        envelope = math.exp(-4.0 * t)
        v1 = math.sin(2 * math.pi * 880 * t)
        v2 = 0.5 * math.sin(2 * math.pi * 1320 * t)
        value = volume * envelope * (v1 + v2) / 1.5
        samples.append(int(value * 32767))
    return samples


def _generate_chime(duration: float = 1.0, volume: float = 0.4) -> "list[int]":
    """生成风铃音效 - 三音递降"""
    samples = []
    freqs = [1047, 880, 659]  # C6, A5, E5
    note_dur = duration / len(freqs)
    for freq in freqs:
        num_samples = int(SAMPLE_RATE * note_dur)
        for i in range(num_samples):
            t = i / SAMPLE_RATE
            envelope = math.exp(-3.0 * t)
            value = volume * envelope * math.sin(2 * math.pi * freq * t)
            samples.append(int(value * 32767))
    return samples


def _generate_soft(duration: float = 0.6, volume: float = 0.35) -> "list[int]":
    """生成柔和提示音 - 低频单音 + 缓慢衰减"""
    num_samples = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(num_samples):
        t = i / SAMPLE_RATE
        envelope = math.cos(math.pi * t / (2 * duration))
        value = volume * envelope * math.sin(2 * math.pi * 523 * t)
        samples.append(int(value * 32767))
    return samples


def _generate_default(duration: float = 0.5, volume: float = 0.45) -> "list[int]":
    """生成默认叮咚音 - 双音交替"""
    samples = []
    # 高音 叮
    half = duration / 2
    num_half = int(SAMPLE_RATE * half)
    for i in range(num_half):
        t = i / SAMPLE_RATE
        envelope = math.exp(-5.0 * t)
        value = volume * envelope * math.sin(2 * math.pi * 1200 * t)
        samples.append(int(value * 32767))
    # 低音 咚
    for i in range(num_half):
        t = i / SAMPLE_RATE
        envelope = math.exp(-3.0 * t)
        value = volume * envelope * math.sin(2 * math.pi * 800 * t)
        samples.append(int(value * 32767))
    return samples


def _write_wav(filepath: Path, samples: "list[int]"):
    """将采样数据写入 .wav 文件"""
    with wave.open(str(filepath), "w") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        data = struct.pack(f"<{len(samples)}h", *samples)
        wf.writeframes(data)


def generate_all(output_dir: Path):
    """生成所有默认音效文件到指定目录"""
    output_dir.mkdir(parents=True, exist_ok=True)

    sounds = {
        "default.wav": _generate_default(),
        "bell.wav": _generate_bell(),
        "chime.wav": _generate_chime(),
        "soft.wav": _generate_soft(),
    }

    for filename, samples in sounds.items():
        filepath = output_dir / filename
        _write_wav(filepath, samples)
        print(f"Generated: {filepath}")


def ensure_sounds(sounds_dir: Path):
    """确保音效文件存在，不存在则自动生成"""
    required = ["default.wav", "bell.wav", "chime.wav", "soft.wav"]
    missing = [f for f in required if not (sounds_dir / f).exists()]
    if missing:
        generate_all(sounds_dir)


if __name__ == "__main__":
    # 直接运行时生成到项目 sounds/ 目录
    project_dir = Path(__file__).parent
    generate_all(project_dir)
    print("Done!")
