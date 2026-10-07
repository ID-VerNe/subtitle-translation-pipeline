# -*- coding: utf-8 -*-
from typing import List, Dict
from core.glossary_manager import glossary_manager
from core.cache_utils import canonical_json

# @lat: [[core-context#Key Concepts#上下文状态构建（build_recent_state）]]
def build_recent_state(final_blocks: List[Dict], max_lines: int = 100) -> Dict:
    if not final_blocks:
        return {}

    recent = final_blocks[-max_lines:]

    return {
        "last_ids": [int(b["index"]) for b in recent if str(b.get("index", "")).isdigit()],
        "pairs": [
            {"id": int(b["index"]), "original": b.get("original", ""), "polished": b.get("polished", "")}
            for b in recent
            if str(b.get("index", "")).isdigit()
        ],
        "usage": "Use for immediate pronoun resolution, sentence continuation, and terminology consistency (match how earlier lines rendered the same term)."
    }


# @lat: [[core-context#Key Concepts#核心术语构建（build_core_terms）]]
def build_core_terms(full_glossary: Dict[str, dict]) -> Dict[str, dict]:
    category_priority = {
        "Proper Name": 0,
        "Named Entities": 1,
        "Technical Term": 2,
        "Automotive": 3,
        "Cultural": 4,
        "Slang": 5,
        "Name": 6,
        "General": 7,
    }
    default_priority = 8

    def sort_key(item):
        src, info = item
        if not isinstance(info, dict):
            return default_priority, str(src).lower()
        cat = str(info.get("category", "")).strip()
        return category_priority.get(cat, default_priority), str(src).lower()

    items = sorted(full_glossary.items(), key=sort_key)
    return {src: info for src, info in items}


def build_glossary_payload(core_terms: Dict[str, dict], local_terms: Dict[str, dict]) -> str:
    payload = {
        "core_terms": core_terms,
        "local_terms": local_terms
    }
    return canonical_json(payload)


# @lat: [[core-context#Key Concepts#动态术语过滤（filter_relevant_glossary）]]
def filter_relevant_glossary(text_content: str, full_glossary: Dict[str, dict]) -> Dict[str, dict]:
    relevant = {}
    text_lower = text_content.lower()
    for src, info in full_glossary.items():
        if src.lower() in text_lower:
            relevant[src] = info
            
    found_names = glossary_manager.search_names(text_content, exclude_list=list(relevant.keys()))
    for name, trans in found_names.items():
        if name not in relevant:
            relevant[name] = {
                "source": name,
                "target": trans,
                "category": "Proper Name"
            }
            
    return relevant
