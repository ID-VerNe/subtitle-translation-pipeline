# -*- coding: utf-8 -*-
import os
import importlib.util

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

EXTRACT_TOOL_PATH = os.path.join(BASE_DIR, "pre-process", "01-extract_srt.py")
ASS_TOOL_PATH = os.path.join(BASE_DIR, "post-process", "02-post_process_ass.py")

extract_tool = load_module("extract_tool", EXTRACT_TOOL_PATH)
ass_tool = load_module("ass_tool", ASS_TOOL_PATH)

# @lat: [[media-process#Key Concepts#媒体桥接（extractor.py）]]
def extract_subtitles_from_mkv(mkv_path):
    return extract_tool.extract_subtitles(mkv_path)

# @lat: [[media-process#Key Concepts#媒体桥接（extractor.py）]]
def convert_ass_to_srt(ass_path):
    return extract_tool.convert_ass_file_to_srt(ass_path)

def generate_ass_from_srt(srt_path, ass_output_path):
    head_path = os.path.join(BASE_DIR, "post-process", "asshead.txt")
    if not os.path.exists(head_path):
        head_path = "asshead.txt"
    ass_tool.srt_to_ass(srt_path, head_path, ass_output_path)
