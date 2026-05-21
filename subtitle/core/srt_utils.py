# -*- coding: utf-8 -*- 
import logging
import re

logger = logging.getLogger(__name__)

def clean_content(content: str) -> str:
    """
    预处理字幕内容：移除形如 [Music], [Applause] 等标签，并清理多余空行。
    """
    # 匹配方括号或圆括号内的音乐、掌声等标签，如 [Music], [Applause], (Laughter)
    # 同时也处理一些常见的无意义标签
    patterns = [
        r'\[Music\]', r'\[Applause\]', r'\[Laughter\]', r'\[Silence\]',
        r'\(Music\)', r'\(Applause\)', r'\(Laughter\)', r'\(Silence\)',
        r'\[.*?\]', # 匹配任何方括号内的内容（谨慎使用，但通常字幕中这种都是非语言信息）
    ]
    
    cleaned = content
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # 移除空行并重新拼接
    lines = [line.strip() for line in cleaned.split('\n') if line.strip()]
    return '\n'.join(lines)

def format_srt_block(index: int, timestamp: str, content: str) -> str:
    """
    统一格式化单个 SRT 字幕块
    """
    return f"{index}\n{timestamp}\n{content}\n\n"

def parse_srt(file_path):
    """
    解析 SRT 文件，修复 BOM 导致第一行丢失的问题，并进行内容预处理
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # 关键修复：移除文件头的 BOM 字符
            content = content.lstrip('﻿')
    except FileNotFoundError:
        print(f"错误：找不到文件 {file_path}")
        return []

    content = content.replace('\r\n', '\n').replace('\r', '\n')
    blocks = content.split('\n\n')
    parsed_blocks = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split('\n')
        # SRT 格式至少需要 2 行：ID, 时间轴, 字幕内容(时间轴和内容可能为空)
        if len(lines) < 2:
            continue

        index = lines[0].strip()
        timestamp = lines[1].strip()
        text_content = "\n".join(lines[2:]).strip()

        # 简单的格式检查
        if not (index.isdigit() or '-->' in timestamp):
            continue
            
        # 预处理内容
        text_content = clean_content(text_content)
            
        # 丢弃内容为空的字幕块，防止 LLM 产生幻觉
        if not text_content:
            logger.warning(f"丢弃空字幕块 ID {index} (预处理后内容为空)")
            continue

        parsed_blocks.append({
            'index': index,
            'timestamp': timestamp,
            'content': text_content
        })

    return parsed_blocks
