# -*- coding: utf-8 -*-
"""
Facade and CLI entrypoint for the subtitle translator GUI.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

PROJECT_ROOT = os.path.dirname(BASE_DIR)
# 检查是否处于嵌入式环境 (python_embed 目录存在)
EMBED_TCL_DIR = os.path.join(PROJECT_ROOT, "python_embed", "Lib", "site-packages", "tcl")
if os.path.exists(EMBED_TCL_DIR):
    os.environ["TCL_LIBRARY"] = os.path.join(EMBED_TCL_DIR, "tcl8.6")
    os.environ["TK_LIBRARY"] = os.path.join(EMBED_TCL_DIR, "tk8.6")

import tkinter as tk
from gui.main_window import SubtitleTranslatorApp

# @lat: [[entries#Key Concepts#桌面 GUI 入口（gui_app.py）]]
def run_gui():
    root = tk.Tk()
    app = SubtitleTranslatorApp(root)
    root.mainloop()

if __name__ == "__main__":
    run_gui()
