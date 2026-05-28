# 语音日历工具 (Voice Calendar)

基于本地 Whisper 模型的桌面语音日历管理工具。通过语音指令添加、删除、查看日历事件，提升日程管理的效率与便捷性。

## 功能特性

- **语音指令管理**: 通过语音说出"明天下午三点开会"等自然语言，自动创建日历事件
- **中文时间解析**: 支持"明天/后天/下周一/三点半"等中文时间表达式
- **混合指令解析**: 规则引擎快速匹配 + LLM 兜底理解复杂指令
- **本地语音识别**: 基于 faster-whisper，无需联网，保护隐私
- **全局快捷键**: 按住右 Alt 键即可录音，松开自动识别并执行
- **日历视图**: 月历视图直观展示事件分布，点击日期查看事件详情
- **事件提醒**: 后台定时扫描，提前提醒即将到来的事件
- **智能后处理**: 同音纠错 + 标点恢复，提升指令识别准确率

## 快速开始

### 环境要求

- Windows 10/11
- Python 3.9+ (推荐 3.12)
- 麦克风设备
- GPU (可选，NVIDIA CUDA 11.8+)

### 安装

```bash
# 创建 Conda 环境
conda create -n voice_calendar python=3.12 -y
conda activate voice_calendar

# 安装 Python 依赖
pip install -r requirements.txt
```

### 运行

```bash
# Windows (需要管理员权限以监听全局快捷键)
python main.py
```

## 使用方式

### 语音指令

1. 启动后，主窗口显示日历视图
2. 按住 **右 Alt** 键开始录音
3. 说出日历指令，如:
   - "明天下午三点团队会议" → 添加事件
   - "删掉明天的面试" → 删除事件
   - "今天有什么安排" → 查询事件
4. 松开按键，自动识别并执行

### 界面操作

- 点击月历中的日期查看当日事件
- 点击事件卡片编辑或删除
- 点击 "+ 添加事件" 手动创建
- 双击托盘图标打开设置

## 项目结构

```
├── main.py              # 程序入口
├── config.py            # 配置管理
├── audio/               # 音频采集
│   └── recorder.py      # 麦克风录音
├── engine/              # 语音识别引擎 + 后处理链
│   ├── whisper_engine.py
│   ├── text_corrector.py
│   ├── punctuation_restorer.py
│   ├── punctuation_processor.py
│   ├── post_processor.py
│   └── hotword_manager.py
├── calendar/            # 日历核心层
│   ├── event.py         # 事件数据模型
│   ├── storage.py       # SQLite 存储
│   ├── manager.py       # 事件管理器
│   └── reminder.py      # 提醒调度器
├── command/             # 指令解析层
│   ├── time_parser.py   # 中文时间解析
│   ├── rule_engine.py   # 正则规则引擎
│   ├── parser.py        # 混合解析入口
│   └── llm_fallback.py  # LLM 兜底
├── ui/                  # GUI 界面
│   ├── main_window.py   # 主窗口（日历视图）
│   ├── event_dialog.py  # 事件编辑对话框
│   ├── settings_window.py # 设置窗口
│   └── voice_panel.py   # 语音状态面板
├── hotkey/              # 全局快捷键
├── utils/               # 工具模块
└── tests/               # 测试脚本
```

## 许可证

MIT License
