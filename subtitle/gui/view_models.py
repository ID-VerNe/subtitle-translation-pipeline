# -*- coding: utf-8 -*-
import os
import logging
import tkinter as tk
from core.config import TranslationConfig

logger = logging.getLogger(__name__)

# @lat: [[gui#Key Concepts#视图模型（AppViewModel）]]
class AppViewModel:
    def __init__(self):
        # File paths
        self.input_file = tk.StringVar()
        self.output_file = tk.StringVar()
        self.format_var = tk.StringVar(value="ass")
        self.bilingual_var = tk.BooleanVar(value=True)
        self.target_lang_var = tk.StringVar(value="zh")
        
        # Preset and UI states
        self.preset_var = tk.StringVar()
        self.progress_var = tk.DoubleVar(value=0)
        
        default_config = TranslationConfig()
        
        # Advanced settings
        self.model_var = tk.StringVar(value=str(default_config.model_name))
        self.api_key_var = tk.StringVar(value=str(default_config.api_key))
        self.api_url_var = tk.StringVar(value=str(default_config.api_url))
        self.batch_size_var = tk.StringVar(value=str(default_config.batch_size))
        self.concurrent_var = tk.StringVar(value=str(default_config.max_concurrent_requests))
        self.rpm_var = tk.StringVar(value=str(default_config.rpm_limit))
        self.retries_var = tk.StringVar(value=str(default_config.max_retries))
        self.retry_delay_var = tk.StringVar(value=str(default_config.retry_delay))
        self.max_tokens_var = tk.StringVar(value=str(default_config.max_tokens))
        
        self.pass_temperature_var = tk.BooleanVar(value=bool(default_config.pass_temperature))
        self.temp_terms_var = tk.DoubleVar(value=float(default_config.temp_terms))
        self.temp_literal_var = tk.DoubleVar(value=float(default_config.temp_literal))
        self.temp_polish_var = tk.DoubleVar(value=float(default_config.temp_polish))
        
        self.enable_discovery_var = tk.BooleanVar(value=bool(default_config.enable_llm_discovery))
        env_names_db = os.environ.get("ENABLE_NAMES_DB", "").lower() == "true"
        self.enable_names_db_var = tk.BooleanVar(value=bool(default_config.enable_names_db or env_names_db))
        self.enable_annotations_var = tk.BooleanVar(value=False)
        
        # Extended Advanced settings
        self.reasoning_effort_var = tk.StringVar(value=str(default_config.reasoning_effort))
        self.enforce_consistency_var = tk.BooleanVar(value=True)
        self.post_check_passes_var = tk.StringVar(value="5")
        self.context_budget_var = tk.StringVar(value=str(default_config.context_budget_tokens))
        self.max_previous_lines_var = tk.StringVar(value=str(default_config.max_previous_lines))

    @staticmethod
    def safe_get_int(var, default=0):
        try:
            val = var.get()
            while isinstance(val, (tuple, list)):
                if len(val) > 0: val = val[0]
                else: return default
            if isinstance(val, str):
                val = val.strip().strip('[](),"\'')
                if not val: return default
            return int(float(val))
        except Exception as e:
            logger.warning(f"参数解析失败: {val} -> {e}, 使用默认值 {default}")
            return default

    @staticmethod
    def safe_get_float(var, default=0.0):
        try:
            val = var.get()
            while isinstance(val, (tuple, list)):
                if len(val) > 0: val = val[0]
                else: return default
            if isinstance(val, str):
                val = val.strip().strip('[](),"\'')
                if not val: return default
            return float(val)
        except:
            return default

    @staticmethod
    def safe_get_bool(val, default=False):
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ('true', '1', 'yes')
        return bool(val) if val is not None else default
