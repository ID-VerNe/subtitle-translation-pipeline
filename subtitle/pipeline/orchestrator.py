# -*- coding: utf-8 -*-

import os
import sys
import json
import asyncio
import logging
from typing import List, Dict
from tqdm import tqdm

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from core.config import TranslationConfig, PRESETS_FILE
from core.srt_utils import parse_srt, format_srt_block
from core.terminology_extractor import extract_global_terms
from core.stages.literal_stage import process_literal_stage
from core.stages.polish_stage import process_polish_stage
from core.context_builder import build_recent_state, build_core_terms
from core.memory.global_profile import (
    load_or_build_global_profile,
    global_profile_text
)
from core.memory.policy_engine import (
    build_translation_policy,
    policy_text,
    normalize_translation_policy
)
from core.memory.scene_manager import (
    load_or_build_scene_map,
    find_scene_for_block,
    scene_guidance_text,
    build_scene_aligned_batches,
    normalize_scene
)
from network.llm_client import close_session_pool
from core.glossary_manager import glossary_manager
from core.cache_utils import canonical_json, get_cache_path

from pipeline.checkpoint_manager import save_checkpoint, load_progress
from pipeline.srt_writer import rewrite_output

logger = logging.getLogger(__name__)

async def self_enforce_consistency(args, config, glossary, global_profile="{}", translation_policy="{}", progress_callback=None):
    final_blocks = parse_srt(args.output_file)
    if not final_blocks:
        logger.warning("未找到可供质检的输出字幕块。")
        return

    bilingual = getattr(args, 'bilingual', False)
    if bilingual:
        paired_blocks = []
        for i in range(0, len(final_blocks), 2):
            if i + 1 < len(final_blocks):
                paired = {
                    'index': final_blocks[i]['index'],
                    'timestamp': final_blocks[i]['timestamp'],
                    'original': final_blocks[i]['content'],
                    'content': final_blocks[i+1]['content'],
                    'polished': final_blocks[i+1]['content']
                }
                paired_blocks.append(paired)
            else:
                paired_blocks.append(final_blocks[i])
        working_blocks = paired_blocks
    else:
        working_blocks = final_blocks

    from core.post_checker import run_post_checker
    max_passes = getattr(args, 'post_check_passes', 5)
    
    post_checked_blocks = await run_post_checker(
        working_blocks, config,
        global_profile=global_profile,
        translation_policy=translation_policy,
        max_passes=max_passes
    )
    
    rewrite_output(args, post_checked_blocks)
    logger.info(f"✅ 全局后置终审完成，已写回 {args.output_file}")


# @lat: [[pipeline#Key Concepts#翻译主流程（run_translation）]]
async def run_translation(args, progress_callback=None):
    target_lang = getattr(args, 'target_lang', 'zh')
    enable_names_db = getattr(args, 'enable_names_db', False)
    config = TranslationConfig(
        api_key=args.api_key,
        api_url=args.api_url,
        model_name=args.model_name,
        batch_size=args.batch_size,
        temp_terms=args.temp_terms,
        temp_literal=args.temp_literal,
        temp_polish=args.temp_polish,
        max_concurrent_requests=args.max_concurrent,
        rpm_limit=getattr(args, 'rpm_limit', 60),
        tpm_limit=getattr(args, 'tpm_limit', 100000),
        max_retries=getattr(args, 'max_retries', 3),
        retry_delay=getattr(args, 'retry_delay', 2.0),
        max_tokens=getattr(args, 'max_tokens', 4096),
        pass_temperature=getattr(args, 'pass_temperature', True),
        target_lang=target_lang,
        enable_llm_discovery=getattr(args, 'enable_llm_discovery', True),
        enable_names_db=enable_names_db,
        reasoning_effort=getattr(args, 'reasoning_effort', ""),
    )
    
    should_reverse = (target_lang == 'en')
    glossary_manager.enable_names_db = config.enable_names_db
    glossary_manager.initialize(reverse=should_reverse)

    glossary_cache_file = getattr(args, 'glossary_cache_file', None)
    if glossary_cache_file is None:
        glossary_cache_file = get_cache_path(args.input_file, "glossary", target_lang)
        
    progress_file = getattr(args, 'progress_file', None)
    if progress_file is None:
        progress_file = get_cache_path(args.input_file, "progress", target_lang)

    blocks = parse_srt(args.input_file)
    if not blocks:
        logger.error(f"无法从 {args.input_file} 加载任何字幕块。")
        return
    logger.info(f"成功加载原文: {len(blocks)} 块")

    from core.safety_fuzzer import safety_fuzzer
    safety_fuzzer.initialize(blocks, config)

    global_profile = await load_or_build_global_profile(config, blocks, args.input_file)
    global_profile_str = global_profile_text(global_profile)
    logger.info("已加载/构建全局画像 global_profile")

    scene_map = await load_or_build_scene_map(config, blocks, args.input_file)
    logger.info(f"已加载/构建场景映射 scene_map: {len(scene_map.get('scenes', []))} 个场景")

    current_glossary = {}
    
    if os.path.exists(glossary_cache_file):
        try:
            with open(glossary_cache_file, 'r', encoding='utf-8') as f:
                current_glossary = json.load(f)
            logger.info(f"🚀 发现任务术语缓存，直接加载: {len(current_glossary)} 条")
        except:
            pass
            
    if not current_glossary and os.path.exists(progress_file):
        full_text = "\n".join([b['content'] for b in blocks])
        current_glossary = glossary_manager.extract_terms(full_text)
        logger.info(f"📂 发现任务进度记录，已从语料库中回填术语: {len(current_glossary)} 条")
        with open(glossary_cache_file, 'w', encoding='utf-8') as f:
            json.dump(current_glossary, f, ensure_ascii=False, indent=2)

    if not current_glossary:
        num_passes = max(5, (len(blocks) + 99) // 100)
        logger.info(f"🔍 未发现历史记录，开始执行动态 {num_passes} 步循环采样提取术语表...")
        current_glossary = await extract_global_terms(config, blocks)
        with open(glossary_cache_file, 'w', encoding='utf-8') as f:
            json.dump(current_glossary, f, ensure_ascii=False, indent=2)
        logger.info(f"术语表已保存至: {glossary_cache_file}")

    translation_policy = build_translation_policy(
        global_profile=global_profile,
        glossary=current_glossary,
        target_lang=target_lang
    )
    translation_policy = normalize_translation_policy(translation_policy)
    translation_policy_str = policy_text(translation_policy)
    core_terms = build_core_terms(current_glossary)
    core_glossary_str = canonical_json(core_terms)
    logger.info("已加载/构建翻译策略 translation_policy")

    print("\n" + "="*60)
    print(f"📋 【当前生效的术语表】")
    print(f"   路径: {os.path.abspath(glossary_cache_file)}")
    print(f"   提示: 若需人工修正术语，请编辑此文件后重新运行脚本。")
    print("="*60 + "\n")

    progress = load_progress(progress_file)
    processed_indices = set(progress.get("processed_indices", []))
    remaining_blocks = [b for b in blocks if b['index'] not in processed_indices]

    if getattr(args, 'scrub_model', None):
        presets = {}
        if os.path.exists(PRESETS_FILE):
            try:
                with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
                    presets = json.load(f)
            except Exception as e:
                logger.warning(f"读取预设文件失败: {e}")
        if args.scrub_model in presets:
            p = presets[args.scrub_model]
            scrub_config = TranslationConfig()
            scrub_config.api_key = p.get('api_key', '')
            scrub_config.api_url = p.get('api_url', scrub_config.api_url)
            scrub_config.model_name = p.get('model_name', '')
            scrub_config.max_tokens = int(p.get('max_tokens', 4096))
            scrub_config.reasoning_effort = p.get('reasoning_effort', 'none')
            
            logger.info(f"Using {args.scrub_model} for ASR purification on {len(remaining_blocks)} blocks...")
            from core.asr_scrubber import run_asr_scrub
            remaining_blocks = await run_asr_scrub(remaining_blocks, scrub_config)
            
            block_dict = {b['index']: b for b in remaining_blocks}
            for b in blocks:
                if b['index'] in block_dict:
                    b['content'] = block_dict[b['index']]['content']
        else:
            logger.warning(f"Scrub model {args.scrub_model} not found in presets. Skipping purification.")

    if not remaining_blocks:
        logger.info("所有字幕块都已翻译完毕，直接进入全片终审质检阶段...")
        if getattr(args, 'enforce_consistency', True):
            global_profile_str = global_profile_text(global_profile)
            translation_policy_str = policy_text(build_translation_policy(global_profile, current_glossary, target_lang))
            await self_enforce_consistency(
                args, config, current_glossary,
                global_profile=global_profile_str,
                translation_policy=translation_policy_str,
                progress_callback=progress_callback
            )
        return

    if not processed_indices:
        open(args.output_file, 'w').close()
        open(args.output_file.replace('.srt', '.literal.srt'), 'w').close()
        open(args.output_file.replace('.srt', '.polished.srt'), 'w').close()
        progress['output_block_index'] = 1 
    progress.setdefault('output_block_index', 1)

    logger.info(f"开始处理，剩余 {len(remaining_blocks)} 块...")

    recent_state_str = progress.get('recent_state', "")

    batch_items = build_scene_aligned_batches(
        remaining_blocks=remaining_blocks,
        scene_map=scene_map,
        batch_size=args.batch_size
    )
    
    next_literal_task = None
    total_batches = len(batch_items)
    pbar = tqdm(total=total_batches, desc="翻译进度", unit="batch")

    try:
        for i, batch_item in enumerate(batch_items):
            batch = batch_item["blocks"]
            scene_id = batch_item["scene_id"]

            if progress_callback:
                progress_callback(i, total_batches)
                
            start_id, end_id = batch[0]['index'], batch[-1]['index']

            current_scene = find_scene_for_block(scene_map, int(batch[0]["index"]))
            current_scene = normalize_scene(current_scene)
            scene_guidance_str = scene_guidance_text(current_scene)
            
            participants = current_scene.get("participants", [])
            current_profile_str = global_profile_text(global_profile, scene_participants=participants)
            
            current_policy = build_translation_policy(
                global_profile=global_profile,
                glossary=current_glossary,
                target_lang=target_lang,
                scene_participants=participants
            )
            current_policy_str = policy_text(current_policy)

            future_context_str = "None"
            if i + 1 < total_batches:
                next_batch = batch_items[i+1]["blocks"]
                next_blocks = []
                for j in range(i+1, min(i+5, total_batches)):
                    next_blocks.extend(batch_items[j]["blocks"])
                future_lines = [f'{b["index"]}: {b["content"]}' for b in next_blocks[:50]]
                future_context_str = "\n".join(future_lines)

            if i == 0:
                literal_map, local_glossary_str = await process_literal_stage(
                    batch, config, current_glossary,
                    core_glossary_text=core_glossary_str,
                    global_profile=current_profile_str,
                    translation_policy=current_policy_str,
                    scene_guidance=scene_guidance_str,
                    previous_context=recent_state_str,
                    future_context=future_context_str
                )
            else:
                literal_map, local_glossary_str = await next_literal_task

            if i + 1 < total_batches:
                next_blocks = []
                for j in range(i+1, min(i+5, total_batches)):
                    next_blocks.extend(batch_items[j]["blocks"])
                next_prev = recent_state_str
                next_future = "None"
                if i + 2 < total_batches:
                    nnext_lines = [f'{b["index"]}: {b["content"]}' for b in batch_items[i+2]["blocks"][:25]]
                    next_future = "\n".join(nnext_lines)
                next_literal_task = asyncio.create_task(process_literal_stage(
                    next_batch, config, current_glossary,
                    core_glossary_text=core_glossary_str,
                    global_profile=current_profile_str,
                    translation_policy=current_policy_str,
                    scene_guidance=scene_guidance_str,
                    previous_context=next_prev,
                    future_context=next_future
                ))

            final_blocks = await process_polish_stage(
                batch, config, literal_map, core_glossary_str, local_glossary_str,
                recent_state=recent_state_str,
                future_context=future_context_str,
                global_profile=current_profile_str,
                translation_policy=current_policy_str,
                scene_guidance=scene_guidance_str
            )
            
            if final_blocks:
                import re
                for fb in final_blocks:
                    orig_nums = sorted(re.findall(r'\d+', re.sub(r'<[^>]+>', '', fb['original'])))
                    trans_nums = sorted(re.findall(r'\d+', re.sub(r'<[^>]+>', '', fb['polished'])))
                    if orig_nums != trans_nums:
                        logger.warning(f"🚨 [Numeric Mismatch] ID {fb['index']}! Orig: {orig_nums} | Trans: {trans_nums} | Text: {fb['polished']}")

                recent_state = build_recent_state(final_blocks)
                recent_state_str = canonical_json(recent_state)
                progress["recent_state"] = recent_state_str

                save_checkpoint(args.output_file, progress_file, final_blocks, progress, bilingual_output=args.bilingual, last_context="")
                pbar.update(1)
                tqdm.write(f"  ✅ 批次 {i+1} (ID {start_id}-{end_id}) 处理完成。")
            else:
                logger.warning(f"批次 {i+1} 未生成任何内容。")

        pbar.close()
        if progress_callback:
            progress_callback(total_batches, total_batches)
        
        logger.info("✅ 翻译完成！")

        if getattr(args, 'enforce_consistency', True):
            await self_enforce_consistency(
                args, config, current_glossary,
                global_profile=global_profile_str,
                translation_policy=translation_policy_str,
                progress_callback=progress_callback
            )

        if getattr(args, 'enable_annotations', False):
            logger.info("\n开始生成全文注释...")
            
            final_blocks = parse_srt(args.output_file)
            
            if final_blocks:
                block_ids = [int(b['index']) for b in final_blocks if b['index'].isdigit()]
                logger.info(f"字幕块 ID 范围: {min(block_ids) if block_ids else 0} - {max(block_ids) if block_ids else 0}")
                
                genre = global_profile.get('genre', '未知')
                
                from core.annotation_pipeline import generate_annotations_for_subtitle
                id_to_annotation = await generate_annotations_for_subtitle(
                    config, 
                    final_blocks, 
                    genre=genre,
                    domain_context=global_profile_str,
                    batch_size=150
                )
                
                if id_to_annotation:
                    logger.info(f"注释 ID 列表: {sorted(id_to_annotation.keys())}")
                
                if id_to_annotation:
                    annotation_output = args.output_file.replace('.srt', '_with_annotations.srt')
                    with open(annotation_output, 'w', encoding='utf-8') as f:
                        for i, block in enumerate(final_blocks, start=1):
                            block_id = int(block['index'])
                            text_content = block.get('polished', block.get('content', ''))
                            f.write(format_srt_block(i, block['timestamp'], text_content))
                            if block_id in id_to_annotation:
                                f.write(format_srt_block(i, block['timestamp'], id_to_annotation[block_id]))
                    
                    logger.info(f"✅ 带注释的字幕已生成: {annotation_output}")
                    logger.info(f"   共添加 {len(id_to_annotation)} 条注释")
                else:
                    logger.info("未识别到需要注释的内容")
            
    finally:
        if next_literal_task and not next_literal_task.done():
            next_literal_task.cancel()
            try:
                await next_literal_task
            except asyncio.CancelledError:
                pass

        await close_session_pool()
