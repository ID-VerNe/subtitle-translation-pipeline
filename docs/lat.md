# 字幕翻译 Pipeline 文档体系

这是「subtitle pipeline source」项目的知识图谱根节点（lat.md Tier 1 入口）。本目录用结构化 Markdown 定义项目的高层概念、业务逻辑与架构，并把每条定义通过 wiki link 锚定到源码符号。Tier 2 的 12 个模块文档已全部创建完毕。

## 顶层入口

本索引指向项目文档体系的三个主干，分别回答"项目是什么 / 怎么运行、整体如何设计、术语含义"三个问题，是进入任何细节前的第一站。

- [[Project]] — 项目入口与技术栈：一个基于 LLM 的全自动视频字幕翻译 Pipeline（Python 3.10+，asyncio 异步驱动），本文件说明它是谁、依赖什么技术、由哪些模块构成、从哪里启动。
- [[Architecture]] — 架构总览：MKV 到 ASS 的完整数据流、模块间依赖关系、技术选型理由，以及梯次拯救、滑动窗口、多 Key 负载均衡、双数据库隔离等关键设计决策的取舍依据。
- [[Glossary]] — 术语表：全局画像、梯次拯救、三级术语库、负载均衡等本项目专有名词的统一定义，全体系内每个概念只在此定义一次，其余文档用 wiki link 引用。

## 模块索引（Tier 2）

以下 12 个模块文档已全部创建，按职责划分为六组：

- [[entries]] — CLI/GUI 启动入口（main.py、translate_srt_llm.py、gui_app.py、webui_gui.py）。
- [[core-memory]] — 记忆引擎：全局画像、翻译策略、场景映射。
- [[core-context]] — 上下文构建、Few-Shot、温度策略。
- [[core-glossary]] — 三级术语库与术语清洗。
- [[core-stages]] — 直译与润色两阶段执行。
- [[core-rescue]] — 梯次拯救引擎。
- [[core-quality]] — 质量检查、后审、注解、ASR 清洗。
- [[core-common]] — 配置、提示词、缓存、SRT 工具等基础能力。
- [[network]] — LLM 客户端与多 Key 负载均衡。
- [[pipeline]] — 任务编排、断点续传、SRT 写出。
- [[gui]] — Tkinter 图形界面（MVC）。
- [[media-process]] — MKV 提取与 ASS 后处理。

## lat.md 工具

本目录由 [lat.md](https://www.npmjs.com/package/lat.md) 管理。安装 `lat` 命令（`npm i -g lat.md`）后运行 `lat --help`，即可让工具把文档中的定义与源码符号给它"锚定"保存同一个知识库，保证设计与实现始终一致。