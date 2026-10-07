# 两阶段翻译引擎（Two-Stage Engine）

直译阶段以 Tool Calling 强制 JSON 输出并通过严格 ID 校验保证 id→trans 映射对齐，润色阶段注入全局画像/翻译策略/场景引导提升自然度与风格；两层共享相同的记忆注入，任一阶段失败均交由梯次拯救引擎降级重试兜底。

## Key Concepts

本节介绍两阶段翻译引擎的执行机制：直译阶段、润色阶段、后置清理及与拯救引擎的协作。

### 直译阶段（Literal Stage）
直译阶段把每个 block 重排为 `{"id": 该行索引, "text": 原内容}` 输入，借助 Tool Calling 将输出约束为 `{"translations": [{"id", "trans"}]}` 的严格 JSON，并依赖 `_do_single_request` 的长度、格式与 ID 集合校验，得到 id 对齐的 `id→trans` 映射，保证下游按行号回填不错位。Reference: [[subtitle/core/stages/literal_stage.py#process_literal_stage]]

### 润色阶段（Polish Stage）
润色阶段把直译结果与原文编成 `{id, original, literal}` 输入，注入 [[core-memory]] 的全局画像、翻译策略、场景引导及前后文，用 `REVIEW_AND_POLISH` 模板走 Tool Calling 强制 JSON 并做 ID 校验；最终按 `index` 以「润色结果 → 直译结果 → 原文」优先级兜底回填，产出含 literal/polished 双版本及 timestamp 的最终块。Reference: [[subtitle/core/stages/polish_stage.py#process_polish_stage]]

### 后置清理（postprocess_translation）
提示词之外的确定性兜底：先删除模型擅自添加的「此处指…」「注:…」说明文本；再依据**原文是否含括号**决定是否清掉译文里多余的中英文括号注释（保留原文自带括号）；随后做标点规范化——全省略号收敛为半省略号、移除中文标点、用「非数字保护」正则移除英文逗号句号并折叠多余空格。Reference: [[subtitle/core/stages/polish_stage.py#postprocess_translation]]

### 与拯救引擎的协作
两阶段不直接调用 LLM，而是统一经由 [[subtitle/core/rescue_engine.py#ladder_rescue_engine]]。它以 `_build_ladder` 生成从输入规模收敛到 1 的降级阶梯，对每个 chunk 调用 `_do_single_request`；当某 chunk 因 ID 不匹配、长度不符或 JSON 解析失败返回 `None` 时自动缩小规模重试，单条仍失败则在结束时以「原文兜底」补位（literal 用原文、polish 用同 id 直译结果），确保永远给下游产出完整列表。Reference: [[subtitle/core/rescue_engine.py#ladder_rescue_engine]]

## Dependencies

内部依赖 [[core-memory]]（画像/策略/场景文本）、[[core-context]]（`filter_relevant_glossary` 过滤局部词汇表）、[[core-rescue]]（ladder_rescue_engine 失败兜底）、[[network]]（`call_llm`/clean_and_extract_json/REFUSAL_SENTINEL facade）与 [[core-common]]（`get_prompt_templates` 加载 `LITERAL_TRANS`/`REVIEW_AND_POLISH` 模板、`canonical_json` 本地序列化）。

[[core-memory]] 提供 global_profile/policy_engine/scene_manager 产出的画像、策略、场景文本；[[network]] 的 `core.llm_client` facade 实际实现位于 subtitle/network/llm_client.py。

外部：network 层 `llm_client` 依赖 `aiohttp`（异步会话）与 `json_repair.repair_json`（JSON 容错修复）；两阶段自身仅依赖标准库 `re`、`logging`、`typing`，真正常用 asyncio 的并发在 orchestrator 侧（`asyncio.create_task` 预取下一批）。

## Consumed By

以下模块（pipeline 与 core-rescue）使用本模块的两阶段执行与降级协作能力。

- [[pipeline]] — orchestrator 按批次先执行 `process_literal_stage` 得到 `literal_map`，再执行 `process_polish_stage`；润色批次 i 期间并发 `asyncio.create_task` 预取批次 i+1 的直译，两项任务重叠以隐藏 LLM 延迟。
- [[core-rescue]] — `ladder_rescue_engine` 按 `stage="literal"|"polish"` 参数分发到对应阶段提示词与工具定义，直译/润色均复用它做降级重试与兜底回填。

## Error Conditions

本模块特有的错误条件全部集中在 `_do_single_request`：

- **JSON 提取拒绝（refusal）**：当 `clean_and_extract_json` 返回 `REFUSAL_SENTINEL` 时返回 `("__REFUSAL__", expected_ids)` 元组，拯救引擎据此记录拒绝的 ID；单条仍拒绝则跳过、最后以原文兜底。
- **结构/类型错误**：结果不是 `list`、条目缺 `id`、`id` 无法提取为整数（`re.search(r'\d+')` 失败或 int 转换抛 `ValueError/TypeError`）时跳过该条目并 `continue`。
- **字段回退**：直译取 `trans/translation/target/text`、润色取 `polished/translation/target/text` 逐字段兜底取文本。
- **长度与 ID 集合失配**：解析后结果条数 ≠ 子块数，或 `returned_ids != expected_ids` 时打日志并返回 `None`——这正是触发拯救引擎缩小 batch 重试的信号。
- **异常兜底**：整个请求抛异常时记录 `exc_info` 并返回 `None`，同样交给上一级 ladder 重试。