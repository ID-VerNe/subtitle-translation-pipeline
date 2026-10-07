# -*- coding: utf-8 -*-
from typing import List, Dict, Tuple

from core.context_builder import filter_relevant_glossary
from core.cache_utils import canonical_json
from core.rescue_engine import ladder_rescue_engine

# @lat: [[core-stages#Key Concepts#直译阶段（Literal Stage）]]
async def process_literal_stage(
    batch_blocks: List[Dict],
    config,
    glossary: Dict[str, str],
    core_glossary_text: str = "{}",
    global_profile: str = "{}",
    translation_policy: str = "{}",
    scene_guidance: str = "{}",
    previous_context: str = "None",
    future_context: str = "None"
) -> Tuple[Dict[str, str], str]:
    """直译阶段。与润色阶段对齐，注入全局画像/策略/场景引导/前后文。"""
    batch_text_all = " ".join([b['content'] for b in batch_blocks])
    local_terms = filter_relevant_glossary(batch_text_all, glossary)
    local_glossary_text = canonical_json(local_terms)

    trans_list = await ladder_rescue_engine(
        batch_blocks,
        config,
        core_glossary_text,
        local_glossary_text,
        stage="literal",
        global_profile=global_profile,
        translation_policy=translation_policy,
        scene_guidance=scene_guidance,
        previous_context=previous_context,
        future_context=future_context
    )

    return {
        str(item['id']): item.get('trans', '')
        for item in trans_list
        if 'id' in item
    }, local_glossary_text
