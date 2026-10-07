# -*- coding: utf-8 -*-
import os
import re
from typing import List, Dict, Tuple, Optional


def parse_srt(file_path: str) -> List[Dict]:
    """解析 SRT 文件，返回字幕块列表"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"错误：找不到文件 {file_path}")
        return []
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except Exception:
            print(f"错误：无法读取文件 {file_path}，请确保是 UTF-8 编码")
            return []

    content = content.replace('\r\n', '\n').replace('\r', '\n')
    blocks = content.split('\n\n')
    parsed_blocks = []
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split('\n')
        if len(lines) < 3:
            continue
        index = lines[0].strip()
        timestamp = lines[1].strip()
        text_lines = lines[2:]
        text_content = "\n".join(text_lines).strip()
        
        if not (index.isdigit() or '-->' in timestamp):
            continue
            
        parsed_blocks.append({
            'index': index,
            'timestamp': timestamp,
            'content': text_content
        })
    return parsed_blocks


def srt_time_to_ass(srt_time: str) -> str:
    """将 SRT 时间 (00:00:09,960) 转换为 ASS 时间 (0:00:09.96)"""
    t = srt_time.replace(',', '.')[:-1]
    if t.startswith('0'):
        t = t[1:]
    return t


def clean_single_line(text: str) -> str:
    """清洗单行文本：清除中文标点、多余空白及 ASS 换行符"""
    text = text.replace('，', ' ').replace('。', ' ')
    text = text.replace(r'\N', ' ').replace(r'\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def detect_language_style(text: str) -> str:
    """
    检测文本样式：
    - 如果文本主要是专有名词+解释（如：LAMMA（林肯郡农机制造商协会）...），判定为注释
    - 包含中文字符则判定为中文
    - 否则判定为英文
    """
    if re.match(r'^[A-Z][A-Za-z0-9\s\-\'\.]*[\(（]', text.strip()):
        return "注释"
    is_chinese = any('\u4e00' <= char <= '\u9fff' for char in text)
    return "中文" if is_chinese else "英文"


def split_bilingual(text: str) -> Tuple[Optional[str], Optional[str]]:
    """若单行文本包含英文+中文混合，尝试在交界处切分"""
    pattern = r'^([a-zA-Z0-9\s,\.\?!;:\'\"\-\(\)]+?)\s*([\u4e00-\u9fa5].*)$'
    match = re.match(pattern, text.strip())
    if match:
        en = match.group(1).strip()
        cn = match.group(2).strip()
        if len(en) > 1 and len(cn) > 0:
            return en, cn
    return None, None


def process_block_content(content: str) -> List[Tuple[str, str]]:
    """
    核心逻辑：将字幕块按行或语言类型进行智能分组解析，返回 [(text, style), ...] 列表。
    支持处理单行中英混排、双语分行以及注释行。
    """
    raw_lines = content.split('\n')
    expanded_lines = []
    for raw_line in raw_lines:
        cleaned = clean_single_line(raw_line)
        if not cleaned:
            continue
        if detect_language_style(cleaned) == "注释":
            expanded_lines.append(cleaned)
        elif bool(re.search(r'[\u4e00-\u9fa5]', cleaned)) and bool(re.search(r'[a-zA-Z]{2,}', cleaned)):
            en, cn = split_bilingual(cleaned)
            if en and cn:
                expanded_lines.append(en)
                expanded_lines.append(cn)
            else:
                expanded_lines.append(cleaned)
        else:
            expanded_lines.append(cleaned)

    groups = []
    current_text_parts = []
    current_style = None

    for line in expanded_lines:
        style = detect_language_style(line)
        if current_style is None:
            current_style = style
            current_text_parts.append(line)
        elif style == current_style:
            current_text_parts.append(line)
        else:
            combined = " ".join(current_text_parts)
            groups.append((combined, current_style))
            current_style = style
            current_text_parts = [line]

    if current_text_parts and current_style:
        combined = " ".join(current_text_parts)
        groups.append((combined, current_style))

    return groups


def srt_to_ass(srt_path: str, head_path: Optional[str] = None, output_path: Optional[str] = None) -> bool:
    """将 SRT 转换为固定格式的双语 ASS 字幕 (支持自动中英分行与注释识别)"""
    if not os.path.exists(srt_path):
        print(f"错误：找不到 SRT 文件 {srt_path}")
        return False

    if not output_path:
        output_path = os.path.splitext(srt_path)[0] + ".ass"
        
    if not head_path or not os.path.exists(head_path):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        head_path = os.path.join(base_dir, "post-process", "asshead.txt")
        if not os.path.exists(head_path):
            head_path = "asshead.txt"

    if not os.path.exists(head_path):
        print(f"错误：找不到 ASS 头部文件 {head_path}")
        return False

    try:
        with open(head_path, 'r', encoding='utf-8') as f:
            header_content = f.read()
    except Exception as e:
        print(f"错误：无法读取头部模板文件 {head_path}，原因: {e}")
        return False

    blocks = parse_srt(srt_path)
    if not blocks:
        print("未提取到有效字幕内容。")
        return False

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header_content)
        if not header_content.endswith('\n'):
            f.write('\n')
        if "[Events]" not in header_content:
            f.write("\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        
        count = 0
        for block in blocks:
            ts = block.get('timestamp', '')
            if '-->' not in ts:
                continue

            start_raw, end_raw = ts.split('-->')
            ass_start = srt_time_to_ass(start_raw.strip())
            ass_end = srt_time_to_ass(end_raw.strip())
            
            event_groups = process_block_content(block['content'])
            for text, style in event_groups:
                if style == "注释":
                    dialogue_line = f"Dialogue: 0,{ass_start},{ass_end},{style},,0,0,0,,{{\\be6}}{text}\n"
                else:
                    dialogue_line = f"Dialogue: 0,{ass_start},{ass_end},{style},,0,0,0,,{{\\be3}}{text}\n"
                f.write(dialogue_line)
                count += 1
            
    print(f"转换成功！生成文件: {output_path} (共生成 {count} 条 ASS 事件)")
    return True
