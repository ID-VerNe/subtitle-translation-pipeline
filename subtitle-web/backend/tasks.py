# -*- coding: utf-8 -*-
import os
import sys
import uuid
import json
import asyncio
import threading
import hashlib
import logging
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent / "subtitle"
sys.path.insert(0, str(BASE_DIR))

from models import TaskStatus, TranslateRequest, PresetConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TaskManager")

TASKS_DIR = Path(__file__).parent / "tasks"
TASKS_DIR.mkdir(exist_ok=True)

PRESETS_FILE = BASE_DIR / "presets.json"


class TranslationTask:
    def __init__(
        self,
        task_id: str,
        input_path: str,
        output_path: str,
        request: TranslateRequest,
        config: PresetConfig
    ):
        self.task_id = task_id
        self.input_path = input_path
        self.output_path = output_path
        self.request = request
        self.config = config
        self.status = TaskStatus(
            task_id=task_id,
            status="pending",
            progress=0,
            current_stage="等待中"
        )
        self.logs: List[str] = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def update_progress(self, progress: int, stage: str):
        with self._lock:
            self.status.progress = min(100, max(0, progress))
            self.status.current_stage = stage
            self._add_log(f"[{stage}] 进度: {self.status.progress}%")

    def _add_log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"{timestamp} - {message}")

    def set_status(self, status: str, error: Optional[str] = None):
        with self._lock:
            self.status.status = status
            if error:
                self.status.error = error
                self._add_log(f"错误: {error}")
            if status == "completed":
                self.status.completed_at = datetime.now()
                self._add_log("任务完成")

    def get_status(self) -> TaskStatus:
        with self._lock:
            return self.status.model_copy(deep=True)

    def get_logs(self) -> List[str]:
        with self._lock:
            return self.logs.copy()


class TaskManager:
    _instance = None
    _lock_instance = threading.Lock()

    def __new__(cls):
        with cls._lock_instance:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._tasks: Dict[str, TranslationTask] = {}
                cls._instance._tasks_lock = threading.Lock()
            return cls._instance

    def create_task(
        self,
        input_path: str,
        output_path: str,
        request: TranslateRequest,
        config: PresetConfig
    ) -> str:
        task_id = str(uuid.uuid4())[:8]
        task = TranslationTask(task_id, input_path, output_path, request, config)
        with self._tasks_lock:
            self._tasks[task_id] = task
        self._save_task_info(task)
        logger.info(f"创建任务: {task_id}")
        return task_id

    def get_task(self, task_id: str) -> Optional[TranslationTask]:
        with self._tasks_lock:
            return self._tasks.get(task_id)

    def start_task(self, task_id: str):
        task = self.get_task(task_id)
        if task and not task._thread:
            task._thread = threading.Thread(target=self._run_translation, args=(task_id,), daemon=True)
            task._thread.start()
            logger.info(f"启动任务线程: {task_id}")

    def _run_translation(self, task_id: str):
        task = self.get_task(task_id)
        if not task:
            return

        try:
            task.set_status("processing")
            task.update_progress(5, "初始化")

            import importlib.util
            from core.config import TranslationConfig, TranslationArgs

            extract_tool_path = BASE_DIR / "pre-process" / "01-extract_srt.py"
            ass_tool_path = BASE_DIR / "post-process" / "02-post_process_ass.py"

            spec = importlib.util.spec_from_file_location("extract_tool", str(extract_tool_path))
            extract_tool = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(extract_tool)

            spec = importlib.util.spec_from_file_location("ass_tool", str(ass_tool_path))
            ass_tool = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ass_tool)

            working_srt = None
            input_path = task.input_path

            task.update_progress(10, "预处理字幕")

            if input_path.lower().endswith(".mkv"):
                task._add_log("从 MKV 提取字幕...")
                srt_files = extract_tool.extract_subtitles(input_path)
                if srt_files:
                    working_srt = srt_files[0]
                else:
                    task.set_status("failed", "MKV 字幕提取失败")
                    return
            elif input_path.lower().endswith(".srt"):
                working_srt = input_path
            elif input_path.lower().endswith(".ass"):
                task._add_log("将 ASS 转换为 SRT...")
                working_srt = extract_tool.convert_ass_file_to_srt(input_path)

            if not working_srt:
                task.set_status("failed", "无效的输入文件")
                return

            task.update_progress(20, "准备翻译")

            from translate_srt_llm import run_translation

            input_filename = os.path.basename(working_srt)
            file_hash = hashlib.md5(input_filename.encode('utf-8')).hexdigest()

            cache_dir = BASE_DIR / "core" / ".cache"
            cache_dir.mkdir(exist_ok=True)

            if task.request.format == "ass":
                translated_srt = str(cache_dir / f"translated_{file_hash}.srt")
            else:
                translated_srt = task.output_path

            trans_args = TranslationArgs(
                input_file=working_srt,
                output_file=translated_srt,
                bilingual=task.request.bilingual,
                model_name=task.config.model_name,
                batch_size=task.config.batch_size,
                target_lang=task.request.target_lang
            )
            trans_args.api_key = task.config.api_key or ""
            trans_args.api_url = task.config.api_url or ""
            trans_args.max_concurrent = task.config.max_concurrent
            trans_args.rpm_limit = task.config.rpm_limit
            trans_args.max_retries = task.config.max_retries
            trans_args.retry_delay = task.config.retry_delay
            trans_args.max_tokens = task.config.max_tokens
            trans_args.temp_terms = task.request.temperature_terms
            trans_args.temp_literal = task.request.temperature_literal
            trans_args.temp_polish = task.request.temperature_polish
            trans_args.enable_llm_discovery = task.config.enable_discovery
            trans_args.enable_names_db = task.config.enable_names_db

            task.update_progress(25, "翻译中")

            def progress_callback(current: int, total: int):
                progress = 25 + int((current / total) * 65) if total > 0 else 25
                task.update_progress(progress, "翻译字幕")

            asyncio.run(run_translation(trans_args, progress_callback=progress_callback))

            task.update_progress(90, "后处理")

            if task.request.format == "ass":
                task._add_log(f"生成 ASS 格式: {task.output_path}")
                head_path = BASE_DIR / "post-process" / "asshead.txt"
                if not head_path.exists():
                    head_path = Path("asshead.txt")
                ass_tool.srt_to_ass(translated_srt, str(head_path), task.output_path)

            task.update_progress(100, "完成")
            task.set_status("completed")
            task._add_log(f"输出文件: {task.output_path}")
            logger.info(f"任务完成: {task_id} -> {task.output_path}")

        except Exception as e:
            logger.error(f"任务执行失败 {task_id}: {e}", exc_info=True)
            task.set_status("failed", str(e))

    def _save_task_info(self, task: TranslationTask):
        info_file = TASKS_DIR / f"{task.task_id}.json"
        with open(info_file, "w", encoding="utf-8") as f:
            json.dump({
                "task_id": task.task_id,
                "input_path": task.input_path,
                "output_path": task.output_path,
                "request": task.request.model_dump(),
                "config": task.config.model_dump(),
                "created_at": task.status.created_at.isoformat()
            }, f, ensure_ascii=False, indent=2)

    def load_presets(self) -> Dict[str, PresetConfig]:
        if PRESETS_FILE.exists():
            try:
                with open(PRESETS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {k: PresetConfig(**v) for k, v in data.items()}
            except Exception as e:
                logger.error(f"加载预设失败: {e}")
        return {}

    def save_presets(self, presets: Dict[str, PresetConfig]):
        try:
            with open(PRESETS_FILE, "w", encoding="utf-8") as f:
                json.dump({k: v.model_dump() for k, v in presets.items()}, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存预设失败: {e}")

    def get_default_config(self) -> PresetConfig:
        try:
            from core.config import TranslationConfig
            default = TranslationConfig()
            return PresetConfig(
                api_url=str(default.api_url),
                api_key=str(default.api_key),
                model_name=str(default.model_name),
                batch_size=default.batch_size,
                max_concurrent=default.max_concurrent_requests,
                rpm_limit=default.rpm_limit,
                max_retries=default.max_retries,
                retry_delay=default.retry_delay,
                max_tokens=default.max_tokens,
                enable_discovery=default.enable_llm_discovery,
                enable_names_db=default.enable_names_db,
                temp_terms=default.temp_terms,
                temp_literal=default.temp_literal,
                temp_polish=default.temp_polish
            )
        except Exception as e:
            logger.error(f"获取默认配置失败: {e}")
            return PresetConfig()


task_manager = TaskManager()
