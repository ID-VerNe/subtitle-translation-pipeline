# -*- coding: utf-8 -*-
import os
import sys
import argparse

# 确保 subtitle 目录在 sys.path 中
_SUBTITLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SUBTITLE_DIR not in sys.path:
    sys.path.insert(0, _SUBTITLE_DIR)

from media.ass_writer import (
    parse_srt,
    srt_time_to_ass,
    clean_single_line,
    split_bilingual,
    process_block_content,
    srt_to_ass
)


def main():
    parser = argparse.ArgumentParser(description="Post-process: 将 SRT 转换为固定格式的双语 ASS 字幕 (支持自动中英分行)")
    parser.add_argument("srt_file", help="输入的 SRT 字幕文件路径")
    parser.add_argument("--head", "-t", default=None, help="ASS 头部模板文件路径 (默认使用同目录下的 asshead.txt)")
    parser.add_argument("--output", "-o", default=None, help="输出的 ASS 文件路径 (默认同名)")
    
    args = parser.parse_args()
    
    if args.head:
        head_path = args.head
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        head_path = os.path.join(script_dir, "asshead.txt")
    
    srt_to_ass(args.srt_file, head_path, args.output)


if __name__ == "__main__":
    main()