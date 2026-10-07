# -*- coding: utf-8 -*-
from typing import List, Optional
from .extract_tool import extract_subtitles, convert_ass_file_to_srt
from .ass_writer import srt_to_ass


def extract_subtitles_from_mkv(mkv_path: str) -> List[str]:
    """从 MKV 文件提取字幕"""
    return extract_subtitles(mkv_path)


def convert_ass_to_srt(ass_path: str) -> Optional[str]:
    """将 ASS 字幕转换为 SRT"""
    return convert_ass_file_to_srt(ass_path)


def generate_ass_from_srt(srt_path: str, ass_output_path: str, head_path: Optional[str] = None) -> bool:
    """将 SRT 字幕生成 ASS 格式"""
    return srt_to_ass(srt_path, head_path=head_path, output_path=ass_output_path)
