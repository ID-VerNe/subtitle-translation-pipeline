# 上下文与策略增强（Context & Strategy）

为每一批翻译动态构建上下文锚点、过滤相关术语、匹配 Few-Shot 示例并决定温度，平衡全片记忆连续性与单批 Token 成本，两阶段执行时读取同一套增强信号。

## Key Concepts

本节介绍本模块动态构建翻译上下文与策略的增强机制：上下文状态构建、核心术语构建、动态术语过滤、Few-Shot 示例引导与动态温度策略。

### 上下文状态构建（build_recent_state）
解释：把上一批已产出的最近状态（默认最后 100 行、可传 max_lines 调整）压缩为三个回灌字段——`last_ids` 抽取已完成的行号锚点、`pairs` 保留"原文 + 润色"成对样本、`usage` 说明其用途。锚点随批次前移形成滚动窗口，供直译解决代词消解、句子延续，供润色保持术语一致性。空输入安全返回空 dict。Reference: [[subtitle/core/context_builder.py#build_recent_state]]
### 核心术语构建（build_core_terms）
解释：按 `category_priority` 内建优先级表（Proper Name 0、Named Entities 1、Technical Term 2、Automotive 3、Cultural 4、Slang 5、Name 6、General 7）对全库术语排序，未命中的类别落到默认优先级 8，同优先级按源词小写字典序；`sort_key` 对非 dict 节点做兜底。返回优先级升序的有序 dict，保证最关键术语稳定排前、全程注入。Reference: [[subtitle/core/context_builder.py#build_core_terms]]
### 动态术语过滤（filter_relevant_glossary）
解释：先对当前批文本做大小写忽略的子串匹配（`src.lower() in text_lower`），从全库过滤出确实出现在本批文本中的术语；再调用 `glossary_manager.search_names` 从人名库补充 Proper Name 类条目并去重。只把命中的术语子集塞入上下文，避免不相关词条占据 Token 并减少干扰。Reference: [[subtitle/core/context_builder.py#filter_relevant_glossary]]
### Few-Shot 示例引导（FewShotExampleManager）
解释：内置按场景分类的高质量示例库（humor_sarcasm、technical_farming、dialogue_casual、emotion_strong），每条含原文/直译/润色/备注。`get_examples_for_scene` 用 tone_mapping 把场景语气标签映射到示例类别并收集，无匹配回退到通用对话示例，截断到 max_examples 后格式化为 Markdown 注入润色阶段；`add_custom_example` 支持追加用户优化示例。Reference: [[subtitle/core/fewshot_manager.py#FewShotExampleManager]]
### 动态温度策略（DynamicTemperatureStrategy）
解释：以直译与润色各自的基准温度（0.3 / 0.5）为起点，分别累加场景语气修正（技术降、幽默/情感升）与内容特征修正（含数字/专有名词降、含俚语/文化梗/短句升），结果夹取到 [0.0, 1.0] 并保留两位。`analyze_content_features` 用正则与俚语标记自动打标，`get_recommendation` 汇总两阶段温度并生成原因字符串。Reference: [[subtitle/core/temperature_strategy.py#DynamicTemperatureStrategy]]

## Dependencies
内部模块：[[core-common]]（`build_glossary_payload` 依赖其 `canonical_json` 做稳定序列化，底层走 config 配置），[[core-glossary]]（`glossary_manager` 提供术语源与 `search_names` 人名补充，flashtext 关键词匹配在其内部封装）。外部依赖：标准库 `typing`；序列化经 `canonical_json`（json.dumps，sort_keys 去空格、保留中文）完成，温度特征分析使用标准库 `re`。

## Consumed By

以下模块使用本模块构建的上下文、术语过滤、Few-Shot 示例与温度策略。

- [[pipeline]] — orchestrator 批量构建上下文注入批次
- [[core-stages]] — 直译/润色读取最近状态、术语、示例与温度
- [[core-rescue]] — 降级重试时透传上下文与策略

## Error Conditions
各函数均为纯基础数据结构操作，几乎不抛业务异常并自带空安全：`build_recent_state` 对空 `final_blocks` 返回空 dict；`build_core_terms` 对非 dict 节点按默认优先级兜底；`filter_relevant_glossary` 对空文本自然返回空结果。未引入显式 try/except——异常面仅可能来自底层 `glossary_manager.search_names` 的数据库读取，已由其自身处理。