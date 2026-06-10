# -*- coding: utf-8 -*-
import asyncio
import logging
from typing import List, Dict, OrderedDict
from collections import OrderedDict as ODict

from .llm_client import call_llm, clean_and_extract_json
from .prompts import load_prompt
from .cache_utils import canonical_json

logger = logging.getLogger(__name__)

async def extract_annotations_batch(
    config, 
    blocks: List[Dict],
    genre: str = "未知"
) -> List[Dict]:
    """
    对一批字幕块提取需要注释的术语。
    
    Args:
        blocks: [{"index": 1, "original": "...", "polished": "..."}]
        genre: 影片类型
    
    Returns:
        [{"subtitle_id": 15, "term": "LAMMA", "explanation": "..."}]
    """
    prompt_template = load_prompt("annotation_extract")
    
    input_data = [
        {
            "id": int(b['index']),
            "original": b['original'],
            "translation": b['polished']
        }
        for b in blocks
    ]
    
    messages = [{
        "role": "user",
        "content": prompt_template.format(
            genre=genre,
            json_input=canonical_json(input_data)
        )
    }]
    
    tools = [{
        "type": "function",
        "function": {
            "name": "submit_annotations",
            "parameters": {
                "type": "object",
                "properties": {
                    "annotations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "subtitle_id": {"type": "integer"},
                                "term": {"type": "string"},
                                "explanation": {"type": "string"}
                            },
                            "required": ["subtitle_id", "term", "explanation"]
                        }
                    }
                },
                "required": ["annotations"]
            }
        }
    }]
    
    raw = await call_llm(
        config, 
        messages, 
        temperature=0.3,
        tools=tools,
        response_format={"type": "json_object"}
    )
    
    data = clean_and_extract_json(raw)
    
    if isinstance(data, dict) and "annotations" in data:
        return data["annotations"]
    elif isinstance(data, list):
        return data
    else:
        logger.warning(f"注释提取返回格式异常: {type(data)}")
        return []


async def generate_annotations_for_subtitle(
    config,
    translated_blocks: List[Dict],
    genre: str = "未知",
    batch_size: int = 150
) -> Dict[int, str]:
    """
    全文扫描生成注释。
    
    Args:
        translated_blocks: 已翻译的字幕块列表
        genre: 影片类型
        batch_size: 每批扫描的字幕数量
    
    Returns:
        {subtitle_id: 注释文本} 的字典
    """
    print(f"\n=== 开始全文注释扫描 (共 {len(translated_blocks)} 条字幕) ===")
    
    all_annotations = []
    
    # 分批扫描
    for i in range(0, len(translated_blocks), batch_size):
        batch = translated_blocks[i:i+batch_size]
        print(f"  扫描批次 {i//batch_size + 1}: ID {batch[0]['index']}-{batch[-1]['index']}")
        
        try:
            batch_annotations = await extract_annotations_batch(config, batch, genre)
            all_annotations.extend(batch_annotations)
        except Exception as e:
            logger.error(f"批次 {i//batch_size + 1} 注释提取失败: {e}")
            continue
        
        await asyncio.sleep(0.5)
    
    print(f"  ✅ 共识别 {len(all_annotations)} 个潜在注释点")
    
    # 全局去重：同一术语只保留首次出现
    term_first_occurrence = ODict()
    
    for anno in all_annotations:
        term = anno.get('term', '').strip()
        subtitle_id = anno.get('subtitle_id')
        explanation = anno.get('explanation', '').strip()
        
        if not term or not explanation:
            continue
        
        # 规范化术语（用于去重）
        term_normalized = term.lower()
        
        if term_normalized not in term_first_occurrence:
            term_first_occurrence[term_normalized] = {
                'subtitle_id': subtitle_id,
                'term': term,
                'explanation': explanation
            }
    
    print(f"  🔍 去重后保留 {len(term_first_occurrence)} 个注释")
    
    # 构建 ID -> 注释文本 的映射
    id_to_annotation = {}
    
    for info in term_first_occurrence.values():
        subtitle_id = info['subtitle_id']
        term = info['term']
        explanation = info['explanation']
        
        # 格式：term explanation（如果 explanation 不包含 term）
        if term.lower() not in explanation.lower():
            annotation_text = f"{term} {explanation}"
        else:
            annotation_text = explanation
        
        id_to_annotation[subtitle_id] = annotation_text
    
    return id_to_annotation
