# -*- coding: utf-8 -*-
import os
import json
from dataclasses import dataclass, field
from typing import List

# --- 基础路径 ---
# 获取 config.py 所在的目录 (subtitle/core)
CURRENT_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
# BASE_DIR 应该是 subtitle 目录
BASE_DIR = os.path.dirname(CURRENT_FILE_DIR)
# ROOT_DIR 应该是项目根目录
ROOT_DIR = os.path.dirname(BASE_DIR)
CACHE_DIR = os.path.join(ROOT_DIR, ".cache")

# 预设文件路径
PRESETS_FILE = os.path.join(BASE_DIR, "presets.json")
PRESETS_EXAMPLE = os.path.join(BASE_DIR, "presets.json.example")

# --- 语料库路径 (供 glossary_manager 直接使用) ---
GLOSSARY_DIR = os.path.join(BASE_DIR, 'glossaries')
GLOSSARY_DB_PATH = os.path.join(BASE_DIR, 'glossary_cache.db')
NAMES_DB_PATH = os.path.join(GLOSSARY_DIR, 'names_translation.db')
LLM_DISCOVERY_DB_PATH = os.path.join(BASE_DIR, 'llm_discovery.db')
LLM_DISCOVERY_CN_DB_PATH = os.path.join(BASE_DIR, 'llm_discovery_cn.db')

# @lat: [[core-common#Key Concepts#配置体系（config.py）]]
def load_presets():
    """从 presets.json 加载配置预设"""
    if not os.path.exists(PRESETS_FILE) and os.path.exists(PRESETS_EXAMPLE):
        import shutil
        try:
            shutil.copy(PRESETS_EXAMPLE, PRESETS_FILE)
            print(f"已根据模板创建预设文件: {PRESETS_FILE}")
        except Exception as e:
            print(f"创建预设文件失败: {e}")

    if os.path.exists(PRESETS_FILE):
        try:
            with open(PRESETS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"加载预设失败: {e}")
    return {}

# @lat: [[core-common#Key Concepts#配置体系（config.py）]]
def save_presets(presets):
    """将预设保存到文件"""
    try:
        with open(PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump(presets, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"保存预设失败: {e}")

# @lat: [[core-common#Key Concepts#配置体系（config.py）]]
@dataclass
class TranslationConfig:
    # --- API 配置 ---
    api_key: str = ""
    api_url: str = "http://localhost:19183/v1/chat/completions"
    model_name: str = "openai/gpt-oss-20b"
    
    # 自动解析的多 Key 列表
    api_keys: List[str] = field(init=False, default_factory=list)
    
    # --- NER 专用 API 配置 (智能回退逻辑) ---
    ner_api_key: str = ""
    ner_api_url: str = ""
    ner_model_name: str = ""
    
    # --- 并发控制 ---
    max_concurrent_requests: int = 4
    rpm_limit: int = 60
    tpm_limit: int = 100000
    batch_size: int = 8
    
    # --- 容错配置 ---
    max_retries: int = 3
    retry_delay: float = 2.0
    max_tokens: int = 8192

    # --- 上下文预算 (1M 上下文模型) ---
    # 输入上下文预算（远低于 1M 留余量），用于估算单批可塞多少行/记忆。
    # 当前为软约束占位，pipeline 据此决定 recent_state 行数与 batch 上限。
    context_budget_tokens: int = 200000
    # 跨 batch 记忆锚点行数（原硬编码 2 行，1M 上下文下拉到 25-30）
    max_previous_lines: int = 25

    # --- 推理力度 (支持 reasoning_effort 的模型，如 SenseNova) ---
    # 可选: low / medium / high / none。空字符串表示不传该字段（模型默认行为）。
    # 输出慢的推理模型设为 "none" 可跳过 reasoning 阶段，大幅降低延迟。
    reasoning_effort: str = ""
    
    # --- 语料库配置 ---
    glossary_dir: str = GLOSSARY_DIR
    glossary_db_path: str = GLOSSARY_DB_PATH
    llm_discovery_db_path: str = LLM_DISCOVERY_DB_PATH
    enable_llm_discovery: bool = True
    enable_names_db: bool = False
    
    # [新增] 目标语言，默认中文 'zh'，可选英文 'en' 
    target_lang: str = "zh" 
    
    # --- LLM 温度配置 ---
    pass_temperature: bool = True
    temp_terms: float = 0.1
    temp_literal: float = 0.3
    temp_polish: float = 0.5

    # --- Claude Code CLI / Codex TUI 模仿模式 ---
    claude_cli_mode: bool = False
    codex_mode: bool = False

    def __post_init__(self):
        # 尝试从 presets.json 加载
        presets = load_presets()
        active_name = presets.get("_current")
        
        # 优先级：指定当前预设 > 第一个预设 > 默认硬编码值
        data = {}
        if active_name and active_name in presets:
            data = presets[active_name]
        elif presets:
            # 排除下划线开头的元数据键
            valid_presets = {k: v for k, v in presets.items() if not k.startswith("_")}
            if valid_presets:
                data = next(iter(valid_presets.values()))

        if data:
            self.api_key = data.get("api_key", self.api_key)
            self.api_url = data.get("api_url", self.api_url)
            self.model_name = data.get("model_name", self.model_name)

            self.max_concurrent_requests = int(data.get("max_concurrent", data.get("max_concurrent_requests", self.max_concurrent_requests)))
            self.rpm_limit = int(data.get("rpm_limit", self.rpm_limit))
            self.tpm_limit = int(data.get("tpm_limit", self.tpm_limit))
            self.batch_size = int(data.get("batch_size", self.batch_size))

            self.max_retries = int(data.get("max_retries", self.max_retries))
            self.retry_delay = float(data.get("retry_delay", self.retry_delay))
            self.max_tokens = int(data.get("max_tokens", self.max_tokens))

            self.context_budget_tokens = int(data.get("context_budget_tokens", self.context_budget_tokens))
            self.max_previous_lines = int(data.get("max_previous_lines", self.max_previous_lines))
            self.reasoning_effort = data.get("reasoning_effort", self.reasoning_effort)

            self.enable_llm_discovery = str(data.get("enable_discovery", data.get("enable_llm_discovery", self.enable_llm_discovery))).lower() == "true"
            self.enable_names_db = str(data.get("enable_names_db", self.enable_names_db)).lower() == "true"

            self.pass_temperature = str(data.get("pass_temperature", self.pass_temperature)).lower() == "true"
            self.temp_terms = float(data.get("temp_terms", self.temp_terms))
            self.temp_literal = float(data.get("temp_literal", self.temp_literal))
            self.temp_polish = float(data.get("temp_polish", self.temp_polish))
            self.target_lang = data.get("target_lang", self.target_lang)
            self.claude_cli_mode = str(data.get("claude_cli_mode", self.claude_cli_mode)).lower() == "true"
            self.codex_mode = str(data.get("codex_mode", self.codex_mode)).lower() == "true"

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

# @lat: [[core-common#Key Concepts#配置体系（config.py）]]
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

# @lat: [[core-common#Key Concepts#配置体系（config.py）]]
def save_config_to_presets(config_dict: dict, preset_name: str = "Default"):
    """将配置字典保存到 presets.json 中，只更新提供的字段，保留未在 GUI 中展示的字段"""
    presets = load_presets()
    
    # 映射表
    mapping = {
        "LLM_API_KEY": "api_key",
        "LLM_API_URL": "api_url",
        "LLM_MODEL_NAME": "model_name",
        "MAX_CONCURRENT_REQUESTS": "max_concurrent",
        "RPM_LIMIT": "rpm_limit",
        "BATCH_SIZE": "batch_size",
        "MAX_RETRIES": "max_retries",
        "RETRY_DELAY": "retry_delay",
        "MAX_TOKENS": "max_tokens",
        "PASS_TEMPERATURE": "pass_temperature",
        "TEMP_TERMS": "temp_terms",
        "TEMP_LITERAL": "temp_literal",
        "TEMP_POLISH": "temp_polish",
        "ENABLE_LLM_DISCOVERY": "enable_discovery",
        "ENABLE_NAMES_DB": "enable_names_db",
        "REASONING_EFFORT": "reasoning_effort",
        "ENFORCE_CONSISTENCY": "enforce_consistency",
        "POST_CHECK_PASSES": "post_check_passes",
        "CONTEXT_BUDGET_TOKENS": "context_budget_tokens",
        "MAX_PREVIOUS_LINES": "max_previous_lines"
    }
    
    new_preset_data = {}
    for k, v in config_dict.items():
        json_key = mapping.get(k, k.lower())
        new_preset_data[json_key] = v
        
    if preset_name not in presets:
        presets[preset_name] = {}
        
    presets[preset_name].update(new_preset_data)
    presets["_current"] = preset_name
    save_presets(presets)

# @lat: [[core-common#Key Concepts#配置体系（config.py）]]
class TranslationArgs:
    def __init__(self, input_file, output_file, bilingual, model_name=None, batch_size=None, target_lang="zh", enable_names_db=None, enable_annotations=False, enforce_consistency=True):
        self.input_file = input_file
        self.output_file = output_file
        self.bilingual = bilingual
        self.target_lang = target_lang
        
        # 加载基础配置 (从 presets.json 读取)
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
        self.context_budget_tokens = config.context_budget_tokens
        self.max_previous_lines = config.max_previous_lines
        self.reasoning_effort = config.reasoning_effort
        
        self.pass_temperature = config.pass_temperature
        self.temp_terms = config.temp_terms
        self.temp_literal = config.temp_literal
        self.temp_polish = config.temp_polish
        self.enable_llm_discovery = config.enable_llm_discovery
        self.enable_names_db = enable_names_db if enable_names_db is not None else config.enable_names_db
        self.enable_annotations = enable_annotations
        self.enforce_consistency = enforce_consistency
        self.claude_cli_mode = config.claude_cli_mode
        self.codex_mode = config.codex_mode
        self.progress_file = None
        self.glossary_cache_file = None
