import logging
from typing import List, Dict
from core.llm_client import call_llm
from core.config import TranslationConfig

logger = logging.getLogger(__name__)

# @lat: [[core-quality#Key Concepts#ASR 清洗（ASR Scrub）]]
def apply_scrub_corrections(blocks: List[Dict], corrections: List[Dict]) -> List[Dict]:
    """Applies corrections to the text blocks."""
    if not corrections:
        return blocks
        
    for block in blocks:
        text = block['content']
        for corr in corrections:
            orig = corr.get('original')
            fixed = corr.get('corrected')
            if orig and fixed and orig in text:
                text = text.replace(orig, fixed)
        block['content'] = text
    return blocks

# @lat: [[core-quality#Key Concepts#ASR 清洗（ASR Scrub）]]
async def run_asr_scrub(blocks: List[Dict], scrub_config: TranslationConfig) -> List[Dict]:
    """Runs a global ASR purification pass using a high-intelligence model, with chunking."""
    
    CHUNK_SIZE = 250  # Split into smaller chunks to prevent LLM infinite loops
    all_corrections = []
    
    for i in range(0, len(blocks), CHUNK_SIZE):
        chunk_blocks = blocks[i:i+CHUNK_SIZE]
        full_text = "\n".join([f"{b['index']}: {b['content']}" for b in chunk_blocks])
        
        from core.prompts import load_prompt
        # TODO: Dynamically load domain_context if available (for now, pass empty string or default)
        sys_prompt = load_prompt("asr_scrubber").format(domain_context="No specific domain context provided.")

        msgs = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"Here is the subtitle chunk:\n\n{full_text}"}
        ]
        
        tools = [{
            "type": "function",
            "function": {
                "name": "submit_corrections",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "corrections": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "original": {"type": "string"},
                                    "corrected": {"type": "string"},
                                    "reason": {"type": "string"}
                                },
                                "required": ["original", "corrected", "reason"]
                            }
                        }
                    },
                    "required": ["corrections"]
                }
            }
        }]
        
        logger.info(f"🚀 启动 ASR 净化 (Model: {scrub_config.model_name}), 处理区块 {i}-{i+len(chunk_blocks)}...")
        raw = await call_llm(scrub_config, msgs, temperature=0.1, tools=tools, response_format={"type": "json_object"})
        
        corrections = []
        if raw:
            try:
                from core.llm_client import clean_and_extract_json
                data = clean_and_extract_json(raw)
                if isinstance(data, dict) and "corrections" in data:
                    corrections = data["corrections"]
                elif isinstance(data, list):
                    corrections = data
            except Exception as e:
                logger.error(f"Failed to parse scrub corrections for chunk {i}: {e}")
                
        if corrections:
            all_corrections.extend(corrections)
        elif not raw:
            logger.warning(f"⚠️ ASR 净化区块 {i}-{i+len(chunk_blocks)} 返回空内容 (可能 Reasoning 耗尽了 Token 预算或 finish_reason 为 length)")
            
    if all_corrections:
        logger.info(f"✅ ASR 净化成功，共发现 {len(all_corrections)} 处硬伤/黑话，已实施全量拦截！")
        for c in all_corrections:
            logger.info(f"   - {c.get('original')} -> {c.get('corrected')} ({c.get('reason')})")
        return apply_scrub_corrections(blocks, all_corrections)
    else:
        logger.info("✅ ASR 净化完成，未发现需替换的严重错误。")
        return blocks
