# 任务编排（Orchestration）

串联「解析 SRT → 术语表/全局画像/场景映射 → 两阶段分批翻译（直译+润色异步预取）→ 质检写出」的调度层，负责批次编排、断点续传、进度回调与最终字幕写出。

## Key Concepts

本节介绍任务编排层的关键机制：翻译主流程、一致性终审、断点续传与字幕写出。

### 翻译主流程（run\_translation）

orchestrator 的核心调度入口：解析 SRT 得 `blocks`，并行构建 global\_profile 与 scene\_map，按「缓存命中优先」加载三级术语表并构建翻译策略，再按 `processed_indices` 过滤剩余批次、用 `build_scene_aligned_batches` 场景对齐分组。

主循环每批跑直译 `process_literal_stage`，`asyncio.create_task` 异步预取下一批，再 `process_polish_stage` 润色并做数字一致性校验、写盘更新进度条，最后进入终审阶段。Reference: \[\[subtitle/pipeline/orchestrator.py#run\_translation]]

### 一致性终审（self\_enforce\_consistency）

全片翻译完成后的自主审核。重新解析已写出的输出文件，双语模式下把「原文+译文」配对为 `paired_blocks`，再调用 `run_post_checker` 执行至多 `post_check_passes` 轮后置检查，用 `rewrite_output` 将复核结果整片回写。本方法独立于 run\_translation 可复用。Reference: \[\[subtitle/pipeline/orchestrator.py#self\_enforce\_consistency]]

### 断点续传（checkpoint）

进度随「每批完成」持久化：`save_checkpoint` 把每批 literal/polished 追加写盘，并把 `processed_indices`、`recent_state`、`output_block_index`、`last_index`、`last_context` 写入进度文件；`load_progress` 重启时读出索引与上下文，跳过已处理块并保持上下文连续。

路径由 `get_cache_path(...,"progress",...)` 生成并带文件指纹 hash，确保同输入只复用同进度。Reference: \[\[subtitle/pipeline/checkpoint\_manager.py#save\_checkpoint]] 与 \[\[subtitle/pipeline/checkpoint\_manager.py#load\_progress]]

### 字幕写出（rewrite\_output）

将 `final_blocks` 整片重写为最终 SRT。bilingual 模式下每条字幕以「原文块+译文块」成对落盘、输出块索引每次递增 2；单语模式仅写译文、索引递增 1。每次调用都从 1 重新编号写满整个文件，与断点续传的「追加写」互补：前者用于终审后整片覆盖。Reference: \[\[subtitle/pipeline/srt\_writer.py#rewrite\_output]]

## Dependencies

内部模块：

- \[\[core-common]] — `TranslationConfig` 组装温度/限流参数，`parse_srt`/`format_srt_block` 解析与格式化，`get_cache_path`/`canonical_json` 定位缓存与稳定序列化（含文件指纹）。

- \[\[core-memory]] — `load_or_build_global_profile`/`global_profile_text` 全局画像，`build_translation_policy`/`policy_text` 策略，`load_or_build_scene_map`/`find_scene_for_block`/`build_scene_aligned_batches` 场景映射与按场景分批。

- \[\[core-glossary]] — `glossary_manager` 初始化/术语提取/回填，`extract_global_terms`/`build_core_terms` 构建术语与核心术语文本。

- \[\[core-stages]] — `process_literal_stage`（直译）、`process_polish_stage`（润色）、`build_recent_state`（批次上下文快照）。

- \[\[core-rescue]] — 批内梯次拯救逻辑依附于直译/润色阶段调用，本身由各 stage 内部触发。

- \[\[core-context]] — `recent_state_str`/`future_context_str` 等上下文串由阶段与 build\_recent\_state 提供；温度策略经 TranslationConfig 注入。

- \[\[core-quality]] — `run_post_checker` 后置终审、`run_asr_scrub` 可选 ASR 清洗、`generate_annotations_for_subtitle` 可选全文注释。

- \[\[network]] — `close_session_pool` 收尾释放 LLM 连接池。

外部：`asyncio`（异步预取与 task 取消）、`tqdm`（批次进度条）、`json`/`os`（缓存读写与路径）。

## Consumed By

以下模块使用本模块的流水线调度、进度回调与字幕写出能力。

- \[\[entries]] — subtitle/main.py（CLI）、translate\_srt\_llm.py（脚本）、webui 任务线程调用 `run_translation` 启动流水线，贡献 args 运行时配置。

- \[\[gui]] — `task_controller` 作为 `progress_callback` 订阅批次进度，驱动界面进度展示。

## Error Conditions

本节列出本模块编排与写出时可能出现的错误与兜底行为。

- 输入无可解析字幕：`parse_srt` 返回空（`blocks` 为空）时直接报错返回，不进入流水线（orchestrator 守卫逻辑）。

- 批次产空：某批 `process_polish_stage` 未返回 `final_blocks`，仅记 warning 日志并跳过该批 checkpoint，不终止后续批次。

- 进度文件损坏：`load_progress` 捕获 `json.JSONDecodeError`/`IOError` 后回退为默认 `{"last_index":0,"processed_indices":[]}`，从零重新开始。

- 术语缓存损坏：`run_translation` 读取 glossary 缓存 `try/except` 静默降级，命中为空时触发重新采样提取。

- 异步预取 task 未完成：`finally` 中对残留的 `next_literal_task` 执行 `cancel()` 并 `await` 吞掉 `CancelledError`，保证连接池正常释放。

