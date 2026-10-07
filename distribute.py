# -*- coding: utf-8 -*-
"""
Subtitle Pipeline Distribution Script (Python)
- 打包绿组翻译工具分发包
- presets.json 替换为组内精简版
- 默认不分发 names_translation.db 等大型数据库（支持 --full 完整模式）
- 自动过滤日志、缓存、临时文件及测试备份
- 压缩后删除临时文件夹，只保留 zip
"""

import os
import sys
import shutil
import zipfile
import json
import argparse
from datetime import datetime

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST_NAME = "_dist_staging"
DIST_PATH = os.path.join(ROOT, DIST_NAME)

# 要复制的组件
ITEMS = ["subtitle", "WebUi.md", "README.md", "start_gui.bat", "python_embed"]
BAT_FILE = "文章翻译.bat"
BAT_SOURCE = os.path.join(ROOT, BAT_FILE)

BASE_NAME = "绿组翻译工具"


def make_ignore_filter(full: bool = False):
    """创建目录复制过滤规则"""
    def _ignore(directory, files):
        ignored = set()
        for f in files:
            # 忽略常见缓存与开发目录
            if f in ("__pycache__", ".cache", ".git", ".idea", ".vscode", ".plan", ".handoffs", ".workbuddy", "outputs"):
                ignored.add(f)
            elif f.endswith((".pyc", ".pyo", ".log", ".tmp")):
                ignored.add(f)
            elif "副本" in f or f.startswith(".backup_"):
                ignored.add(f)
            elif f == "translation.log":
                ignored.add(f)
            elif f.endswith(".db"):
                # 如果是完整打包模式且为 names_translation.db，则保留
                if full and f == "names_translation.db":
                    continue
                # 其余数据库（如 glossary_cache.db, llm_discovery.db 等）以及非完整模式下的 names_db 均忽略
                ignored.add(f)
        return ignored
    return _ignore


def main():
    parser = argparse.ArgumentParser(description="绿组翻译工具分发打包脚本")
    parser.add_argument(
        "--full",
        action="store_true",
        help="完整打包模式：包含 names_translation.db 等大文件（默认不包含）"
    )
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_suffix = "_full" if args.full else ""
    zip_name = f"{BASE_NAME}{mode_suffix}_{timestamp}.zip"
    zip_path = os.path.join(ROOT, zip_name)

    print(f"=== 开始分发打包 (模式: {'完整版 --full' if args.full else '标准轻量版 (不含人名库)'}) ===")

    # 1. Cleanup old dist folder
    if os.path.exists(DIST_PATH):
        print("Cleaning old distribution folder...")
        shutil.rmtree(DIST_PATH, ignore_errors=True)

    # 2. Create dist folder
    os.makedirs(DIST_PATH, exist_ok=True)

    # 3. Copy components with ignore patterns
    ignore_filter = make_ignore_filter(full=args.full)
    print("Preparing distribution files...")
    for item in ITEMS:
        src = os.path.join(ROOT, item)
        dst = os.path.join(DIST_PATH, item)
        if os.path.exists(src):
            if os.path.isdir(src):
                shutil.copytree(src, dst, ignore=ignore_filter, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            print(f"  Copied: {item}")
        else:
            print(f"  [WARNING] Not found: {item}")

    # 复制 bat 文件
    if os.path.exists(BAT_SOURCE):
        shutil.copy2(BAT_SOURCE, os.path.join(DIST_PATH, BAT_FILE))
        print(f"  Copied: {BAT_FILE}")

    # 4. Handle presets.json
    subtitle_dir = os.path.join(DIST_PATH, "subtitle")
    presets_json = os.path.join(subtitle_dir, "presets.json")
    presets_copy = os.path.join(subtitle_dir, "presets - 副本.json")
    presets_example = os.path.join(subtitle_dir, "presets.json.example")

    for f in [presets_json, presets_copy, presets_example]:
        if os.path.exists(f):
            os.remove(f)

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
    with open(presets_example, "w", encoding="utf-8") as f:
        json.dump(single_preset, f, indent=4, ensure_ascii=False)
    print("  Created new presets.json and presets.json.example (single glm-5.2 preset)")

    # 5. Create ZIP
    if os.path.exists(zip_path):
        os.remove(zip_path)

    print(f"\nCreating ZIP: {zip_name} ...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root_dir, dirs, files in os.walk(DIST_PATH):
            for file in files:
                file_path = os.path.join(root_dir, file)
                arcname = os.path.relpath(file_path, DIST_PATH)
                zf.write(file_path, arcname)

    # 6. Cleanup temp folder
    print("Removing temporary folder...")
    shutil.rmtree(DIST_PATH, ignore_errors=True)

    print(f"\n[OK] 打包完成！Zip 文件: {zip_path}")


if __name__ == "__main__":
    main()
