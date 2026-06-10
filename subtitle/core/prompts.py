# -*- coding: utf-8 -*-
import os
from typing import Dict

PROMPT_DIR = os.path.join(os.path.dirname(__file__), '..', 'prompts')

def load_prompt(name: str) -> str:
    """从文件加载单个 prompt 模板。"""
    try:
        with open(os.path.join(PROMPT_DIR, f"{name}.prompt"), 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        raise ValueError(f"Prompt template '{name}.prompt' not found in '{PROMPT_DIR}'")

def get_prompt_templates(target_lang: str = "zh") -> Dict[str, str]:
    """加载所有 prompt 模板。"""
    suffix = "_en" if target_lang == "en" else ""
    return {
        "TERM_EXTRACT": load_prompt("term_extract"),
        "NER_NAMES": load_prompt("ner_names"),
        "LITERAL_TRANS": load_prompt(f"literal_trans{suffix}"),
        "REVIEW_AND_POLISH": load_prompt(f"review_and_polish{suffix}"),
        "ANNOTATION_EXTRACT": load_prompt("annotation_extract"),
    }
