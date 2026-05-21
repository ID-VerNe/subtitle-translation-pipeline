# -*- coding: utf-8 -*-

import json
import re
import time
import asyncio
import aiohttp
import logging
import hashlib
from typing import List, Dict, Optional, Union
from json_repair import repair_json
from .request_handler import AsyncRateLimitedSession, LoadBalancedSession, SmartLoadBalancer

# 设置模块日志
logger = logging.getLogger(__name__)

# 全局会话池：存储单个 Key 的实例
_session_pool: Dict[str, AsyncRateLimitedSession] = {}
# 全局负载均衡器缓存
_balancer_pool: Dict[str, Union[LoadBalancedSession, SmartLoadBalancer]] = {}


def get_session(config, use_smart_balancer: bool = True) -> Union[AsyncRateLimitedSession, LoadBalancedSession, SmartLoadBalancer]:
    """获取或创建限速会话，支持多 Key 负载均衡与自动并发优化
    
    Args:
        config: 配置对象
        use_smart_balancer: 是否使用智能负载均衡器（默认True）
    """
    global _session_pool, _balancer_pool
    
    # 1. 强制解析所有 Keys (保底逻辑)
    raw_api_key = getattr(config, 'api_key', "")
    if not raw_api_key:
        api_keys = []
    else:
        # 支持英文逗号、中文逗号、空格、换行符分隔
        import re
        api_keys = [k.strip() for k in re.split(r'[,\uff0c\s\n]+', raw_api_key) if k.strip()]
    
    if not api_keys:
        logger.error("No API Key found in config!")
        return None

    # 2. 创建唯一标识
    balancer_key = hashlib.md5(f"{','.join(api_keys)}{config.api_url}{use_smart_balancer}".encode()).hexdigest()
    
    if balancer_key in _balancer_pool:
        return _balancer_pool[balancer_key]

    # 3. 初始化子会话
    sessions = []
    is_glm_flash = "glm-4.6v-flash" in config.model_name.lower()
    
    if len(api_keys) > 1:
        logger.info(f"🚀 Detected Multi-Key Pool: {len(api_keys)} keys found.")
    
    for key in api_keys:
        session_id = hashlib.md5(f"{key}{config.api_url}".encode()).hexdigest()
        
        if session_id not in _session_pool:
            rpm = config.rpm_limit
            tpm = config.tpm_limit
            
            # --- 核心：自动并发逻辑 ---
            if is_glm_flash:
                # 针对 GLM-4.6V-Flash，每个 Key 强制 1 并发
                # 这样总并发就等于 Key 的数量，不需要用户手动去改并发设置
                concurrency = 1
                tpm = min(tpm, 150000)
                logger.info(f"  - Key {key[:8]}...: GLM-4.6V-Flash optimized (Concurrency=1, RPM={rpm})")
            else:
                # 其他模型，按用户设置平分并发，或保持用户设置
                # 这里我们采取"用户设置即单 Key 并发"的策略，这样多 Key 就能自动倍增
                concurrency = config.max_concurrent_requests
            
            _session_pool[session_id] = AsyncRateLimitedSession(
                api_key=key,
                rpm=rpm,
                tpm=tpm,
                concurrency=concurrency
            )
        sessions.append(_session_pool[session_id])

    # 4. 封装返回
    if len(sessions) == 1:
        _balancer_pool[balancer_key] = sessions[0]
        return sessions[0]
    
    # 使用智能负载均衡器（如果启用且有多于1个API）
    if use_smart_balancer and len(sessions) > 1:
        max_retries = getattr(config, 'max_retries', 3)
        balancer = SmartLoadBalancer(sessions, max_retries=max_retries)
        logger.info(f"🧠 Using SmartLoadBalancer with {len(sessions)} APIs, max_retries={max_retries}")
    else:
        balancer = LoadBalancedSession(sessions)
        logger.info(f"⚖️ Using LoadBalancedSession with {len(sessions)} APIs")
    
    _balancer_pool[balancer_key] = balancer
    return balancer


def clean_and_extract_json(text: Optional[str]) -> Union[Dict, List]:
    """
    更鲁棒的 JSON 提取器：优先寻找 Markdown 代码块，然后结合 json_repair 进行容错处理。
    """
    if text is None:
        return []
    
    text = text.strip()
    if not text:
        return []

    # 1. 优先尝试提取 Markdown 代码块 (这是最准确的)
    code_block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
    match = re.search(code_block_pattern, text)
    if match:
        json_str = match.group(1).strip()
        try:
            return json.loads(json_str)
        except:
            # 如果代码块里的也不合法，尝试用 repair_json 修复
            try:
                repaired = repair_json(json_str)
                data = json.loads(repaired)
                if data is not None:
                    return data
            except:
                pass

    # 2. 如果没有代码块，或者代码块解析失败，尝试直接解析全文
    try:
        data = json.loads(text)
        if data is not None:
            return data
    except:
        pass

    # 3. 寻找第一个 [ 或 { 开始的位置，截取到最后并尝试修复
    start_idx = -1
    for i, char in enumerate(text):
        if char in ['{', '[']:
            start_idx = i
            break
    
    if start_idx != -1:
        # 尝试寻找对应的结束符
        potential_json = text[start_idx:]
        try:
            # 优先尝试标准解析
            data = json.loads(potential_json)
            return data
        except:
            # 失败后再尝试修复
            try:
                repaired = repair_json(potential_json)
                data = json.loads(repaired)
                if data is not None:
                    return data
            except:
                pass

    # 4. 终极保底：对原始文本直接 repair
    try:
        repaired = repair_json(text)
        data = json.loads(repaired)
        return data if data is not None else []
    except:
        return []


async def _do_llm_request(session, config, payload: Dict, timeout: int = 120) -> Optional[str]:
    """执行单个LLM请求"""
    # 打印 Payload 详情（仅调试）
    if "deepseek" in config.model_name.lower():
        logger.debug(f"📤 [Payload]: {json.dumps(payload, ensure_ascii=False)}")

    response = await session.post(config.api_url, json=payload, timeout=timeout)
    
    if response.status == 429:
        # 触发速率限制，抛出异常让上层处理重试
        raise Exception(f"Rate limited (429)")
    
    raw_resp = await response.text()
    if response.status != 200:
        # 增加对 400/403 错误的详细调试信息
        error_info = f"API Error {response.status}: {raw_resp}"
        
        # 针对 DeepSeek 的 400 错误打印完整响应 body
        if "deepseek" in config.model_name.lower():
            logger.error(f"❌ [Full Error Response]: {raw_resp}")

        if response.status == 400:
            # 对于参数错误，打印简略的 payload 帮助排查（隐去 messages 内容防止日志过大）
            debug_payload = payload.copy()
            if len(debug_payload.get("messages", [])) > 0:
                debug_payload["messages"] = f"<{len(payload.get('messages', []))} messages>"
            error_info += f" | Payload: {json.dumps(debug_payload, ensure_ascii=False)}"
        
        logger.error(error_info)
        raise Exception(f"API Error {response.status}")
    
    try:
        data = json.loads(raw_resp)
    except Exception:
        raise Exception(f"Invalid JSON response: {raw_resp[:500]}")

    if 'choices' not in data or not data['choices']:
        raise Exception("Invalid API Response: missing choices")
        
    message = data['choices'][0].get('message', {})
    
    # 记录推理过程（如果有）
    reasoning = message.get('reasoning_content')
    if reasoning:
        logger.info(f"🧠 [DeepSeek Reasoning]:\n{reasoning}")
    
    if "tool_calls" in message and message["tool_calls"]:
        result = message["tool_calls"][0]["function"].get("arguments", "")
        logger.debug(f"🛠️ [Tool Call Result]: {result[:200]}...")
        return result

    content = message.get('content')
    if content:
        safe_content = content[:200].replace('\n', ' ')
        logger.info(f"📥 [LLM Response]: {safe_content}...")
    
    refusal = message.get('refusal')

    if refusal:
        logger.warning(f"模型拒绝回答 (Refusal): {refusal}")
        return ""

    if content is None or content.strip() == "":
        finish_reason = data['choices'][0].get('finish_reason')
        if finish_reason == "content_filter":
            logger.warning("API 因内容安全过滤 (content_filter) 返回空内容")
        return ""
        
    return content.strip()


def _prepare_payload(config, messages: List[Dict], temperature: float, tools: Optional[List[Dict]] = None, response_format: Optional[Dict] = None) -> Dict:
    """统一构建 API 请求 Payload，处理特定模型的差异化逻辑"""
    is_deepseek_flash = "deepseek-v4-flash" in config.model_name.lower()
    
    # 深度拷贝 messages，避免副作用
    current_messages = [m.copy() for m in messages]
    
    # 针对 DeepSeek-V4-Flash (SenseNova) 的官方极简模式
    if is_deepseek_flash:
        # ⚠️ 调试结论：该模型在商汤后端目前极不稳定。
        # 这里的 minimal_payload 尽量贴近官方 curl，但加上必要的控速参数。
        minimal_payload = {
            "model": config.model_name,
            "messages": current_messages,
            "temperature": 0.1,  # 降低随机性
            "max_tokens": 4096,  # 设定一个安全的上限，防止默认 65k 导致超时
            "stream": False
        }
        return minimal_payload

    payload = {
        "model": config.model_name,
        "messages": current_messages,
        "temperature": temperature,
        "max_tokens": config.max_tokens,
        "stream": False
    }

    if response_format:
        payload["response_format"] = response_format
    elif tools:
        payload["tools"] = tools
        tool_name = tools[0]["function"]["name"]
        payload["tool_choice"] = {"type": "function", "function": {"name": tool_name}}
        
    return payload


async def call_llm(config, messages: List[Dict], temperature: float = 0.5, tools: Optional[List[Dict]] = None, response_format: Optional[Dict] = None) -> Optional[str]:
    """异步调用 LLM API，支持智能负载均衡和失败重试"""
    
    payload = _prepare_payload(config, messages, temperature, tools, response_format)

    # 获取会话（使用智能负载均衡器）
    session = get_session(config, use_smart_balancer=True)
    
    # 如果是 SmartLoadBalancer，使用队列模式
    if isinstance(session, SmartLoadBalancer):
        try:
            # 定义任务函数
            async def task_func(sess, *args, **kwargs):
                return await _do_llm_request(sess, config, payload)
            
            # 提交任务并等待结果
            result = await session.execute(task_func)
            return result
            
        except Exception as e:
            logger.error(f"API 请求最终失败: {e}")
            return None
    
    # 否则使用传统模式（单会话或旧版负载均衡）
    for attempt in range(config.max_retries):
        try:
            result = await _do_llm_request(session, config, payload)
            return result
            
        except Exception as e:
            if attempt < config.max_retries - 1:
                # 指数退避
                wait_time = config.retry_delay * (2 ** attempt)
                logger.warning(f"Request failed (attempt {attempt + 1}/{config.max_retries}), retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"API 请求最终失败: {e}")
    
    return None


async def call_llm_batch(config, batch_messages: List[List[Dict]], temperature: float = 0.5, 
                        tools: Optional[List[Dict]] = None, response_format: Optional[Dict] = None,
                        progress_callback: Optional[callable] = None) -> List[Optional[str]]:
    """批量调用 LLM API，充分利用智能负载均衡器的并发能力
    
    Args:
        config: 配置对象
        batch_messages: 多组消息列表
        temperature: 温度参数
        tools: 工具定义
        response_format: 响应格式
        progress_callback: 进度回调函数，接收 (completed, total) 参数
    
    Returns:
        结果列表，与 batch_messages 顺序一致
    """
    if not batch_messages:
        return []
    
    session = get_session(config, use_smart_balancer=True)
    total = len(batch_messages)
    
    # 如果不是 SmartLoadBalancer，回退到传统 gather 模式
    if not isinstance(session, SmartLoadBalancer):
        tasks = [
            call_llm(config, messages, temperature, tools, response_format)
            for messages in batch_messages
        ]
        return await asyncio.gather(*tasks)
    
    # 使用 SmartLoadBalancer 的队列模式
    results = {}
    task_ids = []
    
    # 提交所有任务
    for idx, messages in enumerate(batch_messages):
        payload = _prepare_payload(config, messages, temperature, tools, response_format)
        
        # 定义任务函数，捕获 idx 以便返回正确顺序
        async def task_func(sess, payload=payload, idx=idx):
            result = await _do_llm_request(sess, config, payload)
            return idx, result
        
        task_id = await session.submit(task_func)
        task_ids.append((idx, task_id))
    
    # 等待所有任务完成
    completed = 0
    for idx, task_id in task_ids:
        try:
            _, result = await session.wait_for_task(task_id)
            results[idx] = result
            completed += 1
            if progress_callback:
                progress_callback(completed, total)
        except Exception as e:
            logger.error(f"Task {task_id} (index {idx}) failed: {e}")
            results[idx] = None
            completed += 1
            if progress_callback:
                progress_callback(completed, total)
    
    # 按原始顺序返回结果
    return [results.get(i) for i in range(total)]


def get_load_balancer_stats(config) -> Optional[Dict]:
    """获取负载均衡器统计信息"""
    balancer_key = hashlib.md5(f"{getattr(config, 'api_key', '')}{config.api_url}True".encode()).hexdigest()
    
    if balancer_key in _balancer_pool:
        balancer = _balancer_pool[balancer_key]
        if isinstance(balancer, SmartLoadBalancer):
            return balancer.get_stats()
    
    return None


def reset_session_pool():
    """重置会话池（用于测试或重新配置）"""
    global _session_pool, _balancer_pool
    _session_pool.clear()
    _balancer_pool.clear()
    logger.info("Session pool reset")
