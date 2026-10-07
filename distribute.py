# -*- coding: utf-8 -*-
"""
Subtitle Pipeline Distribution Script (Python)
- 打包绿组翻译工具分发包
- presets.json 替换为组内精简版 (presets - 副本.json)
- 压缩后删除临时文件夹，只保留 zip
"""

import os
import shutil
import zipfile
import json
from datetime import datetime

ROOT = r"C:\Users\VerNe\Downloads\Documents\translate_principle\subtitle pipeline source"
DIST_NAME = "subtitle pipeline source"
DIST_PATH = os.path.join(ROOT, DIST_NAME)

# 要复制的内容
ITEMS = ["subtitle", "WebUi.md", "README.md", "start_gui.bat", "python_embed"]

# 特殊文件：Unicode 文件名通过 Python 字符串直接处理
BAT_FILE = "文章翻译.bat"
BAT_SOURCE = os.path.join(ROOT, BAT_FILE)

# Zip 命名
BASE_NAME = "绿组翻译工具"
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
ZIP_NAME = f"{BASE_NAME}_{TIMESTAMP}.zip"
ZIP_PATH = os.path.join(ROOT, ZIP_NAME)


def main():
    # 1. Cleanup old dist folder
    if os.path.exists(DIST_PATH):
        print("Cleaning old distribution folder...")
        shutil.rmtree(DIST_PATH, ignore_errors=True)

    # 2. Create dist folder
    os.makedirs(DIST_PATH, exist_ok=True)

    # 3. Copy components
    print("Preparing distribution files...")
    for item in ITEMS:
        src = os.path.join(ROOT, item)
        dst = os.path.join(DIST_PATH, item)
        if os.path.exists(src):
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            print(f"  Copied: {item}")
        else:
            print(f"  [WARNING] Not found: {item}")

    # 复制 bat 文件（含中文名）
    if os.path.exists(BAT_SOURCE):
        shutil.copy2(BAT_SOURCE, os.path.join(DIST_PATH, BAT_FILE))
        print(f"  Copied: {BAT_FILE}")

    # 4. Handle presets.json
    subtitle_dir = os.path.join(DIST_PATH, "subtitle")
    presets_json = os.path.join(subtitle_dir, "presets.json")
    presets_copy = os.path.join(subtitle_dir, "presets - 副本.json")
    presets_example = os.path.join(subtitle_dir, "presets.json.example")

    # 删除旧的 preset 文件
    for f in [presets_json, presets_copy, presets_example]:
        if os.path.exists(f):
            os.remove(f)
            print(f"  Removed old preset file: {os.path.basename(f)}")

    # 写入新的单模型 presets.json
    single_preset = {
        "glm-5.2": {
            "api_key": "",
            "api_url": "https://token.sensenova.cn/v1/chat/completions",
            "model_name": "glm-5.2",
            "max_concurrent": "1",
            "rpm_limit": "30",
            "batch_size": "15",
            "max_retries": "5",
            "retry_delay": "2.0",
            "max_tokens": "4096",
            "temp_terms": "0.1",
            "temp_literal": "0.1",
            "temp_polish": "0.5",
            "enable_discovery": "True",
            "enable_names_db": "False",
            "enable_annotations": "False",
            "reasoning_effort": "none",
            "context_budget_tokens": "200000",
            "max_previous_lines": "25",
            "enforce_consistency": "True",
            "tpm_limit": "2000000"
        },
        "_current": "glm-5.2"
    }
    
    with open(presets_json, "w", encoding="utf-8") as f:
        json.dump(single_preset, f, indent=4, ensure_ascii=False)
    print("  Created new presets.json (single glm-5.2 preset)")

    # 5. Create ZIP
    if os.path.exists(ZIP_PATH):
        os.remove(ZIP_PATH)

    print(f"\nCreating ZIP: {ZIP_NAME} ...")
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for root_dir, dirs, files in os.walk(DIST_PATH):
            for file in files:
                file_path = os.path.join(root_dir, file)
                arcname = os.path.relpath(file_path, DIST_PATH)
                zf.write(file_path, arcname)

    # 6. Cleanup temp folder
    print("Removing temporary folder...")
    shutil.rmtree(DIST_PATH, ignore_errors=True)

    print(f"\nDone! Zip created at: {ZIP_PATH}")


if __name__ == "__main__":
    main()
