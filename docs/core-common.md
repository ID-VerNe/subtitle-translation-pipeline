# 基础工具（Core Common）

全模块共享的配置、提示词、缓存与 SRT 处理基础能力，位于 `subtitle/core/` 的 config.py、prompts.py、cache_utils.py、srt_utils.py 四个文件。它们提供 presets.json 多预设加载与 TranslationConfig 配置载体、`.prompt` 模板加载、文件/请求级缓存 Key 与 JSON 落盘、以及 SRT 解析/格式化/清洗，是翻译链路各层复用最广、依赖最少的地基层。

## Key Concepts

本节介绍本模块共享的基础能力：配置体系（config.py）、提示词模板（prompts.py）、缓存工具（cache_utils.py）与 SRT 工具（srt_utils.py）四类底层组件及其在翻译链路中的复用。

### 配置体系（config.py）
`config.py` 以 presets.json（多预设）为唯一配置源，`TranslationConfig` dataclass 在 `__post_init__` 中按三级优先级灌入 API Key/URL/模型、并发、容错、上下文预算、多温度与目标语言等字段。

`load_presets` 在 presets 缺失时用 `presets.json.example` 自动生成模板并读取整个预设字典；`TranslationConfig` 把逗号分隔的 `api_key` 解析为 `api_keys` 多 Key 列表、对缺失的 NER 专用配置回退到主模型，同时确保语料目录与 `CACHE_DIR` 存在。`save_config_to_presets` 用 Key 映射表把 GUI 字段写回指定预设并置 `_current`；`clear_cache` 清空统一缓存目录及遗留旧缓存。

Reference: [[subtitle/core/config.py#TranslationConfig]] 与 [[subtitle/core/config.py#load_presets]] 与 [[subtitle/core/config.py#save_presets]] 与 [[subtitle/core/config.py#TranslationArgs]] 与 [[subtitle/core/config.py#clear_cache]] 与 [[subtitle/core/config.py#save_config_to_presets]]

补充说明 `TranslationArgs`：命令行/入口的输入参数载体，读 `input_file/output_file/bilingual/target_lang`，内部构造 `TranslationConfig` 并把 API Key、并发、容错、温度等字段平铺到属性上，供 pipeline 与 GUI 消费。

### 提示词模板（prompts.py）
`prompts.py` 从 `subtitle/prompts/` 目录加载 `.prompt` 模板：`load_prompt` 读取指定模板、缺失时抛 `ValueError`；`get_prompt_templates` 按目标语言追加变体后缀并返回六类模板字典，供术语抽取、直译、润色、注解、后审各阶段取用。

`get_prompt_templates(target_lang="zh")`：`en` 时对直译与润色模板加载 `_en` 变体，一次性返回 `TERM_EXTRACT`、`NER_NAMES`、`LITERAL_TRANS`、`REVIEW_AND_POLISH`、`ANNOTATION_EXTRACT`、`POST_CHECK` 六类模板字典。

Reference: [[subtitle/core/prompts.py#load_prompt]] 与 [[subtitle/core/prompts.py#get_prompt_templates]]

### 缓存工具（cache_utils.py）
`cache_utils.py` 提供缓存 Key 与 JSON 落盘两类能力：`canonical_json` 生成稳定 JSON 字符串以最大化缓存命中；`file_fingerprint` 对文件内容求 md5；`get_cache_path`/`build_request_cache_key` 组装缓存路径与请求级缓存 Key；`load_json_file`/`save_json_file` 做容错读写。

`canonical_json` 使用 sort_keys=True、紧凑分隔符、`ensure_ascii=False`，保证 dict 顺序稳定；`file_fingerprint` 逐块求 md5（忽略文件名）；`build_file_cache_key` 把指纹、语言、模型、提示词版本 PROMPT_VERSION、schema 版本 SCHEMA_VERSION 打包后 md5；`get_cache_path` 按 `<文件名>_<文件哈希>_<用途>_<语言>.json` 组织落盘路径；`load_json_file`/`save_json_file` 写前自动建目录、读失败返回默认值。

Reference: [[subtitle/core/cache_utils.py#canonical_json]] 与 [[subtitle/core/cache_utils.py#file_fingerprint]] 与 [[subtitle/core/cache_utils.py#build_file_cache_key]] 与 [[subtitle/core/cache_utils.py#get_cache_path]] 与 [[subtitle/core/cache_utils.py#build_request_cache_key]] 与 [[subtitle/core/cache_utils.py#load_json_file]] 与 [[subtitle/core/cache_utils.py#save_json_file]]

### SRT 工具（srt_utils.py）
`srt_utils.py` 提供字幕格式处理三件套：`parse_srt` 以 UTF-8 读取、统一换行并清洗字幕块后返回 `{index, timestamp, content}` 字典列表；`clean_content` 移除注释/样式标记；`format_srt_block` 把字段统一格式化为标准 SRT 块。

`parse_srt` 修掉文件头 BOM（`lstrip`）、统一 CRLF/CR 换行、按空行切块，校验块 ID 为数字或含 `-->` 时间轴，逐块调用 `clean_content` 预处理并丢弃内容为空的块（防 LLM 幻觉）。

Reference: [[subtitle/core/srt_utils.py#parse_srt]] 与 [[subtitle/core/srt_utils.py#clean_content]] 与 [[subtitle/core/srt_utils.py#format_srt_block]]

## Dependencies
本模块是基础层，仅依赖标准库：`json`、`dataclasses`、`os`、`typing`、`hashlib`、`re`、`logging`（srt_utils），以及 `shutil`（懒加载，仅换行 copy/清理缓存时导入）；未使用 JSON 修复类第三方库，也无 SQLite 依赖。缓存一律 JSON 落盘。模块间仅 cache_utils 通过函数内动态 `from .config import CACHE_DIR` 避免循环依赖。被除自身外的所有模块上层依赖。

## Consumed By

以下模块使用本模块提供的配置、提示词、缓存与 SRT 基础能力。

- [[pipeline]] — orchestrator 用 `TranslationConfig` 取配置、`parse_srt` 解析输入、`canonical_json`/`get_cache_path` 落缓存；srt_writer、checkpoint_manager 用 `format_srt_block` 写入 SRT 断点。
- [[core-stages]] — literal_stage、polish_stage 用 `canonical_json` 稳定请求缓存。
- [[core-rescue]] — rescue_engine 用 `get_prompt_templates` 取直译提示词、`canonical_json` 缓存。
- [[core-memory]] — global_profile、scene_manager 用 `load_prompt`/`canonical_json`/`get_cache_path`/`load_json_file`/`save_json_file` 存取画像与场景缓存，policy_engine 用 `canonical_json`。
- [[core-glossary]] — terminology_extractor 用 `get_prompt_templates` 获取术语抽取模板。
- [[core-context]] — context_builder 用 `canonical_json` 缓存相关术语上下文。
- [[core-quality]] — quality_checker/annotation_pipeline、post_checker 复用提示词加载与缓存工具。
- [[network]] — llm_client、request_handler 依赖缓存工具与配置构建请求 Key。
- [[gui]] — preset_manager 用 `save_config_to_presets`/`load_presets`/`save_presets` 管理预设；main_window 读 `PRESETS_FILE`；view_models 构造 `TranslationConfig`；task_controller 用 `TranslationArgs` 与 `clear_cache`/`get_cache_path`。
- [[entries]] — main.py 用 `TranslationConfig`/`TranslationArgs`/`CACHE_DIR`/`get_cache_path`；translate_srt_llm 用 `TranslationConfig`；compare_translations 用 `parse_srt` 对比字幕。

## Error Conditions

本节列出本模块处理失败时可能出现的错误与兜底行为。

- presets.json 缺失且无 `.example`：`load_presets` 返回 `{}`，`TranslationConfig` 回退硬编码默认值，pipeline 可正常以默认配置运行。
- presets.json 损坏（JSON 解析失败）：`load_presets` 捕获底层异常并返回 `{}`，不中断调用方。
- `.prompt` 模板缺失：`load_prompt` 抛 `ValueError(f"Prompt template ... not found")`，该异常向上传导，提示词依赖方会因此失败。
- 读取非 `en` 语言时直译/润色无 `_<lang>` 变体：`get_prompt_templates` 仅区分 `en` 与其他语言（其余按默认无后缀加载），不会因语言代码错误而崩溃。
- 输入 SRT 文件不存在：`parse_srt` 打印错误并返回 `[]`，调用方按空字幕处理。
- 预处理（`clean_content`）后内容为空：`parse_srt` 记录 warning 并丢弃该块，防止空块触发 LLM 幻觉。
- 写 presets.json 失败：`save_presets` 捕获异常仅打印错误，不抛出；GUI 保存配置时不会硬中断。
- 缓存读/写异常：`load_json_file` 返回默认值，`save_json_file` 自动建目录，均不向上抛。