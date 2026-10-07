# 网络与请求层（Network Layer）

封装 LLM HTTP 调用、稳健 JSON 解析、RPM/TPM 限速与多 Key 智能负载均衡，向上层提供可替换的会话抽象，并复用 requests.Session + asyncio 完成异步请求与自动重试。

## Key Concepts

本节介绍网络与请求层的核心能力：LLM 调用封装、非规范 JSON 修复、会话工厂、内容拒绝哨兵、智能负载均衡与限速并控。

### LLM 调用封装（call\_llm）

`call_llm` 是除 batch 外的唯一入口：先用 `_prepare_payload` 构造 Payload，再经 `get_session` 执行 `_do_llm_request`，并按 429/400/SSE/refusal/tool\_calls 等情形分类处理错误；非负载均衡模式用指数退避重试 `config.max_retries` 次。`call_llm_batch` 利用 SmartLoadBalancer 队列并发批量提交并保持结果顺序。Reference: \[\[subtitle/network/llm\_client.py#call\_llm]] 与 \[\[subtitle/network/llm\_client.py#call\_llm\_batch]]

### 非规范 JSON 修复（clean\_and\_extract\_json）

LLM 常输出带解释或损坏的 JSON，本函数采取逐级兜底：优先匹配 Markdown 代码块 ` ```json ` 提取；失败则对整个文本 `json.loads`；再从前向后找首个 `{`/`[` 截取子串尝试解析；每一级失败后都调用 `json_repair` 的 `repair_json` 做容错修复，最终仍失败返回空列表。Reference: \[\[subtitle/network/llm\_client.py#clean\_and\_extract\_json]]

### 会话工厂（get\_session）

`get_session` 解析 api\_key（中英文逗号/空格/换行分隔）得到 Key 列表，按 `(keys, api_url, use_smart_balancer)` 生成 MD5 缓存键复用实例；单 Key 返回 `AsyncRateLimitedSession`，多 Key 在 `use_smart_balancer` 时返回 `SmartLoadBalancer`，否则回退 `LoadBalancedSession`。

并对 GLM-4.6V-Flash 把每 Key 并发强制为 1 并限 TPM。Reference: \[\[subtitle/network/llm\_client.py#get\_session]]

### 内容拒绝哨兵（REFUSAL\_SENTINEL 与 ContentRefusalError）

当模型返回 refusal 字段或 finish\_reason 为 content\_filter 时，`_do_llm_request` 抛出 `ContentRefusalError`；`call_llm`/`call_llm_batch` 在 `raise_on_refusal=False`（默认）时转为返回空串、为 True 时返回哨兵对象 `REFUSAL_SENTINEL`，以区分"模型拒绝"与普通失败，避免 SmartLoadBalancer 把拒绝当故障重试。Reference: \[\[subtitle/network/llm\_client.py#ContentRefusalError]]

### 智能负载均衡（SmartLoadBalancer）

基于任务队列（TaskQueue/Task/TaskStatus）+ 每 Key 健康监控（APIHealth）实现：工作协程从队列取任务，`_select_best_api` 依"成功率 × 可用并发槽位 /（平均响应时间 + 1）"，未用过的 Key 给高分、跳过连续失败超过阈值的不可用 Key；失败自动重入队换 Key 重启，超过 max\_retries 标记永久失败。`get_stats` 暴露队列与各 API 指标。Reference: \[\[subtitle/network/request\_handler.py#SmartLoadBalancer]]

### 限速与并控（RateLimiter / AsyncRateLimitedSession）

`RateLimiter` 用 `collections.deque` 维护 60 秒滑动窗口，`wait_async` 校验 RPM 固定间隔与 TPM 剩余额度；`AsyncRateLimitedSession` 用 `asyncio.Semaphore` 控并发，内部用 `requests.Session`（经线程池执行），响应经包装成 aiohttp 兼容接口，429 时冷却 10 秒并记录 token 消耗。Reference: \[\[subtitle/network/request\_handler.py#RateLimiter]] 与 \[\[subtitle/network/request\_handler.py#AsyncRateLimitedSession]]

## Dependencies

内部模块依赖 config 读取 Key/模型/RPM/TPM/并发等参数：\[\[core-common]]。外部第三方库：`requests`（HTTP 会话，线程池执行）、`aiohttp`（链路其他层可能使用）、`json_repair`（修复非规范 JSON）；标准库：`asyncio`、`json`、`re`、`time`、`hashlib`、`uuid`、`collections`、`threading`、`logging`、`dataclasses`、`enum`。

## Consumed By

以下模块调用本模块的 LLM 客户端、JSON 修复与限速负载均衡能力。

- \[\[core-stages]] — 直译/润色调用 call\_llm

- \[\[core-rescue]] — 失败兜底调用

- \[\[core-glossary]] — NER 人名提取调用

- \[\[core-quality]] — 终审/注解调用

- \[\[core-memory]] — 画像/场景构建调用

- \[\[pipeline]]、\[\[entries]] — 全链路

## Error Conditions

本节列出网络请求层可能出现的错误与对应的兜底行为。

- 429 限流：`_do_llm_request` 对 429 抛 `Rate limited (429)`，`AsyncRateLimitedSession` 检测到 429 时冷却 10 秒。

- 非 200 状态：抛 `API Error {status}`，400/DeepSeek 场景打印脱敏 payload 便于排查。

- 内容拒绝（拒绝回答或 content\_filter）：抛 `ContentRefusalError`，上层据 `raise_on_refusal` 返回哨兵或空串。

- JSON/SSE 解析失败或缺少 choices：抛 `Invalid JSON response` / `Invalid API Response: missing choices`。

- 超时重试：指数退避（`retry_delay * 2^attempt`），达到 max\_retries 后 `call_llm` 返回 None。

- 网关/连接异常：SmartLoadBalancer 遇异常记健康失败并重入队换 Key，超重试后抛错写入 `_results`。

