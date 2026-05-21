# -*- coding: utf-8 -*-
import os
import json
import glob
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, Toplevel
import pyperclip

# 配置路径
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

class GlossaryManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("语料库智能管理器")
        self.root.geometry("800x600")

        # 内存中存储已有的 source_term，用于去重
        self.existing_terms = set()
        self.current_batch = [] # 当前准备保存的批次

        # --- 界面布局 ---

        # 1. 顶部操作区
        top_frame = tk.Frame(root, pady=10)
        top_frame.pack(fill=tk.X, padx=10)

        self.btn_check_clipboard = tk.Button(top_frame, text="📋 读取剪贴板并去重", command=self.check_clipboard, bg="#e1f5fe", font=("微软雅黑", 10))
        self.btn_check_clipboard.pack(side=tk.LEFT, padx=5)

        self.btn_manual_add = tk.Button(top_frame, text="➕ 手动添加单条", command=self.open_manual_dialog, font=("微软雅黑", 10))
        self.btn_manual_add.pack(side=tk.LEFT, padx=5)

        self.btn_refresh = tk.Button(top_frame, text="🔄 刷新现有库", command=self.load_existing_db, font=("微软雅黑", 10))
        self.btn_refresh.pack(side=tk.RIGHT, padx=5)

        # 2. 状态标签
        self.lbl_status = tk.Label(root, text="就绪", fg="gray", anchor="w")
        self.lbl_status.pack(fill=tk.X, padx=10)

        # 3. 中间文本编辑区 (预览/编辑 JSON)
        tk.Label(root, text="待保存内容预览 (可直接修改):").pack(anchor="w", padx=10)
        self.text_area = scrolledtext.ScrolledText(root, font=("Consolas", 10))
        self.text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 4. 底部保存区
        bottom_frame = tk.Frame(root, pady=10)
        bottom_frame.pack(fill=tk.X, padx=10)

        self.btn_save = tk.Button(bottom_frame, text="💾 保存为新文件 (自动序号)", command=self.save_to_new_file, bg="#c8e6c9", font=("微软雅黑", 11, "bold"))
        self.btn_save.pack(fill=tk.X)

        # 初始化加载
        self.load_existing_db()

    def log(self, message, color="black"):
        self.lbl_status.config(text=message, fg=color)

    def load_existing_db(self):
        """扫描当前目录下所有 json，加载 source_term 到内存"""
        self.existing_terms.clear()
        json_files = glob.glob(os.path.join(CURRENT_DIR, "*.json"))
        
        count = 0
        for fpath in json_files:
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            term = item.get("source_term", "").strip().lower()
                            if term:
                                self.existing_terms.add(term)
                                count += 1
            except Exception:
                pass # 忽略损坏的文件
        
        self.log(f"已加载现有语料库: {len(json_files)} 个文件，共 {count} 个词条", "blue")

    def get_next_filename(self):
        """获取下一个可用的数字文件名，例如 14.json"""
        json_files = glob.glob(os.path.join(CURRENT_DIR, "*.json"))
        max_num = 0
        for fpath in json_files:
            basename = os.path.basename(fpath)
            name_part = os.path.splitext(basename)[0]
            if name_part.isdigit():
                num = int(name_part)
                if num > max_num:
                    max_num = num
        return f"{max_num + 1}.json"

    def check_clipboard(self):
        """读取剪贴板，验证 JSON 格式，并去重"""
        content = pyperclip.paste().strip()
        if not content:
            messagebox.showwarning("提示", "剪贴板为空！")
            return

        try:
            # 尝试修复常见的格式错误 (比如末尾多了逗号)
            if content.endswith(","):
                content = content[:-1]
            
            data = json.loads(content)
        except json.JSONDecodeError as e:
            messagebox.showerror("格式错误", f"剪贴板内容不是有效的 JSON。\n\n错误信息: {e}")
            return

        # 统一处理：如果是单个对象，转为列表
        if isinstance(data, dict):
            data = [data]
        
        if not isinstance(data, list):
            messagebox.showerror("格式错误", "JSON 必须是对象列表 (Array) 或单个对象。")
            return

        # 开始去重和验证
        valid_entries = []
        duplicates = []
        ignored = 0

        for item in data:
            # 检查必要字段
            if "source_term" not in item or "target_term" not in item:
                ignored += 1
                continue
            
            src = item["source_term"].strip()
            # 补全默认 category
            if "category" not in item:
                item["category"] = "General"
            
            # 去重检查 (不区分大小写)
            if src.lower() in self.existing_terms:
                duplicates.append(src)
            else:
                valid_entries.append(item)

        # 更新当前批次
        self.current_batch = valid_entries
        self.update_text_area()

        msg = f"处理完成！\n\n✅ 有效新词: {len(valid_entries)} 条\n🚫 忽略重复: {len(duplicates)} 条\n⚠️ 格式无效: {ignored} 条"
        if duplicates:
            msg += f"\n\n重复词示例: {', '.join(duplicates[:5])}..."
        
        messagebox.showinfo("结果", msg)
        self.log(f"就绪 - 待保存: {len(valid_entries)} 条", "green" if valid_entries else "orange")

    def update_text_area(self):
        """将 current_batch 格式化显示在文本框"""
        content = json.dumps(self.current_batch, ensure_ascii=False, indent=4)
        self.text_area.delete(1.0, tk.END)
        self.text_area.insert(tk.END, content)

    def open_manual_dialog(self):
        """打开手动添加弹窗"""
        dialog = Toplevel(self.root)
        dialog.title("手动添加词条")
        dialog.geometry("400x300")
        
        tk.Label(dialog, text="原文 (Source Term):").pack(pady=5)
        entry_src = tk.Entry(dialog, width=40)
        entry_src.pack()
        
        tk.Label(dialog, text="译文 (Target Term):").pack(pady=5)
        entry_tgt = tk.Entry(dialog, width=40)
        entry_tgt.pack()
        
        tk.Label(dialog, text="分类 (Category):").pack(pady=5)
        entry_cat = tk.Entry(dialog, width=40)
        entry_cat.insert(0, "Named Entities")
        entry_cat.pack()
        
        def add_entry():
            src = entry_src.get().strip()
            tgt = entry_tgt.get().strip()
            cat = entry_cat.get().strip()
            
            if not src or not tgt:
                messagebox.showwarning("提示", "原文和译文不能为空")
                return
            
            if src.lower() in self.existing_terms:
                messagebox.showwarning("重复", f"'{src}' 已存在于语料库中！")
                return

            new_entry = {
                "source_term": src,
                "target_term": tgt,
                "category": cat
            }
            
            # 从文本框读取最新内容，合并
            try:
                current_text = self.text_area.get(1.0, tk.END).strip()
                if current_text:
                    current_data = json.loads(current_text)
                else:
                    current_data = []
            except:
                current_data = []
            
            current_data.append(new_entry)
            self.current_batch = current_data
            self.update_text_area()
            self.existing_terms.add(src.lower()) # 临时添加到内存防止重复添加
            
            dialog.destroy()
            self.log("已手动添加 1 条", "blue")

        tk.Button(dialog, text="添加", command=add_entry, bg="#c8e6c9", width=20).pack(pady=20)

    def save_to_new_file(self):
        """保存当前文本框内容到新文件"""
        # 1. 从文本框获取最终内容 (允许用户手动修改过)
        try:
            content = self.text_area.get(1.0, tk.END).strip()
            if not content:
                messagebox.showwarning("提示", "没有内容可保存")
                return
            final_data = json.loads(content)
        except json.JSONDecodeError:
            messagebox.showerror("错误", "文本框中的内容不是有效的 JSON，请检查格式。")
            return

        if not final_data:
            return

        # 2. 获取文件名
        filename = self.get_next_filename()
        filepath = os.path.join(CURRENT_DIR, filename)

        # 3. 写入
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=4)
            
            messagebox.showinfo("成功", f"已成功保存到:\n{filename}\n\n包含 {len(final_data)} 个词条。")
            
            # 4. 重置状态
            self.current_batch = []
            self.text_area.delete(1.0, tk.END)
            self.load_existing_db() # 重新加载以更新查重库
            
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = GlossaryManagerApp(root)
    root.mainloop()
