# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import pyperclip
import os
import sys
import asyncio

# 尝试导入现有的术语管理器
try:
    # 将父目录加入路径以便导入 subtitle.core
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from subtitle.core.glossary_manager import glossary_manager
    GLOSSARY_AVAILABLE = True
except ImportError:
    GLOSSARY_AVAILABLE = False

class WebUiGui:
    def __init__(self, root):
        self.root = root
        self.root.title("AI 翻译 WebUI 助手 - v1.1")
        self.root.geometry("1000x800")

        # 初始化术语库
        self.glossary_stats = "未加载"
        if GLOSSARY_AVAILABLE:
            try:
                glossary_manager.initialize()
                count = len(glossary_manager.term_mapping)
                self.glossary_stats = f"已加载 {count} 条术语"
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

        # 中部：控制区域
        ctrl_frame = ttk.Frame(main_frame)
        ctrl_frame.pack(fill=tk.X, pady=(0, 10))

        self.use_glossary = tk.BooleanVar(value=True)
        self.glossary_chk = ttk.Checkbutton(ctrl_frame, text="接入术语库与人名库 (自动识别)", variable=self.use_glossary)
        self.glossary_chk.pack(side=tk.LEFT)

        # 下部：步骤按钮区域
        btn_frame = ttk.LabelFrame(main_frame, text="2. 选择步骤生成 Prompt", padding="10")
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        steps = [
            ("步骤 0: 初始化 (System)", self.gen_step_0),
            ("步骤 1: 术语提取", self.gen_step_1),
            ("步骤 2: 直译", self.gen_step_2),
            ("步骤 3: 找茬审校", self.gen_step_3),
            ("步骤 4A: 最终意译", self.gen_step_4a),
            ("步骤 4B: 克拉克森风格", self.gen_step_4b),
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
        prompt = """# Role (角色设定)
你是一名精通简体中文的专业技术译者，特别擅长将专业的英文学术论文或技术文档转换为通俗易懂的中文科普文章。

# Global Rules (全局规范)
在接下来的对话中，我们将对一段英文文本进行翻译。无论进行到哪一步，你都必须严格遵守以下规范：
1. **人名处理**：技术书籍中的人名通常不翻译，除非是众所周知的（如乔布斯）。
2. **书名处理**：有中文版的用中文版书名；无中文版的直接保留英文书名。
3. **术语格式**：英文术语首次出现时，若有必要，应使用“HTML（Hypertext Markup Language，超文本标识语言）”的格式，之后可使用简写。
4. **代码处理**：代码块（Code Block）完全不翻译。代码内的注释需翻译（中英对照）。
5. **标点符号**：译文必须遵循中文标点符号的使用习惯，严禁照搬英文标点。
6. **图表**：图题、表题需翻译。"""
        self.set_output(prompt)

    def gen_step_1(self):
        content = self.get_input()
        if not content:
            messagebox.showwarning("警告", "请先输入英文原文")
            return

        self.status_var.set("正在通过 LLM 智能提取术语与人名...")
        self.root.update_idletasks() # 强制刷新 UI 显示状态

        glossary_info = ""
        name_info = ""
        
        if self.use_glossary and GLOSSARY_AVAILABLE:
            try:
                # 1. 提取静态术语库内容
                found = glossary_manager.extract_terms(content)
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
                
                # 2. 【核心升级】调用统一的 LLM 人名识别模块
                from subtitle.core.config import TranslationConfig
                config = TranslationConfig()
                
                # 显式传入已在主库中发现的词，作为最高优先级排除
                exclude_list = list(found.keys()) if found else []
                
                # 在同步环境中运行异步识别任务
                try:
                    found_names = asyncio.run(glossary_manager.fetch_names_with_llm(content, config))
                    # 再次在结果层进行过滤，确保万无一失
                    if found_names:
                        found_names = {k: v for k, v in found_names.items() if k not in exclude_list}
                except Exception as e:
                    import traceback
                    print("--- NER 执行异常详情 ---")
                    traceback.print_exc()
                    print("------------------------")
                    found_names = {}
                
                if found_names:
                    name_info = "\n<已知人名引用>\n以下是人名翻译数据库中的建议译名，请优先采用：\n\n"
                    name_info += "| 英文名 | 建议中文译名 |\n"
                    name_info += "| --- | --- |\n"
                    for en, cn in found_names.items():
                        name_info += f"| {en} | {cn} |\n"
                    name_info += "\n"
                else:
                    print("DEBUG: LLM 未识别到任何库中存在的人名")
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.status_var.set(f"识别出错: {e}")

        prompt = f"""<任务> 识别用户输入文本中的技术术语和人物全名。请严格按照示例中的格式，展示翻译前后的对应关系。
{glossary_info}{name_info}
<注意> 
1. 除了上述提供的已知译名外，请自行识别文本中出现的其他重要人物、地名或技术词汇。
2. 即使我没有提供译名的人名，也请你在表格中列出并给出你认为最准确的中文翻译。

<示例>
| 英文 | 中文 |
| --- | --- |
| Prompt Engineering | 提示词工程 |
| Jeremy Clarkson | 杰里米·克拉克森 |
| Context | 上下文 |

<输入文本> 
{content}"""
        self.set_output(prompt)

    def gen_step_2(self):
        prompt = """<任务> 接下来进行第二步：直译。

请参考**上文生成的术语表格**，以及**最开始的输入文本**，进行逐句直译。

<限制> 
1. 维持原有的段落格式，不省略任何信息。
2. 优先保证准确性，暂不需要过度润色。
3. 遇到上文表格中的术语，请严格按照表格对应的中文进行翻译。

请直接输出直译结果："""
        self.set_output(prompt)

    def gen_step_3(self):
        prompt = """<任务> 接下来进行第三步：审校找茬。

请作为审校专家，检查**刚刚生成的直译文本**，结合**英文原文**，指出其中具体存在的问题。

<检查标准>
1. **表达习惯**：指出不符合中文表达习惯或句子结构笨拙的位置。
2. **规范检查**：
   - 人名是否保留英文（除众所周知外）？
   - 书名是否有中文版？无中文版需保留英文。
   - 首次出现的英文术语是否使用了“HTML格式”？
   - 标点符号是否已转换为中文标点？
3. **代码与图表**：检查代码注释是否翻译，代码本体是否保留。
4. **注释规划**：找出文中需要添加“译者注”的地方。

<输出要求>
1. 列出具体的问题清单。
2. 列出**拟添加注释的清单**（格式：原文词汇 -> 拟解释内容）。"""
        self.set_output(prompt)

    def gen_step_4a(self):
        prompt = """<任务> 接下来进行第四步：最终意译。

请基于**上一步指出的问题清单**，对**之前的直译文本**进行修正和润色。

<要求>
1. **风格调整**：将语风转化为“通俗易懂的科普文章”。
2. **问题修正**：必须逐一解决上文指出的所有问题。
3. **格式保留**：保持原有的段落和结构不变。
4. **输出限制**：**只输出最终的翻译文本**。
5. **插入注释**：在正文中需要解释的地方插入 [注x] 标记，并在文末列出。

请输出最终翻译结果："""
        self.set_output(prompt)

    def gen_step_4b(self):
        prompt = """<任务> 最终意译（克拉克森特调版 + 客观注释）。

<核心指令>
原文作者是 **Jeremy Clarkson**，他的风格是：**尖酸刻薄、极度夸张、英式幽默、充满比喻**。

<角色分离设定>
1. **正文部分**：请完全沉浸在 **Jeremy Clarkson** 的角色中，用第一人称（“我”）进行翻译，风格要辛辣、口语化。
2. **注释部分**：请切换回 **客观译者** 的身份（第三人称）。

请输出最终翻译结果："""
        self.set_output(prompt)

if __name__ == "__main__":
    root = tk.Tk()
    app = WebUiGui(root)
    root.mainloop()