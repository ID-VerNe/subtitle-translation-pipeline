# -*- coding: utf-8 -*-
import json
import os
from typing import List, Dict

from core.srt_utils import format_srt_block

# @lat: [[pipeline#Key Concepts#断点续传（checkpoint）]]
def save_checkpoint(srt_file: str, progress_file: str, blocks: List[Dict], progress_data: Dict, bilingual_output: bool = False, last_context: str = ""):
    """保存中间件和最终输出。"""
    if not blocks:
        return

    output_block_index = progress_data.get('output_block_index', 1)

    literal_file = srt_file.replace('.srt', '.literal.srt')
    polished_file = srt_file.replace('.srt', '.polished.srt')

    with open(srt_file, 'a', encoding='utf-8') as f, \
         open(literal_file, 'a', encoding='utf-8') as f_lit, \
         open(polished_file, 'a', encoding='utf-8') as f_pol:
        for b in blocks:
            f_lit.write(format_srt_block(b['index'], b['timestamp'], b.get('literal', '')))
            f_pol.write(format_srt_block(b['index'], b['timestamp'], b.get('polished', '')))
            
            if bilingual_output:
                original_text = b.get('original', b.get('content', ''))
                f.write(format_srt_block(output_block_index, b['timestamp'], original_text))
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


# @lat: [[pipeline#Key Concepts#断点续传（checkpoint）]]
def load_progress(progress_file: str) -> Dict:
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"last_index": 0, "processed_indices": []}
