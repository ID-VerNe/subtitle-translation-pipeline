# -*- coding: utf-8 -*-
from typing import List, Dict

from core.cache_utils import canonical_json


# @lat: [[core-memory#Key Concepts#翻译策略（Translation Policy）]]
def normalize_translation_policy(policy: Dict) -> Dict:
    """规范化翻译策略中的数组顺序"""
    if not isinstance(policy, dict):
        return policy
        
    if "pronoun_rules" in policy and isinstance(policy["pronoun_rules"], list):
        policy["pronoun_rules"] = sorted(
            policy["pronoun_rules"],
            key=lambda x: canonical_json(x)
        )
        
    if "register_rules" in policy and isinstance(policy["register_rules"], list):
        policy["register_rules"] = sorted(
            policy["register_rules"],
            key=lambda x: canonical_json(x)
        )
        
    if "core_term_rules" in policy and isinstance(policy["core_term_rules"], list):
        policy["core_term_rules"] = sorted(
            policy["core_term_rules"],
            key=lambda x: str(x[0]) if isinstance(x, list) and x else ""
        )
        
    return policy


# @lat: [[core-memory#Key Concepts#翻译策略（Translation Policy）]]
def build_translation_policy(global_profile: Dict, glossary: Dict, target_lang: str, scene_participants: List[str] = None) -> Dict:
    """
    上下文感知的策略构建。
    """
    characters = global_profile.get("characters", [])
    relationships = global_profile.get("relationships", [])
    
    parts_set = {p.lower() for p in (scene_participants or [])}
    
    pronoun_rules = []
    for c in characters:
        names = c.get("names", [])
        if not names: continue
        
        char_id = c.get("id", "").lower()
        is_relevant = char_id in parts_set or any(n.lower() in parts_set for n in names)
        
        if not is_relevant and len(pronoun_rules) > 10:
            continue

        gender = c.get("gender", "")
        default_pronoun = ""
        if target_lang == "zh":
            if gender.lower() in ["female", "woman", "girl", "女", "女性"]:
                default_pronoun = "她"
            elif gender.lower() in ["male", "man", "boy", "男", "男性"]:
                default_pronoun = "他"

        pronoun_rules.append({
            "names": names,
            "default_pronoun": default_pronoun
        })

    register_rules = []
    for r in relationships:
        f, t = r.get("from", "").lower(), r.get("to", "").lower()
        if not scene_participants or f in parts_set or t in parts_set:
            register_rules.append({
                "from": r.get("from", ""),
                "to": r.get("to", ""),
                "relationship": r.get("type", ""),
                "register": r.get("register", "")
            })
    
    core_term_rules = []
    for src, info in glossary.items():
        target = info.get("target", str(info)) if isinstance(info, dict) else str(info)
        if target: core_term_rules.append([src, target])

    return {
        "pronoun_rules": pronoun_rules,
        "register_rules": register_rules,
        "style_rules": [
            "保持影视字幕口吻，自然、简洁、口语化",
            "不要合并、拆分或遗漏字幕 ID",
            "角色称谓、人称和语气必须前后一致",
            "避免机器直译腔",
            "Domain 优先于逐字：依据场景 domain 选词义，荒谬释义须按 domain 纠正，可修正源文本明显 ASR 错字",
            "禁止无依据音译：普通名词不得当专名音译（如 line/track 在铁路语境译线路/轨道，不译利涅/赛道）",
        ],
        "core_term_rules": core_term_rules
    }


# @lat: [[core-memory#Key Concepts#翻译策略（Translation Policy）]]
def policy_text(policy: Dict) -> str:
    policy = normalize_translation_policy(policy)
    return canonical_json(policy)
