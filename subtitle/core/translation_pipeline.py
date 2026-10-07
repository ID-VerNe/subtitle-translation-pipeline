# -*- coding: utf-8 -*- 
"""
Facade for the refactored translation pipeline modules.
This file is kept for backward compatibility.
"""

from .context_builder import (
    build_recent_state,
    build_core_terms,
    build_glossary_payload,
    filter_relevant_glossary
)

from .terminology_extractor import (
    extract_global_terms
)

from .rescue_engine import (
    _do_single_request,
    _build_ladder,
    ladder_rescue_engine
)

from .stages.literal_stage import (
    process_literal_stage
)

from .stages.polish_stage import (
    postprocess_translation,
    process_polish_stage
)

__all__ = [
    "build_recent_state",
    "build_core_terms",
    "build_glossary_payload",
    "filter_relevant_glossary",
    
    "extract_global_terms",
    
    "_do_single_request",
    "_build_ladder",
    "ladder_rescue_engine",
    
    "process_literal_stage",
    
    "postprocess_translation",
    "process_polish_stage"
]
