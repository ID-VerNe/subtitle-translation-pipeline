# 📽️ Subtitle Translation Pipeline (字幕翻译流水线)

本模块是整个项目的核心翻译引擎，旨在通过 **“全局画像扫描”** 与 **“分治式两阶段翻译”** 架构，解决传统字幕翻译中上下文断裂、角色代词混乱、专有名词不统一等顽疾。

---

## 🏗️ 核心架构原理 (Architecture Principles)

整个 Pipeline 遵循以下五个关键步骤，实现了从“纯文本翻译”到“剧本感知式翻译”的跨越。

### 1. 全局画像扫描 (Global Discovery)
*   **痛点**：LLM 每次只能看到几十行字幕，不知道整部片的题材和人物背景。
*   **解法**：在正式翻译前，系统对全文进行 **15% 动态采样**（首、中、尾均衡采样），利用 LLM 生成一份包含：**影片类型 (Genre)、整体语调 (Tone)、详细人物画像 (Characters, 含性别/说话风格)、人物关系图谱 (Relationships)** 的全局报告。
*   **产出**：`global_profile.json`。

### 2. 场景映射与对齐 (Scene Mapping)
*   **痛点**：批次 (Batch) 切分往往是死板的，会切断对话。
*   **解法**：系统预先将全文切分为逻辑场景 (Scenes)，并利用 LLM 强化每个场景的 **参与者列表、场景摘要、特定语域 (Domain)**。
*   **结果**：翻译批次会尽可能与场景边界对齐，确保对话语境的连贯。
*   **产出**：`scene_map.json`。

### 3. 三级智能术语库 (Intelligent Glossary)
*   **核心库 (Core)**：存放全片最核心的专有名词，全程跟随。
*   **动态库 (Local)**：每批次翻译前，根据当前文本内容动态过滤出最相关的术语。
*   **人名库 (Name DB)**：集成 67 万条《世界人名翻译大辞典》数据。通过 **LLM NER (命名实体识别)** 提取文中人名，并在库中自动匹配，彻底解决 `Will` (动词 vs 人名) 等歧义。

### 4. 两阶段执行引擎 (Two-Stage Engine)
*   **阶段 A：直译 (Literal Stage)**：专注于 **ID 对应** 与 **语义还原**。通过 Tool Calling (Function Calling) 强制模型输出 JSON，并进行严格的格式校验。
*   **阶段 B：润色 (Polish Stage)**：基于直译结果，注入 **全局画像**、**翻译策略** 和 **场景引导**。
*   **性能优化**：引入 **异步预取 (Prefetch)**。当 Pipeline 在润色批次 `i` 时，后台已在并发进行批次 `i+1` 的直译。

### 5. 梯次拯救引擎 (Ladder Rescue Engine)
*   **痛点**：长文本翻译经常遇到 API 超时或内容安全拦截 (Content Filter)。
*   **解法**：遇到失败时，系统自动启动 **三级降级策略**：
    1.  **TIER 1 (Full)**：减小批次大小重试（如 8->4->2->1）。
    2.  **TIER 2 (Compact)**：剥离最近的动态记忆，保留场景引导重试。
    3.  **TIER 3 (Minimal)**：剥离场景引导，仅保留全局画像与核心术语重试。
*   **兜底**：若全部失败，自动退回到直译结果或原文，确保任务永不中断。

---

## 🚀 关键技术实现

### 🧠 智能负载均衡 (Smart Load Balancer)
*   支持 **多 API Key 自动调度**，实时监控每组 API 的成功率、响应时间和可用槽位。
*   针对特定模型（如 `GLM-4-Flash`）内置并发优化策略，自动压制并发以防止 429 报错。
*   使用 `json_repair` 与多层正则提取技术，确保在模型输出非规范 JSON 时仍能稳健解析。

### 📊 动态上下文压缩
*   为了防止 Context 膨胀导致 Token 浪费和理解力下降，Pipeline 会根据当前场景参与者，**动态压缩** 全局画像中的角色信息，仅回灌相关的角色背景。

---

## 📂 模块文件结构

```text
subtitle/core/
├── config.py               # 配置与预设管理 (presets.json)
├── llm_client.py           # API 客户端、负载均衡、JSON 容错
├── global_memory.py        # 全局画像、场景映射、翻译策略构建
├── translation_pipeline.py  # 两阶段翻译逻辑、梯次拯救引擎
├── glossary_manager.py     # 术语库、人名数据库管理
├── srt_utils.py            # 字幕解析与格式化
└── cache_utils.py          # 缓存与持久化工具
```

---

## 🛠️ 如何配置？

请参考根目录下的 [README.md](../README.md) 进行基础安装。所有的 Pipeline 高级参数（温度、并发、采样率等）均可通过 `subtitle/presets.json` 进行精细调节。
