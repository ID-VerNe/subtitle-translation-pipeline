# 质量与清理（Quality & Cleanup）

翻译主链之外的硬保障：质量检查器以规则库背离 LLM 地捕获书面语/机翻痕迹/长度异常/情绪丢失，后审跑颜色标签对齐、确定性清洗与多轮 LLM 逻辑终审，另可按批生成文化注解并插入字幕，还能在翻译前用独立 scrub 模型修正 ASR 语音转写错字，共同补足提示词约束之外的质量兜底。

## Key Concepts

本节介绍质量与清理模块的硬保障能力：规则质量检查与术语一致性回查、颜色标签对齐与清洗、LLM 终审、注解管线与 ASR 清洗。

### 规则质量检查（TranslationQualityChecker）
硬规则质检，完全不依赖 LLM，在润色后对每个 block 捕获四类问题：命中 `formal_words` 书面语黑名单（「进行/实施/显著/然而」等）、命中 `machine_patterns` 机翻特征正则（连续「的的/了了」、重复标点）、译文长度越界（短于原文 40% 判「过短」，长于 150% 判「过长」）、原始情绪标记（`!/?.../Fuck`）在译文中消失。「过短/过长」取其比值并保留问题文本以便人工复盘。Reference: [[subtitle/core/quality_checker.py#TranslationQualityChecker]]

### 术语一致性回查（check_consistency）
接收 glossary 术语表做全片一致性校验：仅当【英文原文】包含某个 glossary 源词时才记录该 block，再检查对应【中文译文】是否含规定目标译法，缺失者列为「术语不一致」并只展示前 3 个 case。注意其方向修正——在原文里找源词、在译文里找目标，避免旧实现「在中文里找英文词」导致的漏检。Reference: [[subtitle/core/quality_checker.py#TranslationQualityChecker]]

### 颜色标签对齐与清洗（align_color_tags / level1_deterministic_cleaning）
后审 Level 1 的确定性清洗：`align_color_tags` 若原文含 `<font color=...>` 则剥离译文所有 font 标签后按原文颜色重新包裹，若原文无标签则把译文残留 font 标签一并剥除；`level1_deterministic_cleaning` 遍历 paired_blocks 应用该对齐，比对变化后同步写回 `polished` 与 `content` 字段并统计清洗行数。Reference: [[subtitle/core/post_checker.py#align_color_tags]] 与 [[subtitle/core/post_checker.py#level1_deterministic_cleaning]]

### LLM 终审（run_post_checker）
后审统一入口，按 Level 1 → Level 3 执行：先跑确定性清洗，再交给 `level3_iterative_llm_logic_audit` 做最多 `max_passes`（默认 5）轮全局对抗逻辑审校，某轮无改动即早停通关。

每轮 `run_single_pass_audit` 动态加载 `post_check` 模板、超 500 行自动切块，以 Tool Calling 约束模型提交 `submit_audit_corrections` 结构化 JSON，按 ID 应用修复结果并再次过 `align_color_tags`。Reference: [[subtitle/core/post_checker.py#run_post_checker]]

### 注解管线（Annotation Pipeline）
翻译完成后按 `batch_size`（默认 150）分批扫描字幕，`generate_annotations_for_subtitle` 汇总 `extract_annotations_batch` 的提取结果、按术语小写归一化全局去重并构造 `{subtitle_id: 注释文本}` 映射，供 SRT 写出时插入产出 `_with_annotations.srt`。Reference: [[subtitle/core/annotation_pipeline.py#generate_annotations_for_subtitle]] 与 [[subtitle/core/annotation_pipeline.py#extract_annotations_batch]]

`extract_annotations_batch` 加载 `annotation_extract` 模板、以 Tool Calling 约束模型返回 `submit_annotations` JSON（subtitle_id/term/explanation），只保留术语首次出现。

### ASR 清洗（ASR Scrub）
可选前置净化：用独立 `scrub_model` 加载 `asr_scrubber` 模板，按 `CHUNK_SIZE=250` 切块让高智力模型找出转写硬伤/黑话，Tool Calling 约束返回 `submit_corrections`；再由 `apply_scrub_corrections` 对 block 文本做字符串替换修正。Reference: [[subtitle/core/asr_scrubber.py#run_asr_scrub]] 与 [[subtitle/core/asr_scrubber.py#apply_scrub_corrections]]

`submit_corrections` 结构含 original/corrected/reason；`apply_scrub_corrections` 仅当原文含该子串时 `replace`。

## Dependencies

内部依赖 [[core-common]]（提示词模板与配置）、[[network]]（`call_llm` 与 `clean_and_extract_json`，core/llm_client.py 仅为转发 facade）、[[core-glossary]]（`check_consistency` 回查术语表）；注解管线另依赖 `canonical_json` 做本地序列化。

[[subtitle/core/prompts.py#load_prompt]] 加载 `post_check`/`annotation_extract`/`asr_scrubber` 模板，[[subtitle/core/config.py#TranslationConfig]] 承载 api_key/model_name 配置；[[subtitle/network/llm_client.py#call_llm]] 与 [[subtitle/network/llm_client.py#clean_and_extract_json]] 负责全部 LLM 调用与 JSON 容错解析，post_checker/annotation_pipeline 从 `.llm_client` 进入，asr_scrubber 直接 `from core.llm_client` 绝对导入；`check_consistency` 回查的 glossary 形如 `{source: {target: ...}}`，cache_utils 的 [[subtitle/core/cache_utils.py#canonical_json]] 做注解本地序列化。

外部：标准库 `re`（正则黑名单/标签剥离）、`asyncio`（注解批次间 `asyncio.sleep(0.5)` 限速）、`json`（模板变量序列化）、`logging`/`typing`。此外 quality_checker 与 post_checker 依赖 `OrderedDict`（注解全局去重时的 `from collections import OrderedDict`）。

## Consumed By

以下模块（pipeline 与 entries）使用本模块的质量终审、注解与 ASR 清洗能力。

- [[pipeline]] — orchestrator 在翻译完成后立即 `run_post_checker` 做三级终审；按配置在前置阶段用独立 scrub 模型跑 `run_asr_scrub`；并在 SRT 写出前调用 `generate_annotations_for_subtitle` 生成 `_with_annotations.srt`。
- [[entries]] — 是否启用注解管线与 ASR 清洗由入口命令行/GUI 配置开关决定（`--annotations`/`--scrub` 类选项控制对应分支）。

## Error Conditions

各子检查器采用「静默降级、绝不中断主链」的错误语义：

- **一致性检查结构兜底**：`check_consistency` 对 glossary 条目同时兼容 `dict`（取 `target`）与 `str`，无有效 `target` 时 `continue` 跳过该词，不会因为术语表格式异常而崩溃。
- **终审 JSON 解析失败**：`run_single_pass_audit` 中 `clean_and_extract_json` 抛异常时仅 `logger.error` 并丢弃该轮纠正；`all_corrections` 为空返回 `(paired_blocks, False)`，直接触发下一轮早停判断。
- **ID 应用失败**：修复条目 `cid` 不在索引映射或 `fixed` 为空则跳过；`by_id` 仅收录可转为整数 index 的 block。
- **注解 ID 防御转换**：`subtitle_id` 为字符串时用 `re.search(r'\d+')` 提取，`int()` 抛 `ValueError/TypeError` 时置 `None`，被忽略；批次层提取异常用 `logger.error` 后 `continue` 跳过该批继续下一批。
- **ASR 空返回/解析失败**：`run_asr_scrub` 分块解析异常仅记录错误；`raw` 为空时告警（提示 Reasoning 耗尽 token、`finish_reason=length`）；`corrections` 为空则原样返回 blocks，`apply_scrub_corrections` 对空纠正列表直接短路返回。