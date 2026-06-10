# -*- coding: utf-8 -*-
import os
import sys
import argparse
import asyncio
import hashlib
import logging
from typing import List

# 添加当前目录到路径，确保可以导入核心模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.config import TranslationConfig, TranslationArgs, CACHE_DIR
from core.cache_utils import get_cache_path
from translate_srt_llm import run_translation

# 动态加载子模块
import importlib.util

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# 获取子工具路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACT_TOOL_PATH = os.path.join(BASE_DIR, "pre-process", "01-extract_srt.py")
ASS_TOOL_PATH = os.path.join(BASE_DIR, "post-process", "02-post_process_ass.py")

extract_tool = load_module("extract_tool", EXTRACT_TOOL_PATH)
ass_tool = load_module("ass_tool", ASS_TOOL_PATH)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MainWorkflow")

async def main():
    parser = argparse.ArgumentParser(description="字幕翻译一站式工具 - 从 MKV 到最终版字幕")
    
    # 输入输出控制
    parser.add_argument("-i", "--input", required=True, help="输入文件 (MKV 或 SRT)")
    parser.add_argument("-o", "--output", help="最终输出文件名 (可选)")
    parser.add_argument("-f", "--format", choices=["srt", "ass"], default="ass", help="最终输出格式 (默认 ass)")
    
    # 常用覆盖参数
    parser.add_argument("--to-english", action="store_true", help="开启中译英模式")
    parser.add_argument("--bilingual", action="store_true", default=True, help="是否生成双语字幕 (默认开启)")
    parser.add_argument("--no-bilingual", action="store_false", dest="bilingual", help="仅保留中文字幕")
    parser.add_argument("--model", type=str, help="覆盖 presets.json 中的模型名称")
    parser.add_argument("--batch-size", type=int, help="覆盖 presets.json 中的批次大小")
    parser.add_argument("--enable-names-db", action="store_true", help="启用人名数据库 (默认禁用)")
    parser.add_argument("--enable-annotations", action="store_true", help="启用注释生成 (默认禁用)")
    
    args = parser.parse_args()

    target_lang = "en" if args.to_english else "zh"
    input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
        logger.error(f"找不到输入文件: {input_path}")
        return

    final_format = args.format
    if args.output:
        if args.output.lower().endswith(".srt"): final_format = "srt"
        elif args.output.lower().endswith(".ass"): final_format = "ass"
    
    final_output = args.output if args.output else os.path.splitext(input_path)[0] + f".{final_format}"

    # 1. 预处理
    working_srt = None
    if input_path.lower().endswith(".mkv"):
        logger.info(f"检测到 MKV 文件，正在提取字幕...")
        srt_files = extract_tool.extract_subtitles(input_path)
        if srt_files: working_srt = srt_files[0]
        else:
            logger.error("MKV 字幕提取失败。")
            return
    elif input_path.lower().endswith(".srt"):
        working_srt = input_path
    elif input_path.lower().endswith(".ass"):
        logger.info("检测到 ASS 文件，正在转换为 SRT 以进行翻译...")
        working_srt = extract_tool.convert_ass_file_to_srt(input_path)

    # 2. 翻译
    if final_format == "ass":
        translated_srt = get_cache_path(
            input_file=working_srt,
            purpose="translated",
            target_lang=target_lang,
            model_name=args.model or "",
            extension=".srt"
        )
    else:
        translated_srt = final_output

    trans_args = TranslationArgs(
        input_file=working_srt,
        output_file=translated_srt,
        bilingual=args.bilingual,
        model_name=args.model,
        batch_size=args.batch_size,
        target_lang=target_lang
    )
    if args.enable_names_db:
        trans_args.enable_names_db = True
    if args.enable_annotations:
        trans_args.enable_annotations = True

    await run_translation(trans_args)

    # 3. 后处理
    if final_format == "ass":
        logger.info(f"正在生成 ASS 格式: {final_output}")
        head_path = os.path.join(BASE_DIR, "post-process", "asshead.txt")
        if not os.path.exists(head_path): head_path = "asshead.txt"
        
        # 如果启用了注释，使用带注释的 SRT
        source_srt = translated_srt
        if args.enable_annotations:
            annotation_srt = translated_srt.replace('.srt', '_with_annotations.srt')
            if os.path.exists(annotation_srt):
                logger.info(f"使用带注释的字幕文件: {annotation_srt}")
                source_srt = annotation_srt
        
        ass_tool.srt_to_ass(source_srt, head_path, final_output)
        logger.info(f"✅ 完成！最终字幕文件已生成: {os.path.abspath(final_output)}")
    else:
        logger.info(f"✅ 完成！最终字幕文件已生成: {os.path.abspath(final_output)}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(main())
    else:
        # 如果没有参数，启动 GUI
        from gui_app import run_gui
        run_gui()
