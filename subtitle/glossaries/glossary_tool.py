import os
import re
import glob

def clean_ass_text(text):

    # 去除 ASS 标签 { ... }
    text = re.sub(r'\{.*?\}', '', text)
    # 替换换行符
    text = text.replace(r'\N', ' ').replace(r'\n', ' ')
    return text.strip()

def is_contains_chinese(text):
    """判断文本是否包含中文字符"""
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            return True
    return False

def parse_ass(file_path):
    """
    解析 ASS 文件，返回 [(en_line, cn_line), ...]
    策略：根据 'Start Time' 对齐不同层级的字幕
    """
    with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
        lines = f.readlines()

    events_start = False
    format_indices = {}
    time_groups = {}; # Key: Start_Time, Value: { 'cn': [], 'en': [] }

    # 1. 读取并分组
    for line in lines:
        line = line.strip()
        if line.startswith('[Events]'):
            events_start = True
            continue
        
        if not events_start:
            continue

        if line.startswith('Format:'):
            # 解析 Format 行，获取字段位置
            parts = [p.strip() for p in line[7:].split(',')]
            format_indices = {name: i for i, name in enumerate(parts)}
            continue

        if line.startswith('Dialogue:'):
            # 这是一个非常简化的 CSV 解析，因为 Text 字段可能包含逗号
            # ASS 的格式通常是前几个字段固定，最后一个字段是 Text
            # 我们假设 Text 是第 9 个字段 (下标 9)
            
            # 找到 Text 之前的逗号数量
            text_idx = format_indices.get('Text', 9)
            parts = line[9:].split(',', text_idx) 
            
            if len(parts) <= text_idx:
                continue
                
            start_time = parts[format_indices.get('Start', 1)].strip()
            style = parts[format_indices.get('Style', 3)].strip()
            raw_text = parts[-1].strip()
            
            # 清洗文本
            clean_content = clean_ass_text(raw_text)
            if not clean_content:
                continue

            # 过滤策略：
            # 1. 忽略 "水印", "注释", "特效" 等 Style (可选，根据实际情况)
            # 这里简单通过判断是否包含汉字来区分中英文
            # 2. 忽略极短的数字或符号
            if len(clean_content) < 2 and not clean_content.isalnum():
                continue

            if start_time not in time_groups:
                time_groups[start_time] = {'cn': [], 'en': []}
            
            # 区分中英文
            if is_contains_chinese(clean_content):
                time_groups[start_time]['cn'].append(clean_content)
            else:
                time_groups[start_time]['en'].append(clean_content)

    # 2. 配对输出
    pairs = []
    # 按时间排序
    sorted_times = sorted(time_groups.keys())
    
    for t in sorted_times:
        group = time_groups[t]
        cns = group['cn']
        ens = group['en']
        
        # 只有当中英文都存在时才配对
        # 如果有多行（比如双语字幕被拆成了两行中文），则合并
        if cns and ens:
            cn_text = " ".join(cns)
            en_text = " ".join(ens)
            pairs.append((en_text, cn_text))
            
    return pairs

def parse_srt(file_path):
    """
    解析 SRT 文件 (简易版)
    假设 SRT 块内部是双语，或者是上下两个块时间轴一致
    这里为了通用，采用简单策略：
    读取所有文本块，判断是否包含中文，如果一段英文紧接着一段中文，则配对。
    """
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # 正则匹配 SRT 块
    # 格式: 序号 \n 时间轴 \n 文本
    blocks = re.split(r'\n\s*\n', content.strip())
    
    parsed_lines = []
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3: 
            continue
            
        # 抛弃序号和时间轴，只保留文本行
        text_lines = lines[2:]
        full_text = " ".join(text_lines)
        
        # 尝试在单块内分割双语 (常见的字幕格式：一行英文一行中文)
        # 如果包含中文和英文，尝试按行分割
        if is_contains_chinese(full_text):
            eng_part = []
            chn_part = []
            for tl in text_lines:
                # 简单去除一些类似 HTML 的标签 <i>...</i>
                tl = re.sub(r'<.*?>', '', tl).strip()
                if not tl: continue
                
                if is_contains_chinese(tl):
                    chn_part.append(tl)
                else:
                    eng_part.append(tl)
            
            if eng_part and chn_part:
                parsed_lines.append((" ".join(eng_part), " ".join(chn_part)))
    
    return parsed_lines

def main():
    # 获取脚本所在目录
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 递归获取当前目录及子目录下所有的 .ass 和 .srt
    all_files = []
    for ext in ['*.ass', '*.srt']:
        # 使用 ** 配合 recursive=True 实现递归搜索
        pattern = os.path.join(base_dir, '**', ext)
        all_files.extend(glob.glob(pattern, recursive=True))
    
    print(f"找到 {len(all_files)} 个字幕文件待处理...")

    for file_path in all_files:
        file_name = os.path.basename(file_path)
        # 将 .txt 生成在原文件所在目录下，避免同名文件在不同子目录时发生冲突
        output_path = file_path + ".txt"
        
        print(f"正在处理: {file_path} ...")
        
        pairs = []
        if file_path.lower().endswith('.ass'):
            pairs = parse_ass(file_path)
        elif file_path.lower().endswith('.srt'):
            pairs = parse_srt(file_path)
            
        if not pairs:
            print(f"  ⚠️  未提取到有效双语对: {file_name}")
            continue
            
        with open(output_path, 'w', encoding='utf-8') as f:
            for en, cn in pairs:
                f.write(f"{en}\n{cn}\n")
        
        print(f"  ✅ 已生成语料: {os.path.basename(output_path)} (共 {len(pairs)} 对)")

if __name__ == "__main__":
    main()