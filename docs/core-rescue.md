# 梯次拯救引擎（Ladder Rescue Engine）

请求失败时按批次容量逐级降级重试（8→4→2→1 减半缩批次），识别模型拒绝并记忆/跳过被拒行，全部降级仍失败时兜底退回原文或直译，保证每条字幕永不因单次 API 失败而中断。

## Key Concepts

本节介绍梯次拯救引擎的核心机制：降级梯次、单次请求执行、拒绝感知与兜底策略。

### 降级梯次（Batch-Size Ladder）

本模块的「梯次」降级作用于**单次请求的批次容量**，而非提示词上下文：失败时只缩小每批字幕条数，`global_profile`、`scene_guidance`、`previous_context` 等一律原样透传。梯次由 [[subtitle/core/rescue_engine.py#_build_ladder]] 从 `input_size` 反复 `cur // 2`（不足时 `cur - 1`）缩至 1 生成，再去重排序为候选容量序列。

`_build_ladder` 从输入 `input_size` 出发每步 `cur // 2`（不足时 `cur - 1` 保证收敛）直至 1，如输入 8 得 `[8,4,2,1]`、输入 5 得 `[5,2,1]`，再去重后由主入口 `ladder_rescue_engine` 降序排序为候选容量序列，供 `while` 主循环从小到大逐级尝试。

### 单次请求执行（_do_single_request）

[[subtitle/core/rescue_engine.py#_do_single_request]] 负责一次真正与 LLM 的交互：先按 `stage` 选取模板、把字幕块规范化为入参，经 [[subtitle/core/cache_utils.py#canonical_json]] 稳定序列化并装配强制 JSON 输出的 tool/`response_format`，随后以 `raise_on_refusal=True` 调用 [[subtitle/network/llm_client.py#call_llm]]；拒绝时立即回包拒绝哨兵，成功则解析并校验长度与 ID 集合完全对齐。

`stage=literal` 用 `LITERAL_TRANS`、`polish` 用 `REVIEW_AND_POLISH`（来自 [[subtitle/core/prompts.py#get_prompt_templates]]）；入参规范化为 `{id, text}/{id, original, literal}`；返回值为拒绝哨兵时回包 `("__REFUSAL__", expected_ids)`；成功则用 [[subtitle/network/llm_client.py#clean_and_extract_json]] 解析、内置 `_scrub` 清洗注释/斜杠，动态识别 `trans`/`polished` 字段，`returned_ids != expected_ids` 即返回 `None` 视为失败。

### 拒绝感知（Refusal Awareness）

拒绝被当作一种「可跳过」而非「可重试」的错误分开处理：`_do_single_request` 以 `raise_on_refusal=True` 复用 [[subtitle/network/llm_client.py#ContentRefusalError]] 与 `REFUSAL_SENTINEL` 区分拒绝与普通失败；当结果为拒绝哨兵且已降到 `size == 1` 时，主循环把该行 id 记入 `refused_ids` 并跳过。

后续循环里 `chunk_ids <= refused_ids` 的分块直接 `continue`，既不重试也不产出内容。

### 兜底策略（Fallback）

完整性优先于质量：当对某一条字幕所有可用容量都重试失败（`success` 恒为 False）时，`ladder_rescue_engine` 在 `if not success` 分支直接落铺兜底结果——`stage == "literal"` 时 `trans` 退回字幕**原文**，`stage == "polish"` 时 `polished` 退回该行直译映射 `literal_map`（缺失则退回原文），保证每个索引最终都有结果返回，从而让任务永不中断。

## Dependencies

内部模块：[[core-stages]]（直译/润色阶段构造批次并装配上下文、术语/画像/策略/场景引导）、[[core-common]]（其中 [[subtitle/core/prompts.py#get_prompt_templates]] 与 [[subtitle/core/cache_utils.py#canonical_json]] 被直接调用）、[[network]]（[[subtitle/network/llm_client.py#call_llm]]、[[subtitle/network/llm_client.py#clean_and_extract_json]]、`REFUSAL_SENTINEL`）。外部：`logging`、`re`（读代码确认：`import logging; import re`）；`asyncio` 与 `json_repair` 未在此文件直接 import，JSON 容错由 network 层内的 `json_repair` 承担。

## Consumed By

以下模块（core-stages 与 pipeline）使用本模块的降级重试与兜底能力。

- [[core-stages]] — 直译/润色请求失败时由本模块统一兜底（[[subtitle/core/rescue_engine.py#ladder_rescue_engine]] 作二者唯一请求代码路径）
- [[pipeline]] — orchestrator 逐批调用本引擎，将失败降级与该批结果的下游处理隔离

## Error Conditions

[[subtitle/core/rescue_engine.py#ladder_rescue_engine]] 特有的错误处置逻辑：`_do_single_request` 对解析失败、长度/格式不符、ID 不匹配、或任何异常统一吞掉并返回 `None`（仅打 warning/error 日志），由主循环判定为"该容量失败"。当所有降级容量都对同一行失败时触发兜底退回原文/直译（见下方兜底策略）；若缩到 `size == 1` 仍返回拒绝哨兵则记入 `refused_ids` 放弃该行。由此保证只要原文件解析正确，每个 `blocks` 索引都一定有输出，类似乎"永不抛错中断"的契约。