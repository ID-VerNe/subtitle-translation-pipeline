# -*- coding: utf-8 -*-
from pydantic import BaseModel, Field
from typing import Optional, Dict, Literal
from datetime import datetime


class TranslateRequest(BaseModel):
    target_lang: Literal["zh", "en"] = "zh"
    format: Literal["ass", "srt"] = "ass"
    bilingual: bool = True
    temperature_terms: float = Field(default=0.1, ge=0.0, le=1.0)
    temperature_literal: float = Field(default=0.3, ge=0.0, le=1.0)
    temperature_polish: float = Field(default=0.5, ge=0.0, le=1.0)


class TaskStatus(BaseModel):
    task_id: str
    status: Literal["pending", "processing", "completed", "failed"]
    progress: int = Field(default=0, ge=0, le=100)
    current_stage: str = ""
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


class TaskResponse(BaseModel):
    task_id: str
    status: str


class PresetConfig(BaseModel):
    api_url: Optional[str] = ""
    api_key: Optional[str] = ""
    model_name: Optional[str] = ""
    batch_size: int = 8
    max_concurrent: int = 4
    rpm_limit: int = 60
    max_retries: int = 3
    retry_delay: float = 2.0
    max_tokens: int = 4096
    enable_discovery: bool = True
    enable_names_db: bool = False
    target_lang: str = "zh"
    target_format: str = "ass"
    bilingual: bool = True
    temp_terms: float = 0.1
    temp_literal: float = 0.3
    temp_polish: float = 0.5


class PresetItem(BaseModel):
    name: str
    config: PresetConfig


class PresetResponse(BaseModel):
    presets: Dict[str, PresetConfig]
