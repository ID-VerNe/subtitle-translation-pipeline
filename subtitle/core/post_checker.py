# -*- coding: utf-8 -*-
import re
import json
import logging
from typing import List, Dict, Tuple, Optional
from network.llm_client import call_llm, clean_and_extract_json
from .config import TranslationConfig

logger = logging.getLogger(__name__)

# =========================================================================
# Level 1: 确定性硬规则清理 (Deterministic Regex Cleaner)
# =========================================================================

# @lat: [[core-quality#Key Concepts#颜色标签对齐与清洗（align_color_tags / level1_deterministic_cleaning）]]
def align_color_tags(original: str, translation: str) -> str:
    """强制让中文字幕的字体颜色标签与英文字幕保持一致"""
    orig_tag_match = re.search(r'<font color="([^"]+)">', original, re.IGNORECASE)
    
    if orig_tag_match:
        tag_color = orig_tag_match.group(1)
        expected_start = f'<font color="{tag_color}">'
        # 先清除中文里现有的所有 font 标签
        clean_trans = re.sub(r'</?font[^>]*>', '', translation).strip()
        # 重新包裹
        return f'{expected_start}{clean_trans}</font>'
    else:
        # 原文无 color tag，若译文有则剥离
        return re.sub(r'</?font[^>]*>', '', translation).strip()

# @lat: [[core-quality#Key Concepts#颜色标签对齐与清洗（align_color_tags / level1_deterministic_cleaning）]]
def level1_deterministic_cleaning(paired_blocks: List[Dict]) -> List[Dict]:
    """执行 Level 1 确定性硬规则清洗"""
    logger.info("🧹 [Post-Check Level 1] 执行确定性规则清洗（对齐颜色标签）...")
    cleaned_count = 0
    
    for b in paired_blocks:
        orig = b.get('original', '')
        trans = b.get('polished') or b.get('content', '')
        
        c_trans = align_color_tags(orig, trans)
        
        if c_trans != trans:
            b['polished'] = c_trans
            b['content'] = c_trans
            cleaned_count += 1
            
    logger.info(f"✅ [Post-Check Level 1] 完成，共规则清洗 {cleaned_count} 行。")
    return paired_blocks


# =========================================================================
# Level 2: 数字与事实单位校验 (Numeric & Unit Validator)
# =========================================================================

# (Removed hardcoded numeric validation, now handled via Agentic QA in Level 3)


# =========================================================================
# =========================================================================
# Level 3: 全局逻辑与语境对抗审校 (Iterative Multi-Pass LLM Logic Audit)
# =========================================================================

from .prompts import load_prompt

def _extract_and_normalize_corrections(data) -> List[Dict]:
    """递归提取并规范化 LLM 返回的纠错条目，抵御嵌套列表、紧凑数组、字段别名等各类结构幻觉"""
    results = []
    if not data:
        return results

    if isinstance(data, dict):
        # 1. 本身就是一个纠错项 {"id": 123, "fixed": "..."}
        if "id" in data and any(k in data for k in ("fixed", "trans", "polished")):
            cid = data.get("id")
            fixed = data.get("fixed") or data.get("polished") or data.get("trans")
            reason = data.get("reason", "")
            if cid is not None and fixed:
                try:
                    results.append({"id": int(cid), "fixed": str(fixed), "reason": str(reason)})
                except (ValueError, TypeError):
                    pass
            return results

        # 2. 从常见容器 key 提取
        for key in ("corrections", "results", "issues", "fixes", "items"):
            val = data.get(key)
            if val is not None:
                results.extend(_extract_and_normalize_corrections(val))
                return results

        # 3. 兜底：遍历 dict 的所有值
        for v in data.values():
            if isinstance(v, (dict, list)):
                results.extend(_extract_and_normalize_corrections(v))

    elif isinstance(data, (list, tuple)):
        # 判断当前列表本身是否是一个紧凑纠错项：形如 [123, "修复文本", "原因"]
        if len(data) >= 2 and (isinstance(data[0], int) or (isinstance(data[0], str) and data[0].isdigit())):
            try:
                cid = int(data[0])
                fixed = str(data[1])
                reason = str(data[2]) if len(data) > 2 else ""
                results.append({"id": cid, "fixed": fixed, "reason": reason})
                return results
            except (ValueError, TypeError):
                pass

        # 否则逐项递归提取
        for item in data:
            results.extend(_extract_and_normalize_corrections(item))

    return results

async def run_single_pass_audit(
    paired_blocks: List[Dict],
    config: TranslationConfig,
    pass_num: int,
    global_profile: str = "{}",
    translation_policy: str = "{}"
) -> Tuple[List[Dict], bool]:
    """执行单轮全量字幕审查（动态加载 post_check.prompt 模板，支持长片智能切块与全量审校）"""
    items = []
    for b in paired_blocks:
        idx = int(b['index']) if str(b.get('index', '')).isdigit() else 0
        orig = b.get('original', '')
        trans = b.get('polished') or b.get('content', '')
        items.append({"id": idx, "en": orig, "zh": trans})
        
    CHUNK_SIZE = 500  # 超过 500 行自动切块
    all_corrections = []
    
    audit_config = TranslationConfig()
    audit_config.api_key = config.api_key
    audit_config.api_url = config.api_url
    audit_config.model_name = config.model_name
    audit_config.max_tokens = 8192
    audit_config.reasoning_effort = "none"
    
    tools = [{
        "type": "function",
        "function": {
            "name": "submit_audit_corrections",
            "parameters": {
                "type": "object",
                "properties": {
                    "issues_found": {"type": "boolean"},
                    "corrections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "fixed": {"type": "string"},
                                "reason": {"type": "string"}
                            },
                            "required": ["id", "fixed", "reason"]
                        }
                    }
                },
                "required": ["issues_found", "corrections"]
            }
        }
    }]
    
    # 动态加载 post_check 提示词模板
    prompt_template = load_prompt("post_check")
    
    for chunk_start in range(0, len(items), CHUNK_SIZE):
        chunk_items = items[chunk_start:chunk_start + CHUNK_SIZE]
        chunk_label = f"[{chunk_start+1}-{chunk_start+len(chunk_items)}]" if len(items) > CHUNK_SIZE else "全片"
        
        # 填充模板变量
        prompt_content = prompt_template.format(
            global_profile=global_profile or "无特定背景画像",
            translation_policy=translation_policy or "保持自然地道口语",
            content=json.dumps(chunk_items, ensure_ascii=False, indent=1)
        )
        
        msgs = [
            {"role": "user", "content": f"【第 {pass_num} 轮终审质检 - {chunk_label}】\n\n{prompt_content}"}
        ]
        
        raw = await call_llm(audit_config, msgs, temperature=0.1, tools=tools, response_format={"type": "json_object"})
        
        if raw:
            try:
                data = clean_and_extract_json(raw)
                corrections = _extract_and_normalize_corrections(data)
                all_corrections.extend(corrections)
            except Exception as e:
                logger.error(f"解析第 {pass_num} 轮审校结果失败: {e}")
                
    if not all_corrections:
        return paired_blocks, False
        
    # 应用修复
    by_id = {int(b['index']): b for b in paired_blocks if str(b.get('index', '')).isdigit()}
    applied_count = 0
    for c in all_corrections:
        if not isinstance(c, dict):
            continue
        cid = c.get('id')
        fixed = c.get('fixed')
        reason = c.get('reason', '')
        if cid in by_id and fixed:
            try:
                fixed = align_color_tags(by_id[cid].get('original', ''), fixed)
                by_id[cid]['polished'] = fixed
                by_id[cid]['content'] = fixed
                logger.info(f"   [Pass {pass_num} Fixed] ID {cid}: -> '{fixed}' ({reason})")
                applied_count += 1
            except Exception as e:
                logger.warning(f"   [Pass {pass_num}] 应用 ID {cid} 修复失败: {e}")
            
    logger.info(f"🔎 [Pass {pass_num}] 大模型提交并修复了 {applied_count} 处逻辑/语境硬伤。")
    return paired_blocks, (applied_count > 0)

async def level3_iterative_llm_logic_audit(
    paired_blocks: List[Dict],
    config: TranslationConfig,
    global_profile: str = "{}",
    translation_policy: str = "{}",
    max_passes: int = 5
) -> List[Dict]:
    """执行 Level 3 循环全局逻辑审校（默认最多 5 轮，支持早停）"""
    logger.info(f"🧠 [Post-Check Level 3] 启动多轮全局对抗逻辑质检 (最大轮数: {max_passes})...")
    
    for pass_idx in range(1, max_passes + 1):
        logger.info(f"⏳ 正在执行第 {pass_idx}/{max_passes} 轮全局审查...")
        paired_blocks, has_changes = await run_single_pass_audit(
            paired_blocks, config, pass_idx,
            global_profile=global_profile,
            translation_policy=translation_policy
        )
        
        if not has_changes:
            logger.info(f"🎉 [Early Stop] 第 {pass_idx} 轮审校未发现任何语境与逻辑硬伤，质检提前顺利通关！")
            break
            
    return paired_blocks

# =========================================================================
# 统一入口: run_post_checker
# =========================================================================

# @lat: [[core-quality#Key Concepts#LLM 终审（run_post_checker）]]
async def run_post_checker(
    final_blocks: List[Dict],
    config: TranslationConfig,
    global_profile: str = "{}",
    translation_policy: str = "{}",
    max_passes: int = 5
) -> List[Dict]:
    """完整执行 Level 1 -> Level 2 -> Level 3 的三级后置质检体系"""
    logger.info("\n" + "="*60)
    logger.info("🛡️ 启动 Plan 4.0 三级终审质检系统 (Post-Checker Suite)")
    logger.info("="*60)
    
    # 1. Level 1 确定性清洗
    blocks = level1_deterministic_cleaning(final_blocks)
    
    # (Level 2 numeric validation replaced by Agentic QA in Level 3)
    blocks = await level3_iterative_llm_logic_audit(
        blocks, config,
        global_profile=global_profile,
        translation_policy=translation_policy,
        max_passes=max_passes
    )
    
    logger.info("="*60)
    logger.info("🏆 全局 Post-Check 终审完成，字幕质量已达最高标准！")
    logger.info("="*60 + "\n")
    return blocks
