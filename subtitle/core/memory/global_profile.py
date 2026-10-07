# -*- coding: utf-8 -*-
from typing import List, Dict

from core.llm_client import call_llm, clean_and_extract_json
from core.cache_utils import load_json_file, save_json_file, canonical_json, get_cache_path
from core.prompts import load_prompt


# @lat: [[core-memory#Key Concepts#全局画像（Global Profile）]]
def sample_blocks_for_global_profile(blocks: List[Dict]) -> List[Dict]:
    """
    固定采样策略，避免每次 Global Discovery 输入变化。
    取开头 15%、中间 15%、结尾 15%。
    """
    n = len(blocks)
    if n <= 120:
        return blocks

    ranges = [
        (0, int(n * 0.15)),
        (int(n * 0.425), int(n * 0.575)),
        (int(n * 0.85), n),
    ]

    sampled = []
    seen = set()

    for start, end in ranges:
        for b in blocks[start:end]:
            idx = b.get("index")
            if idx not in seen:
                sampled.append(b)
                seen.add(idx)

    return sampled


def compact_blocks_for_prompt(blocks: List[Dict], max_chars: int = 12000) -> str:
    lines = []
    total = 0

    for b in blocks:
        line = f'{b["index"]}: {b["content"]}'
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line)

    return "\n".join(lines)


def default_global_profile(target_lang: str) -> Dict:
    return {
        "characters": [],
        "genre": [],
        "relationships": [],
        "setting": {
            "location": "",
            "time": "",
            "world_type": ""
        },
        "tone": [],
        "translation_style": {
            "avoid": ["机器直译腔", "过度书面语"],
            "style": "影视字幕",
            "target_lang": target_lang
        }
    }


def sanitize_global_profile(profile: Dict) -> Dict:
    """
    清洗 LLM 返回的画像数据，丢弃不符合 schema 的脏元素。
    针对 LLM 把 schema 键名当值混入对象数组的情况（如 relationships 里混入 "characters"）。
    """
    if not isinstance(profile, dict):
        return profile

    for key in ("characters", "relationships"):
        value = profile.get(key)
        if isinstance(value, list):
            profile[key] = [v for v in value if isinstance(v, dict)]
        else:
            profile[key] = []

    return profile


# @lat: [[core-memory#Key Concepts#全局画像（Global Profile）]]
def normalize_global_profile(profile: Dict) -> Dict:
    """对画像进行深度规范化，确保数组顺序稳定，最大化缓存命中"""
    if not isinstance(profile, dict):
        return profile
    
    for key in ["genre", "tone"]:
        if key in profile and isinstance(profile[key], list):
            profile[key] = sorted([str(x) for x in profile[key]])
            
    if "characters" in profile and isinstance(profile["characters"], list):
        profile["characters"] = sorted(
            profile["characters"],
            key=lambda x: canonical_json(x)
        )
        for char in profile["characters"]:
            if isinstance(char.get("names"), list):
                char["names"] = sorted([str(n) for n in char["names"]])
            if isinstance(char.get("speech_style"), list):
                char["speech_style"] = sorted([str(s) for s in char["speech_style"]])
                
    if "relationships" in profile and isinstance(profile["relationships"], list):
        profile["relationships"] = sorted(
            profile["relationships"],
            key=lambda x: canonical_json(x)
        )
        
    return profile


# @lat: [[core-memory#Key Concepts#全局画像（Global Profile）]]
async def build_global_profile(config, blocks: List[Dict]) -> Dict:
    sampled = sample_blocks_for_global_profile(blocks)
    content = compact_blocks_for_prompt(sampled)

    prompt_template = load_prompt("global_memory")
    prompt = prompt_template.format(
        target_lang=config.target_lang,
        content=content
    )

    messages = [{"role": "user", "content": prompt}]

    raw = await call_llm(
        config,
        messages,
        temperature=0.0,
        response_format={"type": "json_object"}
    )

    data = clean_and_extract_json(raw)

    if not isinstance(data, dict):
        return default_global_profile(config.target_lang)

    base = default_global_profile(config.target_lang)
    base.update(data)

    base = sanitize_global_profile(base)
    return base


# @lat: [[core-memory#Key Concepts#全局画像（Global Profile）]]
async def load_or_build_global_profile(config, blocks: List[Dict], input_file: str) -> Dict:
    path = get_cache_path(input_file, "global_profile", config.target_lang)

    cached = load_json_file(path)
    if isinstance(cached, dict) and cached:
        cached = sanitize_global_profile(cached)
        return cached

    profile = await build_global_profile(config, blocks)
    profile = sanitize_global_profile(profile)
    profile = normalize_global_profile(profile)
    save_json_file(path, profile, pretty=True)
    return profile


# @lat: [[core-memory#Key Concepts#全局画像（Global Profile）]]
def compact_global_profile(profile: Dict, scene_participants: List[str] = None) -> Dict:
    """
    上下文感知的画像压缩逻辑。
    优先保留当前场景相关的角色，压缩不相关角色的信息。
    """
    if not isinstance(profile, dict):
        return {}

    all_chars = profile.get("characters", [])
    
    if not scene_participants:
        important_chars = all_chars[:5]
    else:
        parts_set = {p.lower() for p in scene_participants}
        important_chars = []
        other_chars = []
        
        for char in all_chars:
            is_relevant = False
            char_id = char.get("id", "").lower()
            if char_id in parts_set:
                is_relevant = True
            else:
                for name in char.get("names", []):
                    if name.lower() in parts_set:
                        is_relevant = True
                        break
            
            if is_relevant:
                important_chars.append(char)
            else:
                other_chars.append(char)
        
        if len(important_chars) < 3:
            for c in other_chars:
                if c not in important_chars:
                    important_chars.append(c)
                if len(important_chars) >= 3:
                    break

    return {
        "genre": profile.get("genre", []),
        "tone": profile.get("tone", []),
        "setting": profile.get("setting", {}),
        "translation_style": profile.get("translation_style", {}),
        "relevant_characters": important_chars
    }


def global_profile_text(profile: Dict, scene_participants: List[str] = None) -> str:
    """生成压缩后的规范化文本"""
    compact = compact_global_profile(profile, scene_participants)
    compact = normalize_global_profile(compact)
    return canonical_json(compact)
