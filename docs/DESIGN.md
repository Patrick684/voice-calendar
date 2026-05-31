# 语音日历工具 - 技术设计文档

## 架构概述

语音日历工具采用分层架构设计，主要分为以下几层：

```
┌─────────────────────────────────────────────┐
│                  UI 层                        │
│   main_window / event_dialog / stats_view    │
├─────────────────────────────────────────────┤
│              应用控制层 (main.py)              │
│   录音调度 → 识别 → 解析 → 执行 → UI 刷新     │
├──────────────────┬──────────────────────────┤
│   指令解析层      │      日历核心层            │
│   rule_engine    │      manager / storage    │
│   time_parser    │      event / reminder     │
│   intent_model   │      achievement / stats  │
│   parser(混合)   │      backup / classifier  │
├──────────────────┴──────────────────────────┤
│              语音引擎层                       │
│   whisper_engine → post_processor 链          │
│   (text_corrector + punctuation_restorer)    │
└─────────────────────────────────────────────┘
```

### 指令解析策略

采用**混合解析**策略，按优先级依次尝试：

1. **规则引擎** (`rule_engine.py`)：正则匹配 + 关键词检测，处理明确的添加/删除/查询/修改指令
2. **意图分类模型** (`intent_classifier.py`)：基于 BERT 的五分类模型，对规则引擎无法匹配的文本进行意图预测
3. **LLM 兜底** (`llm_fallback.py`)：对模型置信度不足的指令，调用 LLM 理解复杂语义

### 存储层

- SQLite 本地存储，Schema v4（含增量迁移）
- 支持软删除（`deleted_at` 字段），回收站可恢复
- 循环事件使用 iCal RRULE 格式存储规则，运行时展开实例

### UI 层

- 基于 CustomTkinter 构建桌面 GUI
- 月历视图 + 事件列表 + 拖拽交互
- 独立窗口：查询结果窗口（CTkToplevel，贴主窗口左侧）

## 项目结构

```
├── main.py                 # 程序入口
├── config.py               # 配置管理
├── audio/                  # 音频采集
│   └── recorder.py         # 麦克风录音
├── engine/                 # 语音识别引擎 + 后处理链
│   ├── whisper_engine.py   # faster-whisper 封装
│   ├── text_corrector.py   # 同音纠错
│   ├── punctuation_restorer.py  # 标点恢复
│   ├── punctuation_processor.py # 标点后处理
│   ├── post_processor.py   # 后处理链
│   └── hotword_manager.py  # 热词管理
├── calendar_pkg/           # 日历核心层
│   ├── event.py            # 事件数据模型（含优先级/分类/循环/软删除）
│   ├── storage.py          # SQLite 存储（Schema v4 + 增量迁移）
│   ├── manager.py          # 事件管理器 + 循环展开
│   ├── reminder.py         # 提醒调度器（分类音效 + 免打扰）
│   ├── classifier.py       # 事件自动分类器
│   ├── backup.py           # 备份导出/导入
│   ├── stats.py            # 打卡统计引擎
│   └── achievement.py      # 成就系统
├── command/                # 指令解析层
│   ├── time_parser.py      # 中文时间解析（含过去日期）
│   ├── rule_engine.py      # 正则规则引擎（含优先级/循环检测）
│   ├── parser.py           # 混合解析入口（多指令分割）
│   ├── intent_classifier.py # 意图分类模型（BERT）
│   ├── completion.py       # 智能指令补全
│   └── llm_fallback.py     # LLM 兜底
├── ui/                     # GUI 界面
│   ├── main_window.py      # 主窗口（日历 + 拖拽 + 排序）
│   ├── event_dialog.py     # 事件编辑对话框
│   ├── settings_window.py  # 设置窗口
│   ├── voice_panel.py      # 语音状态面板
│   ├── time_dial.py        # 时间拨盘（24h 标尺）
│   ├── stats_view.py       # 统计与成就视图
│   └── query_window.py     # 查询结果独立窗口
├── hotkey/                 # 全局快捷键
├── models/                 # 意图分类模型
├── scripts/                # 训练/工具脚本
└── tests/                  # 测试脚本
    ├── verify_calendar.py  # 日历层测试
    └── verify_command.py   # 指令解析层测试
```

## 开发

### 代码质量

项目使用 [ruff](https://github.com/astral-sh/ruff) 进行代码检查和格式化，配置见 `pyproject.toml`。

```bash
# 检查 lint
ruff check .

# 自动修复
ruff check --fix .

# 格式化
ruff format .
```

### Pre-commit Hook

已配置 pre-commit hook（`.qoder/hooks/pre-commit`），每次 commit 自动运行：

1. `ruff check` — lint 检查
2. `ruff format --check` — 格式检查
3. `verify_calendar.py` — 日历层测试
4. `verify_command.py` — 指令解析层测试

### 测试

```bash
python tests/verify_calendar.py   # 日历层测试
python tests/verify_command.py    # 指令解析层测试
```

### CI/CD

GitHub Actions 配置于 `.github/workflows/ci.yml`，在 Python 3.10/3.11/3.12 三版本上运行：

- ruff check
- ruff format --check
- verify_command.py（指令解析层测试）

### 分支策略

- `main` 分支保持稳定，只接受经过测试的功能代码
- 开发新功能使用 `feature/xxx` 分支，完成后通过 PR 合并回 `main`
- 修复 Bug 使用 `fix/xxx` 分支
