# -*- coding: utf-8 -*-
import os
import sys
import argparse
import asyncio
import hashlib
import logging
from typing import List

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# 添加当前目录到路径，确保可以导入核心模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.config import TranslationConfig, TranslationArgs, CACHE_DIR
from core.cache_utils import get_cache_path
from translate_srt_llm import run_translation

from media.extractor import (
    extract_subtitles_from_mkv,
    convert_ass_to_srt,
    generate_ass_from_srt
)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MainWorkflow")

# @lat: [[entries#Key Concepts#CLI 总控入口（main.py）]]
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
    parser.add_argument("--api-key", type=str, help="覆盖 presets.json 中的 API Key")
    parser.add_argument("--api-url", type=str, help="覆盖 presets.json 中的 API URL")
    
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
        srt_files = extract_subtitles_from_mkv(input_path)
        if srt_files: working_srt = srt_files[0]
        else:
            logger.error("MKV 字幕提取失败。")
            return
    elif input_path.lower().endswith(".srt"):
        working_srt = input_path
    elif input_path.lower().endswith(".ass"):
        logger.info("检测到 ASS 文件，正在转换为 SRT 以进行翻译...")
        working_srt = convert_ass_to_srt(input_path)

    # 2. 翻译
    if final_format == "ass":
        translated_srt = get_cache_path(
            input_file=working_srt,
            purpose="translated",
            target_lang=target_lang,
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
        target_lang=target_lang,
        api_key=args.api_key,
        api_url=args.api_url
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
        
        generate_ass_from_srt(source_srt, final_output, head_path=head_path)
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
