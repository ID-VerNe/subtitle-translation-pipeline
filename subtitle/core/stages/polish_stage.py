# -*- coding: utf-8 -*-
import re
from typing import List, Dict

from core.rescue_engine import ladder_rescue_engine

# @lat: [[core-stages#Key Concepts#后置清理（postprocess_translation）]]
def postprocess_translation(original: str, translation: str) -> str:
    """
    后处理：
    1. 移除不应存在的标点：逗号(，,)、句号(。.)、顿号(、)
    2. 保留：感叹号(!！)、问号(?？)、单双引号(' " ‘ ’ “ ”)、半省略号(…)、分号(;；)
    3. 转换：全省略号(……) -> 半省略号(…)
    """
    # 防御性编程：确保输入为字符串
    original = str(original) if original is not None else ""
    translation = str(translation) if translation is not None else ""
    
    translation = re.sub(r'\*?此处指[^\*]*\*?', '', translation)
    translation = re.sub(r'注[:：].*', '', translation)
    
    if not re.search(r'[\(\)（）]', original):
        cleaned = re.sub(r'[\(（].*?[\)）]', '', translation)
        cleaned = cleaned.strip()
        translation = cleaned or translation 
        
    # 标点符号规范化
    translation = translation.replace("……", "…")
    # 安全移除英文逗号和句号（避免破坏数字如 3.14 或 1,000）
    translation = re.sub(r'(?<!\d)[.,](?!\d)', ' ', translation)
    # 移除中文逗号、句号、顿号
    translation = re.sub(r'[，。、]', ' ', translation)
    
    # 清理多余空格
    translation = re.sub(r' +', ' ', translation)
    
    # 修复翻译中可能遗留的双横杠
    translation = re.sub(r'-\s*-+', '-', translation)
    
    # 移除大模型可能幻觉生成的 ASS 标签
    translation = re.sub(r'\{.*?\}', '', translation)
        
    return translation.strip()

# @lat: [[core-stages#Key Concepts#润色阶段（Polish Stage）]]
async def process_polish_stage(
    batch_blocks: List[Dict], 
    config, 
    literal_map: Dict[str, str], 
    core_glossary_text: str = "{}",
    local_glossary_text: str = "{}", 
    previous_context: str = "", 
    future_context: str = "",
    recent_state: str = "",
    global_profile: str = "{}",
    translation_policy: str = "{}",
    scene_guidance: str = "{}"
) -> List[Dict]:
    polished_list = await ladder_rescue_engine(
        batch_blocks, config, core_glossary_text, local_glossary_text, stage="polish",
        literal_map=literal_map,
        previous_context=recent_state or previous_context,
        future_context=future_context,
        global_profile=global_profile,
        translation_policy=translation_policy,
        scene_guidance=scene_guidance
    )
    polish_map = {str(item['id']): item.get('polished', '') for item in polished_list if 'id' in item}
    final_blocks = []
    for block in batch_blocks:
        idx = str(block['index'])
        final_text = polish_map.get(idx) or literal_map.get(idx) or block['content']
        
        final_text = postprocess_translation(block['content'], final_text)
        
        final_blocks.append({
            "index": block['index'], "timestamp": block['timestamp'],
            "original": block['content'], "polished": final_text,
            "literal": literal_map.get(idx, "")
        })
    return final_blocks
