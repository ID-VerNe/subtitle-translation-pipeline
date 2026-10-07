# Glossary — 术语表

本文件是整个文档体系的单一术语权威来源：每个概念只在下方定义一次，[[Architecture]]、[[Project]] 及各 Tier 2 模块文档统一用 wiki link 引用，避免同义重复。术语按主题分组，翻译方向（英→中 / 中→英）不影响其含义，仅影响部分库文件的选择。

## 记忆类概念

本节涵盖系统把"整片视角"固化为结构化记忆的三个产物，是整个 Pipeline 区别于纯文本翻译的基石。

### 全局画像

全局画像（Global Profile）是一份描述整部影片语义特征的结构化 JSON：包含影片类型（Genre）、整体语调（Tone）、详细人物画像（Characters，含性别/说话风格）、人物关系图谱（Relationships）与世界观设定。它在正式翻译前由 LLM 生成，并在每个批次翻译时按场景参与者动态压缩后回灌给模型，解决"LLM 只见几十行、不通全片"的上下文断裂问题。落地为 `global_profile.json`，对应源码实现见 [[subtitle/core/memory/global_profile.py#build_global_profile|global_profile]]。

### 全局画像采样

全局画像采样（Global Discovery Sampling）是生成画像前对全文的固定采样策略：在 >120 块时取"开头 15%、中间 15%、结尾 15%"三段（首/中/尾各 15%），覆盖影片开篇、发展与结局。采样比例与位置固定以保证可复现性和稳定性，采样后的文本经压缩后送入 LLM 生成画像。见 [[subtitle/core/memory/global_profile.py#sample_blocks_for_global_profile|sample_blocks_for_global_profile]]。

### 翻译策略

翻译策略（Translation Policy）是由全局画像、全片术语与目标语言综合生成的翻译规范 JSON，用于约束整体译法（语气、风格、术语处理）。它基于画像动态构建并可随场景参与者动态收敛（`build_translation_policy`），在直译与润色两阶段都注入提示词，保障全片译风一致。见 [[subtitle/core/memory/policy_engine.py#build_translation_policy|policy_engine]]。

### 场景映射

场景映射（Scene Mapping）把全文分割成语义上自洽的场景：先按固定粒度切出基础场景块，再由 LLM 富化每个场景的参与者列表、场景摘要与特定语域；翻译批次严格对齐到这些固定边界，避免切段打断对话。见 [[subtitle/core/memory/scene_manager.py#load_or_build_scene_map|scene_manager]]。

## 翻译执行概念

本节定义翻译"如何执行"的两个阶段与失败兜底机制。

### 直译阶段

直译阶段（Literal Stage）是两阶段翻译的第一步，负责 ID 对应与语义还原。它对批次内的字幕逐条建立 `id→trans` 映射，通过 Tool Calling 强制模型输出 JSON，并严格校验 ID 与格式，保证每行译文编号不丢失不错位。见 [[subtitle/core/stages/literal_stage.py#process_literal_stage|literal_stage]]。

### 润色阶段

润色阶段（Polish Stage）是两阶段翻译的第二步，基于直译结果注入全局画像、翻译策略与场景引导，提升译文的自然度与可读性；随后做标点与括号注释的后置清理——原文无括号时删除模型擅自添加的括号注释，这是提示词约束之外的第二道防线。见 [[subtitle/core/stages/polish_stage.py#process_polish_stage|polish_stage]]。

### 梯次拯救

梯次拯救（Ladder Rescue）是请求失败的逐级降级重试机制。遇到 API 超时或内容安全拦截（拒绝）时依次执行：(1) 缩小批次重试（8→4→2→1）；(2) 剥离动态记忆仅保留场景引导；(3) 仅留全局画像与核心术语。系统记忆被拒行并主动跳过；兜底规则为"直译退回原文、润色退回直译"，保证任务永不中断——完整性优先于质量。见 [[subtitle/core/rescue_engine.py#ladder_rescue_engine|rescue_engine]]。

## 术语库体系

本节统一"术语怎么办"这一横向关切，包含承载存储的四个库与按用途划分的三级词条，概念间相互配合而非互斥。

### 三级术语库

术语按用途分为三级：核心术语（全片核心专有名词，全程跟随）、动态术语库（每批次按当前文本子串匹配过滤出相关的局部术语）、人名库（专为人名歧义服务的独立库），共同构成"全程一致 + 局部贴合 + 专名准确"的术语保障。

### 核心术语

核心术语（Core Terms）是从全片术语中提取出最关键的专有名词子集，在直译与润色请求中全程注入，保证同一名词在整片翻译中译法稳定统一。由 `build_core_terms` 从完整术语中构建（见 [[subtitle/core/context_builder.py#build_core_terms|context_builder]]）。

### 动态术语库

动态术语库（Local Glossary / 动态库）并非存储库，而是每个批次翻译前用 flashtext 对当前文本做子串匹配、从全库过滤出的相关术语子集。它避免把不相关术语塞入上下文，节省 Token 并减少干扰。见 [[subtitle/core/context_builder.py#filter_relevant_glossary|filter_relevant_glossary]]。

### 人名库

人名库（Name DB）是集成约 67 万条《世界人名翻译大辞典》数据的 SQLite 库（`glossaries/names_translation.db`）。系统用 LLM NER 提取文中人名（`fetch_names_with_llm`），或按大写启发式从文本识别候选者（`search_names`），再在库中匹配译名，解决 `Will`（动词 vs 人名）等歧义。

### 发现库

发现库（Discovery DB，`llm_discovery.db`）存储 LLM 自动发现并持久化的术语（category 为 `LLM_Discovered`）。它与人审词条分库隔离，可独立开关加载与提取；中→英反向翻译时使用 `llm_discovery_cn.db`。见 [[subtitle/core/glossary_manager.py#GlossaryManager|glossary_manager]]。

### 精校库

精校库（Curated DB，`glossary_cache.db`）存储人工整理、质量可信的静态词条，由 `glossaries/*.json` 词条文件按文件哈希增量导入（category 如 General）。它作为全片的终极权威术语源，发现库自动词条不得污染它，体现"人审成果优先"。见 [[subtitle/core/glossary_manager.py#GlossaryManager|GlossaryManager]]。

## 运行与容错概念

本节定义系统如何在资源受限、可中断的环境下稳定运行。

### 负载均衡

负载均衡（Load Balancing）指 `SmartLoadBalancer` 在多 API Key 之间按"成功率 × 可用并发槽 /（平均响应时间+1）"打分择优选路，跳过不健康 Key，失败任务自动重启并换 Key 重试；同时用 `RateLimiter` 控制 RPM/TPM，针对 `GLM-4-Flash` 压制并发防 429。见 [[subtitle/network/request_handler.py#SmartLoadBalancer|request_handler]]。

### 断点续传

断点续传（Checkpoint / Resume）通过进度 JSON 记录已处理的字幕块（`processed_indices`）与最近的上下文锚点，任务中断后可跳过已处理块直接从剩余位置续跑，并复用已生成的术语缓存，避免重复烧钱。见 [[subtitle/pipeline/checkpoint_manager.py#save_checkpoint|checkpoint_manager]]。

### 双语输出

双语输出（Bilingual Output）指最终 SRT 中每一行字幕以"原文 + 译文"成对写出的模式：`srt_writer` 用递增的 `output_block_index` 依次写入原文块与译文块，方便对照观看；关闭时仅输出译文。见 [[subtitle/pipeline/srt_writer.py#rewrite_output|srt_writer]]。

### 滑动窗口

滑动窗口（Sliding Window）是一对限速与上下文的两处应用。限速侧，`RateLimiter` 用 deque 记录过去 60 秒的请求与 Token 消耗，逐出过期记录以结算 TPM 余量；上下文侧，`build_recent_state` 只回灌最近 N 行（`max_previous_lines`）作为跨批次锚点并预取未来语境，兼顾记忆连续性与 Token 成本。

## 质量增强概念

本节定义四类可选/可插拔的质量增强能力，它们位于翻译主链之外但显著提升成片质量。

### 温度策略

温度策略（Temperature Strategy）根据场景特征动态决定直译与润色阶段的温度：技术性内容用低温度求精确，幽默/情感内容用高温度求创造力。由 `DynamicTemperatureStrategy` 依据场景语域、是否含数字/俚语等信号自动调整，而非全程使用固定值。见 [[subtitle/core/temperature_strategy.py#DynamicTemperatureStrategy|temperature_strategy]]。

### Few-Shot

Few-Shot（示例引导）为不同场景类型（幽默、技术、情感强烈等）预置少量高质量翻译示例作为参考，在润色阶段随场景特征自动匹配注入，引导模型模仿指定风格。见 [[subtitle/core/fewshot_manager.py#FewShotExampleManager|fewshot_manager]]。

### ASR 清洗

ASR 清洗（ASR Scrub）是可选的前置净化步骤：使用独立的 `scrub_model`（从 presets 指定）对剩余未翻译块做语音识别文本修正，纠正 ASR 产生的错字/断句后再进入翻译。见 [[subtitle/core/asr_scrubber.py#run_asr_scrub|asr_scrubber]]。

### 注解管线

注解管线（Annotation Pipeline）在翻译完成后按字幕块批量生成文化/bg 注释（可选开启），并把注解作为独立 SRT 块插入，产出 `_with_annotations.srt` 供 ASS 阶段使用。见 [[subtitle/core/annotation_pipeline.py#generate_annotations_for_subtitle|annotation_pipeline]]。

### 颜色标签对齐

颜色标签对齐（Color Tag Alignment）是终审阶段 `post_checker` 的第一级确定性格间清理逻辑：对一对（原文+译文）字幕执行确定性清洗与颜色标签对齐，保证字幕里的样式标签在原文与译文中位置一致，再进入更深层的 LLM 逻辑审查。见 [[subtitle/core/post_checker.py#align_color_tags|post_checker]]。

## 相关文档

本节给出理解系统所需路径的快速入口，指向数据流、术语与模块细节。

- 术语对应的实现细节在 [[Architecture#数据流]] 与各个 Tier 2 模块文档（见 [[Project#模块清单]]）中展开。
- 生成这些术语的业务流程起点见 [[Architecture#技术选型]]。