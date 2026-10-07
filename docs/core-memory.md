# 记忆引擎（Memory Engine）

本模块把整部影片的"整片视角"固化为三块结构化记忆——全局画像（Global Profile）、翻译策略（Translation Policy）、场景映射（Scene Map）——在直译与润色阶段随批次逐段注入，保证角色称谓、语域与场景口径全程一致。

## Key Concepts

本节介绍本模块的三块记忆引擎——全局画像、翻译策略、场景映射——以及它们的门面封装。

### 全局画像（Global Profile）
描述影片类型（genre）、语调整体（tone）、人物画像（characters，含 names/gender/speech_style）、人物关系（relationships）、场景设置（setting）与翻译风格偏好（translation_style），由 LLM 按固定采样生成并存为 `global_profile.json`。

采样采用固定三段式以稳定输入：标题块总数 ≤120 时全量返回，否则取开头 15%、中间 15%（0.425~0.575 区间）与结尾 15%，去重后通过 `compact_blocks_for_prompt` 压入提示词，调用 `call_llm`（temperature=0.0、`response_format=json_object`）。构建流程为 build→sanitize→normalize：`sanitize_global_profile` 丢弃不符合 schema 的脏元素（针对 LLM 把键名混入数组），`normalize_global_profile` 用 `canonical_json` 稳定数组顺序以最大化缓存命中。`load_or_build_global_profile` 优先读缓存，miss 时回退到 `default_global_profile` 兜底再落盘；`global_profile_text` 经上下文感知的 `compact_global_profile` 生成规范化文本，其中可针对当前场景参与者保留相关角色、压缩无关角色。

Reference: [[subtitle/core/memory/global_profile.py#sample_blocks_for_global_profile]]、[[subtitle/core/memory/global_profile.py#build_global_profile]]、[[subtitle/core/memory/global_profile.py#load_or_build_global_profile]]、[[subtitle/core/memory/global_profile.py#normalize_global_profile]]、[[subtitle/core/memory/global_profile.py#compact_global_profile]]

### 翻译策略（Translation Policy）
由全局画像 + 术语表 + 目标语言综合生成的一棵规范 JSON 树，是直译/润色阶段的刚性约束。结构含四类规则：
- `pronoun_rules` —— 由字符名与性别映射的人称代词规则（zh 下 female 系→"她"、male 系→"他"）。
- `register_rules` —— 由人物关系派生的语域规则（称呼称谓、语气八股）。
- `core_term_rules` —— 术语表扁平化的关键术语对照（源词→目标词对）。
- `style_rules` —— 固定影视字幕风格、字幕 ID 完整性、角色称谓一致性、Domain 优先纠义与禁止无依据音译等硬性条目。

构建时按 `scene_participants` 做上下文感知裁剪：相关角色的人称规则优先全量保留，无关角色超出阈值即截断，关系仅当涉及当前场景参与者时保留；`policy_text` 再经 `normalize_translation_policy` 统一数组顺序后以 `canonical_json` 输出。

Reference: [[subtitle/core/memory/policy_engine.py#build_translation_policy]]、[[subtitle/core/memory/policy_engine.py#normalize_translation_policy]]、[[subtitle/core/memory/policy_engine.py#policy_text]]

### 场景映射（Scene Map）
把整片切成场景并为每个场景补充语义信息，使翻译批次对齐场景边界：`build_simple_scene_map` 按固定 block 数线性切块生成场景骨架，`load_or_build_scene_map` 优先读缓存、逐场景 LLM 富化参与者/语气/领域/摘要并即时落盘。

切块默认 `scene_size=80`，生成 `scene_XXXX`、起止 `block_range`、前 12 条文本的 `summary` 骨架并置 `enriched=False`；`enrich_single_scene` LLM 富化 participants/tone/domain/summary/translation_notes，超 45 条再做首中尾采样；`find_scene_for_block` 按 `block_range` 定位任意字幕块所属场景；`scene_guidance_text` 生成场景引导；`build_scene_aligned_batches` 依据场景边界分批，使批次绝不跨越场景。

翻译批次按 `batch_size` 一条切分，翻译时可携带该场景的参与者与语域上下文。

Reference: [[subtitle/core/memory/scene_manager.py#build_simple_scene_map]]、[[subtitle/core/memory/scene_manager.py#enrich_single_scene]]、[[subtitle/core/memory/scene_manager.py#load_or_build_scene_map]]、[[subtitle/core/memory/scene_manager.py#scene_guidance_text]]、[[subtitle/core/memory/scene_manager.py#build_scene_aligned_batches]]

### 记忆门面（global_memory.py）
`global_memory.py` 是 memory 子模块的门面（Facade），仅为向后兼容将三个文件的顶层函数统一 re-export 到 `__all__`，本身不含业务逻辑。调用方既可 `from core.global_memory import ...` 也可直接 `from core.memory.xxx import ...`，两者等价。

Reference: [[subtitle/core/global_memory.py]]

## Dependencies
内部模块：读取 [[core-common]]（`target_lang`、`load_prompt` 加载 `global_memory.prompt`/`global_scene.prompt`、`cache_utils` 的缓存与序列化）；调用 [[network]]（`call_llm` 与 `clean_and_extract_json`）生成画像和富化场景。

[[core-common]] 提供 `config.target_lang`、`core.prompts.load_prompt`，`cache_utils` 的 `get_cache_path`/`load_json_file`/`save_json_file`/`canonical_json`；[[network]] 的 `core.network.llm_client` 提供 `call_llm` 与 `clean_and_extract_json`。

外部：缓存经 `cache_utils` 以 **JSON 落盘**（非 SQLite）——画像存 `global_profile.json`、场景存 `scene_map.json`，路径由 `get_cache_path(input_file, key, target_lang)` 派生；`typing` 与标准库 `json` 仅作类型与序列化。被 [[core-stages]] 与 [[pipeline]] 消费。

## Consumed By

以下模块（pipeline 与 core-stages）使用本模块的三块记忆注入翻译。

- [[pipeline]] — orchestrator 在采样后构建全局画像、翻译策略与场景映射，再将三块记忆注入翻译。
- [[core-stages]] — 直译/润色阶段读取画像文本与场景引导，按场景对齐批次逐段使用。

## Error Conditions

本节列出本模块构建与加载记忆时可能出现的错误与兜底行为。

- 画像 JSON 解析失败或 LLM 返回非 dict：`build_global_profile` 回退 `default_global_profile`（空字符/空关系/默认影视字幕风格），保证下游不中断。
- LLM 把 schema 键名混入对象数组：`sanitize_global_profile` 丢弃非 dict 脏元素。
- 场景富化解析失败：`enrich_single_scene` 返回 `{}`，该场景不置 `enriched`，下次调用重试（同一次运行内自然推进）。
- 读缓存失败（`load_json_file` 返回非 dict/空）：分别回退到重新构建画像或重新切场景骨架；场景缓存损坏时从 `build_simple_scene_map` 重建。
- JSON 键可含非字符串（LLM 脏数据）：`normalize_translation_policy` 用 `canonical_json` 排序稳妥处理。
- 网络失败：`call_llm` 异常会向上抛出，交由调用方（orchestrator）统一重试/兜底，本模块不吞异常。