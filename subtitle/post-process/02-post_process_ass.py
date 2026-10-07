import os
import argparse
import re

def parse_srt(file_path):
    """解析 SRT 文件，返回字幕块列表"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"错误：找不到文件 {file_path}")
        return []
    except UnicodeDecodeError:
        # 尝试其他编码
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except:
            print(f"错误：无法读取文件 {file_path}，请确保是 UTF-8 编码")
            return []

    # 统一换行符
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
        # 这里保留原始的行结构
        text_content = "\n".join(text_lines).strip()
        
        # 简单的格式检查
        if not (index.isdigit() or '-->' in timestamp):
            continue
            
        parsed_blocks.append({
            'index': index,
            'timestamp': timestamp,
            'content': text_content
        })
    return parsed_blocks

def srt_time_to_ass(srt_time):
    """
    将 SRT 时间 (00:00:09,960) 转换为 ASS 时间 (0:00:09.96)
    """
    t = srt_time.replace(',', '.')[:-1]
    if t.startswith('0'):
        t = t[1:]
    return t

def clean_single_line(text):
    """
    清洗单行文本：清除中文标点，ASS代码等
    """
    text = text.replace('，', ' ').replace('。', ' ')
    text = text.replace(r'\N', ' ')
    
    # 修复因为移除括号内容可能留下的双横杠
    text = re.sub(r'-\s*-+', '-', text)
    
    # 彻底移除原有的 ASS 标签 (例如 {\an8})，避免在后面被重复叠加或漏出
    text = re.sub(r'\{.*?\}', '', text)
    
    # 移除 ASS 标签后检查是否只剩下横杠，如果是，则返回空字符串
    if not text.strip('-— \t'):
        return ""
        
    return text.strip()

# @lat: [[media-process#Key Concepts#智能分行（process_block_content）]]
def detect_language_style(text):
    """
    简单的语言检测：
    - 包含中文字符则认为是中文
    - 否则是英文
    （注释识别由时间戳分组逻辑处理）
    """
    is_chinese = any('\u4e00' <= char <= '\u9fff' for char in text)
    return "中文" if is_chinese else "英文"

# @lat: [[media-process#Key Concepts#智能分行（process_block_content）]]
def process_block_content(content):
    """
    核心逻辑：将一个字幕块的内容按语言分组
    """
    lines = content.split('\n')
    groups = []
    
    current_text_parts = []
    current_style = None
    
    for line in lines:
        cleaned_line = clean_single_line(line)
        if not cleaned_line:
            continue
            
        style = detect_language_style(cleaned_line)
        
        if current_style is None:
            current_style = style
            current_text_parts.append(cleaned_line)
        elif style == current_style:
            current_text_parts.append(cleaned_line)
        else:
            combined_text = " ".join(current_text_parts)
            groups.append((combined_text, current_style))
            current_style = style
            current_text_parts = [cleaned_line]
    
    if current_text_parts and current_style:
        combined_text = " ".join(current_text_parts)
        groups.append((combined_text, current_style))
        
    return groups

# @lat: [[media-process#Key Concepts#ASS 生成（srt_to_ass）]]
def srt_to_ass(srt_path, ass_head_path, output_path=None):
    if not os.path.exists(srt_path):
        print(f"错误：找不到 SRT 文件 {srt_path}")
        return

    if not os.path.exists(ass_head_path):
        print(f"错误：找不到 ASS 头部文件 {ass_head_path}")
        return

    if output_path is None:
        output_path = os.path.splitext(srt_path)[0] + '.ass'
    
    # 1. 读取头部
    print(f"正在读取头部模板: {ass_head_path}")
    with open(ass_head_path, 'r', encoding='utf-8') as f:
        header_content = f.read()
        
    # 2. 解析 SRT
    print(f"正在解析 SRT: {srt_path}")
    blocks = parse_srt(srt_path)
    print(f"共找到 {len(blocks)} 条字幕块")
    
    # 按时间戳分组
    from collections import defaultdict
    timestamp_groups = defaultdict(list)
    for block in blocks:
        timestamp_groups[block['timestamp']].append(block)
    
    # 3. 生成 ASS
    print("正在进行智能分行转换...")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header_content)
        if not header_content.endswith('\n'):
            f.write('\n')
            
        count = 0
        for timestamp in sorted(timestamp_groups.keys()):
            group = timestamp_groups[timestamp]
            
            if '-->' not in timestamp:
                continue
                
            start_raw, end_raw = timestamp.split(' --> ')
            ass_start = srt_time_to_ass(start_raw.strip())
            ass_end = srt_time_to_ass(end_raw.strip())
            
            for idx, block in enumerate(group):
                event_groups = process_block_content(block['content'])
                
                for text, detected_style in event_groups:
                    # 按位置确定样式：第1个块英文，第2个块中文，第3个及以后注释
                    if idx == 0:
                        style = "英文"
                    elif idx == 1:
                        style = "中文"
                    else:
                        style = "注释"
                    
                    # 根据样式设置不同的特效代码
                    if style == "注释":
                        dialogue_line = f"Dialogue: 0,{ass_start},{ass_end},{style},,0,0,0,,{{\\be6}}{text}\n"
                    else:
                        dialogue_line = f"Dialogue: 0,{ass_start},{ass_end},{style},,0,0,0,,{{\\be3}}{text}\n"
                    f.write(dialogue_line)
                    count += 1
            
    print(f"转换成功！生成文件: {output_path} (共生成 {count} 条 ASS 事件)")

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