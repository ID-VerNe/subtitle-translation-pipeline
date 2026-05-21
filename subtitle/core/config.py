# -*- coding: utf-8 -*-
import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

# 加载 .env 文件（如果存在）
load_dotenv()

# --- 基础路径 ---
# 获取 config.py 所在的目录 (subtitle/core)
CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
# BASE_DIR 应该是 subtitle 目录
BASE_DIR = os.path.dirname(CURRENT_FILE_DIR)
# ROOT_DIR 应该是项目根目录
ROOT_DIR = os.path.dirname(BASE_DIR)
CACHE_DIR = os.path.join(ROOT_DIR, ".cache")

# --- 语料库路径 (供 glossary_manager 直接使用) ---
GLOSSARY_DIR = os.path.join(BASE_DIR, 'glossaries')
GLOSSARY_DB_PATH = os.path.join(BASE_DIR, 'glossary_cache.db')
NAMES_DB_PATH = os.path.join(GLOSSARY_DIR, 'names_translation.db')
LLM_DISCOVERY_DB_PATH = os.path.join(BASE_DIR, 'llm_discovery.db')
LLM_DISCOVERY_CN_DB_PATH = os.path.join(BASE_DIR, 'llm_discovery_cn.db')

@dataclass
class TranslationConfig:
    # --- API 配置 ---
    api_key: str = os.getenv("LLM_API_KEY", "")
    api_url: str = os.getenv("LLM_API_URL", "http://localhost:19183/v1/chat/completions")
    model_name: str = os.getenv("LLM_MODEL_NAME", "openai/gpt-oss-20b")
    
    # 自动解析的多 Key 列表
    api_keys: List[str] = field(init=False, default_factory=list)
    
    # --- NER 专用 API 配置 (智能回退逻辑) ---
    ner_api_key: str = os.getenv("NER_API_KEY", "")
    ner_api_url: str = os.getenv("NER_API_URL", "")
    ner_model_name: str = os.getenv("NER_MODEL_NAME", "")
    
    # --- 并发控制 ---
    max_concurrent_requests: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "4"))
    rpm_limit: int = int(os.getenv("RPM_LIMIT", "60"))
    tpm_limit: int = int(os.getenv("TPM_LIMIT", "100000"))
    batch_size: int = int(os.getenv("BATCH_SIZE", "8")),
    
    # --- 容错配置 ---
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    retry_delay: float = float(os.getenv("RETRY_DELAY", "2.0"))
    max_tokens: int = int(os.getenv("MAX_TOKENS", "4096")),
    
    # --- 语料库配置 ---
    glossary_dir: str = GLOSSARY_DIR
    glossary_db_path: str = GLOSSARY_DB_PATH
    llm_discovery_db_path: str = LLM_DISCOVERY_DB_PATH
    enable_llm_discovery: bool = os.getenv("ENABLE_LLM_DISCOVERY", "True").lower() == "true"
    enable_names_db: bool = os.getenv("ENABLE_NAMES_DB", "False").lower() == "true"
    
    # [新增] 目标语言，默认中文 'zh'，可选英文 'en' 
    target_lang: str = "zh" 
    
    # --- LLM 温度配置 ---
    temp_terms: float = float(os.getenv("TEMP_TERMS", "0.1"))
    temp_literal: float = float(os.getenv("TEMP_LITERAL", "0.3"))
    temp_polish: float = float(os.getenv("TEMP_POLISH", "0.5"))

    def __post_init__(self):
        # 处理多 API Key 情况 (逗号分隔)
        self.api_keys = [k.strip() for k in self.api_key.split(",") if k.strip()]
        
        # 如果没有配置 NER 专用 Key，则全部回退到主模型配置
        if not self.ner_api_key:
            self.ner_api_key = self.api_key
            self.ner_api_url = self.api_url
            self.ner_model_name = self.model_name
        else:
            # 如果配置了 Key 但没配置 URL/Model，则补全
            if not self.ner_api_url: self.ner_api_url = self.api_url
            if not self.ner_model_name: self.ner_model_name = "glm-4-flash"

        # 确保目录存在
        os.makedirs(self.glossary_dir, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)

def clear_cache():
    """清理统一的缓存目录以及可能残留的旧缓存目录"""
    import shutil
    # 1. 清理统一的根目录缓存
    if os.path.exists(CACHE_DIR):
        shutil.rmtree(CACHE_DIR)
        os.makedirs(CACHE_DIR, exist_ok=True)
    
    # 2. 清理可能残留在 subtitle 目录下的旧缓存
    old_cache = os.path.join(BASE_DIR, ".cache")
    if os.path.exists(old_cache) and os.path.abspath(old_cache) != os.path.abspath(CACHE_DIR):
        shutil.rmtree(old_cache)
    
    return True

def save_config_to_env(config_dict: dict):
    """将配置字典保存到 .env 文件中"""
    env_path = os.path.join(os.path.dirname(BASE_DIR), ".env")
    
    # 读取现有的 .env 内容
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    
    # 更新或添加配置项
    new_lines = []
    processed_keys = set()
    
    for line in lines:
        stripped = line.strip()
        if stripped and "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=")[0].strip()
            if key in config_dict:
                new_lines.append(f"{key}={config_dict[key]}\n")
                processed_keys.add(key)
                continue
        new_lines.append(line)
        
    # 添加原本不存在的项
    for key, value in config_dict.items():
        if key not in processed_keys:
            new_lines.append(f"{key}={value}\n")
            
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

class TranslationArgs:
    def __init__(self, input_file, output_file, bilingual, model_name=None, batch_size=None, target_lang="zh"):
        self.input_file = input_file
        self.output_file = output_file
        self.bilingual = bilingual
        self.target_lang = target_lang
        
        # 加载基础配置 (从 .env 读取)
        config = TranslationConfig()
        
        self.api_key = config.api_key
        self.api_url = config.api_url
        self.model_name = model_name if model_name else config.model_name
        self.batch_size = batch_size if batch_size else config.batch_size
        
        self.max_concurrent = config.max_concurrent_requests
        self.rpm_limit = config.rpm_limit
        self.tpm_limit = config.tpm_limit
        self.max_retries = config.max_retries
        self.retry_delay = config.retry_delay
        self.max_tokens = config.max_tokens
        
        self.temp_terms = config.temp_terms
        self.temp_literal = config.temp_literal
        self.temp_polish = config.temp_polish
        self.enable_llm_discovery = config.enable_llm_discovery
        self.enable_names_db = config.enable_names_db
        self.progress_file = None
        self.glossary_cache_file = None
