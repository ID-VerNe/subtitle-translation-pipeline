# -*- coding: utf-8 -*-
import os
import asyncio
from typing import List, Dict

from .llm_client import call_llm, call_llm_batch, clean_and_extract_json
from .cache_utils import load_json_file, save_json_file, canonical_json
from .config import CACHE_DIR


GLOBAL_PROFILE_PROMPT_VERSION = "GLOBAL_PROFILE_V1"


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


def normalize_global_profile(profile: Dict) -> Dict:
    """对画像进行深度规范化，确保数组顺序稳定，最大化缓存命中"""
    if not isinstance(profile, dict):
        return profile
    
    # 1. 简单字符串数组排序
    for key in ["genre", "tone"]:
        if key in profile and isinstance(profile[key], list):
            profile[key] = sorted([str(x) for x in profile[key]])
            
    # 2. 对象数组排序：使用 canonical_json 作为排序键保证绝对确定性
    if "characters" in profile and isinstance(profile["characters"], list):
        profile["characters"] = sorted(
            profile["characters"],
            key=lambda x: canonical_json(x)
        )
        # 对 character 内部的 names 和 speech_style 也进行排序
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
        
    # core_term_rules 本身就是按 glossary key 排序构建的，这里再次加固
    if "core_term_rules" in policy and isinstance(policy["core_term_rules"], list):
        policy["core_term_rules"] = sorted(
            policy["core_term_rules"],
            key=lambda x: str(x[0]) if isinstance(x, list) and x else ""
        )
        
    return policy


def normalize_scene(scene: Dict) -> Dict:
    """规范化单个场景数据的数组顺序"""
    if not isinstance(scene, dict):
        return scene
        
    for key in ["participants", "tone", "domain", "translation_notes"]:
        if key in scene and isinstance(scene[key], list):
            scene[key] = sorted([str(x) for x in scene[key]])
            
    return scene


async def build_global_profile(config, blocks: List[Dict]) -> Dict:
    sampled = sample_blocks_for_global_profile(blocks)
    content = compact_blocks_for_prompt(sampled)

    prompt = f"""
你是字幕翻译项目的全局信息分析器。
请根据采样字幕，抽取对后续翻译有帮助的全局信息。

要求：
1. 只输出 JSON。
2. 不要写解释。
3. 字段必须稳定。
4. 如果信息无法判断，使用空字符串或空数组。
5. 重点关注角色、关系、性别、身份、说话风格、整体题材、整体语气。

输出 JSON schema：
{{
  "genre": [],
  "tone": [],
  "setting": {{
    "time": "",
    "location": "",
    "world_type": ""
  }},
  "characters": [
    {{
      "id": "char_xxx",
      "names": [],
      "gender": "",
      "role": "",
      "speech_style": [],
      "self_ref": ""
    }}
  ],
  "relationships": [
    {{
      "from": "char_xxx",
      "to": "char_yyy",
      "type": "",
      "register": ""
    }}
  ],
  "translation_style": {{
    "target_lang": "{config.target_lang}",
    "style": "影视字幕",
    "avoid": ["机器直译腔", "过度书面语"]
  }}
}}

字幕采样：
{content}
""".strip()

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

    return base


async def load_or_build_global_profile(config, blocks: List[Dict], cache_key: str) -> Dict:
    path = os.path.join(CACHE_DIR, f"global_profile_{cache_key}_{config.target_lang}.json")

    cached = load_json_file(path)
    if isinstance(cached, dict) and cached:
        return cached

    profile = await build_global_profile(config, blocks)
    profile = normalize_global_profile(profile)
    save_json_file(path, profile, pretty=True)
    return profile


def compact_global_profile(profile: Dict, scene_participants: List[str] = None) -> Dict:
    """
    上下文感知的画像压缩逻辑。
    优先保留当前场景相关的角色，压缩不相关角色的信息。
    """
    if not isinstance(profile, dict):
        return {}

    all_chars = profile.get("characters", [])
    
    # 如果没有指定参与者，默认保留前 5 个角色以维持基础认知
    if not scene_participants:
        important_chars = all_chars[:5]
    else:
        # 匹配逻辑：场景参与者列表与角色 ID 或 名字进行模糊匹配
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
        
        # 补齐策略：如果匹配到的角色太少，补充前几个主角
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
    compact = normalize_global_profile(compact) # 复用排序逻辑
    return canonical_json(compact)


def build_translation_policy(global_profile: Dict, glossary: Dict, target_lang: str, scene_participants: List[str] = None) -> Dict:
    """
    上下文感知的策略构建。
    """
    characters = global_profile.get("characters", [])
    relationships = global_profile.get("relationships", [])
    
    # 确定哪些角色需要详细规则
    parts_set = {p.lower() for p in (scene_participants or [])}
    
    pronoun_rules = []
    for c in characters:
        names = c.get("names", [])
        if not names: continue
        
        char_id = c.get("id", "").lower()
        is_relevant = char_id in parts_set or any(n.lower() in parts_set for n in names)
        
        # 如果当前场景不涉及该角色且角色列表已长，则跳过其代词规则
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
        # 只保留涉及当前场景角色的关系
        f, t = r.get("from", "").lower(), r.get("to", "").lower()
        if not scene_participants or f in parts_set or t in parts_set:
            register_rules.append({
                "from": r.get("from", ""),
                "to": r.get("to", ""),
                "relationship": r.get("type", ""),
                "register": r.get("register", "")
            })
    
    # 关系规则也限制长度
    register_rules = register_rules[:15]

    core_term_rules = []
    for src, info in glossary.items():
        target = info.get("target", str(info)) if isinstance(info, dict) else str(info)
        if target: core_term_rules.append([src, target])

    return {
        "pronoun_rules": pronoun_rules[:20],
        "register_rules": register_rules,
        "style_rules": [
            "保持影视字幕口吻，自然、简洁、口语化",
            "不要合并、拆分或遗漏字幕 ID",
            "角色称谓、人称和语气必须前后一致",
            "避免机器直译腔"
        ],
        "core_term_rules": core_term_rules[:60] # 核心术语也适当压缩
    }


def policy_text(policy: Dict) -> str:
    # 已经由 build_translation_policy 构建，这里只需规范化
    policy = normalize_translation_policy(policy)
    return canonical_json(policy)


def build_simple_scene_map(blocks: List[Dict], scene_size: int = 80) -> Dict:
    """
    第一版先不用 LLM，按固定 block 数切 scene。
    这样稳定、便宜、缓存友好。
    """
    scenes = []

    for i in range(0, len(blocks), scene_size):
        chunk = blocks[i:i + scene_size]
        if not chunk:
            continue

        start_id = int(chunk[0]["index"])
        end_id = int(chunk[-1]["index"])

        # 默认摘要为前几个 block 的片段
        text_sample = " ".join([b["content"] for b in chunk[:12]])

        scenes.append({
            "scene_id": f"scene_{len(scenes) + 1:04d}",
            "block_range": [start_id, end_id],
            "participants": [],
            "tone": [],
            "domain": [],
            "summary": text_sample[:300],
            "translation_notes": [],
            "enriched": False  # [关键项] 标记该场景是否已通过 LLM 强化
        })

    return {
        "scenes": scenes,
        "fully_enriched": False
    }


def find_scene_for_block(scene_map: Dict, block_id: int) -> Dict:
    for scene in scene_map.get("scenes", []):
        start, end = scene.get("block_range", [0, 0])
        if start <= block_id <= end:
            return scene
    return {}


def scene_guidance_text(scene: Dict) -> str:
    if not scene:
        return "{}"
    return canonical_json({
        "scene_id": scene.get("scene_id", ""),
        "summary": scene.get("summary", ""),
        "participants": scene.get("participants", []),
        "tone": scene.get("tone", []),
        "domain": scene.get("domain", []),
        "translation_notes": scene.get("translation_notes", [])
    })


async def enrich_single_scene(config, scene: Dict, blocks: List[Dict]) -> Dict:
    """
    为单个场景调用 LLM 进行强化分析。
    """
    block_map = {int(b["index"]): b for b in blocks}
    start, end = scene["block_range"]
    scene_blocks = [block_map[i] for i in range(start, end + 1) if i in block_map]
    
    # 采样以节省 token：开头 15 行，中间 15 行，结尾 15 行
    n = len(scene_blocks)
    if n > 45:
        sampled = scene_blocks[:15] + scene_blocks[n//2-7:n//2+8] + scene_blocks[-15:]
    else:
        sampled = scene_blocks
        
    content = "\n".join([f"{b['index']}: {b['content']}" for b in sampled])
    
    prompt = f"""
你是一个专业的剧本分析师。请分析以下场景片段，并提取关键信息用于辅助翻译。

要求：
1. 只输出 JSON。
2. 不要修改 scene_id。
3. 如果信息不确定，请返回空列表。

输出 Schema：
{{
  "scene_id": "{scene['scene_id']}",
  "participants": ["角色名"],
  "tone": ["语气描述"],
  "domain": ["场景领域/主题"],
  "summary": "一句话场景摘要",
  "translation_notes": ["翻译注意事项"]
}}

场景片段：
{content}
""".strip()

    messages = [{"role": "user", "content": prompt}]
    raw = await call_llm(
        config, 
        messages, 
        temperature=0.0, 
        response_format={"type": "json_object"}
    )
    
    data = clean_and_extract_json(raw)
    if not isinstance(data, dict):
        return {}
        
    return {
        "participants": data.get("participants", []),
        "tone": data.get("tone", []),
        "domain": data.get("domain", []),
        "summary": data.get("summary", scene.get("summary", "")),
        "translation_notes": data.get("translation_notes", [])
    }


async def load_or_build_scene_map(config, blocks: List[Dict], cache_key: str) -> Dict:
    target_lang = config.target_lang
    path = os.path.join(CACHE_DIR, f"scene_map_{cache_key}_{target_lang}.json")

    cached = load_json_file(path)
    if isinstance(cached, dict) and cached.get("scenes"):
        scene_map = cached
    else:
        # 1. 先用规则生成基础 map
        scene_map = build_simple_scene_map(blocks)
        # 立即保存基础 map
        save_json_file(path, scene_map, pretty=True)

    # 2. 检查是否全部强化过
    if scene_map.get("fully_enriched", False):
        return scene_map

    # 3. 逐个场景强化
    scenes = scene_map.get("scenes", [])
    any_updated = False
    
    print(f"\n🎬 正在使用 LLM 逐个强化场景映射 (共 {len(scenes)} 个场景)...")
    
    for scene in scenes:
        if scene.get("enriched", False):
            continue
            
        print(f"   ⏳ 强化场景 {scene['scene_id']} [{scene['block_range'][0]}-{scene['block_range'][1]}]...")
        
        enriched_data = await enrich_single_scene(config, scene, blocks)
        if enriched_data:
            # 严格限制：只更新内容字段，不改 scene_id 和 block_range
            scene.update(enriched_data)
            scene["enriched"] = True
            any_updated = True
            # 原子化保存：每成功一个就存一次
            save_json_file(path, scene_map, pretty=True)
            
    # 4. 检查是否全部完成
    if all(s.get("enriched", False) for s in scenes):
        scene_map["fully_enriched"] = True
        save_json_file(path, scene_map, pretty=True)
        
    return scene_map


def build_scene_aligned_batches(
    remaining_blocks: List[Dict],
    scene_map: Dict,
    batch_size: int
) -> List[Dict]:
    """
    返回结构：
    [
      {
        "scene_id": "scene_0001",
        "blocks": [...]
      }
    ]
    """
    batches = []

    # 显式按索引排序，确保即使输入块不连续也能按正确顺序分批
    sorted_remaining = sorted(
        remaining_blocks,
        key=lambda b: int(b["index"]) if str(b.get("index", "")).isdigit() else 0
    )

    block_by_id = {
        int(b["index"]): b
        for b in sorted_remaining
        if str(b.get("index", "")).isdigit()
    }

    for scene in scene_map.get("scenes", []):
        start, end = scene.get("block_range", [0, 0])

        scene_blocks = [
            block_by_id[i]
            for i in range(start, end + 1)
            if i in block_by_id
        ]

        for i in range(0, len(scene_blocks), batch_size):
            chunk = scene_blocks[i:i + batch_size]
            if chunk:
                batches.append({
                    "scene_id": scene.get("scene_id", ""),
                    "blocks": chunk
                })

    return batches
