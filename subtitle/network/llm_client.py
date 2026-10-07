# -*- coding: utf-8 -*-

import json
import re
import time
import asyncio
import logging
import hashlib
from typing import List, Dict, Optional, Union
from json_repair import repair_json
from core.config import normalize_api_url
from .request_handler import AsyncRateLimitedSession, LoadBalancedSession, SmartLoadBalancer


# @lat: [[network#Key Concepts#内容拒绝哨兵（REFUSAL_SENTINEL 与 ContentRefusalError）]]
class ContentRefusalError(Exception):
    """模型拒绝翻译内容（refusal / content_filter）时抛出"""


# 设置模块日志
logger = logging.getLogger(__name__)

# 全局会话池：存储单个 Key 的实例
_session_pool: Dict[str, AsyncRateLimitedSession] = {}
# 全局负载均衡器缓存
_balancer_pool: Dict[str, Union[LoadBalancedSession, SmartLoadBalancer]] = {}

# Sentinel 对象：用于区分"模型拒绝"和其他失败
REFUSAL_SENTINEL = object()


# @lat: [[network#Key Concepts#会话工厂（get_session）]]
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
                concurrency=concurrency,
                claude_cli_mode=config.claude_cli_mode if hasattr(config, 'claude_cli_mode') else False,
                codex_mode=config.codex_mode if hasattr(config, 'codex_mode') else False
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


# @lat: [[network#Key Concepts#非规范 JSON 修复（clean_and_extract_json）]]
def clean_and_extract_json(text: Optional[str]) -> Union[Dict, List]:
    """
    更鲁棒的 JSON 提取器：优先寻找 Markdown 代码块，然后结合 json_repair 进行容错处理。
    """
    if text is None:
        return []
    
    text = text.strip()
    if not text:
        return []

    def _sanitize_for_repair(s: str) -> str:
        s = re.sub(r'\\n', '\n', s)
        s = re.sub(r'\\r', '\r', s)
        s = re.sub(r'\\t', '\t', s)
        return s

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
                repaired = repair_json(_sanitize_for_repair(json_str))
                data = json.loads(repaired)
                if data is not None:
                    return data
            except:
                pass

    # 2. 如果没有代码块，或者代码块解析失败，尝试直接解析全文
    try:
        data = json.loads(text)
        if data is not None:
            # 兼容模型返回了序列化后的 JSON 字符串
            if isinstance(data, str):
                try:
                    inner = json.loads(data)
                    if inner is not None:
                        return inner
                except:
                    pass
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
                repaired = repair_json(_sanitize_for_repair(potential_json))
                data = json.loads(repaired)
                if data is not None:
                    return data
            except:
                pass

    # 4. 终极保底：对原始文本直接 repair
    try:
        repaired = repair_json(_sanitize_for_repair(text))
        data = json.loads(repaired)
        return data if data is not None else []
    except:
        return []


async def _do_llm_request(session, config, payload: dict, timeout: int = 1200) -> Optional[str]:
    """执行单一的LLM请求"""
    import json
    if "deepseek" in config.model_name.lower():
        # logger.debug(f"🔍 [Payload]: {json.dumps(payload, ensure_ascii=False)}")
        pass

    if any(k in config.model_name.lower() for k in ("sensenova",)):
        timeout = max(timeout, 1200)

    api_url = normalize_api_url(getattr(config, 'api_url', ''))
    response = await session.post(api_url, json=payload, timeout=timeout)
    
    if response.status == 429:
        raise Exception("Rate limited (429)")
    
    raw_resp = await response.text()
    if response.status != 200:
        error_info = f"API Error {response.status}: {raw_resp}"
        
        if "deepseek" in config.model_name.lower():
            # logger.error(f"🚨 [Full Error Response]: {raw_resp}")
            pass

        if response.status == 400:
            debug_payload = payload.copy()
            if len(debug_payload.get("messages", [])) > 0:
                debug_payload["messages"] = f"<{len(payload.get('messages', []))} messages>"
            error_info += f" | Payload: {json.dumps(debug_payload, ensure_ascii=False)}"
        
        logger.error(error_info)
        
        if response.status == 400 and ("data_inspection_failed" in raw_resp or "inappropriate content" in raw_resp.lower()):
            raise ContentRefusalError("安全审核拦截了该批次内容 (data_inspection_failed)")
            
        raise Exception(f"API Error {response.status}")
    
    try:
        data = json.loads(raw_resp)
    except Exception:
        if raw_resp.strip().startswith("data:"):
            logger.info("检测到 SSE 格式响应，尝试解析...")
            content_parts = []
            for line in raw_resp.strip().split("\n"):
                line = line.strip()
                if line.startswith("data:") and line != "data: [DONE]":
                    sse_json_str = line[5:].strip()
                    if sse_json_str:
                        try:
                            sse_data = json.loads(sse_json_str)
                            choices = sse_data.get("choices", [])
                            for choice in choices:
                                delta = choice.get("delta", {})
                                if delta.get("content"):
                                    content_parts.append(delta["content"])
                        except:
                            pass
            if content_parts:
                combined = "".join(content_parts)
                logger.info(f"🌟 [SSE Parsed Response]: {combined[:200]}...")
                return combined
        raise Exception(f"Invalid JSON response: {raw_resp[:500]}")

    content = None
    if 'choices' in data and len(data['choices']) > 0:
        message = data['choices'][0].get('message', {})
        content = message.get('content')
        if content:
            safe_content = content[:200].replace('\n', ' ')
            logger.info(f"🎯 [LLM Response]: {safe_content}...")
        
        refusal = message.get('refusal')
        if refusal:
            logger.warning(f"模型拒绝回答 (Refusal): {refusal}")
            raise ContentRefusalError(f"Model refused: {refusal[:200]}")

        if content is None or content.strip() == "":
            finish_reason = data['choices'][0].get('finish_reason')
            if finish_reason == "content_filter":
                logger.warning("API 触发安全策略 (content_filter) 拒绝返回")
                raise ContentRefusalError("Content filter triggered")
            return ""
            
        return content.strip()
    return None

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
            "max_tokens": 4096,  # 设定一个安全的上限，防止默认 65k 导致超时
            "stream": False
        }
        if getattr(config, 'pass_temperature', True):
            minimal_payload["temperature"] = 0.1  # 降低随机性
        return minimal_payload

    payload = {
        "model": config.model_name,
        "messages": current_messages,
        "max_tokens": config.max_tokens,
        "stream": False
    }
    
    if getattr(config, 'pass_temperature', True):
        payload["temperature"] = temperature

    # 推理力度控制：支持 reasoning_effort 的模型（如 SenseNova）可设
    # none/low/medium/high。设为 "none" 时跳过推理阶段，显著降低延迟。
    # 未配置（空串）则不传该字段，沿用模型默认。
    reasoning_effort = getattr(config, "reasoning_effort", "")
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort

    if response_format:
        payload["response_format"] = response_format
    elif tools:
        payload["tools"] = tools
        tool_name = tools[0]["function"]["name"]
        payload["tool_choice"] = {"type": "function", "function": {"name": tool_name}}
        
    return payload


async def call_llm(config, messages: List[Dict], temperature: float = 0.5, tools: Optional[List[Dict]] = None, response_format: Optional[Dict] = None, raise_on_refusal: bool = False) -> Optional[str]:
    """异步调用 LLM API，支持智能负载均衡和失败重试

    Args:
        raise_on_refusal: 为 True 时模型拒绝返回 REFUSAL_SENTINEL，否则返回空字符串（旧行为）
    """

    payload = _prepare_payload(config, messages, temperature, tools, response_format)

    # 获取会话（使用智能负载均衡器）
    session = get_session(config, use_smart_balancer=True)

    # 如果是 SmartLoadBalancer，使用队列模式
    if isinstance(session, SmartLoadBalancer):
        try:
            # 定义任务函数：内部捕获 ContentRefusalError 防止 SmartLoadBalancer 重试
            async def task_func(sess, *args, **kwargs):
                try:
                    return await _do_llm_request(sess, config, payload)
                except ContentRefusalError:
                    if raise_on_refusal:
                        return REFUSAL_SENTINEL
                    return ""

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

        except ContentRefusalError:
            if raise_on_refusal:
                return REFUSAL_SENTINEL
            return ""
        except Exception as e:
            if attempt < config.max_retries - 1:
                # 指数退避
                wait_time = config.retry_delay * (2 ** attempt)
                logger.warning(f"Request failed (attempt {attempt + 1}/{config.max_retries}), retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"API 请求最终失败: {e}")
    
    return None


# @lat: [[network#Key Concepts#LLM 调用封装（call_llm）]]
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


async def close_session_pool():
    """彻底关闭会话池中的所有会话"""
    global _session_pool, _balancer_pool
    
    # 首先关闭负载均衡器 (这会关闭关联的任务协程和子会话)
    for balancer in list(_balancer_pool.values()):
        if hasattr(balancer, "__aexit__"):
            await balancer.__aexit__(None, None, None)
    
    # 然后关闭任何未通过负载均衡器管理的独立会话
    for session in list(_session_pool.values()):
        if hasattr(session, "__aexit__"):
            await session.__aexit__(None, None, None)
            
    _balancer_pool.clear()
    _session_pool.clear()
    logger.info("Session pool closed and cleared")
