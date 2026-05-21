# 🚀 Subtitle Translation Pipeline (字幕翻译流水线)

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

这是一款基于 **LLM (大语言模型)** 的全自动、高精度视频字幕翻译工具。通过“全局画像扫描”与“场景对齐”技术，实现了远超传统分段翻译的连贯性与角色一致性。

---

## ✨ 核心特性

*   **🎬 剧本级理解**：通过“全局画像 (Global Discovery)”自动识别全片题材、角色性别、语调及复杂的人物关系。
*   **🧠 智能语境润色**：两阶段执行引擎（直译+意译），润色时参考上下文滑动窗口，告别代词混乱。
*   **🛡️ 梯次拯救引擎**：内置 8->1 梯次降级重试逻辑，自动绕过 API 限制与敏感词拦截，确保任务永不中断。
*   **⚖️ 智能负载均衡**：支持多 API Key 自动调度，实时监控速率与成功率，最大化提升翻译效率。
*   **🖱️ 极简图形界面**：提供直观的 GUI 工具，支持环境预设切换，零门槛上手。

---

## ⚡ 快速开始

### 1. 部署环境
确保已安装 Python 3.10+。克隆仓库后执行：
```bash
cd subtitle
pip install -r requirements.txt
```

### 2. 启动 GUI
双击根目录下的 `start_gui.bat` 启动图形界面。首次运行将自动根据模板创建 `presets.json`。

### 3. 配置 API
在 GUI 的 **“高级配置”** 标签页中填入你的 API Key 和 URL 并保存即可开始翻译。

---

## 📖 深入文档

为了更好地利用本工具，建议阅读以下详细文档：

*   **[用户使用手册 (User Manual)](subtitle/README.md)**：详细的安装步骤、CLI 参数说明、语料库管理方法。
*   **[流水线原理架构 (Pipeline Principles)](subtitle/PIPELINE_PRINCIPLES.md)**：深入了解全局扫描、场景映射、梯次拯救等核心算法逻辑。

---

## 📂 目录结构

*   `subtitle/`：核心代码库，包含 GUI、CLI 以及所有 Prompt 模板。
*   `python_embed/`：(可选) 嵌入式 Python 环境，用于便携运行。
*   `start_gui.bat`：Windows 一键启动脚本。

---

## 📄 开源协议

本项目采用 MIT 协议开源。
