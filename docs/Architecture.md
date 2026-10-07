# Architecture — 架构总览

本文件描述系统从原始媒体到成品字幕的端到端架构：数据如何流动、模块之间如何依赖、关键技术如何选型，以及几个影响全局的关键设计决策。它是理解 `core/`、`pipeline/`、`network/`、`media/` 等目录协同关系的唯一入口。

## 数据流

字幕翻译是"媒体输入 → 多级 LLM 加工 → 字幕输出"的管道。整体分为预处理、记忆构建、分治翻译、质量控制、输出五段，每一段都有明确的输入产物与落盘产物。

1. **MKV → SRT**：`main.py` 识别输入类型。MKV 用 [[subtitle/media/extractor.py#extract_subtitles_from_mkv|extractor]] 提取内嵌字幕；ASS 先转 SRT；纯 SRT 直达。SRT 随后被 [[subtitle/core/srt_utils.py#parse_srt|srt_utils]] 解析成带 `index/timestamp/content` 的字幕块列表。
2. **全局画像**：按"首 15% + 中 15% + 尾 15%"做固定采样（[[subtitle/core/memory/global_profile.py#sample_blocks_for_global_profile|sample_blocks_for_global_profile]]），由 LLM 生成含影片类型、语调、人物画像、人物关系的 `global_profile`，落盘 `global_profile.json`。
3. **术语库构建**：若无历史缓存，按分页循环采样用 LLM 提取全片术语（[[subtitle/core/terminology_extractor.py#extract_global_terms|extract_global_terms]]），经清洗后分为核心术语与局部动态术语（见 [[Glossary#术语库体系#三级术语库]]）。
4. **场景映射**：先按固定粒度切基础场景块，再由 LLM 语义富化每个场景（参与者、摘要、语域），得到 `scene_map`；翻译批次对齐到固定场景边界上，避免切断对话（[[subtitle/core/memory/scene_manager.py#build_scene_aligned_batches|build_scene_aligned_batches]]）。
5. **两阶段翻译**：`pipeline/orchestrator.py` 对每个批次先跑直译（[[subtitle/core/stages/literal_stage.py#process_literal_stage|literal_stage]]）再跑润色（[[subtitle/core/stages/polish_stage.py#process_polish_stage|polish_stage]]），两阶段共享全局画像、策略、场景引导与前/后文上下文；批次 `i` 润色时并发预取批次 `i+1` 的直译。
6. **质量控制**：逐批做数字一致性检查与润色后清理；翻译完成后可进入全片终审（[[subtitle/core/post_checker.py#run_post_checker|post_checker]]）与注解生成（[[subtitle/core/annotation_pipeline.py#generate_annotations_for_subtitle|annotation_pipeline]]）。
7. **SRT → ASS**：`pipeline/srt_writer.py` 写出最终 SRT（含可选双语）；如目标为 ASS，再由 [[subtitle/post-process/02-post_process_ass.py#srt_to_ass|srt_to_ass]] 附加样式表生成 ASS。

尾部链接坐标：产物统一落在 `.cache`；中间态含 `.literal.srt`、`.polished.srt` 与进度 JSON，供[[Architecture#关键设计决策]]之断点续传使用。

## 模块依赖关系

依赖方向整体自"上层入口 + 编排"指向"高层业务"再指向"基础工具"，禁止反向循环。

- `subtitle/main.py`、`gui_app.py`、`webui_gui.py`、`translate_srt_llm.py` → 调用 `pipeline/orchestrator.run_translation`（见 [[subtitle/pipeline/orchestrator.py#run_translation]]）。
- `pipeline/orchestrator` → 依赖 `core/global_memory`（画像/策略/场景）、`core/translation_pipeline`（两阶段与语义工具）与 `network/llm_client`。
- `core/translation_pipeline` 是一个兼容层门面（Facade），聚合 `core/context_builder`、`core/terminology_extractor`、`core/rescue_engine`、`core/stages/*` 的导出。
- `core/stages/*` 与 `core/rescue_engine` → 依赖 `network/llm_client` 的 `call_llm` 与 `clean_and_extract_json`。
- `network/llm_client` → 依赖 `network/request_handler`（会话、限速、负载均衡）。
- `core/glossary_manager` → 依赖 `network/llm_client`（NER 人名提取）、`core/config`（库路径）、`core/prompts`；数据落在 SQLite。
- `core/global_memory` → 将三块记忆逻辑委托给 `core/memory/*`（global_profile / policy_engine / scene_manager）。
- `core/*` 与 `pipeline/*` 共享 `core/srt_utils`、`core/cache_utils`、`core/config`、`core/prompts` 等基础工具。

一张"门面 + 逻辑拆分"的依赖图：`orchestrator → translation_pipeline(门面) → stages/rescue/context → llm_client → request_handler`，向上提供可替换的会话层，向下统一提示词与缓存基建。

## 技术选型

本项目刻意选用轻量、易自部署的组件，兼顾 LLM 结构化输出与高并发。

- **asyncio + aiohttp/requests**：`network/llm_client` 导入 `aiohttp` 封装异步响应，而实际阻塞请求由 `requests.Session` 在线程池执行（`run_in_executor`），再用 `Semaphore` 限并发——既保留异步编排，又能复用 requests 生态的会话与认证。
- **json_repair**：LLM 常返回非规范 JSON，`call_llm → clean_and_extract_json` 用 `repair_json` 修复，再配合多层正则兜底，保证 Tool Calling / JSON 模式的稳健解析（见 [[subtitle/network/llm_client.py#clean_and_extract_json]]）。
- **SQLite 术语库**：三类库均为独立 `.db` 文件。`glossary_cache.db`（精校库）、`llm_discovery.db`（发现库，反向时使用 `llm_discovery_cn.db`）、`glossaries/names_translation.db`（人名库）。`glossaries/*.json` 词条通过文件哈希增量入库（见 [[subtitle/core/glossary_manager.py#GlossaryManager]]）。
- **flashtext**：`KeywordProcessor` 把术语建成多关键词自动机，做 O(1) 的子串提取（`extract_terms`），替代逐条正则匹配，翻译逐批过滤动态术语时性能更优。
- **Tkinter / pyperclip**：桌面 GUI 采用标准库 Tkinter 的 MVC 分层，`pyperclip` 服务剪贴板复制；不引入重量级桌面框架。

## 关键设计决策

本节记录系统中最影响行为的五条取舍，每条都是"在资源约束与质量目标之间"的有意识选择。

### 梯次拯救

长文本翻译常遭 API 超时或内容安全拦截。请求失败时 `ladder_rescue_engine` 启动三级降级：(TIER 1) 缩小批次重试（8→4→2→1）；(TIER 2) 剥离动态记忆、保留场景引导；(TIER 3) 仅留全局画像与核心术语。系统会记忆曾被拒绝的行，降级与缩批时主动跳过；若全部失败，直译退回原文、润色退回直译，保证任务永不中断——这是"完整性优先于质量"的显式取舍（见 [[subtitle/core/rescue_engine.py#ladder_rescue_engine]] 与 [[Glossary#翻译执行概念#梯次拯救]]）。

### 滑动窗口

滑动窗口被两处采用。其一在 `RateLimiter`：用 deque 记录过去 60 秒的请求与 Token 消耗，逐出过期记录以计算 TPM 余量实现限速（见 [[subtitle/network/request_handler.py#RateLimiter]]）。其二在上下文管理：`build_recent_state` 只回灌最近 N 行（由 `max_previous_lines` 控制，1M 上下文下约 25-30 行）作为跨批次锚点，兼顾记忆连续性与 Token 成本；`prefetch` 预取未来 4 批共 50 行作为未来语境。

### 多 Key 负载均衡

`SmartLoadBalancer` 面向多 API Key 路由：任务入队后由工作协程 `_select_best_api` 按"成功率 × 可用并发槽 /（平均响应时间+1）"打分择路，跳过不健康 Key；失败任务自动重启并换 Key 重试。针对 `GLM-4-Flash` 等模型内置并发压制防 429。另支持 `claude_cli_mode` / `codex_mode` 两种模仿终端客户端的请求头模式（见 [[subtitle/network/request_handler.py#SmartLoadBalancer]] 与 [[Glossary#运行与容错概念#负载均衡]]）。

### 双数据库隔离

双库隔离指人审精校词条与 LLM 自动发现词条分库存储：glossary_cache.db 存人工词条，llm_discovery.db 存自动词条，增量加载、可独立开关，避免自动词条污染人审成果；中→英反向启用 llm_discovery_cn.db（见 [[subtitle/core/glossary_manager.py#GlossaryManager]] 与 [[Glossary#术语库体系#发现库]]）。

### 双库语境预取与场景对齐

翻译批次不按行数硬切，而是对齐到场景固定边界（`build_scene_aligned_batches`），确保同批字幕落在同一语境；同时利用 `asyncio.create_task` 预取下一批直译，在等待润色模型返回时并行推进直译，显著降低整片串行延迟（见 [[subtitle/pipeline/orchestrator.py#run_translation]] 与 [[Architecture#数据流]]）。

## 相关文档

本节给出理解系统所需路径的快速入口，指向数据流、术语与模块细节。

- 各模块的详细实现见 [[Project#模块清单]] 中列出的 12 个 Tier 2 文档。
- 架构中涉及的全部专有名词统一在 [[Glossary]] 定义。