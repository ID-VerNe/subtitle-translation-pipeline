# -*- coding: utf-8 -*-
import os
import json
import hashlib
from typing import Any

# --- 版本控制 ---
# 改变这些值会强制使相关类别的缓存失效
PROMPT_VERSION = "v2.2"  # 提示词版本
SCHEMA_VERSION = "20260521"  # 缓存数据结构版本

def canonical_json(obj: Any) -> str:
    """
    生成缓存友好的稳定 JSON 字符串。
    注意：
    - sort_keys=True 保证 dict 字段顺序稳定
    - separators 去掉多余空格，减少 token
    - ensure_ascii=False 保留中文
    """
    return json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":")
    )


def file_fingerprint(path: str) -> str:
    """
    基于文件内容生成 hash，而不是基于文件名。
    避免同名不同内容串缓存，也避免同内容改名后缓存失效。
    """
    if not os.path.exists(path):
        return "non_existent_file"
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def build_file_cache_key(
    input_file: str,
    target_lang: str,
    model_name: str = "",
    prompt_version: str = PROMPT_VERSION,
    schema_version: str = SCHEMA_VERSION
) -> str:
    """
    构建文件级缓存 Key。用于 Profile, Scene Map, Progress 等。
    包含了文件内容、语言、模型以及系统版本信息。
    """
    payload = {
        "fingerprint": file_fingerprint(input_file),
        "target_lang": target_lang,
        "model_name": model_name,
        "prompt_version": prompt_version,
        "schema_version": schema_version
    }
    return hashlib.md5(canonical_json(payload).encode("utf-8")).hexdigest()


def build_request_cache_key(model_name: str, payload: dict) -> str:
    """
    构建请求级缓存 Key。用于具体的 LLM 请求/响应缓存。
    """
    wrap = {
        "model": model_name,
        "payload": payload
    }
    return hashlib.md5(canonical_json(wrap).encode("utf-8")).hexdigest()


def load_json_file(path: str, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json_file(path: str, data: Any, pretty: bool = True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        else:
            f.write(canonical_json(data))
