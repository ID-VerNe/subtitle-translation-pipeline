# -*- coding: utf-8 -*-
import subprocess
import json
import os
import shutil
import re
from typing import List, Optional


def ass_time_to_seconds(ass_time: str) -> float:
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


def seconds_to_srt_time(seconds: float) -> str:
    """将秒数转换为 SRT 时间格式 (00:00:20,000)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:
        ms = 0
        secs += 1
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def ass_to_srt(ass_content: str) -> str:
    """将 ASS 内容字符串转换为 SRT 内容字符串"""
    srt_lines = []
    pattern = re.compile(r'Dialogue:\s*.*?,(\d+:\d{2}:\d{2}\.\d{2}),(\d+:\d{2}:\d{2}\.\d{2}),.*?,.*?,.*?,.*?,.*?,.*?,(.*)')
    
    counter = 1
    for line in ass_content.splitlines():
        match = pattern.match(line)
        if match:
            start_str, end_str, text = match.groups()
            start_seconds = ass_time_to_seconds(start_str)
            end_seconds = ass_time_to_seconds(end_str)
            
            text = re.sub(r'\{.*?\}', '', text)
            text = text.replace(r'\N', '\n').replace(r'\n', '\n')
            
            srt_lines.append(f"{counter}")
            srt_lines.append(f"{seconds_to_srt_time(start_seconds)} --> {seconds_to_srt_time(end_seconds)}")
            srt_lines.append(text.strip())
            srt_lines.append("")
            
            counter += 1
            
    return "\n".join(srt_lines)


def convert_ass_file_to_srt(ass_path: str) -> Optional[str]:
    """读取 ASS 文件并转换为 SRT 文件，返回新的 SRT 文件路径"""
    try:
        with open(ass_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(ass_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except Exception:
            print(f"  [转换失败] 无法读取文件编码: {ass_path}")
            return None

    srt_content = ass_to_srt(content)
    srt_path = os.path.splitext(ass_path)[0] + ".srt"
    with open(srt_path, 'w', encoding='utf-8') as f:
        f.write(srt_content)
    
    return srt_path


def extract_subtitles(mkv_path: str) -> List[str]:
    """从 MKV 文件中提取字幕。如果提取出的是 ASS，自动转换为 SRT。"""
    if not shutil.which('mkvmerge') or not shutil.which('mkvextract'):
        print("错误: 未找到 MKVToolNix 工具。请确保安装并将 mkvmerge/mkvextract 添加到系统环境变量 PATH 中。")
        return []

    if not os.path.exists(mkv_path):
        print(f"文件未找到: {mkv_path}")
        return []

    print(f"正在分析文件: {mkv_path} ...")

    try:
        cmd_info = ['mkvmerge', '-J', mkv_path]
        result = subprocess.run(cmd_info, capture_output=True, text=True, encoding='utf-8')
        data = json.loads(result.stdout)
    except Exception as e:
        print(f"分析文件失败: {e}")
        return []

    tracks = data.get('tracks', [])
    subtitle_tracks = [t for t in tracks if t['type'] == 'subtitles']

    if not subtitle_tracks:
        print("该文件中未发现字幕轨道。")
        return []

    print(f"发现 {len(subtitle_tracks)} 条字幕轨道，准备提取...")

    extract_cmd = ['mkvextract', 'tracks', mkv_path]
    base_name = os.path.splitext(mkv_path)[0]
    extracted_files = []

    for track in subtitle_tracks:
        tid = track['id']
        codec = track['properties'].get('codec_id', '')
        lang = track['properties'].get('language', 'und')
        
        ext = '.srt'
        is_ass = False
        should_skip = False
        
        if 'S_TEXT/UTF8' in codec:
            ext = '.srt'
        elif 'S_TEXT/ASS' in codec or 'S_TEXT/SSA' in codec:
            ext = '.ass'
            is_ass = True
        elif 'S_HDMV/PGS' in codec or 'S_VOBSUB' in codec or 'S_DVBSUB' in codec:
            print(f" -> [跳过] 轨道 {tid} ({lang}): {codec} 是图形字幕，无法转换为文本。")
            should_skip = True
        else:
            print(f" -> [警告] 轨道 {tid} ({lang}): {codec} 格式未知，尝试提取为 .srt 可能失败。")
            ext = '.srt'

        if should_skip:
            continue

        out_filename = f"{base_name}_track{tid}_{lang}{ext}"
        extract_cmd.append(f"{tid}:{out_filename}")
        extracted_files.append({
            "path": out_filename,
            "is_ass": is_ass,
            "track_id": tid,
            "lang": lang
        })
        print(f" -> 轨道 {tid} ({lang}): {codec} 将提取为 {os.path.basename(out_filename)}")

    try:
        subprocess.run(extract_cmd, check=True)
        print("\n提取成功！")
    except subprocess.CalledProcessError as e:
        print(f"\n提取过程中发生错误: {e}")
        return []

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
                try:
                    os.remove(path)
                    print(f"    已清理原始 ASS 文件: {os.path.basename(path)}")
                except Exception as e:
                    print(f"    清理文件失败: {e}")
            else:
                print(f"    转换失败，保留原文件。")
        elif path.lower().endswith('.srt'):
            final_srt_files.append(path)
    
    return final_srt_files
