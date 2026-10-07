# -*- coding: utf-8 -*-
from core.srt_utils import format_srt_block

# @lat: [[pipeline#Key Concepts#字幕写出（rewrite_output）]]
def rewrite_output(args, final_blocks):
    """将 final_blocks 写入 SRT 文件。"""
    bilingual = getattr(args, 'bilingual', False)
    with open(args.output_file, 'w', encoding='utf-8') as f:
        output_block_index = 1
        for block in final_blocks:
            text = block.get('polished', '') or block.get('content', '')
            if bilingual:
                original_text = block.get('original', '')
                f.write(format_srt_block(output_block_index, block['timestamp'], original_text))
                output_block_index += 1
                f.write(format_srt_block(output_block_index, block['timestamp'], text))
                output_block_index += 1
            else:
                f.write(format_srt_block(output_block_index, block['timestamp'], text))
                output_block_index += 1
