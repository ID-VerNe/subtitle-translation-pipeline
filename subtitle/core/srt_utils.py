# -*- coding: utf-8 -*- 
import logging
import re

logger = logging.getLogger(__name__)

# @lat: [[core-common#Key Concepts#SRT 工具（srt_utils.py）]]
def clean_content(content: str) -> str:
    """
    预处理字幕内容：
    1. 移除 (环境声音) 和 [环境声音] 提示词
    2. 移除 <color style> 等样式控件词
    """
    patterns = [
        r'\[.*?\]', # 匹配方括号内任意内容，如 [Upbeat music]
        r'\(.*?\)', # 匹配圆括号内任意内容，如 (Sighs)
        r'<.*?>',   # 匹配尖括号样式标签，如 <font color="#ffff">, <i>
        r'\{.*?\}', # 匹配大括号内的 ASS 标签，如 {\an8}
    ]
    
    cleaned = content
    for pattern in patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
    # 敏感词脱敏（防止触发大模型风控 400 拦截）
    # 替换规则：保留首尾字母，中间用 * 替换
    profanity_patterns = {
        r'\b(f)uck(ing|er|s)?\b': r'\1**k\2',
        r'\b(s)hit(ting|s)?\b': r'\1**t\2',
        r'\b(b)itch(es|ing)?\b': r'\1***h\2',
        r'\b(c)unt(s)?\b': r'\1**t\2',
        r'\b(n)igg(a|er|s)?\b': r'\1***\2',
        r'\b(w)hore(s)?\b': r'\1***e\2',
    }
    
    for pattern, replacement in profanity_patterns.items():
        # 保留原有大小写结构，re.IGNORECASE 会导致无法引用正确的捕获组大小写，所以直接原样替换
        # 但为了应对大写，我们额外加一层 ignorecase 匹配
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    
    # 合并因为删除标签留下的多个横杠 (例如 '- -')
    cleaned = re.sub(r'-\s*-+', '-', cleaned)

    # 清理并过滤残余废行
    valid_lines = []
    for line in cleaned.split('\n'):
        stripped = line.strip()
        if not stripped:
            continue
        
        # 移除 ASS 标签和 HTML 标签后检查是否只剩下横杠
        pure_text = re.sub(r'\{.*?\}|<.*?>', '', stripped)
        # 如果整行在去除横杠和空格后为空，说明是括号被清理后残留的对话横杠，需整行删除
        if not pure_text.strip('-— \t'):
            continue
        valid_lines.append(stripped)
        
    return '\n'.join(valid_lines)

# @lat: [[core-common#Key Concepts#SRT 工具（srt_utils.py）]]
def format_srt_block(index: int, timestamp: str, content: str) -> str:
    """
    统一格式化单个 SRT 字幕块
    """
    return f"{index}\n{timestamp}\n{content}\n\n"

# @lat: [[core-common#Key Concepts#SRT 工具（srt_utils.py）]]
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
