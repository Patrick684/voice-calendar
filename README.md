# 语音日历工具 (Voice Calendar)

基于本地语音识别的桌面日历管理工具。按住快捷键说出日程安排，自动创建、删除、查询日历事件，无需联网，保护隐私。

## 功能亮点

- **语音驱动**：按住右 Alt 键说话，松开即执行，支持一句话包含多条指令
- **中文理解**：识别"明天下午三点"、"下周一"、"每天早上九点"等自然语言时间
- **智能管理**：事件优先级、自动分类、循环事件、软删除回收站
- **可视化**：月历视图、拖拽改期、时间拨盘微调、热力图统计、成就系统

## 快速开始

### 环境要求

- Windows 10/11
- Python 3.10+（推荐 3.12）
- 麦克风设备
- GPU（可选，NVIDIA CUDA 11.8+ 可加速语音识别）

### 安装

```bash
# 创建虚拟环境
conda create -n voice_calendar python=3.12 -y
conda activate voice_calendar

# 安装依赖
pip install -r requirements.txt
```

### 运行

```bash
# 需要管理员权限以监听全局快捷键
python main.py
```

## 使用方式

### 语音指令

启动后，按住 **右 Alt** 键开始录音，说出指令后松开即可执行：

| 说法示例 | 效果 |
|----------|------|
| "明天下午三点团队会议" | 添加事件 |
| "后天上午十点面试" | 添加事件 |
| "每天上午九点晨会" | 添加循环事件 |
| "每周六下午跑步" | 添加循环事件 |
| "删掉明天的面试" | 删除事件（进入回收站） |
| "今天有什么安排" | 查询当日事件 |
| "看看这周的日程" | 查询本周事件 |
| "把明天的会改到后天" | 修改事件日期 |

支持一句话包含多条指令，用逗号或"还有"分隔：
> "明天早上八点起床，下午三点开会，还有后天上午面试"

### 优先级关键词

语音中包含以下关键词时，事件会自动标记对应优先级：

| 优先级 | 关键词 | 显示 |
|--------|--------|------|
| 紧急且重要 | "紧急且重要"、"既紧急又重要" | ‼️ |
| 紧急 | "紧急"、"deadline" | ❗ |
| 重要 | "重要" | ★ |
| 普通 | 无关键词时默认 | ○ |

> 示例："明天紧急提交项目报告" → 自动标记为「紧急」优先级

未包含关键词的事件默认为「普通」优先级，可在界面中通过拖拽调整。

### 界面操作

| 操作 | 效果 |
|------|------|
| 点击月历日期 | 查看当日事件列表 |
| 左键点击事件卡片 | 打开编辑对话框 |
| 左键拖拽卡片到日期格子 | 移动事件到新日期 |
| 上下拖拽卡片（优先级模式） | 调整事件优先级 |
| 点击卡片左侧颜色条 | 展开时间拨盘 |
| 拖拽拨盘滑块 | 调整事件时间（半小时精度） |
| 点击「★ 优先级排序」 | 切换时间/优先级排序 |
| 点击「+ 添加事件」 | 手动创建事件 |
| 点击「📈 统计」 | 查看热力图、分类统计、成就 |
| Ctrl+Z | 撤销上次拖拽/时间调整 |

### 事件分类

事件根据标题关键词自动归类，不同分类在卡片左侧显示对应颜色条：

- 🔵 工作
- 🟢 健康
- 🟡 学习
- 🟠 生活
- 🟣 娱乐
- 🔴 社交
- ⚪ 其他

## 许可证

MIT License

## 演示视频

> 🎬 [Demo 视频链接（待补充）](#)

## 第三方依赖与致谢

本项目使用了以下开源框架和库：

| 依赖 | 用途 | 许可证 |
|------|------|--------|
| [FunASR (Paraformer)](https://github.com/modelscope/FunASR) | 本地语音识别引擎 | Apache-2.0 |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 备用语音识别引擎 | MIT |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | GUI 界面框架 | MIT |
| [PyTorch](https://pytorch.org/) | 深度学习框架 | BSD-3-Clause |
| [Transformers](https://github.com/huggingface/transformers) | 意图分类模型推理 | Apache-2.0 |
| [keyboard](https://github.com/boppreh/keyboard) | 全局快捷键监听 | MIT |
| [python-dateutil](https://github.com/dateutil/dateutil) | 日期时间解析（RRULE） | Apache-2.0 |
| [pypinyin](https://github.com/mozillazg/python-pinyin) | 汉字拼音转换（近音纠错） | MIT |
| [scikit-learn](https://scikit-learn.org/) | 意图分类模型训练 | BSD-3-Clause |
| [Inno Setup](https://jrsoftware.org/isinfo.php) | Windows 安装包构建 | Inno Setup License |
| [PyInstaller](https://pyinstaller.org/) | Python 应用打包 | GPL-2.0 (bootloader: Apache-2.0) |

## 代码来源

本项目的语音识别引擎封装、音频录制模块、热词管理等基础设施代码复用自作者早期项目：

> **[voice-input-method](https://github.com/Patrick684/voice-input-method)** — 基于本地语音识别的 Windows 输入法工具

在原项目基础上，本项目新增了日历管理、中文时间语义解析、指令解析引擎、意图分类模型、GUI 交互等全部业务功能。

---

> 技术架构与开发文档见 [docs/DESIGN.md](docs/DESIGN.md)
