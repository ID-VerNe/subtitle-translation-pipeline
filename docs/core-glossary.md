# 三级术语库体系（Intelligent Glossary）

全片术语的提取、清洗、分级存储与按需注入体系，保证专名译法全程一致：核心术语全程跟随、动态术语按子串过滤、人名经 LLM/NER 提取后与人名库匹配，双库物理隔离存储。

## Key Concepts

本节介绍三级术语库体系的组织与流转：术语库管理器、术语清洗、全局术语提取、双库物理隔离与人名库及 NER 识别。

### 术语库管理器（GlossaryManager）

`GlossaryManager` 是全术语体系的中枢门面，管理精校库/发现库/人名库三类 SQLite 库的加载、增量导入、术语提取保存与人名搜索，类内方法含 `initialize`、`incremental_update`、`extract_terms`、`save_terms`、`search_names`、`fetch_names_with_llm`，模块末尾暴露单例 `glossary_manager`。

`initialize` 按方向选定发现库路径、`_init_db` 建表（`terms`/`file_hashes`，并迁移补 `description`/`instruction` 列）并建索引，随后执行 `incremental_update` 增量导入与 `_load_to_memory` 加载到内存的 `keyword_processor`（flashtext）与 `term_mapping`；`extract_terms` 用 flashtext 子串匹配从文本中按需提取术语，可分别开关静态/发现库词条（以 `category == 'LLM_Discovered'` 区分）。

Reference: [[subtitle/core/glossary_manager.py#GlossaryManager]]

### 术语清洗（sanitize_glossary）

对提取/合成得到的术语字典做全量持久清洗，过滤无效与危险词条。`sanitize_term_entry` 校验源/目标非空、剥离 target 括号内解释（`[\(（]…[\)）]`）、遇 `/` 或 `、` 取最前单选词、超 30 字符判无效并返回 `None`；`sanitize_glossary` 遍历字典，兼容 `{source,target}` 结构化与 `str` 两种词条形式，重写清洗后的 `source`/`target`。

Reference: [[subtitle/core/glossary_sanitizer.py#sanitize_glossary]]、[[subtitle/core/glossary_sanitizer.py#sanitize_term_entry]]

### 全局术语提取（extract_global_terms）

`extract_global_terms` 以「数据分集 × 每批采样」的多步循环模式提取全片术语：分批跨步行采样拼成长文本、按 4000 字符切片后为每片发起 `TERM_EXTRACT` 任务，结果经处理归一化、清洗并 `save_terms` 回写发现库后返回最终术语表。

首轮并行追加 `NER_NAMES` 人名任务；`call_llm_batch` 批量请求（tqdm 进度条，末段打印负载均衡统计）。结果经 `process_item` 递归归一化为统一字典，人名结果调 `search_names` 回填 `Proper Name (DB)`；最后合并 `extract_terms` 的存量术语表、经 `sanitize_glossary` 清洗。

`num_passes = max(5, (len(blocks)+99)//100)` 保证至少 5 轮覆盖不同采样偏移；词条里层结构（list/dict/嵌套）与应急字段（terms/glossary/source/term/src 等）均做兜底解析。

Reference: [[subtitle/core/terminology_extractor.py#extract_global_terms]]

### 双库物理隔离

精校库 `glossary_cache.db`（人审词条）与发现库 `llm_discovery.db`（LLM 自动发现词条）物理分离、互不污染：精校库经 MD5 文件哈希对语料 JSON 做增量导入，发现库由 `save_terms` 写入、可用配置独立启停。

精校库 `incremental_update` 用 MD5 文件哈希对 `glossaries/` 目录与 `online_db_api/glossary` 的 JSON 做增量导入，仅变化文件触发 `_process_single_file` 的 `INSERT OR REPLACE`；发现库 `category='LLM_Discovered'`，中→英反向用 `llm_discovery_cn.db`；可用 `enable_llm_discovery` 配置独立启停，正向/反向 `initialize()` 切换不同 db 路径。

### 人名库与 NER

`search_names` 配合 `enable_names_db` 开关：优先使用外部传入的 `known_names`（LLM NER 提取结果），否则回退启发式生成候选，并强制用 `term_mapping` 排除已入库词条消歧，再查询人名库匹配译名；`fetch_names_with_llm` 为统一的人名识别入口。

启发式指首字母大写词对 + 大写词 + 停用词表 + 大小写差异过滤生成候选；对候选做 `SELECT…FROM names WHERE 源语言 IN (…) COLLATE NOCASE` 查询，并过滤威妥玛/音节音节的短词与过长的多义译名；`fetch_names_with_llm`：LLM 识别人名后自动走 `search_names` 匹配译名。

## Dependencies

内部依赖 [[core-common]]（配置路径与提示词模板）与 [[network]]（`call_llm`/`call_llm_batch` 等），并被 [[core-context]] 反向调用；外部依赖 `sqlite3`、`flashtext.KeywordProcessor` 与 `hashlib`/`json`/`re`/`logging` 等标准库。

[[core-common]] 的 `config.py` 提供 `GLOSSARY_DIR`/`GLOSSARY_DB_PATH`/`LLM_DISCOVERY_DB_PATH`/`LLM_DISCOVERY_CN_DB_PATH`/`NAMES_DB_PATH` 与 `TranslationConfig.enable_llm_discovery`/`enable_names_db`、`prompts.get_prompt_templates` 的 `TERM_EXTRACT`/`NER_NAMES` 模板；[[network]] 的 `clean_and_extract_json`/`get_load_balancer_stats`；[[core-context]] 的 `filter_relevant_glossary` 用 `search_names` 做局部人名消歧。

外部：`sqlite3`（三库存取）、`flashtext.KeywordProcessor`（子串术语匹配，`case_sensitive=False`）、`hashlib.md5`（文件指纹增量）、`json`/`re`/`logging`（序列化、正则与日志）。人名库 `names_translation.db` 表结构为 `names(源语言, 中文译名, 国家)`。

## Consumed By

以下模块使用本模块生成的全局术语表、内存术语索引与局部人名消歧能力。

- [[pipeline]] — 翻译管线构建阶段调用 `extract_global_terms` 生成全局术语表，翻译前 `initialize()` 构建内存术语索引。
- [[core-stages]] — 直译/润色阶段注入核心（核心术语）与动态（按批匹配的局部术语）两级术语。
- [[core-context]] — `filter_relevant_glossary` 按当前文本子串过滤相关术语并经人名库补充局部专名，组装 glossary payload。

## Error Conditions

本节列出本模块处理失败时可能出现的错误与兜底行为。

- 单个语料文件导入失败：`incremental_update` 捕获异常仅记 `logger.error` 并跳过该文件，不中断整体增量更新。
- 发现库/精校库不存在：`_load_from_db` 对不存在的 db 直接 `return`，初始化仍可完成。
- LLM 人名识别异常：`fetch_names_with_llm` 捕获异常返回 `{}`；`search_names` 查询失败同样自兜底返回 `{}`，人名缺失不阻塞翻译。
- 发现库持久化失败：`save_terms` 捕获异常只记录错误，内存数据仍保留。
- 反向（中→英）模式：`category` 属于 `Idioms/Colloquialisms`、`Slang` 的词条被黑名单跳过，避免习语倒置误导；反向把 target 按逗号拆分为多个可检索键。
- 人名库脏数据：威妥玛/音节音节的短词（`len(source)<=3`）与多义译名（target 逗号分隔 >5 项且非 `known_names`）被丢弃。