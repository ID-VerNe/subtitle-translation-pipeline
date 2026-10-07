# -*- coding: utf-8 -*-
from network.llm_client import ContentRefusalError
from core.safety_fuzzer import safety_fuzzer
import logging
import re
from typing import List, Dict, Tuple

from core.llm_client import call_llm, clean_and_extract_json, REFUSAL_SENTINEL
from core.prompts import get_prompt_templates
from core.cache_utils import canonical_json

logger = logging.getLogger(__name__)


# @lat: [[core-rescue#Key Concepts#单次请求执行（_do_single_request）]]
async def _do_single_request(stage: str, sub_blocks: List[Dict], config, core_glossary_text: str, local_glossary_text: str, **kwargs) -> List[Dict]:
    """执行单次 API 请求并进行严格的 ID 校验"""
    try:
        templates = get_prompt_templates(config.target_lang)
        expected_ids = {int(b['index']) for b in sub_blocks}

        if stage == "literal":
            input_data = [{"id": int(b['index']), "text": b['content']} for b in sub_blocks]
            c_text = core_glossary_text
            l_text = local_glossary_text
            msgs = [{"role": "user", "content": templates["LITERAL_TRANS"].format(
                core_glossary=c_text, local_glossary=l_text,
                global_profile=kwargs.get("global_profile", "{}"),
                translation_policy=kwargs.get("translation_policy", "{}"),
                scene_guidance=kwargs.get("scene_guidance", "{}"),
                previous_context=kwargs.get("previous_context", "None"),
                future_context=kwargs.get("future_context", "None"),
                json_input=canonical_json(input_data)
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
            
            raw = await call_llm(config, msgs, temperature=config.temp_literal, tools=tools, response_format={"type": "json_object"}, raise_on_refusal=True)
            if raw is REFUSAL_SENTINEL:
                return ("__REFUSAL__", expected_ids)
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
            
            ctx = kwargs.get('previous_context', "None")
            f_ctx = kwargs.get('future_context', "None")
            c_text = core_glossary_text
            l_text = local_glossary_text

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
            
            raw = await call_llm(config, msgs, temperature=config.temp_polish, tools=tools, response_format={"type": "json_object"}, raise_on_refusal=True)
            if raw is REFUSAL_SENTINEL:
                return ("__REFUSAL__", expected_ids)
            data = clean_and_extract_json(raw)
            if isinstance(data, dict) and "results" in data:
                res = data["results"]
            else:
                res = data

        if not isinstance(res, list):
            return None

        final_res = []
        def _scrub(text):
            if not isinstance(text, str): return text
            text = re.sub(r'([\u4e00-\u9fa5]+)/[\u4e00-\u9fa5]+', r'\1', text)
            text = re.sub(r'（(注：|听音|意思).*?）', '', text)
            text = re.sub(r'\((注：|听音|意思).*?\)', '', text)
            return text

        for item in res:
            if not isinstance(item, dict) or 'id' not in item:
                continue
            
            if 'trans' in item:
                item['trans'] = _scrub(item['trans'])
            if 'polished' in item:
                item['polished'] = _scrub(item['polished'])
            
            raw_id = item["id"]
            try:
                if isinstance(raw_id, int):
                    item_id = raw_id
                elif isinstance(raw_id, str):
                    match = re.search(r'\d+', raw_id)
                    if match:
                        item_id = int(match.group())
                    else:
                        logger.warning(f"无法从 ID 中提取整数: {raw_id}")
                        continue
                else:
                    item_id = int(raw_id)
            except (ValueError, TypeError) as e:
                logger.warning(f"ID 解析失败: {raw_id} -> {e}")
                continue
            
            translated_text = ""
            if stage == "literal":
                translated_text = item.get("trans") or item.get("translation") or item.get("target") or item.get("text") or ""
            else:
                translated_text = item.get("polished") or item.get("translation") or item.get("target") or item.get("text") or ""
                
            final_res.append({
                "id": item_id,
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
    
    except Exception as e:
        logger.error(f"[{stage.upper()}] 请求处理异常: {e}", exc_info=True)
        return None


# @lat: [[core-rescue#Key Concepts#降级梯次（Batch-Size Ladder）]]
def _build_ladder(input_size: int) -> List[int]:
    """生成从 input_size 收敛到 1 的降级阶梯。"""
    if input_size <= 1:
        return [1]

    ladder = [input_size]
    cur = input_size
    while cur > 1:
        nxt = max(1, cur // 2)
        if nxt == cur:
            nxt = cur - 1
        ladder.append(nxt)
        cur = nxt
    seen = []
    for s in ladder:
        if s not in seen:
            seen.append(s)
    return seen


# @lat: [[core-rescue#Key Concepts#兜底策略（Fallback）]]
async def ladder_rescue_engine(blocks: List[Dict], config, core_glossary_text: str, local_glossary_text: str, stage: str, **kwargs) -> List[Dict]:
    """梯次拯救引擎：失败时缩小 batch 重试"""
    input_size = len(blocks)
    ladder = _build_ladder(input_size)
    ladder = sorted(list(set(ladder)), reverse=True)

    results = []
    refused_ids: set[int] = set()

    idx = 0
    while idx < len(blocks):
        success = False
        remaining = len(blocks) - idx
        available_sizes = [s for s in ladder if s <= remaining]

        for size in available_sizes:
            chunk = blocks[idx:idx+size]
            chunk_ids = {int(b['index']) for b in chunk}

            if chunk_ids <= refused_ids:
                continue

            res = await _do_single_request(stage, chunk, config, core_glossary_text, local_glossary_text, **kwargs)
            if isinstance(res, tuple) and res[0] == "__REFUSAL__":
                if size == 1:
                    refused_ids.update(res[1])
                    # 调用探雷器清洗这个具体的块
                    await safety_fuzzer.heal_blocks(chunk)
                    # 再次尝试执行这个单行（自愈后应该可以通过了，除非有多个违禁词，这里简化为继续）
                    # 为了稳定，直接 break，下一次如果还有同样的词，早就被全局替换了
                    break
                continue

            if res:
                results.extend(res)
                idx += size
                success = True
                break

        if not success:
            bad_block = blocks[idx]
            refused_ids.discard(int(bad_block['index']))
            if stage == "literal":
                res_item = {"id": int(bad_block['index']), "trans": bad_block['content']}
                results.append(res_item)
            else:
                lit = kwargs.get('literal_map', {}).get(str(bad_block['index']), bad_block['content'])
                res_item = {"id": int(bad_block['index']), "polished": lit}
                results.append(res_item)
            idx += 1

    return results
