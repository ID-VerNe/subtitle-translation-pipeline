# -*- coding: utf-8 -*-
import re
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# @lat: [[core-glossary#Key Concepts#术语清洗（sanitize_glossary）]]
def sanitize_term_entry(source: str, target: str) -> Optional[Tuple[str, str]]:
    """清洗单个术语，返回 (clean_source, clean_target) 或 None (若不合法)"""
    if not source or not target:
        return None
        
    s_clean = source.strip()
    s_lower = s_clean.lower()
    t_clean = str(target).strip()

    # (Hardcoded banned words and bad_markers filters removed. 
    # Now relying on Agentic prompt instructions in term_extract.prompt to prevent these.)
        
    # 3. 剥离 target 中的所有括号解释
    t_clean = re.sub(r'[\(（].*?[\)）]', '', t_clean).strip()
    
    # 4. 如果包含斜杠或顿号，选取最前面最干净的单选词
    if '/' in t_clean:
        t_clean = t_clean.split('/')[0].strip()
    if '、' in t_clean:
        t_clean = t_clean.split('、')[0].strip()
        
    if not t_clean or len(t_clean) > 30:
        return None
        
    return s_clean, t_clean

# @lat: [[core-glossary#Key Concepts#术语清洗（sanitize_glossary）]]
def sanitize_glossary(glossary: Dict[str, dict]) -> Dict[str, dict]:
    """对术语字典进行全量清洗和过滤"""
    cleaned = {}
    for src, info in glossary.items():
        if isinstance(info, dict):
            tgt = info.get("target") or info.get("target_term") or ""
            res = sanitize_term_entry(src, tgt)
            if res:
                c_src, c_tgt = res
                info_copy = info.copy()
                info_copy["source"] = c_src
                info_copy["target"] = c_tgt
                cleaned[c_src] = info_copy
        elif isinstance(info, str):
            res = sanitize_term_entry(src, info)
            if res:
                c_src, c_tgt = res
                cleaned[c_src] = {"source": c_src, "target": c_tgt, "category": "General"}
                
    return cleaned
