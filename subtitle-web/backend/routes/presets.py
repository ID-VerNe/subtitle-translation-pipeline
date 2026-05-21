# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException
from typing import Dict

from models import PresetConfig, PresetResponse, PresetItem
from tasks import task_manager

router = APIRouter(prefix="/api", tags=["presets"])


@router.get("/presets", response_model=PresetResponse)
async def get_presets():
    presets = task_manager.load_presets()
    return PresetResponse(presets=presets)


@router.post("/presets")
async def save_preset(item: PresetItem):
    presets = task_manager.load_presets()
    presets[item.name] = item.config
    task_manager.save_presets(presets)
    return {"success": True, "name": item.name}


@router.delete("/presets/{name}")
async def delete_preset(name: str):
    presets = task_manager.load_presets()
    if name not in presets:
        raise HTTPException(status_code=404, detail=f"预设 '{name}' 不存在")
    del presets[name]
    task_manager.save_presets(presets)
    return {"success": True, "deleted": name}


@router.get("/config", response_model=PresetConfig)
async def get_config():
    return task_manager.get_default_config()
