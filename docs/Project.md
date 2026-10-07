# Project — 字幕翻译 Pipeline 项目入口

这是一个基于 LLM 的全自动视频字幕翻译 Pipeline。它接收 MKV 或 SRT 输入，通过"全局画像扫描 + 分治式两阶段翻译 + 梯次拯救 + 三级术语库"架构，产出高质量的中英互译字幕（SRT/ASS），并支持双语输出、断点续传、术语记忆与 AAC 风格美化。核心逻辑位于 `subtitle/` 包。

## 技术栈

本小节列举支撑整个 Pipeline 运行的核心依赖与运行时约束。技术选型遵循"Python 生态 + 异步高并发 + LLM 结构化输出"的路线，避免引入重框架。

- **语言/运行时**：Python 3.10+；全程基于 `asyncio` 异步任务模型，GUI 与 CLI 共用同一套异步编排。
- **HTTP/并发**：`aiohttp`（异步响应封装）配合 `requests.Session` 在线程池中执行阻塞请求（见 [[subtitle/network/request_handler.py#AsyncRateLimitedSession|request_handler]]），并用 `asyncio.Semaphore` 约束并发。
- **LLM 调用**：`json_repair` 修复模型输出的损坏 JSON，`flashtext` 做术语的 O(1) 子串多关键词匹配，`tqdm` 展示批次进度。
- **存储**：SQLite（`sqlite3` 标准库）承载三级术语库——静态精校库、LLM 发现库、人名库各自独立库文件，详见 [[Architecture#关键设计决策#双数据库隔离]] 与 [[Glossary#术语库体系#三级术语库]]。
- **界面**：Tkinter 构建桌面 MVC 界面；`pyperclip` 支持剪贴板交互；另有一套基于 QuickStart 的 WebUI（见 [[subtitle/gui_app.py#run_gui|gui_app]] 与 [[subtitle/webui_gui.py#WebUiGui|webui]]）。
- **配置文件**：`presets.json` 保存多组模型预设（API Key、温度、并发、批次等），运行时由 [[subtitle/core/config.py#TranslationConfig|TranslationConfig]] 加载。

## 架构模式

本项目采用"记忆引擎驱动 + 两阶段执行 + 外部防御层"的分层架构，形似 RAG + Compose 的工程实现。

- **记忆引擎（Memory）**：把"整片视角"沉淀为三块可复用的结构化记忆——全局画像、翻译策略、场景映射，对应 `core/memory/` 三个子模块，翻译每一批时动态回灌（见 [[core-memory]]）。
- **分治式两阶段（Two-Stage）**：直译阶段负责 ID 对齐与语义还原，润色阶段负责可读性与风格。两阶段间用异步预取重叠，提升吞吐（见 [[core-stages]]）。
- **防御层（Defense）**：梯次拯救兜底请求失败、后置清洗与终审质检兜底模型过度解释，形成"提示词约束之外的硬保障"（见 [[core-rescue]]、[[core-quality]]）。
- **编排层（Orchestration）**：`pipeline/orchestrator.py` 串起采样→建库→建场景→逐步翻译→终审全流程，并托管断点与进度（见 [[pipeline]]）。
- **多 Key 负载均衡**：网络层按成功率、响应时间、可用并发槽动态择优选路，降低 429 与失败率（见 [[network]]）。

## 模块清单

Phase 1 预置以下 12 个模块的 wiki 索引，分别对应 `subtitle/` 下的真实目录与文件；详细说明将在 Phase 2 的文档中展开。

- [[entries]] — CLI/GUI 入口：`subtitle/main.py`、`translate_srt_llm.py`、`gui_app.py`、`webui_gui.py`。
- [[core-memory]] — 记忆引擎：`core/memory/` 的 global_profile、policy_engine、scene_manager。
- [[core-stages]] — 两阶段翻译：`core/stages/` 的 literal_stage、polish_stage。
- [[core-rescue]] — 梯次拯救引擎：`core/rescue_engine.py`。
- [[core-glossary]] — 三级术语库：glossary_manager、glossary_sanitizer、terminology_extractor。
- [[core-context]] — 上下文与策略增强：context_builder、fewshot_manager、temperature_strategy。
- [[core-quality]] — 质量与清理：quality_checker、post_checker、annotation_pipeline、asr_scrubber。
- [[core-common]] — 基础工具：config、prompts、cache_utils、srt_utils。
- [[network]] — 网络与请求层：`network/llm_client`、`network/request_handler`（负载均衡）。
- [[pipeline]] — 任务编排：orchestrator、checkpoint_manager、srt_writer。
- [[gui]] — 图形界面：gui/main_window、view_models、preset_manager、task_controller。
- [[media-process]] — 媒体前后处理：media/extractor、pre-process、post-process。

## 入口点说明

本节说明从哪几个入口进入系统。四个入口面向不同场景，但最终都汇聚到 `pipeline/orchestrator.run_translation`。

- **CLI 总控**：`subtitle/main.py` 提供"从 MKV/SRT/ASS 到最终版字幕"的一站式命令行；无参数时自动拉起 GUI（[[subtitle/main.py#main]]）。
- **翻译 CLI**：`subtitle/translate_srt_llm.py` 暴露细粒度翻译参数（批次、温度、并发、RPM/TPM、中英方向），并托管全流程编排（[[subtitle/translate_srt_llm.py#main]]）。
- **桌面 GUI**：`subtitle/gui_app.py` 的 `run_gui` 启动 Tkinter MVC 界面；内部由 `gui/task_controller.py` 驱动异步任务（[[subtitle/gui_app.py#run_gui]]）。
- **WebUI**：`subtitle/webui_gui.py` 提供浏览器交互式分步翻译入口（[[subtitle/webui_gui.py#WebUiGui]]）。
- **媒体桥接**：`subtitle/media/extractor.py` 统一封装 MKV 提取与 ASS/SRT 互转，供 main.py 调用（[[subtitle/media/extractor.py#extract_subtitles_from_mkv]]）。

## 相关文档

本节给出理解系统所需路径的快速入口，指向数据流、术语与模块细节。

- 从 MKV 到 ASS 的端到端数据流见 [[Architecture#数据流]]。
- 概念一致的统一定义见 [[Glossary]]。
- 模块内部细节将在各 Tier 2 文档（即上方模块清单的 12 个文件）中展开。