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

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import pyperclip
import asyncio

# 尝试导入现有的术语管理器
try:
    # 将父目录加入路径以便导入 subtitle.core
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from subtitle.core.glossary_manager import glossary_manager
    GLOSSARY_AVAILABLE = True
except ImportError:
    GLOSSARY_AVAILABLE = False

# @lat: [[entries#Key Concepts#WebUI 入口（webui_gui.py）]]
class WebUiGui:
    def __init__(self, root):
        self.root = root
        self.root.title("AI 翻译 WebUI 助手 - v1.2")
        self.root.geometry("1000x800")

        # 初始化术语库 (在 WebUI 模式下，强制加载发现库以便使用，但严禁在该进程内进行保存)
        self.glossary_stats = "未加载"
        if GLOSSARY_AVAILABLE:
            try:
                # 显式告知加载发现库，但保持全局 enable_discovery 不变（用于控制保存权限）
                glossary_manager.initialize(load_discovery=True)
                
                # 【安全性确保】在 WebUI 进程中强制关闭保存权限，即使全局配置开启了也不允许在此处保存
                glossary_manager.enable_discovery = False
                
                count = len(glossary_manager.term_mapping)
                self.glossary_stats = f"已加载 {count} 条术语 (发现库设为只读)"
            except Exception as e:
                self.glossary_stats = f"加载失败: {e}"

        self.setup_ui()

    def setup_ui(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 顶部：状态与工具栏
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.stat_label = ttk.Label(status_frame, text=f"系统状态: {self.glossary_stats}", foreground="blue")
        self.stat_label.pack(side=tk.LEFT)
        
        ttk.Button(status_frame, text="刷新语料库", command=self.refresh_glossary).pack(side=tk.RIGHT)

        # 上部：输入区域
        input_label = ttk.Label(main_frame, text="1. 请输入英文原文:")
        input_label.pack(anchor=tk.W, pady=(0, 5))
        
        self.input_text = scrolledtext.ScrolledText(main_frame, height=12, font=("Consolas", 11))
        self.input_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 中部：控制区域 (拆分为三个独立开关)
        ctrl_frame = ttk.LabelFrame(main_frame, text="辅助功能开关", padding="5")
        ctrl_frame.pack(fill=tk.X, pady=(0, 10))

        self.use_static = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl_frame, text="接入静态术语库", variable=self.use_static).pack(side=tk.LEFT, padx=10)

        self.use_discovery = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl_frame, text="接入发现库 (自动记忆)", variable=self.use_discovery).pack(side=tk.LEFT, padx=10)

        self.use_names = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl_frame, text="接入人名数据库", variable=self.use_names).pack(side=tk.LEFT, padx=10)

        # 下部：步骤按钮区域
        btn_frame = ttk.LabelFrame(main_frame, text="2. 选择步骤生成 Prompt", padding="10")
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        steps = [
            ("步骤 0: 初始化 (System)", self.gen_step_0),
            ("步骤 1: 术语提取", self.gen_step_1),
            ("步骤 2: 直译", self.gen_step_2),
            ("步骤 3: 找茬审校", self.gen_step_3),
            ("步骤 4A: 最终意译", self.gen_step_4a),
            ("步骤 4B: 风格化", self.gen_step_4b),
        ]

        for i, (name, cmd) in enumerate(steps):
            btn = ttk.Button(btn_frame, text=name, command=cmd)
            btn.grid(row=i // 3, column=i % 3, sticky=tk.EW, padx=5, pady=5)
        
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=1)

        # 底部：输出区域
        output_label = ttk.Label(main_frame, text="3. 生成的 Prompt (已自动复制到剪贴板):")
        output_label.pack(anchor=tk.W, pady=(0, 5))

        self.output_text = scrolledtext.ScrolledText(main_frame, height=15, font=("Consolas", 10), bg="#f8f9fa")
        self.output_text.pack(fill=tk.BOTH, expand=True)

        # 状态栏
        self.status_var = tk.StringVar(value="准备就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(5, 0))

    def refresh_glossary(self):
        try:
            glossary_manager.initialize()
            count = len(glossary_manager.term_mapping)
            self.stat_label.config(text=f"系统状态: 已成功刷新 ({count} 条术语)")
            messagebox.showinfo("成功", f"语料库已刷新，当前加载 {count} 条术语")
        except Exception as e:
            messagebox.showerror("错误", f"刷新失败: {e}")

    def set_output(self, text):
        self.output_text.delete(1.0, tk.END)
        self.output_text.insert(tk.END, text)
        pyperclip.copy(text)
        self.status_var.set("Prompt 已生成并复制到剪贴板！")

    def get_input(self):
        return self.input_text.get(1.0, tk.END).strip()

    def gen_step_0(self):
        from subtitle.core.prompts import load_prompt
        # TODO: Load domain context if available
        prompt = load_prompt("webui_step_0").format(domain_context="")
        self.set_output(prompt)

    def gen_step_1(self):
        content = self.get_input()
        if not content:
            messagebox.showwarning("警告", "请先输入英文原文")
            return

        self.status_var.set("正在执行智能识别...")
        self.root.update_idletasks() # 强制刷新 UI 显示状态

        glossary_info = ""
        name_info = ""
        
        if GLOSSARY_AVAILABLE:
            try:
                # 1. 提取术语 (根据开关过滤)
                found = glossary_manager.extract_terms(
                    content, 
                    include_static=self.use_static.get(), 
                    include_discovery=self.use_discovery.get()
                )
                
                if found:
                    glossary_info = "\n<已知术语引用>\n以下是术语库中已有的术语，请严格遵守：\n\n"
                    glossary_info += "| 英文 | 中文 | 类别 | 说明 |\n"
                    glossary_info += "| --- | --- | --- | --- |\n"
                    for en, info in found.items():
                        target = info.get('target', '')
                        cat = info.get('category', 'General')
                        desc = info.get('description', '').replace('\n', ' ')
                        glossary_info += f"| {en} | {target} | {cat} | {desc} |\n"
                    glossary_info += "\n"
                
                # 2. 调用 LLM 人名识别 (仅在开关开启时)
                if self.use_names.get():
                    from subtitle.core.config import TranslationConfig
                    config = TranslationConfig()
                    exclude_list = list(found.keys()) if found else []
                    
                    try:
                        # 显式传递 force_enable=True 以跳过全局配置检查
                        found_names = asyncio.run(glossary_manager.fetch_names_with_llm(content, config, force_enable=True))
                        if found_names:
                            found_names = {k: v for k, v in found_names.items() if k not in exclude_list}
                    except Exception as e:
                        print(f"NER 执行异常: {e}")
                        found_names = {}
                    
                    if found_names:
                        name_info = "\n<已知人名引用>\n以下是人名翻译数据库中的建议译名，请优先采用：\n\n"
                        name_info += "| 英文名 | 建议中文译名 |\n"
                        name_info += "| --- | --- |\n"
                        for en, cn in found_names.items():
                            name_info += f"| {en} | {cn} |\n"
                        name_info += "\n"

            except Exception as e:
                import traceback
                traceback.print_exc()
                self.status_var.set(f"识别出错: {e}")

        from subtitle.core.prompts import load_prompt
        prompt_template = load_prompt("webui_step_1")
        prompt = prompt_template.format(
            glossary_info=glossary_info,
            name_info=name_info,
            content=content
        )
        self.set_output(prompt)

    def gen_step_2(self):
        from subtitle.core.prompts import load_prompt
        prompt = load_prompt("webui_step_2")
        self.set_output(prompt)

    def gen_step_3(self):
        from subtitle.core.prompts import load_prompt
        prompt = load_prompt("webui_step_3")
        self.set_output(prompt)

    def gen_step_4a(self):
        from subtitle.core.prompts import load_prompt
        prompt = load_prompt("webui_step_4a")
        self.set_output(prompt)

    def gen_step_4b(self):
        from subtitle.core.prompts import load_prompt
        # TODO: Load domain context if available
        prompt = load_prompt("webui_step_4b").format(domain_context="")
        self.set_output(prompt)

if __name__ == "__main__":
    root = tk.Tk()
    app = WebUiGui(root)
    root.mainloop()