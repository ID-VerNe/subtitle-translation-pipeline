# -*- coding: utf-8 -*-
import os
import sys
import argparse

# 确保 subtitle 目录在 sys.path 中
_SUBTITLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SUBTITLE_DIR not in sys.path:
    sys.path.insert(0, _SUBTITLE_DIR)

from media.extract_tool import (
    ass_time_to_seconds,
    seconds_to_srt_time,
    ass_to_srt,
    convert_ass_file_to_srt,
    extract_subtitles
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从 MKV 提取字幕并自动转换为 SRT 格式")
    parser.add_argument("input_file", nargs='?', help="输入的 MKV 视频文件路径")
    
    args = parser.parse_args()
    
    if args.input_file:
        extract_subtitles(args.input_file)
    else:
        parser.print_help()
        print("\n[提示] 未指定文件。查找当前目录下的 MKV 文件...")
        mkvs = [f for f in os.listdir('.') if f.lower().endswith('.mkv')]
        if len(mkvs) == 1:
            print(f"找到一个文件: {mkvs[0]}")
            extract_subtitles(mkvs[0])
        elif len(mkvs) > 1:
            print("找到多个 MKV 文件，请指定一个文件路径运行。")
