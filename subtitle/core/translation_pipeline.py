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
from .cache_utils import canonical_json

logger = logging.getLogger(__name__)

def build_recent_state(final_blocks: List[Dict], max_lines: int = 2) -> Dict:
    """
    构建极小动态上下文，替代上一批完整 原文 -> 译文 回灌。
    只保留最近 1-2 行，用于解决紧邻代词、省略、语气延续。
    """
    if not final_blocks:
        return {}

    recent = final_blocks[-max_lines:]

    return {
        "last_ids": [int(b["index"]) for b in recent if str(b.get("index", "")).isdigit()],
        "last_translations": [b.get("polished", "") for b in recent],
        "usage": "Only use this for immediate pronoun resolution or sentence continuation."
    }


def build_core_terms(full_glossary: Dict[str, dict], limit: int = 80) -> Dict[str, dict]:
    """
    构建全片稳定核心术语。
    简化版：先取前 limit 个。
    后续可以按频率、category、人工标记优化。
    """
    items = list(full_glossary.items())[:limit]
    return {
        src: info
        for src, info in items
    }


def build_glossary_payload(core_terms: Dict[str, dict], local_terms: Dict[str, dict]) -> str:
    payload = {
        "core_terms": core_terms,
        "local_terms": local_terms
    }
    return canonical_json(payload)

def filter_relevant_glossary(text_content: str, full_glossary: Dict[str, dict]) -> Dict[str, dict]:
    relevant = {}
    text_lower = text_content.lower()
    for src, info in full_glossary.items():
        if src.lower() in text_lower:
            relevant[src] = info
            
    # [集成人名库查询]
    # 传入已在术语库中发现的词作为排除列表
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
    """提取术语（集成 LLM NER 人名提取），使用批量队列模式"""
    templates = get_prompt_templates(config.target_lang)
    
    # 动态计算采样步数：每 100 块对应 1 步，最少 5 步
    num_passes = max(5, (len(blocks) + 99) // 100)
    print(f"=== Step 1: 构建术语表 (动态 {num_passes} 步循环采样) ===")
    
    all_llm_glossary = {}
    tasks = []
    ner_tasks = []
    
    # 创建术语提取与 NER 任务
    for pass_idx in range(num_passes):
        sampled_text = ""
        for i in range(pass_idx, len(blocks), num_passes):
            sampled_text += blocks[i]['content'] + "\n"
        
        MAX_SAMPLE_LEN = 4000
        text_parts = [sampled_text[i:i+MAX_SAMPLE_LEN] for i in range(0, len(sampled_text), MAX_SAMPLE_LEN)]
        
        for part_text in text_parts:
            # 术语提取 (使用主模型)
            messages = [{"role": "user", "content": templates["TERM_EXTRACT"].format(content=part_text)}]
            tasks.append((messages, config.temp_terms, {"type": "json_object"}))
            
            # NER 人名识别 (使用专用配置)
            if pass_idx == 0:
                from dataclasses import replace
                ner_msgs = [{"role": "user", "content": templates["NER_NAMES"].format(content=part_text)}]
                # 使用 replace 官方方法克隆并修改字段
                ner_config = replace(config, 
                    model_name=config.ner_model_name,
                    api_key=config.ner_api_key,
                    api_url=config.ner_api_url
                )
                ner_tasks.append((ner_config, ner_msgs))

    if tasks or ner_tasks:
        print(f"  🚀 发起 {len(tasks)} 个术语提取任务 + {len(ner_tasks)} 个 NER 人名任务...")
        
        # 使用批量调用模式
        all_results = []
        
        # 术语提取任务
        if tasks:
            term_messages = [t[0] for t in tasks]
            pbar = tqdm(total=len(tasks) + len(ner_tasks), desc="术语提取中")
            
            def update_progress(completed, total):
                pbar.n = completed
                pbar.refresh()
            
            term_results = await call_llm_batch(
                config, 
                term_messages, 
                temperature=config.temp_terms,
                response_format={"type": "json_object"},
                progress_callback=update_progress
            )
            all_results.extend(term_results)
        
        # NER 任务（使用不同配置，需要单独处理）
        ner_results = []
        for ner_config, ner_msgs in ner_tasks:
            result = await call_llm(ner_config, ner_msgs, temperature=0.0, response_format={"type": "json_object"})
            ner_results.append(result)
            pbar.update(1)
        
        pbar.close()

        # A. 处理术语结果
        for result in term_results:
            data = clean_and_extract_json(result)
            def process_item(k, v):
                if isinstance(v, str):
                    all_llm_glossary[k] = {"source": k, "target": v, "category": "LLM_Extracted"}
                elif isinstance(v, dict):
                    target = v.get('target') or v.get('translation') or v.get('trans') or v.get('meaning')
                    if target:
                        all_llm_glossary[k] = {"source": v.get('source', k), "target": target, "category": v.get('category', "LLM_Extracted")}
                    else:
                        for sub_k, sub_v in v.items():
                            process_item(sub_k, sub_v)

            if isinstance(data, dict):
                for k, v in data.items():
                    if k.lower() in ['terms', 'glossary'] and isinstance(v, (list, dict)):
                        if isinstance(v, list):
                            for item in v:
                                if isinstance(item, dict):
                                    src = item.get('source') or item.get('term') or item.get('src')
                                    tgt = item.get('target') or item.get('translation') or item.get('tgt')
                                    if src and tgt:
                                        all_llm_glossary[src] = {"source": src, "target": tgt, "category": "LLM_Extracted"}
                        else:
                            for sub_k, sub_v in v.items():
                                process_item(sub_k, sub_v)
                    else:
                        process_item(k, v)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        src = item.get('source') or item.get('term') or item.get('src')
                        tgt = item.get('target') or item.get('translation') or item.get('tgt')
                        if src and tgt:
                            all_llm_glossary[src] = {"source": src, "target": tgt, "category": "LLM_Extracted"}

        # B. 处理 NER 结果
        for res in ner_results:
            # 这里的 res 是 call_llm 的原始字符串输出，由 fetch_names_with_llm 内部处理
            # 但因为在 extract_global_terms 中我们是并发发起的，
            # 所以我们在这里提取出名字，再统一查库
            data = clean_and_extract_json(res)
            names = []
            if isinstance(data, dict) and "names" in data:
                names = data["names"]
            elif isinstance(data, list):
                names = data
            
            if names:
                name_mappings = glossary_manager.search_names("", known_names=names)
                for name, trans in name_mappings.items():
                    if name not in all_llm_glossary:
                        all_llm_glossary[name] = {"source": name, "target": trans, "category": "Proper Name (DB)"}
    
    full_text = "\n".join([b['content'] for b in blocks])
    historical_glossary = glossary_manager.extract_terms(full_text)
    final_glossary = {**all_llm_glossary, **historical_glossary}
    
    if all_llm_glossary:
        simple_save = {k: v.get('target', str(v)) if isinstance(v, dict) else v for k, v in all_llm_glossary.items()}
        glossary_manager.save_terms(simple_save)
    
    # 打印负载均衡器统计信息
    stats = get_load_balancer_stats(config)
    if stats:
        print(f"\n  📊 API 统计:")
        for api_stat in stats['apis']:
            print(f"     API {api_stat['api_index']}: 成功率 {api_stat['success_rate']:.1%}, "
                  f"响应时间 {api_stat['avg_response_time']:.2f}s, "
                  f"可用槽位 {api_stat['available_slots']}")
    
    print(f"  ✅ 最终术语表包含 {len(final_glossary)} 条目")
    return final_glossary

async def _do_single_request(stage: str, sub_blocks: List[Dict], config, core_glossary_text: str, local_glossary_text: str, use_context: bool, **kwargs) -> List[Dict]:
    """执行单次 API 请求并进行严格的 ID 校验"""
    templates = get_prompt_templates(config.target_lang)
    expected_ids = {int(b['index']) for b in sub_blocks}

    if stage == "literal":
        input_data = [{"id": int(b['index']), "text": b['content']} for b in sub_blocks]
        c_text = core_glossary_text if use_context else "{}"
        l_text = local_glossary_text if use_context else "{}"
        msgs = [{"role": "user", "content": templates["LITERAL_TRANS"].format(
            core_glossary=c_text, local_glossary=l_text, json_input=canonical_json(input_data)
        )}]
        
        tools = [{
            "type": "function",
            "function": {
                "name": "submit_literal_translation",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "translations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "integer"},
                                    "trans": {"type": "string"}
                                },
                                "required": ["id", "trans"]
                            }
                        }
                    },
                    "required": ["translations"]
                }
            }
        }]
        
        raw = await call_llm(config, msgs, temperature=config.temp_literal, tools=tools, response_format={"type": "json_object"})
        data = clean_and_extract_json(raw)
        if isinstance(data, dict) and "translations" in data:
            res = data["translations"]
        else:
            res = data
    else:
        polish_input = []
        for b in sub_blocks:
            lit_text = kwargs.get('literal_map', {}).get(str(b['index']), b['content'])
            polish_input.append({"id": int(b['index']), "original": b['content'], "literal": lit_text})
        
        ctx = kwargs.get('previous_context', "None") if use_context else "None"
        f_ctx = kwargs.get('future_context', "None") if use_context else "None"
        c_text = core_glossary_text if use_context else "{}"
        l_text = local_glossary_text if use_context else "{}"

        msgs = [{"role": "user", "content": templates["REVIEW_AND_POLISH"].format(
            core_glossary=c_text, 
            local_glossary=l_text,
            global_profile=kwargs.get("global_profile", "{}"),
            translation_policy=kwargs.get("translation_policy", "{}"),
            scene_guidance=kwargs.get("scene_guidance", "{}"),
            json_input=canonical_json(polish_input),
            previous_context=ctx,
            future_context=f_ctx
        )}]
        
        tools = [{
            "type": "function",
            "function": {
                "name": "submit_polished_translation",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "results": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "integer"},
                                    "polished": {"type": "string"}
                                },
                                "required": ["id", "polished"]
                            }
                        }
                    },
                    "required": ["results"]
                }
            }
        }]
        
        raw = await call_llm(config, msgs, temperature=config.temp_polish, tools=tools, response_format={"type": "json_object"})
        data = clean_and_extract_json(raw)
        if isinstance(data, dict) and "results" in data:
            res = data["results"]
        else:
            res = data

    # 规范化结果格式
    if not isinstance(res, list):
        return None

    final_res = []
    for item in res:
        if not isinstance(item, dict) or 'id' not in item:
            continue
        
        # 鲁棒性提取：兼容多种可能的键名
        translated_text = ""
        if stage == "literal":
            translated_text = item.get("trans") or item.get("translation") or item.get("target") or item.get("text") or ""
        else:
            translated_text = item.get("polished") or item.get("translation") or item.get("target") or item.get("text") or ""
            
        final_res.append({
            "id": int(item["id"]),
            "trans" if stage == "literal" else "polished": translated_text
        })

    if len(final_res) != len(sub_blocks):
        logger.warning(f"[{stage.upper()}] 长度或格式不匹配: 期望 {len(sub_blocks)}, 实际 {len(final_res)}。")
        return None

    returned_ids = {item["id"] for item in final_res}
    if returned_ids != expected_ids:
        logger.warning(f"[{stage.upper()}] ID 不匹配。")
        return None

    if stage == "polish":
        id_to_original = {int(b['index']): b['content'] for b in sub_blocks}
        for item in final_res:
            item['original'] = id_to_original.get(item['id'], "")

    return final_res

async def ladder_rescue_engine(blocks: List[Dict], config, core_glossary_text: str, local_glossary_text: str, stage: str, **kwargs) -> List[Dict]:
    """梯次拯救引擎：动态适配输入大小 + 三级环境剥离策略"""
    input_size = len(blocks)
    base_ladder = [input_size, 12, 10, 8, 6, 4, 2, 1]
    ladder = sorted(list(set(base_ladder)), reverse=True)
    
    results = []
    # 记录原始动态上下文
    original_context = kwargs.get('previous_context', "None")
    original_future = kwargs.get('future_context', "None")
    original_scene = kwargs.get('scene_guidance', "{}")
    
    idx = 0
    while idx < len(blocks):
        success = False
        remaining = len(blocks) - idx
        # 仅尝试小于等于剩余数量的尺寸
        available_sizes = [s for s in ladder if s <= remaining]
        
        for size in available_sizes:
            chunk = blocks[idx:idx+size]
            
            # --- 拯救梯次策略 ---
            
            # TIER 1: 完整上下文 (最强理解力)
            t1_kwargs = {**kwargs, 'previous_context': original_context, 'future_context': original_future, 'scene_guidance': original_scene}
            res = await _do_single_request(stage, chunk, config, core_glossary_text, local_glossary_text, use_context=True, **t1_kwargs)
            if res:
                results.extend(res)
                idx += size
                success = True
                break
                
            # TIER 2: 剥离近场动态记忆，保留场景摘要 (中等理解力，更高稳定性)
            t2_kwargs = dict(t1_kwargs)
            t2_kwargs["previous_context"] = "None"
            t2_kwargs["future_context"] = "None"
            res = await _do_single_request(stage, chunk, config, core_glossary_text, local_glossary_text, use_context=False, **t2_kwargs)
            if res:
                results.extend(res)
                idx += size
                success = True
                break
            
            # TIER 3: 剥离场景摘要，仅保留全局画像、策略与核心术语 (极简模式，最大成功率)
            t3_kwargs = dict(t2_kwargs)
            t3_kwargs["scene_guidance"] = "{}"
            res = await _do_single_request(stage, chunk, config, core_glossary_text, local_glossary_text, use_context=False, **t3_kwargs)
            if res:
                results.extend(res)
                idx += size
                success = True
                break
                
        if not success:
            # 彻底失败：保底逻辑 (返回原文)
            bad_block = blocks[idx]
            if stage == "literal":
                res_item = {"id": int(bad_block['index']), "trans": bad_block['content']}
                results.append(res_item)
            else:
                lit = kwargs.get('literal_map', {}).get(str(bad_block['index']), bad_block['content'])
                res_item = {"id": int(bad_block['index']), "polished": lit}
                results.append(res_item)
            idx += 1
            
    return results

async def process_literal_stage(batch_blocks: List[Dict], config, glossary: Dict[str, str], core_glossary_text: str = "{}") -> Tuple[Dict[str, str], str]:
    batch_text_all = " ".join([b['content'] for b in batch_blocks])
    local_terms = filter_relevant_glossary(batch_text_all, glossary)
    local_glossary_text = canonical_json(local_terms)

    trans_list = await ladder_rescue_engine(
        batch_blocks,
        config,
        core_glossary_text,
        local_glossary_text,
        stage="literal"
    )

    return {
        str(item['id']): item.get('trans', '')
        for item in trans_list
        if 'id' in item
    }, local_glossary_text

def postprocess_translation(original: str, translation: str) -> str:
    """
    后处理翻译内容：如果原文中不含括号，则移除译文中由 LLM 擅自添加的解释性括号及其内容。
    """
    # 检查原文是否包含任何形式的括号
    if not re.search(r'[\(\)（）]', original):
        # 移除译文中的括号内容，包括全角和半角及其中的内容
        # 使用正则表达式匹配成对的括号
        cleaned = re.sub(r'[\(（].*?[\)）]', '', translation)
        # 清理可能留下的多余空格
        cleaned = cleaned.strip()
        return cleaned or translation # 如果清理后变为空（虽然不太可能），保留原样
    return translation

async def process_polish_stage(
    batch_blocks: List[Dict], 
    config, 
    literal_map: Dict[str, str], 
    core_glossary_text: str = "{}",
    local_glossary_text: str = "{}", 
    previous_context: str = "", 
    future_context: str = "",
    recent_state: str = "",
    global_profile: str = "{}",
    translation_policy: str = "{}",
    scene_guidance: str = "{}"
) -> List[Dict]:
    polished_list = await ladder_rescue_engine(
        batch_blocks, config, core_glossary_text, local_glossary_text, stage="polish",
        literal_map=literal_map,
        previous_context=recent_state or previous_context,
        future_context=future_context,
        global_profile=global_profile,
        translation_policy=translation_policy,
        scene_guidance=scene_guidance
    )
    polish_map = {str(item['id']): item.get('polished', '') for item in polished_list if 'id' in item}
    final_blocks = []
    for block in batch_blocks:
        idx = str(block['index'])
        final_text = polish_map.get(idx) or literal_map.get(idx) or block['content']
        
        # 应用后处理：移除不必要的解释性括号
        final_text = postprocess_translation(block['content'], final_text)
        
        final_blocks.append({
            "index": block['index'], "timestamp": block['timestamp'],
            "original": block['content'], "polished": final_text
        })
    return final_blocks
