# -*- coding: utf-8 -*-
"""
Facade for the refactored llm_client module.
This file is kept for backward compatibility.
"""
from network.llm_client import (
    call_llm,
    call_llm_batch,
    clean_and_extract_json,
    close_session_pool,
    get_load_balancer_stats,
    REFUSAL_SENTINEL
)

__all__ = [
    "call_llm",
    "call_llm_batch",
    "clean_and_extract_json",
    "close_session_pool",
    "get_load_balancer_stats",
    "REFUSAL_SENTINEL"
]
