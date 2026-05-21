import subprocess
import json
import os
import shutil
import argparse
import re
import sys

# --------------------------------------------------------------------------- 
# Part 1: 字幕格式转换逻辑 (移植自 02-subtitle_converter.py)
# --------------------------------------------------------------------------- 

def ass_time_to_seconds(ass_time):
    """将 ASS 时间格式 (h:mm:ss.cs) 转换为秒数"""
    try:
        parts = ass_time.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_parts = parts[2].split('.')
        seconds = int(seconds_parts[0])
        cs = int(seconds_parts[1])
        return hours * 3600 + minutes * 60 + seconds + cs / 100.0
    except (ValueError, IndexError):
        return 0.0

def seconds_to_srt_time(seconds):
    """将秒数转换为 SRT 时间格式 (00:00:20,000)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000: # 处理进位
        ms = 0
        secs += 1
        # 此处不处理级联进位，因为 SRT 解析器通常能容忍 60 秒或 60 分的情况，且 round 极少触发 1000
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"

def ass_to_srt(ass_content):
    """将 ASS 内容字符串转换为 SRT 内容字符串"""
    srt_lines = []
    # 匹配 ASS 的 Dialogue 行
    # Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
    pattern = re.compile(r'Dialogue:\s*.*?,(\d+:\d{2}:\d{2}\.\d{2}),(\d+:\d{2}:\d{2}\.\d{2}),.*?,.*?,.*?,.*?,.*?,.*?,(.*)')
    
    counter = 1
    for line in ass_content.splitlines():
        match = pattern.match(line)
        if match:
            start_str, end_str, text = match.groups()
            
            # 转换时间
            start_seconds = ass_time_to_seconds(start_str)
            end_seconds = ass_time_to_seconds(end_str)
            
            # 移除 ASS 样式标签 {\...}
            text = re.sub(r'\{.*?\}', '', text)
            # 处理换行符 \N
            text = text.replace(r'\N', '\n').replace(r'\n', '\n')
            
            srt_lines.append(f"{counter}")
            srt_lines.append(f"{seconds_to_srt_time(start_seconds)} --> {seconds_to_srt_time(end_seconds)}")
            srt_lines.append(text.strip())
            srt_lines.append("") # 空行分隔
            
            counter += 1
            
    return "\n".join(srt_lines)

def convert_ass_file_to_srt(ass_path):
    """读取 ASS 文件并转换为 SRT 文件，返回新的 SRT 文件路径"""
    try:
        with open(ass_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(ass_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except:
            print(f"  [转换失败] 无法读取文件编码: {ass_path}")
            return None

    srt_content = ass_to_srt(content)
    
    srt_path = os.path.splitext(ass_path)[0] + ".srt"
    with open(srt_path, 'w', encoding='utf-8') as f:
        f.write(srt_content)
    
    return srt_path

# --------------------------------------------------------------------------- 
# Part 2: MKV 提取逻辑
# --------------------------------------------------------------------------- 

def extract_subtitles(mkv_path):
    """
    从 MKV 文件中提取字幕。如果提取出的是 ASS，自动转换为 SRT。
    """
    # 检查工具是否存在
    if not shutil.which('mkvmerge') or not shutil.which('mkvextract'):
        print("错误: 未找到 MKVToolNix 工具。请确保安装并将 mkvmerge/mkvextract 添加到系统环境变量 PATH 中。")
        return []

    if not os.path.exists(mkv_path):
        print(f"文件未找到: {mkv_path}")
        return []

    print(f"正在分析文件: {mkv_path} ...")

    # 1. 使用 mkvmerge -J 获取文件信息的 JSON 格式
    try:
        cmd_info = ['mkvmerge', '-J', mkv_path]
        result = subprocess.run(cmd_info, capture_output=True, text=True, encoding='utf-8')
        data = json.loads(result.stdout)
    except Exception as e:
        print(f"分析文件失败: {e}")
        return []

    # 2. 筛选字幕轨道
    tracks = data.get('tracks', [])
    subtitle_tracks = [t for t in tracks if t['type'] == 'subtitles']

    if not subtitle_tracks:
        print("该文件中未发现字幕轨道。")
        return []

    print(f"发现 {len(subtitle_tracks)} 条字幕轨道，准备提取...")

    # 3. 构建提取命令并记录待处理文件
    extract_cmd = ['mkvextract', 'tracks', mkv_path]
    base_name = os.path.splitext(mkv_path)[0]
    
    # 存储提取出的文件信息，以便后续转换
    extracted_files = [] # list of (track_id, file_path, is_ass)

    for track in subtitle_tracks:
        tid = track['id']
        codec = track['properties'].get('codec_id', '')
        lang = track['properties'].get('language', 'und')
        track_name = track['properties'].get('track_name', '')
        
        # 简化语言代码 (例如 chi -> zh, 但这里先保持原样)
        
        # 根据编码确定后缀名
        ext = '.srt'
        is_ass = False
        should_skip = False
        
        if 'S_TEXT/UTF8' in codec:
            ext = '.srt'
        elif 'S_TEXT/ASS' in codec or 'S_TEXT/SSA' in codec:
            ext = '.ass'
            is_ass = True
        elif 'S_HDMV/PGS' in codec:
            ext = '.sup'
        elif 'S_VOBSUB' in codec:
            ext = '.sub'
        elif 'S_DVBSUB' in codec:
             print(f" -> [跳过] 轨道 {tid} ({lang}): {codec} 是图形字幕 (DVB Subtitles)，无法转换为文本。")
             should_skip = True
        else:
             # 对于其他未知格式，尝试作为 SRT 提取可能会失败，为了安全起见可以选择跳过，或者尝试
             print(f" -> [警告] 轨道 {tid} ({lang}): {codec} 格式未知，尝试提取为 .srt 可能失败。")
             ext = '.srt'

        if should_skip:
            continue

        # 构建输出文件名: 原文件名_TrackID_语言.后缀
        out_filename = f"{base_name}_track{tid}_{lang}{ext}"
        
        extract_cmd.append(f"{tid}:{out_filename}")
        extracted_files.append({
            "path": out_filename,
            "is_ass": is_ass,
            "track_id": tid,
            "lang": lang
        })
        
        print(f" -> 轨道 {tid} ({lang}): {codec} 将提取为 {os.path.basename(out_filename)}")

    # 4. 执行提取
    try:
        subprocess.run(extract_cmd, check=True)
        print("\n提取成功！")
    except subprocess.CalledProcessError as e:
        print(f"\n提取过程中发生错误: {e}")
        return []

    # 5. 后处理：自动将 ASS 转换为 SRT
    final_srt_files = []
    
    print("正在检查是否需要格式转换...")
    for item in extracted_files:
        path = item["path"]
        
        if item["is_ass"]:
            print(f" -> 检测到 ASS 字幕: {os.path.basename(path)}，正在转换为 SRT...")
            new_srt_path = convert_ass_file_to_srt(path)
            if new_srt_path:
                print(f"    转换完成: {os.path.basename(new_srt_path)}")
                final_srt_files.append(new_srt_path)
                # 转换成功后删除原始 ASS 文件
                try:
                    os.remove(path)
                    print(f"    已清理原始 ASS 文件: {os.path.basename(path)}")
                except Exception as e:
                    print(f"    清理文件失败: {e}")
            else:
                print(f"    转换失败，保留原文件。 ולא נשמר קובץ המקור.")
        elif path.lower().endswith('.srt'):
            final_srt_files.append(path)
    
    print("\n所有可用的 SRT 字幕文件:")
    for f in final_srt_files:
        print(f" - {f}")
        
    return final_srt_files

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从 MKV 提取字幕并自动转换为 SRT 格式")
    parser.add_argument("input_file", nargs='?', help="输入的 MKV 视频文件路径")
    
    args = parser.parse_args()
    
    if args.input_file:
        extract_subtitles(args.input_file)
    else:
        # 如果没有参数，尝试交互式输入或者查找当前目录下的 mkv
        # 这里为了 CLI 友好，如果没有参数就打印帮助
        parser.print_help()
        
        # 简单的自动查找逻辑（可选）
        print("\n[提示] 未指定文件。查找当前目录下的 MKV 文件...")
        mkvs = [f for f in os.listdir('.') if f.lower().endswith('.mkv')]
        if len(mkvs) == 1:
            print(f"找到一个文件: {mkvs[0]}")
            extract_subtitles(mkvs[0])
        elif len(mkvs) > 1:
            print("找到多个 MKV 文件，请指定一个文件路径运行。")
