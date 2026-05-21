# 字幕翻译 Pipeline 完整源码集 (Consolidated Pipeline Source)

本文件汇集了当前字幕翻译流水线的所有核心代码、配置及 Prompt 模板。

---

## 1. 入口与编排 (Main & Entry Points)

### 1.1 `subtitle/main.py`
```python
# -*- coding: utf-8 -*-
import os
import sys
import argparse
import asyncio
import hashlib
import logging
from typing import List

# 添加当前目录到路径，确保可以导入核心模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.config import TranslationConfig, TranslationArgs, CACHE_DIR
from translate_srt_llm import run_translation

# 动态加载子模块
import importlib.util

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# 获取子工具路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXTRACT_TOOL_PATH = os.path.join(BASE_DIR, "pre-process", "01-extract_srt.py")
ASS_TOOL_PATH = os.path.join(BASE_DIR, "post-process", "02-post_process_ass.py")

extract_tool = load_module("extract_tool", EXTRACT_TOOL_PATH)
ass_tool = load_module("ass_tool", ASS_TOOL_PATH)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MainWorkflow")

async def main():
    parser = argparse.ArgumentParser(description="字幕翻译一站式工具 - 从 MKV 到最终版字幕")
    
    # 输入输出控制
    parser.add_argument("-i", "--input", required=True, help="输入文件 (MKV 或 SRT)")
    parser.add_argument("-o", "--output", help="最终输出文件名 (可选)")
    parser.add_argument("-f", "--format", choices=["srt", "ass"], default="ass", help="最终输出格式 (默认 ass)")
    
    # 常用覆盖参数
    parser.add_argument("--to-english", action="store_true", help="开启中译英模式")
    parser.add_argument("--bilingual", action="store_true", default=True, help="是否生成双语字幕 (默认开启)")
    parser.add_argument("--no-bilingual", action="store_false", dest="bilingual", help="仅保留中文字幕")
    parser.add_argument("--model", type=str, help="覆盖 .env 中的模型名称")
    parser.add_argument("--batch-size", type=int, help="覆盖 .env 中的批次大小")
    parser.add_argument("--enable-names-db", action="store_true", help="启用人名数据库 (默认禁用)")
    
    args = parser.parse_args()

    target_lang = "en" if args.to_english else "zh"
    input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
        logger.error(f"找不到输入文件: {input_path}")
        return

    final_format = args.format
    if args.output:
        if args.output.lower().endswith(".srt"): final_format = "srt"
        elif args.output.lower().endswith(".ass"): final_format = "ass"
    
    final_output = args.output if args.output else os.path.splitext(input_path)[0] + f".{final_format}"

    # 1. 预处理
    working_srt = None
    if input_path.lower().endswith(".mkv"):
        logger.info(f"检测到 MKV 文件，正在提取字幕...")
        srt_files = extract_tool.extract_subtitles(input_path)
        if srt_files: working_srt = srt_files[0]
        else:
            logger.error("MKV 字幕提取失败。")
            return
    elif input_path.lower().endswith(".srt"):
        working_srt = input_path
    elif input_path.lower().endswith(".ass"):
        logger.info("检测到 ASS 文件，正在转换为 SRT 以进行翻译...")
        working_srt = extract_tool.convert_ass_file_to_srt(input_path)

    # 2. 翻译
    cache_dir = CACHE_DIR
    input_filename = os.path.basename(working_srt)
    file_hash = hashlib.md5(input_filename.encode('utf-8')).hexdigest()
    
    if final_format == "ass":
        translated_srt = os.path.join(cache_dir, f"translated_{file_hash}.srt")
    else:
        translated_srt = final_output

    trans_args = TranslationArgs(
        input_file=working_srt,
        output_file=translated_srt,
        bilingual=args.bilingual,
        model_name=args.model,
        batch_size=args.batch_size,
        target_lang=target_lang
    )
    if args.enable_names_db:
        trans_args.enable_names_db = True

    await run_translation(trans_args)

    # 3. 后处理
    if final_format == "ass":
        logger.info(f"正在生成 ASS 格式: {final_output}")
        head_path = os.path.join(BASE_DIR, "post-process", "asshead.txt")
        if not os.path.exists(head_path): head_path = "asshead.txt"
        ass_tool.srt_to_ass(translated_srt, head_path, final_output)
        logger.info(f"✅ 完成！最终字幕文件已生成: {os.path.abspath(final_output)}")
    else:
        logger.info(f"✅ 完成！最终字幕文件已生成: {os.path.abspath(final_output)}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(main())
    else:
        # 如果没有参数，启动 GUI
        from gui_app import run_gui
        run_gui()
```

### 1.2 `subtitle/translate_srt_llm.py`
```python
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
from core.translation_pipeline import extract_global_terms, process_literal_stage, process_polish_stage
from core.glossary_manager import glossary_manager

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
    
    input_filename = os.path.basename(args.input_file)
    file_hash = hashlib.md5(input_filename.encode('utf-8')).hexdigest()
    
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
    previous_context_str = progress.get('last_context', "")

    # --- 4. 准备批次列表 ---
    batches = []
    for i in range(0, len(remaining_blocks), args.batch_size):
        batches.append(remaining_blocks[i: i + args.batch_size])

    # --- 5. 流水线并行处理 (交叠模式) ---
    next_literal_task = None
    total_batches = len(batches)
    pbar = tqdm(total=total_batches, desc="翻译进度", unit="batch")

    for i, batch in enumerate(batches):
        if progress_callback:
            progress_callback(i, total_batches)
            
        start_id, end_id = batch[0]['index'], batch[-1]['index']

        # A. 获取当前批次的直译结果
        if i == 0:
            literal_map, glossary_text = await process_literal_stage(batch, config, current_glossary)
        else:
            literal_map, glossary_text = await next_literal_task

        # B. 准备下文 (Future Context)
        future_context_str = ""
        if i + 1 < total_batches:
            future_blocks = batches[i+1]
            future_context_str = "\n".join([f"- {b['content']}" for b in future_blocks])
            next_literal_task = asyncio.create_task(process_literal_stage(batches[i+1], config, current_glossary))

        # C. 执行润色阶段
        final_blocks = await process_polish_stage(
            batch, config, literal_map, glossary_text, 
            previous_context=previous_context_str,
            future_context=future_context_str
        )
        
        if final_blocks:
            previous_context_str = "\n".join(
                [f"- {b['original']} -> {b['polished']}" for b in final_blocks]
            )

            save_checkpoint(args.output_file, progress_file, final_blocks, progress, bilingual_output=args.bilingual, last_context=previous_context_str)
            pbar.update(1)
            tqdm.write(f"  ✅ 批次 {i+1} (ID {start_id}-{end_id}) 处理完成。")
        else:
            logger.warning(f"批次 {i+1} 未生成任何内容。")

    pbar.close()
    if progress_callback:
        progress_callback(total_batches, total_batches)
    
    logger.info("✅ 翻译完成！")
```

---

## 2. 核心 Pipeline 逻辑 (Core Logic)

### 2.1 `subtitle/core/translation_pipeline.py`
```python
# -*- coding: utf-8 -*- 

import json
import asyncio
import logging
import re
from typing import List, Dict, Tuple
from tqdm import tqdm

from .llm_client import call_llm, call_llm_batch, clean_and_extract_json, get_load_balancer_stats
from .prompts import get_prompt_templates
from .glossary_manager import glossary_manager

logger = logging.getLogger(__name__)

def filter_relevant_glossary(text_content: str, full_glossary: Dict[str, dict]) -> Dict[str, dict]:
    relevant = {}
    text_lower = text_content.lower()
    for src, info in full_glossary.items():
        if src.lower() in text_lower:
            relevant[src] = info
            
    # [集成人名库查询]
    found_names = glossary_manager.search_names(text_content, exclude_list=list(relevant.keys()))
    for name, trans in found_names.items():
        if name not in relevant:
            relevant[name] = {
                "source": name,
                "target": trans,
                "category": "Proper Name"
            }
            
    return relevant

async def extract_global_terms(config, blocks: List[Dict]) -> Dict[str, dict]:
    """提取术语并进行 NER 识别"""
    templates = get_prompt_templates(config.target_lang)
    num_passes = max(5, (len(blocks) + 99) // 100)
    
    all_llm_glossary = {}
    tasks = []
    ner_tasks = []
    
    for pass_idx in range(num_passes):
        sampled_text = ""
        for i in range(pass_idx, len(blocks), num_passes):
            sampled_text += blocks[i]['content'] + "\n"
        
        MAX_SAMPLE_LEN = 4000
        text_parts = [sampled_text[i:i+MAX_SAMPLE_LEN] for i in range(0, len(sampled_text), MAX_SAMPLE_LEN)]
        
        for part_text in text_parts:
            messages = [{"role": "user", "content": templates["TERM_EXTRACT"].format(content=part_text)}]
            tasks.append((messages, config.temp_terms, {"type": "json_object"}))
            
            if pass_idx == 0:
                from dataclasses import replace
                ner_msgs = [{"role": "user", "content": templates["NER_NAMES"].format(content=part_text)}]
                ner_config = replace(config, 
                    model_name=config.ner_model_name,
                    api_key=config.ner_api_key,
                    api_url=config.ner_api_url
                )
                ner_tasks.append((ner_config, ner_msgs))

    if tasks or ner_tasks:
        if tasks:
            term_messages = [t[0] for t in tasks]
            pbar = tqdm(total=len(tasks) + len(ner_tasks), desc="术语提取中")
            term_results = await call_llm_batch(
                config, 
                term_messages, 
                temperature=config.temp_terms,
                response_format={"type": "json_object"},
                progress_callback=lambda c, t: setattr(pbar, 'n', c) or pbar.refresh()
            )
        
        ner_results = []
        for ner_config, ner_msgs in ner_tasks:
            result = await call_llm(ner_config, ner_msgs, temperature=0.0, response_format={"type": "json_object"})
            ner_results.append(result)
            pbar.update(1)
        pbar.close()

        # 处理术语结果
        for result in term_results:
            data = clean_and_extract_json(result)
            def process_item(k, v):
                if isinstance(v, str):
                    all_llm_glossary[k] = {"source": k, "target": v, "category": "LLM_Extracted"}
                elif isinstance(v, dict):
                    target = v.get('target') or v.get('translation') or v.get('trans') or v.get('meaning')
                    if target:
                        all_llm_glossary[k] = {"source": v.get('source', k), "target": target, "category": v.get('category', "LLM_Extracted")}
            if isinstance(data, dict):
                for k, v in data.items():
                    process_item(k, v)

        # 处理 NER 结果
        for res in ner_results:
            data = clean_and_extract_json(res)
            names = data.get("names", []) if isinstance(data, dict) else data
            if names:
                name_mappings = glossary_manager.search_names("", known_names=names)
                for name, trans in name_mappings.items():
                    if name not in all_llm_glossary:
                        all_llm_glossary[name] = {"source": name, "target": trans, "category": "Proper Name (DB)"}
    
    full_text = "\n".join([b['content'] for b in blocks])
    final_glossary = {**all_llm_glossary, **glossary_manager.extract_terms(full_text)}
    glossary_manager.save_terms({k: v.get('target', str(v)) for k, v in all_llm_glossary.items()})
    return final_glossary

async def _do_single_request(stage: str, sub_blocks: List[Dict], config, glossary_text: str, use_context: bool, **kwargs) -> List[Dict]:
    """单次请求执行"""
    templates = get_prompt_templates(config.target_lang)
    expected_ids = {int(b['index']) for b in sub_blocks}

    if stage == "literal":
        input_data = [{"id": int(b['index']), "text": b['content']} for b in sub_blocks]
        msgs = [{"role": "user", "content": templates["LITERAL_TRANS"].format(glossary=glossary_text, json_input=json.dumps(input_data, ensure_ascii=False))}]
        tools = [{"type": "function", "function": {"name": "submit_literal_translation", "parameters": {"type": "object", "properties": {"translations": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "integer"}, "trans": {"type": "string"}}, "required": ["id", "trans"]}}}, "required": ["translations"]}}}]
        raw = await call_llm(config, msgs, temperature=config.temp_literal, tools=tools, response_format={"type": "json_object"})
        data = clean_and_extract_json(raw)
        res = data.get("translations", data)
    else:
        polish_input = [{"id": int(b['index']), "original": b['content'], "literal": kwargs.get('literal_map', {}).get(str(b['index']), b['content'])} for b in sub_blocks]
        msgs = [{"role": "user", "content": templates["REVIEW_AND_POLISH"].format(glossary=glossary_text, json_input=json.dumps(polish_input, ensure_ascii=False), previous_context=kwargs.get('previous_context', "None"), future_context=kwargs.get('future_context', "None"))}]
        tools = [{"type": "function", "function": {"name": "submit_polished_translation", "parameters": {"type": "object", "properties": {"results": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "integer"}, "polished": {"type": "string"}}, "required": ["id", "polished"]}}}, "required": ["results"]}}}]
        raw = await call_llm(config, msgs, temperature=config.temp_polish, tools=tools, response_format={"type": "json_object"})
        data = clean_and_extract_json(raw)
        res = data.get("results", data)

    if not isinstance(res, list) or len(res) != len(sub_blocks): return None
    returned_ids = {int(item['id']) for item in res if 'id' in item}
    if returned_ids != expected_ids: return None
    if stage == "polish":
        id_to_original = {int(b['index']): b['content'] for b in sub_blocks}
        for item in res: item['original'] = id_to_original.get(int(item['id']), "")
    return res

async def ladder_rescue_engine(blocks: List[Dict], config, glossary_text: str, stage: str, **kwargs) -> List[Dict]:
    """梯次重试逻辑"""
    ladder = [8, 6, 4, 2, 1]
    results = []
    running_context = kwargs.get('previous_context', "None")
    idx = 0
    while idx < len(blocks):
        success = False
        remaining = len(blocks) - idx
        for size in [s for s in ladder if s <= remaining]:
            chunk = blocks[idx:idx+size]
            res = await _do_single_request(stage, chunk, config, glossary_text, use_context=True, **{**kwargs, 'previous_context': running_context})
            if not res: res = await _do_single_request(stage, chunk, config, glossary_text, use_context=False, **kwargs)
            if res:
                results.extend(res)
                if stage == "polish":
                    new_ctx = "\n".join([f"- {item.get('original', '')} -> {item.get('polished', '')}" for item in res])
                    running_context = new_ctx if running_context == "None" else running_context + "\n" + new_ctx
                idx += size
                success = True
                break
        if not success:
            bad_block = blocks[idx]
            if stage == "literal": results.append({"id": int(bad_block['index']), "trans": bad_block['content']})
            else: results.append({"id": int(bad_block['index']), "polished": bad_block['content']})
            idx += 1
    return results

async def process_literal_stage(batch_blocks, config, glossary):
    batch_text = " ".join([b['content'] for b in batch_blocks])
    relevant_glossary = filter_relevant_glossary(batch_text, glossary)
    glossary_text = json.dumps(relevant_glossary, ensure_ascii=False)
    trans_list = await ladder_rescue_engine(batch_blocks, config, glossary_text, stage="literal")
    return {str(item['id']): item.get('trans', '') for item in trans_list if 'id' in item}, glossary_text

async def process_polish_stage(batch_blocks, config, literal_map, glossary_text, previous_context="", future_context=""):
    polished_list = await ladder_rescue_engine(batch_blocks, config, glossary_text, stage="polish", literal_map=literal_map, previous_context=previous_context, future_context=future_context)
    polish_map = {str(item['id']): item.get('polished', '') for item in polished_list if 'id' in item}
    return [{"index": b['index'], "timestamp": b['timestamp'], "original": b['content'], "polished": polish_map.get(str(b['index']), b['content'])} for b in batch_blocks]
```

### 2.2 `subtitle/core/llm_client.py`
```python
# -*- coding: utf-8 -*-
import json
import re
import time
import asyncio
import aiohttp
import logging
import hashlib
from typing import List, Dict, Optional, Union
from json_repair import repair_json
from .request_handler import AsyncRateLimitedSession, SmartLoadBalancer

logger = logging.getLogger(__name__)
_session_pool = {}
_balancer_pool = {}

def get_session(config, use_smart_balancer=True):
    global _session_pool, _balancer_pool
    raw_api_key = getattr(config, 'api_key', "")
    api_keys = [k.strip() for k in re.split(r'[,\uff0c\s\n]+', raw_api_key) if k.strip()]
    if not api_keys: return None

    balancer_key = hashlib.md5(f"{','.join(api_keys)}{config.api_url}{use_smart_balancer}".encode()).hexdigest()
    if balancer_key in _balancer_pool: return _balancer_pool[balancer_key]

    sessions = []
    for key in api_keys:
        session_id = hashlib.md5(f"{key}{config.api_url}".encode()).hexdigest()
        if session_id not in _session_pool:
            _session_pool[session_id] = AsyncRateLimitedSession(api_key=key, rpm=config.rpm_limit, tpm=config.tpm_limit, concurrency=config.max_concurrent_requests)
        sessions.append(_session_pool[session_id])

    balancer = SmartLoadBalancer(sessions, max_retries=config.max_retries) if len(sessions) > 1 else sessions[0]
    _balancer_pool[balancer_key] = balancer
    return balancer

def clean_and_extract_json(text):
    if not text: return []
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    json_str = match.group(1).strip() if match else text.strip()
    try: return json.loads(json_str)
    except:
        try: return json.loads(repair_json(json_str))
        except: return []

async def _do_llm_request(session, config, payload, timeout=120):
    response = await session.post(config.api_url, json=payload, timeout=timeout)
    if response.status != 200: raise Exception(f"API Error {response.status}: {await response.text()}")
    data = await response.json()
    message = data['choices'][0]['message']
    if "tool_calls" in message: return message["tool_calls"][0]["function"].get("arguments", "")
    return message.get('content', "").strip()

async def call_llm(config, messages, temperature=0.5, tools=None, response_format=None):
    payload = {"model": config.model_name, "messages": messages, "temperature": temperature, "max_tokens": config.max_tokens, "stream": False}
    if response_format: payload["response_format"] = response_format
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = {"type": "function", "function": {"name": tools[0]["function"]["name"]}}
    
    session = get_session(config)
    if isinstance(session, SmartLoadBalancer):
        return await session.execute(lambda s: _do_llm_request(s, config, payload))
    return await _do_llm_request(session, config, payload)

async def call_llm_batch(config, batch_messages, temperature=0.5, tools=None, response_format=None, progress_callback=None):
    session = get_session(config)
    if not isinstance(session, SmartLoadBalancer):
        return await asyncio.gather(*[call_llm(config, m, temperature, tools, response_format) for m in batch_messages])
    
    task_ids = []
    for idx, messages in enumerate(batch_messages):
        payload = {"model": config.model_name, "messages": messages, "temperature": temperature, "max_tokens": config.max_tokens, "stream": False}
        if response_format: payload["response_format"] = response_format
        if tools: payload["tools"] = tools; payload["tool_choice"] = {"type": "function", "function": {"name": tools[0]["function"]["name"]}}
        task_ids.append((idx, await session.submit(lambda s, p=payload: _do_llm_request(s, config, p))))
    
    results = {}
    for idx, tid in task_ids:
        results[idx] = await session.wait_for_task(tid)
        if progress_callback: progress_callback(len(results), len(batch_messages))
    return [results[i] for i in range(len(batch_messages))]

def get_load_balancer_stats(config):
    key = hashlib.md5(f"{getattr(config, 'api_key', '')}{config.api_url}True".encode()).hexdigest()
    return _balancer_pool[key].get_stats() if key in _balancer_pool and isinstance(_balancer_pool[key], SmartLoadBalancer) else None
```

### 2.3 `subtitle/core/request_handler.py`
```python
# -*- coding: utf-8 -*-
import asyncio
import time
import collections
import aiohttp
import logging
from typing import Optional, Dict, Any, List, Callable

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, rpm, tpm):
        self.rpm, self.tpm = rpm, tpm
        self.request_interval = 60.0 / rpm if rpm > 0 else 0
        self.last_request_time = 0.0
        self.token_window = collections.deque()
        self.lock = asyncio.Lock()

    async def wait_async(self, est_tokens=0):
        while True:
            async with self.lock:
                now = time.time()
                while self.token_window and now - self.token_window[0][0] > 60: self.token_window.popleft()
                current_tpm = sum(item[1] for item in self.token_window)
                wait_rpm = max(0, self.request_interval - (now - self.last_request_time))
                wait_tpm = 60 - (now - self.token_window[0][0]) if self.tpm > 0 and current_tpm + est_tokens > self.tpm else 0
                wait = max(wait_rpm, wait_tpm)
                if wait <= 0:
                    self.last_request_time = now
                    return
            await asyncio.sleep(wait)

class AsyncRateLimitedSession:
    def __init__(self, api_key, rpm=60, tpm=100000, concurrency=4):
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self.limiter = RateLimiter(rpm, tpm)
        self.semaphore = asyncio.Semaphore(concurrency)
        self._session = None

    async def post(self, url, **kwargs):
        if not self._session: self._session = aiohttp.ClientSession(headers=self.headers)
        async with self.semaphore:
            await self.limiter.wait_async(1000)
            resp = await self._session.post(url, **kwargs)
            if resp.status == 200:
                data = await resp.json()
                self.limiter.token_window.append((time.time(), data.get("usage", {}).get("total_tokens", 1000)))
            return resp

class SmartLoadBalancer:
    def __init__(self, sessions, max_retries=3):
        self.sessions = sessions
        self.max_retries = max_retries
        self.queue = asyncio.Queue()
        self.results = {}
        self._workers = []

    async def submit(self, func):
        tid = f"t_{time.time()}_{id(func)}"
        await self.queue.put((tid, func))
        if not self._workers:
            for i in range(sum(s.semaphore._value for s in self.sessions)):
                self._workers.append(asyncio.create_task(self._worker()))
        return tid

    async def _worker(self):
        while True:
            tid, func = await self.queue.get()
            for attempt in range(self.max_retries):
                s = self.sessions[attempt % len(self.sessions)]
                try:
                    self.results[tid] = await func(s)
                    break
                except Exception as e:
                    if attempt == self.max_retries - 1: self.results[tid] = e
            self.queue.task_done()

    async def wait_for_task(self, tid):
        while tid not in self.results: await asyncio.sleep(0.1)
        res = self.results.pop(tid)
        if isinstance(res, Exception): raise res
        return res

    async def execute(self, func):
        return await self.wait_for_task(await self.submit(func))
```

---

## 3. 支撑组件 (Supporting Components)

### 3.1 `subtitle/core/glossary_manager.py`
(内容详见源码，包含术语增量更新、SQLite 持久化及 Flashtext 匹配逻辑)

### 3.2 `subtitle/core/config.py`
```python
# -*- coding: utf-8 -*-
import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()

@dataclass
class TranslationConfig:
    api_key: str = os.getenv("LLM_API_KEY", "")
    api_url: str = os.getenv("LLM_API_URL", "http://localhost:19183/v1/chat/completions")
    model_name: str = os.getenv("LLM_MODEL_NAME", "openai/gpt-oss-20b")
    ner_model_name: str = os.getenv("NER_MODEL_NAME", "glm-4-flash")
    max_concurrent_requests: int = int(os.getenv("MAX_CONCURRENT_REQUESTS", "4"))
    rpm_limit: int = int(os.getenv("RPM_LIMIT", "60"))
    tpm_limit: int = int(os.getenv("TPM_LIMIT", "100000"))
    batch_size: int = int(os.getenv("BATCH_SIZE", "8"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    retry_delay: float = float(os.getenv("RETRY_DELAY", "2.0"))
    max_tokens: int = int(os.getenv("MAX_TOKENS", "4096"))
    target_lang: str = "zh"
    temp_terms: float = 0.1
    temp_literal: float = 0.3
    temp_polish: float = 0.5
    enable_llm_discovery: bool = True
    enable_names_db: bool = False
```

### 3.3 `subtitle/core/srt_utils.py`
```python
# -*- coding: utf-8 -*- 
import re

def clean_content(content):
    cleaned = re.sub(r'\[.*?\]|\(.*?\)', '', content)
    return '\n'.join([l.strip() for l in cleaned.split('\n') if l.strip()])

def parse_srt(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read().lstrip('﻿').replace('\r\n', '\n')
    blocks = []
    for b in content.split('\n\n'):
        lines = b.strip().split('\n')
        if len(lines) >= 3 and '-->' in lines[1]:
            text = clean_content("\n".join(lines[2:]))
            if text: blocks.append({'index': lines[0], 'timestamp': lines[1], 'content': text})
    return blocks
```

---

## 4. Prompt 模板 (Prompt Templates)

### 4.1 `subtitle/prompts/literal_trans.prompt`
(直译指令：强调 ID 对应，严禁合并或漏行)

### 4.2 `subtitle/prompts/review_and_polish.prompt`
(润色指令：Netflix 资深组长角色，处理滑动窗口上下文)

### 4.3 `subtitle/prompts/term_extract.prompt`
(术语提取：采样提取专有名词和专业术语)
