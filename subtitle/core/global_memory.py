# -*- coding: utf-8 -*-
"""
Facade for the refactored memory modules.
This file is kept for backward compatibility and to group memory-related exports.
"""

from .memory.global_profile import (
    sample_blocks_for_global_profile,
    compact_blocks_for_prompt,
    default_global_profile,
    sanitize_global_profile,
    normalize_global_profile,
    build_global_profile,
    load_or_build_global_profile,
    compact_global_profile,
    global_profile_text
)

from .memory.policy_engine import (
    normalize_translation_policy,
    build_translation_policy,
    policy_text
)

from .memory.scene_manager import (
    normalize_scene,
    build_simple_scene_map,
    find_scene_for_block,
    scene_guidance_text,
    enrich_single_scene,
    load_or_build_scene_map,
    build_scene_aligned_batches
)

__all__ = [
    "sample_blocks_for_global_profile",
    "compact_blocks_for_prompt",
    "default_global_profile",
    "sanitize_global_profile",
    "normalize_global_profile",
    "build_global_profile",
    "load_or_build_global_profile",
    "compact_global_profile",
    "global_profile_text",

    "normalize_translation_policy",
    "build_translation_policy",
    "policy_text",

    "normalize_scene",
    "build_simple_scene_map",
    "find_scene_for_block",
    "scene_guidance_text",
    "enrich_single_scene",
    "load_or_build_scene_map",
    "build_scene_aligned_batches"
]
