# -*- coding: utf-8 -*-
import logging
from tkinter import messagebox, simpledialog
from core.config import save_config_to_presets, load_presets, save_presets

logger = logging.getLogger(__name__)

# @lat: [[gui#Key Concepts#预设管理（PresetManager）]]
class PresetManager:
    def __init__(self, view_model, ui_update_callback):
        self.vm = view_model
        self.ui_update_callback = ui_update_callback
        self.all_presets = load_presets()
        self.display_presets = [k for k in self.all_presets.keys() if not k.startswith("_")]
        
    def initialize_preset(self):
        if self.ui_update_callback:
            self.ui_update_callback(self.display_presets)
            
        last_active = self.all_presets.get("_current")
        if last_active and last_active in self.all_presets:
            self.vm.preset_var.set(last_active)
            self.apply_preset()
        elif self.display_presets:
            self.vm.preset_var.set(self.display_presets[0])
            self.apply_preset()

    def apply_preset(self, event=None):
        name = self.vm.preset_var.get()
        if name in self.all_presets:
            p = self.all_presets[name]
            self.all_presets["_current"] = name
            save_presets(self.all_presets)
            
            try:
                if "api_url" in p: self.vm.api_url_var.set(str(p["api_url"]))
                if "api_key" in p: self.vm.api_key_var.set(str(p["api_key"]))
                if "model_name" in p: self.vm.model_var.set(str(p["model_name"]))
                if "batch_size" in p: self.vm.batch_size_var.set(str(p["batch_size"]))
                if "max_concurrent" in p: self.vm.concurrent_var.set(str(p["max_concurrent"]))
                if "rpm_limit" in p: self.vm.rpm_var.set(str(p["rpm_limit"]))
                if "max_retries" in p: self.vm.retries_var.set(str(p["max_retries"]))
                if "retry_delay" in p: self.vm.retry_delay_var.set(str(p["retry_delay"]))
                if "max_tokens" in p: self.vm.max_tokens_var.set(str(p["max_tokens"]))
                if "enable_discovery" in p: self.vm.enable_discovery_var.set(self.vm.safe_get_bool(p["enable_discovery"]))
                if "enable_names_db" in p: self.vm.enable_names_db_var.set(self.vm.safe_get_bool(p["enable_names_db"]))
                if "enable_annotations" in p: self.vm.enable_annotations_var.set(self.vm.safe_get_bool(p["enable_annotations"]))
                if "target_lang" in p: self.vm.target_lang_var.set(str(p["target_lang"]))
                if "target_format" in p: self.vm.format_var.set(str(p["target_format"]))
                if "pass_temperature" in p: self.vm.pass_temperature_var.set(self.vm.safe_get_bool(p["pass_temperature"], default=True))
                if "temp_terms" in p: self.vm.temp_terms_var.set(float(p["temp_terms"]))
                if "temp_literal" in p: self.vm.temp_literal_var.set(float(p["temp_literal"]))
                if "temp_polish" in p: self.vm.temp_polish_var.set(float(p["temp_polish"]))
                
                # Advanced
                if "reasoning_effort" in p: self.vm.reasoning_effort_var.set(str(p["reasoning_effort"]))
                if "enforce_consistency" in p: self.vm.enforce_consistency_var.set(self.vm.safe_get_bool(p["enforce_consistency"], default=True))
                if "post_check_passes" in p: self.vm.post_check_passes_var.set(str(p["post_check_passes"]))
                if "context_budget_tokens" in p: self.vm.context_budget_var.set(str(p["context_budget_tokens"]))
                if "max_previous_lines" in p: self.vm.max_previous_lines_var.set(str(p["max_previous_lines"]))
                
                logger.info(f"已加载环境预设: {name}")
            except Exception as e:
                logger.error(f"应用预设失败: {e}")

    def add_custom_preset(self):
        name = simpledialog.askstring("新预设", "请输入新预设名称:")
        if not name: return
        
        # 继承当前预设中的未展示字段（如 reasoning_effort, context_budget_tokens）
        current_preset_name = self.vm.preset_var.get()
        new_preset = dict(self.all_presets.get(current_preset_name, {}))
        
        # 覆盖 GUI 中可设置的字段
        new_preset.update({
            "api_url": self.vm.api_url_var.get(),
            "api_key": self.vm.api_key_var.get(),
            "model_name": self.vm.model_var.get(),
            "batch_size": self.vm.safe_get_int(self.vm.batch_size_var),
            "max_concurrent": self.vm.safe_get_int(self.vm.concurrent_var),
            "rpm_limit": self.vm.safe_get_int(self.vm.rpm_var),
            "max_retries": self.vm.safe_get_int(self.vm.retries_var),
            "retry_delay": self.vm.safe_get_float(self.vm.retry_delay_var),
            "max_tokens": self.vm.safe_get_int(self.vm.max_tokens_var),
            "enable_discovery": self.vm.enable_discovery_var.get(),
            "enable_names_db": self.vm.enable_names_db_var.get(),
            "enable_annotations": self.vm.enable_annotations_var.get(),
            "target_lang": self.vm.target_lang_var.get(),
            "target_format": self.vm.format_var.get(),
            "pass_temperature": self.vm.pass_temperature_var.get(),
            "temp_terms": self.vm.safe_get_float(self.vm.temp_terms_var),
            "temp_literal": self.vm.safe_get_float(self.vm.temp_literal_var),
            "temp_polish": self.vm.safe_get_float(self.vm.temp_polish_var),
            
            "reasoning_effort": self.vm.reasoning_effort_var.get(),
            "enforce_consistency": str(self.vm.enforce_consistency_var.get()),
            "post_check_passes": str(self.vm.safe_get_int(self.vm.post_check_passes_var)),
            "context_budget_tokens": str(self.vm.safe_get_int(self.vm.context_budget_var)),
            "max_previous_lines": str(self.vm.safe_get_int(self.vm.max_previous_lines_var)),
        })
        
        self.all_presets[name] = new_preset
        self.all_presets["_current"] = name
        save_presets(self.all_presets)
        self.display_presets = [k for k in self.all_presets.keys() if not k.startswith("_")]
        
        self.vm.preset_var.set(name)
        if self.ui_update_callback:
            self.ui_update_callback(self.display_presets)
            
        messagebox.showinfo("成功", f"环境预设 '{name}' 已保存并设为当前！")

    def save_to_current_preset(self):
        try:
            current_preset_name = self.vm.preset_var.get() or "Default"
            config_data = {
                "LLM_API_KEY": self.vm.api_key_var.get(),
                "LLM_API_URL": self.vm.api_url_var.get(),
                "LLM_MODEL_NAME": self.vm.model_var.get(),
                "MAX_CONCURRENT_REQUESTS": str(self.vm.safe_get_int(self.vm.concurrent_var)),
                "RPM_LIMIT": str(self.vm.safe_get_int(self.vm.rpm_var)),
                "BATCH_SIZE": str(self.vm.safe_get_int(self.vm.batch_size_var)),
                "MAX_RETRIES": str(self.vm.safe_get_int(self.vm.retries_var)),
                "RETRY_DELAY": str(self.vm.safe_get_float(self.vm.retry_delay_var)),
                "MAX_TOKENS": str(self.vm.safe_get_int(self.vm.max_tokens_var)),
                "PASS_TEMPERATURE": str(self.vm.pass_temperature_var.get()),
                "TEMP_TERMS": str(self.vm.safe_get_float(self.vm.temp_terms_var)),
                "TEMP_LITERAL": str(self.vm.safe_get_float(self.vm.temp_literal_var)),
                "TEMP_POLISH": str(self.vm.safe_get_float(self.vm.temp_polish_var)),
                "ENABLE_LLM_DISCOVERY": str(self.vm.enable_discovery_var.get()),
                "ENABLE_NAMES_DB": str(self.vm.enable_names_db_var.get()),
                "ENABLE_ANNOTATIONS": str(self.vm.enable_annotations_var.get()),
                "REASONING_EFFORT": self.vm.reasoning_effort_var.get(),
                "ENFORCE_CONSISTENCY": str(self.vm.enforce_consistency_var.get()),
                "POST_CHECK_PASSES": str(self.vm.safe_get_int(self.vm.post_check_passes_var)),
                "CONTEXT_BUDGET_TOKENS": str(self.vm.safe_get_int(self.vm.context_budget_var)),
                "MAX_PREVIOUS_LINES": str(self.vm.safe_get_int(self.vm.max_previous_lines_var))
            }
            save_config_to_presets(config_data, current_preset_name)
            self.all_presets = load_presets()
            messagebox.showinfo("成功", f"配置已保存到预设 '{current_preset_name}'")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
