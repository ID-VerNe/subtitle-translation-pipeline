# -*- coding: utf-8 -*-

import os
import json
import argparse
import asyncio
import logging
import hashlib
from typing import List, Dict
from tqdm import tqdm

# 在定义和修改配置前，先导入它们
from core.config import TranslationConfig, CACHE_DIR
from core.srt_utils import parse_srt, format_srt_block
from core.translation_pipeline import (
    extract_global_terms, 
    process_literal_stage, 
    process_polish_stage, 
    build_recent_state,
    build_core_terms
)
from core.global_memory import (
    load_or_build_global_profile,
    global_profile_text,
    build_translation_policy,
    policy_text,
    load_or_build_scene_map,
    find_scene_for_block,
    scene_guidance_text,
    build_scene_aligned_batches,
    normalize_translation_policy,
    normalize_scene
)
from core.llm_client import close_session_pool
from core.glossary_manager import glossary_manager
from core.cache_utils import build_file_cache_key, canonical_json

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("translation.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def save_checkpoint(srt_file: str, progress_file: str, blocks: List[Dict], progress_data: Dict, bilingual_output: bool = False, last_context: str = ""):
    """
    保存检查点，使用 srt_utils 统一格式化。
    """
    if not blocks:
        return

    output_block_index = progress_data.get('output_block_index', 1)

    with open(srt_file, 'a', encoding='utf-8') as f:
        for b in blocks:
            if bilingual_output:
                # 块分离模式
                f.write(format_srt_block(output_block_index, b['timestamp'], b['original']))
                output_block_index += 1
                f.write(format_srt_block(output_block_index, b['timestamp'], b['polished']))
                output_block_index += 1
            else:
                f.write(format_srt_block(output_block_index, b['timestamp'], b['polished']))
                output_block_index += 1
    
    progress_data['output_block_index'] = output_block_index
    progress_data['last_context'] = last_context
    last_idx = int(blocks[-1]['index'])
    progress_data["last_index"] = last_idx
    processed_set = set(progress_data.get("processed_indices", []))
    processed_set.update(b['index'] for b in blocks)
    progress_data["processed_indices"] = sorted(list(processed_set), key=int)

    with open(progress_file, 'w', encoding='utf-8') as f:
        json.dump(progress_data, f, ensure_ascii=False, indent=2)

def load_progress(progress_file: str) -> Dict:
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"last_index": 0, "processed_indices": []}

async def run_translation(args, progress_callback=None):
    """执行翻译流程的核心逻辑"""
    
    # --- 0. 初始化配置与语料库 ---
    target_lang = getattr(args, 'target_lang', 'zh')
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
        target_lang=target_lang,
        enable_llm_discovery=getattr(args, 'enable_llm_discovery', True)
    )
    
    # 如果目标是英文，开启反向模式
    should_reverse = (target_lang == 'en')
    glossary_manager.initialize(reverse=should_reverse)

    # --- 0.1 动态处理缓存路径 ---
    cache_dir = CACHE_DIR
    
    file_hash = build_file_cache_key(
        input_file=args.input_file,
        target_lang=target_lang,
        model_name=config.model_name
    )
    
    glossary_cache_file = getattr(args, 'glossary_cache_file', None)
    if glossary_cache_file is None:
        glossary_cache_file = os.path.join(cache_dir, f"glossary_{file_hash}_{target_lang}.json")
        
    progress_file = getattr(args, 'progress_file', None)
    if progress_file is None:
        progress_file = os.path.join(cache_dir, f"progress_{file_hash}_{target_lang}.json")

    # --- 1. 加载 SRT ---
    blocks = parse_srt(args.input_file)
    if not blocks:
        logger.error(f"无法从 {args.input_file} 加载任何字幕块。")
        return
    logger.info(f"成功加载原文: {len(blocks)} 块")

    # --- 1.1 构建全局画像 (Global Discovery) ---
    global_profile = await load_or_build_global_profile(config, blocks, file_hash)
    global_profile_str = global_profile_text(global_profile)
    logger.info("已加载/构建全局画像 global_profile")

    scene_map = await load_or_build_scene_map(config, blocks, file_hash)
    logger.info(f"已加载/构建场景映射 scene_map: {len(scene_map.get('scenes', []))} 个场景")

    # --- 2. 构建当前任务的混合术语表 ---
    current_glossary = {}
    
    # 首先尝试从任务缓存加载
    if os.path.exists(glossary_cache_file):
        try:
            with open(glossary_cache_file, 'r', encoding='utf-8') as f:
                current_glossary = json.load(f)
            logger.info(f"🚀 发现任务术语缓存，直接加载: {len(current_glossary)} 条")
        except:
            pass
            
    # 如果没有任务缓存，但有进度文件，说明之前已经跑过发现逻辑，直接通过语料库回填
    if not current_glossary and os.path.exists(progress_file):
        full_text = "\n".join([b['content'] for b in blocks])
        current_glossary = glossary_manager.extract_terms(full_text)
        logger.info(f"📂 发现任务进度记录，已从语料库中回填术语: {len(current_glossary)} 条")
        # 存一份缓存，防止下次再跑这段逻辑
        with open(glossary_cache_file, 'w', encoding='utf-8') as f:
            json.dump(current_glossary, f, ensure_ascii=False, indent=2)

    if not current_glossary:
        num_passes = max(5, (len(blocks) + 99) // 100)
        logger.info(f"🔍 未发现历史记录，开始执行动态 {num_passes} 步循环采样提取术语表...")
        current_glossary = await extract_global_terms(config, blocks)
        with open(glossary_cache_file, 'w', encoding='utf-8') as f:
            json.dump(current_glossary, f, ensure_ascii=False, indent=2)
        logger.info(f"术语表已保存至: {glossary_cache_file}")

    # --- 2.1 构建翻译策略 (Translation Policy) ---
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

    # --- 显眼提示用户术语表位置 ---
    print("\n" + "="*60)
    print(f"📋 【当前生效的术语表】")
    print(f"   路径: {os.path.abspath(glossary_cache_file)}")
    print(f"   提示: 若需人工修正术语，请编辑此文件后重新运行脚本。")
    print("="*60 + "\n")

    # --- 3. 恢复进度 ---
    progress = load_progress(progress_file)
    processed_indices = set(progress.get("processed_indices", []))
    remaining_blocks = [b for b in blocks if b['index'] not in processed_indices]

    if not remaining_blocks:
        logger.info("所有字幕块都已处理完毕。")
        return

    if not processed_indices:
        open(args.output_file, 'w').close()
        progress['output_block_index'] = 1 
    progress.setdefault('output_block_index', 1)

    logger.info(f"开始处理，剩余 {len(remaining_blocks)} 块...")

    # 从进度文件中恢复上下文
    recent_state_str = progress.get('recent_state', "")

    # --- 4. 准备批次列表 (Scene-Aligned) ---
    batch_items = build_scene_aligned_batches(
        remaining_blocks=remaining_blocks,
        scene_map=scene_map,
        batch_size=args.batch_size
    )

    # --- 5. 流水线并行处理 (交叠模式) ---
    # 逻辑：
    # 1. 启动 Batch[i] 的直译 (如果是第一块)
    # 2. 等待 Batch[i] 直译完成
    # 3. 启动 Batch[i] 的润色，【同时】异步启动 Batch[i+1] 的直译 (Prefetch)
    # 4. 等待 Batch[i] 润色完成，获取其结果作为下一块的 Previous Context
    
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
            # 强化场景数据规范化
            current_scene = normalize_scene(current_scene)
            scene_guidance_str = scene_guidance_text(current_scene)
            
            # [核心优化] 获取当前场景的参与者，进行上下文感知的画像和策略压缩
            participants = current_scene.get("participants", [])
            current_profile_str = global_profile_text(global_profile, scene_participants=participants)
            
            current_policy = build_translation_policy(
                global_profile=global_profile,
                glossary=current_glossary,
                target_lang=target_lang,
                scene_participants=participants
            )
            current_policy_str = policy_text(current_policy)

            # A. 获取当前批次的直译结果
            if i == 0:
                # 第一块需要原地等待直译
                literal_map, local_glossary_str = await process_literal_stage(batch, config, current_glossary, core_glossary_text=core_glossary_str)
            else:
                # 后续块使用上一轮启动的预取任务
                literal_map, local_glossary_str = await next_literal_task

            # B. 准备下文 (Future Context)
            future_context_str = ""
            if i + 1 < total_batches:
                # 【核心改动】：在开始润色当前块的同时，启动下一块的直译
                # 这样实现了：第一句意译（并行：第二句直译）
                next_batch = batch_items[i+1]["blocks"]
                next_literal_task = asyncio.create_task(process_literal_stage(next_batch, config, current_glossary, core_glossary_text=core_glossary_str))

            # C. 执行润色阶段
            # 此时 previous_context_str 保证是上一句【意译】出来的结果
            final_blocks = await process_polish_stage(
                batch, config, literal_map, core_glossary_str, local_glossary_str, 
                recent_state=recent_state_str,
                global_profile=current_profile_str,    # 使用上下文感知压缩版
                translation_policy=current_policy_str, # 使用上下文感知压缩版
                scene_guidance=scene_guidance_str
            )
            
            if final_blocks:
                # D. 更新上下文并保存
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
    finally:
        # 安全清理：取消任何挂起的异步预取任务
        if next_literal_task and not next_literal_task.done():
            next_literal_task.cancel()
            try:
                await next_literal_task
            except asyncio.CancelledError:
                pass

        # 彻底关闭 API 会话池，防止 unclosed session 错误
        await close_session_pool()

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="SRT 智能翻译工具 (架构优化版)")

    # --- 文件与路径参数 ---
    parser.add_argument('-i', '--input-file', type=str, default='官方英文.srt', help='输入SRT文件')
    parser.add_argument('-o', '--output-file', type=str, default='官方英文_output.srt', help='输出SRT文件')
    parser.add_argument('--progress-file', type=str, default=None, help='进度文件')
    parser.add_argument('--glossary-cache-file', type=str, default=None, help='术语缓存')
    
    # --- 运行参数 ---
    defaults = TranslationConfig()
    parser.add_argument('--batch-size', type=int, default=defaults.batch_size, help='批次大小')
    parser.add_argument('--max-concurrent', type=int, default=defaults.max_concurrent_requests, help='最大并发请求数')

    parser.add_argument('--bilingual', dest='bilingual', action='store_true', help='开启双语')
    parser.add_argument('--no-bilingual', dest='bilingual', action='store_false', help='仅中文')
    parser.set_defaults(bilingual=True)

    # --- API 与模型参数 ---
    parser.add_argument('--api-key', type=str, default=defaults.api_key, help='API Key')
    parser.add_argument('--api-url', type=str, default=defaults.api_url, help='API URL')
    parser.add_argument('--model-name', type=str, default=defaults.model_name, help='模型名称')
    
    # --- 温度参数 ---
    parser.add_argument('--temp-terms', type=float, default=defaults.temp_terms, help='术语提取温度')
    parser.add_argument('--temp-literal', type=float, default=defaults.temp_literal, help='直译温度')
    parser.add_argument('--temp-polish', type=float, default=defaults.temp_polish, help='润色温度')

    args = parser.parse_args()

    # 启动异步主逻辑
    asyncio.run(run_translation(args))

if __name__ == "__main__":
    main()