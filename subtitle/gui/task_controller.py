# -*- coding: utf-8 -*-
import os
import asyncio
import logging
import threading
from tkinter import messagebox

from core.config import TranslationArgs, clear_cache
from core.cache_utils import get_cache_path
from pipeline.orchestrator import run_translation
from media.extractor import extract_subtitles_from_mkv, convert_ass_to_srt, generate_ass_from_srt

logger = logging.getLogger(__name__)

# @lat: [[gui#Key Concepts#任务控制器（TaskController）]]
class TaskController:
    def __init__(self, view_model, root_window, start_btn, progress_label):
        self.vm = view_model
        self.root = root_window
        self.start_btn = start_btn
        self.progress_label = progress_label

    def do_clear_cache(self):
        if messagebox.askyesno("确认", "确定要清理所有翻译缓存吗？这将删除所有未完成任务的进度记录。"):
            if clear_cache():
                messagebox.showinfo("成功", "缓存已清理完毕。")
                logger.info("已清理所有翻译缓存")

    def update_progress(self, current, total):
        def _update():
            percent = (current / total) * 100 if total > 0 else 0
            self.vm.progress_var.set(percent)
            if self.progress_label:
                self.progress_label.config(text=f"{int(percent)}%")
        self.root.after(0, _update)

    def start_thread(self):
        if not self.vm.input_file.get():
            logger.error("请先选择输入文件！")
            return
        if self.start_btn:
            self.start_btn.config(state="disabled")
        thread = threading.Thread(target=self.run_process)
        thread.daemon = True
        thread.start()

    def run_process(self):
        try:
            input_path = self.vm.input_file.get()
            output_path = self.vm.output_file.get()
            final_fmt = self.vm.format_var.get()
            self.update_progress(0, 100)

            if output_path and not output_path.lower().endswith(f".{final_fmt}"):
                output_path += f".{final_fmt}"

            working_srt = None
            if input_path.lower().endswith(".mkv"):
                logger.info("正在从 MKV 提取字幕...")
                srt_files = extract_subtitles_from_mkv(input_path)
                if srt_files: working_srt = srt_files[0]
                else:
                    logger.error("MKV 字幕提取失败。")
                    return
            elif input_path.lower().endswith(".srt"):
                working_srt = input_path
            elif input_path.lower().endswith(".ass"):
                logger.info("正在将 ASS 转换为 SRT...")
                working_srt = convert_ass_to_srt(input_path)
            
            if not working_srt:
                logger.error("无效的输入文件或预处理失败。")
                return

            if final_fmt == "ass":
                translated_srt = get_cache_path(
                    input_file=working_srt,
                    purpose="translated",
                    target_lang=self.vm.target_lang_var.get(),
                    extension=".srt"
                )
            else:
                translated_srt = output_path if output_path else os.path.splitext(input_path)[0] + ".srt"

            raw_bs = self.vm.safe_get_int(self.vm.batch_size_var, 8)
            if raw_bs <= 0: raw_bs = 8
            
            raw_tokens = self.vm.safe_get_int(self.vm.max_tokens_var, 4096)
            if raw_tokens <= 0: raw_tokens = 4096
            
            raw_concurrent = self.vm.safe_get_int(self.vm.concurrent_var, 4)
            if raw_concurrent <= 0: raw_concurrent = 4

            logger.info(f"任务参数: Batch={raw_bs}, Tokens={raw_tokens}, Concurrent={raw_concurrent}")

            trans_args = TranslationArgs(
                input_file=working_srt,
                output_file=translated_srt,
                bilingual=self.vm.bilingual_var.get(),
                model_name=self.vm.model_var.get(),
                batch_size=raw_bs,
                target_lang=self.vm.target_lang_var.get()
            )
            trans_args.api_key = self.vm.api_key_var.get()
            trans_args.api_url = self.vm.api_url_var.get()
            trans_args.max_concurrent = raw_concurrent
            trans_args.rpm_limit = self.vm.safe_get_int(self.vm.rpm_var, 60)
            trans_args.max_retries = self.vm.safe_get_int(self.vm.retries_var, 3)
            trans_args.retry_delay = self.vm.safe_get_float(self.vm.retry_delay_var, 2.0)
            trans_args.max_tokens = raw_tokens
            trans_args.pass_temperature = self.vm.pass_temperature_var.get()
            trans_args.temp_terms = self.vm.safe_get_float(self.vm.temp_terms_var, 0.1)
            trans_args.temp_literal = self.vm.safe_get_float(self.vm.temp_literal_var, 0.3)
            trans_args.temp_polish = self.vm.safe_get_float(self.vm.temp_polish_var, 0.5)
            trans_args.enable_llm_discovery = self.vm.enable_discovery_var.get()
            trans_args.enable_names_db = self.vm.enable_names_db_var.get()
            trans_args.enable_annotations = self.vm.enable_annotations_var.get()
            
            trans_args.reasoning_effort = self.vm.reasoning_effort_var.get()
            trans_args.enforce_consistency = self.vm.enforce_consistency_var.get()
            trans_args.post_check_passes = self.vm.safe_get_int(self.vm.post_check_passes_var, 5)
            trans_args.context_budget_tokens = self.vm.safe_get_int(self.vm.context_budget_var, 200000)
            trans_args.max_previous_lines = self.vm.safe_get_int(self.vm.max_previous_lines_var, 25)

            asyncio.run(run_translation(trans_args, progress_callback=self.update_progress))

            if final_fmt == "ass":
                logger.info(f"生成 ASS: {output_path}")
                srt_for_ass = translated_srt
                if trans_args.enable_annotations:
                    annotation_srt = translated_srt.replace('.srt', '_with_annotations.srt')
                    if os.path.exists(annotation_srt):
                        srt_for_ass = annotation_srt
                        logger.info(f"使用带注释的 SRT: {annotation_srt}")
                
                generate_ass_from_srt(srt_for_ass, output_path)
            
            logger.info("🎉 翻译完成！")
            self.update_progress(100, 100)
            
            # Show obvious completion prompt
            self.root.after(0, lambda: messagebox.showinfo("完成", f"翻译及质检已全部完成！\n输出文件: {output_path}"))

        except Exception as e:
            logger.error(f"任务失败: {e}", exc_info=True)
        finally:
            if self.start_btn:
                self.root.after(0, lambda: self.start_btn.config(state="normal"))
