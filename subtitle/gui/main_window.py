# -*- coding: utf-8 -*-
import os
import logging
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox

from gui.view_models import AppViewModel
from gui.preset_manager import PresetManager
from gui.task_controller import TaskController

logger = logging.getLogger("GUI")

# @lat: [[gui#Key Concepts#日志桥接（GuiLogger）]]
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


# @lat: [[gui#Key Concepts#主窗口视图（SubtitleTranslatorApp）]]
class SubtitleTranslatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Subtitle Translator GUI")
        self.root.geometry("950x850")
        
        self.vm = AppViewModel()
        
        self.vm.format_var.trace_add("write", self._on_format_changed)
        
        self.preset_combo = None
        self.start_btn = None
        self.progress_label = None
        
        self.setup_ui()
        
        self.preset_manager = PresetManager(self.vm, self._update_preset_combo)
        self.task_controller = TaskController(self.vm, self.root, self.start_btn, self.progress_label)
        
        self.preset_manager.initialize_preset()

        self.log_handler = GuiLogger(self.log_area)
        self.log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger().addHandler(self.log_handler)
        logger.addHandler(self.log_handler)

        from core.config import PRESETS_FILE
        is_first_run = not os.path.exists(PRESETS_FILE)
        if is_first_run:
            messagebox.showwarning("首次运行提示", "未找到 presets.json，已根据模板自动创建。\n请前往『高级配置』标签页设置你的 API Key。")

    def _update_preset_combo(self, display_presets):
        if self.preset_combo:
            self.preset_combo['values'] = display_presets

    def setup_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.trans_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.trans_tab, text=" 翻译主界面 ")
        self._setup_translation_tab()

        self.settings_tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.settings_tab, text=" 高级配置 ")
        self._setup_settings_tab()

    def _setup_translation_tab(self):
        preset_frame = ttk.Frame(self.trans_tab)
        preset_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(preset_frame, text="快速切换环境预设:").pack(side=tk.LEFT, padx=5)
        self.preset_combo = ttk.Combobox(preset_frame, textvariable=self.vm.preset_var, state="readonly", width=35)
        self.preset_combo.pack(side=tk.LEFT, padx=5)
        self.preset_combo.bind("<<ComboboxSelected>>", lambda e: self.preset_manager.apply_preset())

        file_frame = ttk.LabelFrame(self.trans_tab, text="文件选择", padding="10")
        file_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(file_frame, text="输入文件 (MKV/SRT/ASS):").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(file_frame, textvariable=self.vm.input_file, width=70).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(file_frame, text="浏览...", command=self.browse_input).grid(row=0, column=2, pady=2)

        ttk.Label(file_frame, text="输出文件 (可选):").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(file_frame, textvariable=self.vm.output_file, width=70).grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(file_frame, text="浏览...", command=self.browse_output).grid(row=1, column=2, pady=2)

        opt_frame = ttk.LabelFrame(self.trans_tab, text="基础选项", padding="10")
        opt_frame.pack(fill=tk.X, pady=5)

        ttk.Checkbutton(opt_frame, text="双语字幕", variable=self.vm.bilingual_var).grid(row=0, column=0, padx=5, sticky="w")
        
        ttk.Label(opt_frame, text="目标格式:").grid(row=0, column=1, padx=5, sticky="e")
        ttk.Combobox(opt_frame, textvariable=self.vm.format_var, values=["ass", "srt"], state="readonly", width=10).grid(row=0, column=2, sticky="w")

        ttk.Label(opt_frame, text="目标语言:").grid(row=0, column=3, padx=5, sticky="e")
        ttk.Combobox(opt_frame, textvariable=self.vm.target_lang_var, values=["zh", "en"], state="readonly", width=10).grid(row=0, column=4, sticky="w")

        prog_frame = ttk.Frame(self.trans_tab)
        prog_frame.pack(fill=tk.X, pady=10)
        
        self.progress_bar = ttk.Progressbar(prog_frame, variable=self.vm.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, side=tk.LEFT, expand=True, padx=(0, 10))
        
        self.progress_label = ttk.Label(prog_frame, text="0%")
        self.progress_label.pack(side=tk.RIGHT)

        self.start_btn = ttk.Button(self.trans_tab, text="🚀 开始翻译任务", command=lambda: self.task_controller.start_thread())
        self.start_btn.pack(fill=tk.X, ipady=10, pady=5)

        log_frame = ttk.LabelFrame(self.trans_tab, text="运行日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_area = scrolledtext.ScrolledText(log_frame, state='disabled', height=15, font=("Consolas", 9))
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def _setup_settings_tab(self):
        api_frame = ttk.LabelFrame(self.settings_tab, text="API 配置", padding="10")
        api_frame.pack(fill=tk.X, pady=5)

        ttk.Label(api_frame, text="API URL:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(api_frame, textvariable=self.vm.api_url_var, width=65).grid(row=0, column=1, padx=5, sticky="w")

        ttk.Label(api_frame, text="API Key:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(api_frame, textvariable=self.vm.api_key_var, width=65, show="*").grid(row=1, column=1, padx=5, sticky="w")

        ttk.Label(api_frame, text="模型名称:").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(api_frame, textvariable=self.vm.model_var, width=45).grid(row=2, column=1, padx=5, sticky="w")

        pipe_frame = ttk.LabelFrame(self.settings_tab, text="流水线参数", padding="10")
        pipe_frame.pack(fill=tk.X, pady=5)

        ttk.Label(pipe_frame, text="并发请求数:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Spinbox(pipe_frame, from_=1, to=100, textvariable=self.vm.concurrent_var, width=12).grid(row=0, column=1, padx=5, sticky="w")

        ttk.Label(pipe_frame, text="每分钟请求(RPM):").grid(row=0, column=2, sticky="e", padx=10)
        ttk.Spinbox(pipe_frame, from_=1, to=10000, textvariable=self.vm.rpm_var, width=12).grid(row=0, column=3, sticky="w")

        ttk.Label(pipe_frame, text="批次大小(Batch):").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Spinbox(pipe_frame, from_=1, to=50, textvariable=self.vm.batch_size_var, width=12).grid(row=1, column=1, padx=5, sticky="w")

        ttk.Label(pipe_frame, text="Max Tokens:").grid(row=1, column=2, sticky="e", padx=10)
        ttk.Spinbox(pipe_frame, from_=256, to=128000, textvariable=self.vm.max_tokens_var, width=12, increment=256).grid(row=1, column=3, sticky="w")

        ttk.Label(pipe_frame, text="失败重试次数:").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Spinbox(pipe_frame, from_=0, to=10, textvariable=self.vm.retries_var, width=12).grid(row=2, column=1, padx=5, sticky="w")

        ttk.Label(pipe_frame, text="重试延迟(秒):").grid(row=2, column=2, sticky="e", padx=10)
        ttk.Spinbox(pipe_frame, from_=0.1, to=60.0, textvariable=self.vm.retry_delay_var, width=12, increment=0.5).grid(row=2, column=3, sticky="w")

        ttk.Checkbutton(pipe_frame, text="启用 LLM 发现术语库", variable=self.vm.enable_discovery_var).grid(row=3, column=0, sticky="w", pady=5)
        ttk.Checkbutton(pipe_frame, text="启用人名数据库 (默认禁用)", variable=self.vm.enable_names_db_var).grid(row=3, column=1, sticky="w", pady=5)
        
        ttk.Checkbutton(pipe_frame, text="启用全文注释生成（实验性）", variable=self.vm.enable_annotations_var).grid(row=4, column=0, sticky="w", pady=5)

        # --- Advanced Core Params Frame ---
        adv_frame = ttk.LabelFrame(self.settings_tab, text="高级核心参数 (Advanced Core)", padding="10")
        adv_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(adv_frame, text="推理力度 (Reasoning):").grid(row=0, column=0, sticky="w", pady=5)
        reasoning_cb = ttk.Combobox(adv_frame, textvariable=self.vm.reasoning_effort_var, values=["", "none", "low", "medium", "high"], width=10, state="readonly")
        reasoning_cb.grid(row=0, column=1, padx=5, sticky="w")
        
        chk_frame = ttk.Frame(adv_frame)
        chk_frame.grid(row=0, column=2, columnspan=2, sticky="w", padx=10)
        ttk.Checkbutton(chk_frame, text="开启全局终审", variable=self.vm.enforce_consistency_var).pack(side=tk.LEFT)
        ttk.Label(chk_frame, text="最大轮数:").pack(side=tk.LEFT, padx=(10, 2))
        ttk.Spinbox(chk_frame, from_=1, to=10, textvariable=self.vm.post_check_passes_var, width=5).pack(side=tk.LEFT)
        
        ttk.Label(adv_frame, text="上下文预算 (Tokens):").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Spinbox(adv_frame, from_=1000, to=2000000, textvariable=self.vm.context_budget_var, width=12, increment=1000).grid(row=1, column=1, padx=5, sticky="w")
        
        ttk.Label(adv_frame, text="上文参考行数 (Lines):").grid(row=1, column=2, sticky="e", padx=10)
        ttk.Spinbox(adv_frame, from_=1, to=100, textvariable=self.vm.max_previous_lines_var, width=12).grid(row=1, column=3, sticky="w")

        temp_frame = ttk.LabelFrame(self.settings_tab, text="模型温度 (Temperature)", padding="10")
        temp_frame.pack(fill=tk.X, pady=5)

        ttk.Checkbutton(temp_frame, text="传入 Temperature 参数", variable=self.vm.pass_temperature_var).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        def create_temp_slider(parent, label, var, row):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
            s = ttk.Scale(parent, from_=0.0, to=1.0, variable=var, orient=tk.HORIZONTAL)
            s.grid(row=row, column=1, padx=5, sticky="ew")
            l = ttk.Label(parent, width=5)
            l.grid(row=row, column=2, padx=5)
            def update_label(*args):
                try: l.config(text=f"{float(var.get()):.1f}")
                except: pass
            var.trace_add("write", update_label)
            update_label() 

        create_temp_slider(temp_frame, "术语提取 (Terms):", self.vm.temp_terms_var, 1)
        create_temp_slider(temp_frame, "直译阶段 (Literal):", self.vm.temp_literal_var, 2)
        create_temp_slider(temp_frame, "润色阶段 (Polish):", self.vm.temp_polish_var, 3)
        
        temp_frame.columnconfigure(1, weight=1)

        btn_frame = ttk.Frame(self.settings_tab)
        btn_frame.pack(fill=tk.X, pady=10)

        ttk.Button(btn_frame, text="💾 保存当前设置", command=lambda: self.preset_manager.save_to_current_preset()).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, ipady=8)
        ttk.Button(btn_frame, text="➕ 另存为新预设", command=lambda: self.preset_manager.add_custom_preset()).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, ipady=8)
        ttk.Button(btn_frame, text="🗑️ 清理翻译缓存", command=lambda: self.task_controller.do_clear_cache()).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, ipady=8)

    def _on_format_changed(self, *args):
        out = self.vm.output_file.get()
        if out:
            base, _ = os.path.splitext(out)
            self.vm.output_file.set(f"{base}.{self.vm.format_var.get()}")

    def browse_input(self):
        filetypes = [("Media Files", "*.mkv *.srt *.ass"), ("All Files", "*.*")]
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            self.vm.input_file.set(path)
            base, _ = os.path.splitext(path)
            self.vm.output_file.set(f"{base}.{self.vm.format_var.get()}")

    def browse_output(self):
        path = filedialog.asksaveasfilename(defaultextension=f".{self.vm.format_var.get()}")
        if path:
            self.vm.output_file.set(path)
