# -*- coding: utf-8 -*-
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import os
import aiofiles
from pathlib import Path
from typing import Optional

from models import TaskResponse, TaskStatus, TranslateRequest, PresetConfig
from tasks import task_manager

router = APIRouter(prefix="/api", tags=["translate"])

UPLOAD_DIR = Path(__file__).parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/translate", response_model=TaskResponse)
async def translate(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    target_lang: str = "zh",
    format: str = "ass",
    bilingual: bool = True,
    temperature_terms: float = 0.1,
    temperature_literal: float = 0.3,
    temperature_polish: float = 0.5,
    model_name: str = "",
    api_url: str = "",
    api_key: str = "",
    batch_size: int = 8,
    max_concurrent: int = 4,
    rpm_limit: int = 60,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    max_tokens: int = 4096,
    enable_discovery: bool = True,
    enable_names_db: bool = False
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".mkv", ".srt", ".ass"]:
        raise HTTPException(status_code=400, detail="Unsupported file format. Only MKV, SRT, ASS are supported")

    request = TranslateRequest(
        target_lang=target_lang,
        format=format,
        bilingual=bilingual,
        temperature_terms=temperature_terms,
        temperature_literal=temperature_literal,
        temperature_polish=temperature_polish
    )

    config = PresetConfig(
        api_url=api_url,
        api_key=api_key,
        model_name=model_name,
        batch_size=batch_size,
        max_concurrent=max_concurrent,
        rpm_limit=rpm_limit,
        max_retries=max_retries,
        retry_delay=retry_delay,
        max_tokens=max_tokens,
        enable_discovery=enable_discovery,
        enable_names_db=enable_names_db,
        target_lang=target_lang,
        target_format=format,
        bilingual=bilingual,
        temp_terms=temperature_terms,
        temp_literal=temperature_literal,
        temp_polish=temperature_polish
    )

    input_path = UPLOAD_DIR / f"input_{file.filename}"
    async with aiofiles.open(input_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    base_name = os.path.splitext(file.filename)[0]
    output_path = str(UPLOAD_DIR / f"{base_name}_translated.{format}")

    task_id = task_manager.create_task(str(input_path), output_path, request, config)
    background_tasks.add_task(task_manager.start_task, task_id)

    return TaskResponse(task_id=task_id, status="pending")


@router.get("/tasks/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.get_status()


@router.get("/tasks/{task_id}/download")
async def download_result(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    status = task.get_status()
    if status.status != "completed":
        raise HTTPException(status_code=400, detail=f"Task not completed. Current status: {status.status}")

    output_path = task.output_path
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(
        path=output_path,
        filename=os.path.basename(output_path),
        media_type="text/plain"
    )


@router.get("/tasks/{task_id}/logs")
async def get_task_logs(task_id: str):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"logs": task.get_logs()}
