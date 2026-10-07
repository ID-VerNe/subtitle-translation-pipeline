# -*- coding: utf-8 -*-
from typing import List, Dict
from tqdm import tqdm

from network.llm_client import call_llm, call_llm_batch, clean_and_extract_json, get_load_balancer_stats
from core.prompts import get_prompt_templates
from core.glossary_manager import glossary_manager
from core.glossary_sanitizer import sanitize_glossary


# @lat: [[core-glossary#Key Concepts#全局术语提取（extract_global_terms）]]
async def extract_global_terms(config, blocks: List[Dict]) -> Dict[str, dict]:
    """提取术语（集成 LLM NER 人名提取），使用批量队列模式"""
    templates = get_prompt_templates(config.target_lang)
    
    num_passes = max(5, (len(blocks) + 99) // 100)
    print(f"=== Step 1: 构建术语表 (动态 {num_passes} 步循环采样) ===")
    
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
        print(f"  🚀 发起 {len(tasks)} 个术语提取任务 + {len(ner_tasks)} 个 NER 人名任务...")
        
        all_results = []
        
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
        
        ner_results = []
        for ner_config, ner_msgs in ner_tasks:
            result = await call_llm(ner_config, ner_msgs, temperature=0.0, response_format={"type": "json_object"})
            ner_results.append(result)
            pbar.update(1)
        
        pbar.close()

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

        for res in ner_results:
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
    
    final_glossary = sanitize_glossary(final_glossary)
    
    if final_glossary:
        simple_save = {k: v.get('target', str(v)) if isinstance(v, dict) else v for k, v in final_glossary.items()}
        glossary_manager.save_terms(simple_save)
    
    stats = get_load_balancer_stats(config)
    if stats:
        print(f"\n  📊 API 统计:")
        for api_stat in stats['apis']:
            print(f"     API {api_stat['api_index']}: 成功率 {api_stat['success_rate']:.1%}, "
                  f"响应时间 {api_stat['avg_response_time']:.2f}s, "
                  f"可用槽位 {api_stat['available_slots']}")
    
    print(f"  ✅ 最终术语表包含 {len(final_glossary)} 条目")
    return final_glossary
