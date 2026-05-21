# -*- coding: utf-8 -*-
import os
import sys

# --- Embedded Python Tcl/Tk Fix ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
# 检查是否处于嵌入式环境 (python_embed 目录存在)
EMBED_TCL_DIR = os.path.join(PROJECT_ROOT, "python_embed", "Lib", "site-packages", "tcl")
if os.path.exists(EMBED_TCL_DIR):
    os.environ["TCL_LIBRARY"] = os.path.join(EMBED_TCL_DIR, "tcl8.6")
    os.environ["TK_LIBRARY"] = os.path.join(EMBED_TCL_DIR, "tk8.6")
# ----------------------------------

import json
import asyncio
import hashlib
import logging
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox, simpledialog
import importlib.util

# 获取基础路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from core.config import TranslationConfig, TranslationArgs, save_config_to_presets, load_presets, save_presets, CACHE_DIR, clear_cache
from translate_srt_llm import run_translation

# 动态加载工具子模块
def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

EXTRACT_TOOL_PATH = os.path.join(BASE_DIR, "pre-process", "01-extract_srt.py")
ASS_TOOL_PATH = os.path.join(BASE_DIR, "post-process", "02-post_process_ass.py")

extract_tool = load_module("extract_tool", EXTRACT_TOOL_PATH)
ass_tool = load_module("ass_tool", ASS_TOOL_PATH)

logger = logging.getLogger("GUI")

class GuiLogger(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.text_widget.tag_config("INFO", foreground="black")
        self.text_widget.tag_config("ERROR", foreground="red")
        self.text_widget.tag_config("WARNING", foreground="orange")

    def emit(self, record):
        msg = self.format(record)
        def append():
            try:
                self.text_widget.configure(state='normal')
                tag = record.levelname if record.levelname in ["INFO", "ERROR", "WARNING"] else "INFO"
                self.text_widget.insert(tk.END, msg + "\n", tag)
                self.text_widget.see(tk.END)
                self.text_widget.configure(state='disabled')
            except: pass
        self.text_widget.after(0, append)

class SubtitleTranslatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Subtitle Translator GUI")
        self.root.geometry("950x850") # 稍微调大一点适应更多参数
        
        # 检查预设文件是否存在，如果不存在则会触发 core.config 中的自动创建逻辑
        from core.config import PRESETS_FILE
        is_first_run = not os.path.exists(PRESETS_FILE)

        # 加载持久化预设
        self.all_presets = load_presets()
        self.display_presets = [k for k in self.all_presets.keys() if not k.startswith("_")]
        
        # --- 数据绑定 ---
        self.input_file = tk.StringVar()
        self.output_file = tk.StringVar()
        self.format_var = tk.StringVar(value="ass")
        self.bilingual_var = tk.BooleanVar(value=True)
        self.target_lang_var = tk.StringVar(value="zh")
        
        # 高级配置 (初始化为默认值)
        default_config = TranslationConfig()
        self.model_var = tk.StringVar(value=str(default_config.model_name))
        self.api_key_var = tk.StringVar(value=str(default_config.api_key))
        self.api_url_var = tk.StringVar(value=str(default_config.api_url))
        self.batch_size_var = tk.StringVar(value=str(default_config.batch_size))
        self.concurrent_var = tk.StringVar(value=str(default_config.max_concurrent_requests))
        self.rpm_var = tk.StringVar(value=str(default_config.rpm_limit))
        self.retries_var = tk.StringVar(value=str(default_config.max_retries))
        self.retry_delay_var = tk.StringVar(value=str(default_config.retry_delay))
        self.max_tokens_var = tk.StringVar(value=str(default_config.max_tokens))
        
        self.temp_terms_var = tk.DoubleVar(value=float(default_config.temp_terms))
        self.temp_literal_var = tk.DoubleVar(value=float(default_config.temp_literal))
        self.temp_polish_var = tk.DoubleVar(value=float(default_config.temp_polish))
        self.enable_discovery_var = tk.BooleanVar(value=bool(default_config.enable_llm_discovery))
        self.enable_names_db_var = tk.BooleanVar(value=bool(default_config.enable_names_db))

        # --- UI 初始化 ---
        self.setup_ui()
        
        # 优先选中上次使用的预设
        last_active = self.all_presets.get("_current")
        if last_active and last_active in self.all_presets:
            self.preset_var.set(last_active)
            self.apply_preset()
        elif self.display_presets:
            # 默认选中第一个
            self.preset_var.set(self.display_presets[0])
            self.apply_preset()

        # Redirect logging
        self.log_handler = GuiLogger(self.log_area)
        self.log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(self.log_handler)
        logger.addHandler(self.log_handler)

        if is_first_run:
            messagebox.showwarning("首次运行提示", "未找到 presets.json，已根据模板自动创建。\n请前往『高级配置』标签页设置你的 API Key。")

    def safe_get_int(self, var, default=0):
        try:
            val = var.get()
            # 递归解包 tuple/list (针对 Tkinter 某些怪异行为)
            while isinstance(val, (tuple, list)):
                if len(val) > 0: val = val[0]
                else: return default
            
            # 清理字符串中的非数字字符
            if isinstance(val, str):
                val = val.strip().strip('[](),"\'')
                if not val: return default
                
            return int(float(val))
        except Exception as e:
            logger.warning(f"参数解析失败: {val} -> {e}, 使用默认值 {default}")
            return default

    def safe_get_float(self, var, default=0.0):
        try:
            val = var.get()
            while isinstance(val, (tuple, list)):
                if len(val) > 0: val = val[0]
                else: return default
            
            if isinstance(val, str):
                val = val.strip().strip('[](),"\'')
                if not val: return default

            return float(val)
        except: return default

    def setup_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Tab 1: Translation
        self.trans_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.trans_tab, text=" 翻译主界面 ")
        self._setup_translation_tab()

        # Tab 2: Settings
        self.settings_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.settings_tab, text=" 高级配置 ")
        self._setup_settings_tab()

    def _setup_translation_tab(self):
        # Preset Selection
        preset_frame = ttk.Frame(self.trans_tab)
        preset_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(preset_frame, text="快速切换环境预设:").pack(side=tk.LEFT, padx=5)
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset_var, values=self.display_presets, state="readonly", width=35)
        self.preset_combo.pack(side=tk.LEFT, padx=5)
        self.preset_combo.bind("<<ComboboxSelected>>", self.apply_preset)

        # File Selection
        file_frame = ttk.LabelFrame(self.trans_tab, text="文件选择", padding="10")
        file_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(file_frame, text="输入文件 (MKV/SRT/ASS):").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(file_frame, textvariable=self.input_file, width=70).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(file_frame, text="浏览...", command=self.browse_input).grid(row=0, column=2, pady=2)

        ttk.Label(file_frame, text="输出文件 (可选):").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(file_frame, textvariable=self.output_file, width=70).grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(file_frame, text="浏览...", command=self.browse_output).grid(row=1, column=2, pady=2)

        opt_frame = ttk.LabelFrame(self.trans_tab, text="基础选项", padding="10")
        opt_frame.pack(fill=tk.X, pady=5)

        ttk.Checkbutton(opt_frame, text="双语字幕", variable=self.bilingual_var).grid(row=0, column=0, padx=5, sticky="w")
        
        ttk.Label(opt_frame, text="目标格式:").grid(row=0, column=1, padx=5, sticky="e")
        ttk.Combobox(opt_frame, textvariable=self.format_var, values=["ass", "srt"], state="readonly", width=10).grid(row=0, column=2, sticky="w")

        ttk.Label(opt_frame, text="目标语言:").grid(row=0, column=3, padx=5, sticky="e")
        ttk.Combobox(opt_frame, textvariable=self.target_lang_var, values=["zh", "en"], state="readonly", width=10).grid(row=0, column=4, sticky="w")

        prog_frame = ttk.Frame(self.trans_tab)
        prog_frame.pack(fill=tk.X, pady=10)
        
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(prog_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 10))
        
        self.progress_label = ttk.Label(prog_frame, text="0%")
        self.progress_label.pack(side=tk.RIGHT)

        self.start_btn = ttk.Button(self.trans_tab, text="🚀 开始翻译任务", command=self.start_thread)
        self.start_btn.pack(fill=tk.X, ipady=10, pady=5)

        log_frame = ttk.LabelFrame(self.trans_tab, text="运行日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_area = scrolledtext.ScrolledText(log_frame, state='disabled', height=15, font=("Consolas", 9))
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def _setup_settings_tab(self):
        # API Config
        api_frame = ttk.LabelFrame(self.settings_tab, text="API 配置", padding="10")
        api_frame.pack(fill=tk.X, pady=5)

        ttk.Label(api_frame, text="API URL:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(api_frame, textvariable=self.api_url_var, width=65).grid(row=0, column=1, padx=5, sticky="w")

        ttk.Label(api_frame, text="API Key:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(api_frame, textvariable=self.api_key_var, width=65, show="*").grid(row=1, column=1, padx=5, sticky="w")

        ttk.Label(api_frame, text="模型名称:").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(api_frame, textvariable=self.model_var, width=45).grid(row=2, column=1, padx=5, sticky="w")

        # Pipeline Config
        pipe_frame = ttk.LabelFrame(self.settings_tab, text="流水线参数", padding="10")
        pipe_frame.pack(fill=tk.X, pady=5)

        # 使用字符串变量绑定 Spinbox，避免 Tkinter 数值类型转换 Bug
        ttk.Label(pipe_frame, text="并发请求数:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Spinbox(pipe_frame, from_=1, to=100, textvariable=self.concurrent_var, width=12).grid(row=0, column=1, padx=5, sticky="w")

        ttk.Label(pipe_frame, text="每分钟请求(RPM):").grid(row=0, column=2, sticky="e", padx=10)
        ttk.Spinbox(pipe_frame, from_=1, to=10000, textvariable=self.rpm_var, width=12).grid(row=0, column=3, sticky="w")

        ttk.Label(pipe_frame, text="批次大小(Batch):").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Spinbox(pipe_frame, from_=1, to=50, textvariable=self.batch_size_var, width=12).grid(row=1, column=1, padx=5, sticky="w")

        ttk.Label(pipe_frame, text="Max Tokens:").grid(row=1, column=2, sticky="e", padx=10)
        ttk.Spinbox(pipe_frame, from_=256, to=128000, textvariable=self.max_tokens_var, width=12, increment=256).grid(row=1, column=3, sticky="w")

        ttk.Label(pipe_frame, text="失败重试次数:").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Spinbox(pipe_frame, from_=0, to=10, textvariable=self.retries_var, width=12).grid(row=2, column=1, padx=5, sticky="w")

        ttk.Label(pipe_frame, text="重试延迟(秒):").grid(row=2, column=2, sticky="e", padx=10)
        ttk.Spinbox(pipe_frame, from_=0.1, to=60.0, textvariable=self.retry_delay_var, width=12, increment=0.5).grid(row=2, column=3, sticky="w")

        ttk.Checkbutton(pipe_frame, text="启用 LLM 发现术语库", variable=self.enable_discovery_var).grid(row=3, column=0, sticky="w", pady=5)
        ttk.Checkbutton(pipe_frame, text="启用人名数据库 (默认禁用)", variable=self.enable_names_db_var).grid(row=3, column=1, sticky="w", pady=5)

        # Temperature Config
        temp_frame = ttk.LabelFrame(self.settings_tab, text="模型温度 (Temperature)", padding="10")
        temp_frame.pack(fill=tk.X, pady=5)

        def create_temp_slider(parent, label, var, row):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
            # 使用 Scale 时绑定 Label 显示数值
            s = ttk.Scale(parent, from_=0.0, to=1.0, variable=var, orient=tk.HORIZONTAL)
            s.grid(row=row, column=1, padx=5, sticky="ew")
            l = ttk.Label(parent, width=5)
            l.grid(row=row, column=2, padx=5)
            # 实时更新显示数值
            def update_label(*args):
                try: l.config(text=f"{float(var.get()):.1f}")
                except: pass
            var.trace_add("write", update_label)
            update_label() # 初始显示

        create_temp_slider(temp_frame, "术语提取 (Terms):", self.temp_terms_var, 0)
        create_temp_slider(temp_frame, "直译阶段 (Literal):", self.temp_literal_var, 1)
        create_temp_slider(temp_frame, "润色阶段 (Polish):", self.temp_polish_var, 2)
        
        temp_frame.columnconfigure(1, weight=1)

        # Actions
        btn_frame = ttk.Frame(self.settings_tab)
        btn_frame.pack(fill=tk.X, pady=10)

        ttk.Button(btn_frame, text="💾 保存当前设置", command=self.save_to_current_preset).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, ipady=8)
        ttk.Button(btn_frame, text="➕ 另存为新预设", command=self.add_custom_preset).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, ipady=8)
        ttk.Button(btn_frame, text="🗑️ 清理翻译缓存", command=self.do_clear_cache).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, ipady=8)

    def do_clear_cache(self):
        if messagebox.askyesno("确认", "确定要清理所有翻译缓存吗？这将删除所有未完成任务的进度记录。"):
            if clear_cache():
                messagebox.showinfo("成功", "缓存已清理完毕。")
                logger.info("已清理所有翻译缓存")

    def apply_preset(self, event=None):
        name = self.preset_var.get()
        if name in self.all_presets:
            p = self.all_presets[name]
            # 更新当前使用的预设标识
            self.all_presets["_current"] = name
            save_presets(self.all_presets)
            
            # 批量设置，全部转为字符串或对应类型，防止 Tkinter 报错
            try:
                if "api_url" in p: self.api_url_var.set(str(p["api_url"]))
                if "api_key" in p: self.api_key_var.set(str(p["api_key"]))
                if "model_name" in p: self.model_var.set(str(p["model_name"]))
                if "batch_size" in p: self.batch_size_var.set(str(p["batch_size"]))
                if "max_concurrent" in p: self.concurrent_var.set(str(p["max_concurrent"]))
                if "rpm_limit" in p: self.rpm_var.set(str(p["rpm_limit"]))
                if "max_retries" in p: self.retries_var.set(str(p["max_retries"]))
                if "retry_delay" in p: self.retry_delay_var.set(str(p["retry_delay"]))
                if "max_tokens" in p: self.max_tokens_var.set(str(p["max_tokens"]))
                if "enable_discovery" in p: self.enable_discovery_var.set(bool(p["enable_discovery"]))
                if "enable_names_db" in p: self.enable_names_db_var.set(bool(p["enable_names_db"]))
                if "target_lang" in p: self.target_lang_var.set(str(p["target_lang"]))
                if "target_format" in p: self.format_var.set(str(p["target_format"]))
                if "temp_terms" in p: self.temp_terms_var.set(float(p["temp_terms"]))
                if "temp_literal" in p: self.temp_literal_var.set(float(p["temp_literal"]))
                if "temp_polish" in p: self.temp_polish_var.set(float(p["temp_polish"]))
                logger.info(f"已加载环境预设: {name}")
            except Exception as e:
                logger.error(f"应用预设失败: {e}")

    def add_custom_preset(self):
        name = simpledialog.askstring("保存预设", "请输入当前环境预设的名称:")
        if not name: return
        
        new_preset = {
            "api_url": self.api_url_var.get(),
            "api_key": self.api_key_var.get(),
            "model_name": self.model_var.get(),
            "batch_size": self.safe_get_int(self.batch_size_var),
            "max_concurrent": self.safe_get_int(self.concurrent_var),
            "rpm_limit": self.safe_get_int(self.rpm_var),
            "max_retries": self.safe_get_int(self.retries_var),
            "retry_delay": self.safe_get_float(self.retry_delay_var),
            "max_tokens": self.safe_get_int(self.max_tokens_var),
            "enable_discovery": self.enable_discovery_var.get(),
            "enable_names_db": self.enable_names_db_var.get(),
            "target_lang": self.target_lang_var.get(),

            "target_format": self.format_var.get(),
            "temp_terms": self.safe_get_float(self.temp_terms_var),
            "temp_literal": self.safe_get_float(self.temp_literal_var),
            "temp_polish": self.safe_get_float(self.temp_polish_var),
        }
        
        self.all_presets[name] = new_preset
        self.all_presets["_current"] = name
        save_presets(self.all_presets)
        self.display_presets = [k for k in self.all_presets.keys() if not k.startswith("_")]
        self.preset_combo['values'] = self.display_presets
        self.preset_var.set(name)
        messagebox.showinfo("成功", f"环境预设 '{name}' 已保存并设为当前！")

    def save_to_current_preset(self):
        try:
            current_preset_name = self.preset_var.get() or "Default"
            config_data = {
                "LLM_API_KEY": self.api_key_var.get(),
                "LLM_API_URL": self.api_url_var.get(),
                "LLM_MODEL_NAME": self.model_var.get(),
                "MAX_CONCURRENT_REQUESTS": str(self.safe_get_int(self.concurrent_var)),
                "RPM_LIMIT": str(self.safe_get_int(self.rpm_var)),
                "BATCH_SIZE": str(self.safe_get_int(self.batch_size_var)),
                "MAX_RETRIES": str(self.safe_get_int(self.retries_var)),
                "RETRY_DELAY": str(self.safe_get_float(self.retry_delay_var)),
                "MAX_TOKENS": str(self.safe_get_int(self.max_tokens_var)),
                "TEMP_TERMS": str(self.safe_get_float(self.temp_terms_var)),
                "TEMP_LITERAL": str(self.safe_get_float(self.temp_literal_var)),
                "TEMP_POLISH": str(self.safe_get_float(self.temp_polish_var)),
                "ENABLE_LLM_DISCOVERY": str(self.enable_discovery_var.get()),
                "ENABLE_NAMES_DB": str(self.enable_names_db_var.get())
            }
            save_config_to_presets(config_data, current_preset_name)
            # 重新加载内存中的预设
            self.all_presets = load_presets()
            messagebox.showinfo("成功", f"配置已保存到预设 '{current_preset_name}'")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")

    def update_progress(self, current, total):
        def _update():
            percent = (current / total) * 100 if total > 0 else 0
            self.progress_var.set(percent)
            self.progress_label.config(text=f"{int(percent)}%")
        self.root.after(0, _update)

    def browse_input(self):
        filetypes = [("Media Files", "*.mkv *.srt *.ass"), ("All Files", "*.*")]
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            self.input_file.set(path)
            if not self.output_file.get():
                base, _ = os.path.splitext(path)
                self.output_file.set(f"{base}.{self.format_var.get()}")

    def browse_output(self):
        path = filedialog.asksaveasfilename(defaultextension=f".{self.format_var.get()}")
        if path:
            self.output_file.set(path)

    def start_thread(self):
        if not self.input_file.get():
            logger.error("请先选择输入文件！")
            return
        self.start_btn.config(state="disabled")
        thread = threading.Thread(target=self.run_process)
        thread.daemon = True
        thread.start()

    def run_process(self):
        try:
            input_path = self.input_file.get()
            output_path = self.output_file.get()
            final_fmt = self.format_var.get()
            self.update_progress(0, 100)

            if output_path and not output_path.lower().endswith(f".{final_fmt}"):
                output_path += f".{final_fmt}"

            working_srt = None
            if input_path.lower().endswith(".mkv"):
                logger.info("正在从 MKV 提取字幕...")
                srt_files = extract_tool.extract_subtitles(input_path)
                if srt_files: working_srt = srt_files[0]
                else:
                    logger.error("MKV 字幕提取失败。")
                    return
            elif input_path.lower().endswith(".srt"):
                working_srt = input_path
            elif input_path.lower().endswith(".ass"):
                logger.info("正在将 ASS 转换为 SRT...")
                working_srt = extract_tool.convert_ass_file_to_srt(input_path)
            
            if not working_srt:
                logger.error("无效的输入文件或预处理失败。")
                return

            cache_dir = CACHE_DIR
            input_filename = os.path.basename(working_srt)
            file_hash = hashlib.md5(input_filename.encode('utf-8')).hexdigest()
            
            if final_fmt == "ass":
                translated_srt = os.path.join(cache_dir, f"translated_{file_hash}.srt")
            else:
                translated_srt = output_path if output_path else os.path.splitext(input_path)[0] + ".srt"

            # --- 强制参数清洗与验证 ---
            # 1. Batch Size
            raw_bs = self.safe_get_int(self.batch_size_var, 8)
            if raw_bs <= 0: raw_bs = 8
            
            # 2. Max Tokens
            raw_tokens = self.safe_get_int(self.max_tokens_var, 4096)
            if raw_tokens <= 0: raw_tokens = 4096
            
            # 3. Concurrent
            raw_concurrent = self.safe_get_int(self.concurrent_var, 4)
            if raw_concurrent <= 0: raw_concurrent = 4

            logger.info(f"任务参数: Batch={raw_bs}, Tokens={raw_tokens}, Concurrent={raw_concurrent}")

            trans_args = TranslationArgs(
                input_file=working_srt,
                output_file=translated_srt,
                bilingual=self.bilingual_var.get(),
                model_name=self.model_var.get(),
                batch_size=raw_bs,
                target_lang=self.target_lang_var.get()
            )
            # 显式赋值其他参数，确保类型正确
            trans_args.api_key = self.api_key_var.get()
            trans_args.api_url = self.api_url_var.get()
            trans_args.max_concurrent = raw_concurrent
            trans_args.rpm_limit = self.safe_get_int(self.rpm_var, 60)
            trans_args.max_retries = self.safe_get_int(self.retries_var, 3)
            trans_args.retry_delay = self.safe_get_float(self.retry_delay_var, 2.0)
            trans_args.max_tokens = raw_tokens
            trans_args.temp_terms = self.safe_get_float(self.temp_terms_var, 0.1)
            trans_args.temp_literal = self.safe_get_float(self.temp_literal_var, 0.3)
            trans_args.temp_polish = self.safe_get_float(self.temp_polish_var, 0.5)
            trans_args.enable_llm_discovery = self.enable_discovery_var.get()
            trans_args.enable_names_db = self.enable_names_db_var.get()

            asyncio.run(run_translation(trans_args, progress_callback=self.update_progress))

            if final_fmt == "ass":
                logger.info(f"正在生成 ASS: {output_path}")
                head_path = os.path.join(BASE_DIR, "post-process", "asshead.txt")
                if not os.path.exists(head_path): head_path = "asshead.txt"
                ass_tool.srt_to_ass(translated_srt, head_path, output_path)
            
            logger.info("🎉 所有任务已完成！")
            self.update_progress(100, 100)

        except Exception as e:
            logger.error(f"任务失败: {e}", exc_info=True)
        finally:
            self.root.after(0, lambda: self.start_btn.config(state="normal"))

def run_gui():
    root = tk.Tk()
    app = SubtitleTranslatorApp(root)
    root.mainloop()

if __name__ == "__main__":
    run_gui()
