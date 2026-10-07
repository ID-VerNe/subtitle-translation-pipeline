# -*- coding: utf-8 -*-
from typing import List, Dict

from core.llm_client import call_llm, clean_and_extract_json
from core.cache_utils import load_json_file, save_json_file, canonical_json, get_cache_path
from core.prompts import load_prompt


def normalize_scene(scene: Dict) -> Dict:
    """规范化单个场景数据的数组顺序"""
    if not isinstance(scene, dict):
        return scene
        
    for key in ["participants", "tone", "domain", "translation_notes"]:
        if key in scene and isinstance(scene[key], list):
            scene[key] = sorted([str(x) for x in scene[key]])
            
    return scene


# @lat: [[core-memory#Key Concepts#场景映射（Scene Map）]]
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

        text_sample = " ".join([b["content"] for b in chunk[:12]])

        scenes.append({
            "scene_id": f"scene_{len(scenes) + 1:04d}",
            "block_range": [start_id, end_id],
            "participants": [],
            "tone": [],
            "domain": [],
            "summary": text_sample[:300],
            "translation_notes": [],
            "enriched": False 
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


# @lat: [[core-memory#Key Concepts#场景映射（Scene Map）]]
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


# @lat: [[core-memory#Key Concepts#场景映射（Scene Map）]]
async def enrich_single_scene(config, scene: Dict, blocks: List[Dict]) -> Dict:
    """
    为单个场景调用 LLM 进行强化分析。
    """
    block_map = {int(b["index"]): b for b in blocks}
    start, end = scene["block_range"]
    scene_blocks = [block_map[i] for i in range(start, end + 1) if i in block_map]
    
    n = len(scene_blocks)
    if n > 45:
        sampled = scene_blocks[:15] + scene_blocks[n//2-7:n//2+8] + scene_blocks[-15:]
    else:
        sampled = scene_blocks
        
    content = "\n".join([f"{b['index']}: {b['content']}" for b in sampled])
    
    prompt_template = load_prompt("global_scene")
    prompt = prompt_template.format(
        scene_id=scene['scene_id'],
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
        return {}
        
    return {
        "participants": data.get("participants", []),
        "tone": data.get("tone", []),
        "domain": data.get("domain", []),
        "summary": data.get("summary", scene.get("summary", "")),
        "translation_notes": data.get("translation_notes", [])
    }


# @lat: [[core-memory#Key Concepts#场景映射（Scene Map）]]
async def load_or_build_scene_map(config, blocks: List[Dict], input_file: str) -> Dict:
    target_lang = config.target_lang
    path = get_cache_path(input_file, "scene_map", target_lang)

    cached = load_json_file(path)
    if isinstance(cached, dict) and cached.get("scenes"):
        scene_map = cached
    else:
        scene_map = build_simple_scene_map(blocks)
        save_json_file(path, scene_map, pretty=True)

    if scene_map.get("fully_enriched", False):
        return scene_map

    scenes = scene_map.get("scenes", [])
    any_updated = False
    
    print(f"\n🎬 正在使用 LLM 逐个强化场景映射 (共 {len(scenes)} 个场景)...")
    
    for scene in scenes:
        if scene.get("enriched", False):
            continue
            
        print(f"   ⏳ 强化场景 {scene['scene_id']} [{scene['block_range'][0]}-{scene['block_range'][1]}]...")
        
        enriched_data = await enrich_single_scene(config, scene, blocks)
        if enriched_data:
            scene.update(enriched_data)
            scene["enriched"] = True
            any_updated = True
            save_json_file(path, scene_map, pretty=True)
            
    if all(s.get("enriched", False) for s in scenes):
        scene_map["fully_enriched"] = True
        save_json_file(path, scene_map, pretty=True)
        
    return scene_map


# @lat: [[core-memory#Key Concepts#场景映射（Scene Map）]]
def build_scene_aligned_batches(
    remaining_blocks: List[Dict],
    scene_map: Dict,
    batch_size: int
) -> List[Dict]:
    batches = []

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
