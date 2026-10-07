# -*- coding: utf-8 -*-
"""
Facade and CLI entrypoint for the subtitle translation pipeline.
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import argparse
import asyncio
import logging
from logging.handlers import RotatingFileHandler

from core.config import TranslationConfig
from pipeline.orchestrator import run_translation

log_file_path = os.path.join(BASE_DIR, "translation.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(log_file_path, maxBytes=10 * 1024 * 1024, backupCount=3, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# @lat: [[entries#Key Concepts#细粒度翻译 CLI（translate_srt_llm.py）]]
def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="SRT 智能翻译工具 (架构优化版)")

    # --- 文件与路径参数 ---
    parser.add_argument('-i', '--input-file', type=str, default='官方英文.srt', help='输入SRT文件')
    parser.add_argument('-o', '--output-file', type=str, default='官方英文_output.srt', help='输出SRT文件')
    parser.add_argument('--progress-file', type=str, default=None, help='进度文件')
    parser.add_argument('--glossary-cache-file', type=str, default=None, help='术语缓存')
    
    # --- 运行参数 ---
    defaults = TranslationConfig()
    parser.add_argument('--batch-size', type=int, default=defaults.batch_size, help='批次大小')
    parser.add_argument('--max-concurrent', type=int, default=defaults.max_concurrent_requests, help='最大并发请求数')

    parser.add_argument('--bilingual', dest='bilingual', action='store_true', help='开启双语')
    parser.add_argument('--no-bilingual', dest='bilingual', action='store_false', help='仅中文')
    parser.set_defaults(bilingual=True)

    # --- API 与模型参数 ---
    parser.add_argument('--api-key', type=str, default=defaults.api_key, help='API Key')
    parser.add_argument('--api-url', type=str, default=defaults.api_url, help='API URL')
    parser.add_argument('--model-name', type=str, default=defaults.model_name, help='模型名称')
    parser.add_argument('--scrub-model', type=str, default=None, help='The preset model to use for ASR purification')
    
    # --- 温度参数 ---
    parser.add_argument('--temp-terms', type=float, default=defaults.temp_terms, help='术语提取温度')
    parser.add_argument('--temp-literal', type=float, default=defaults.temp_literal, help='直译温度')
    parser.add_argument('--temp-polish', type=float, default=defaults.temp_polish, help='润色温度')

    # --- 推理力度 (支持 reasoning_effort 的模型，如 SenseNova) ---
    parser.add_argument('--reasoning-effort', type=str, default=defaults.reasoning_effort,
                        choices=['', 'low', 'medium', 'high', 'none'],
                        help='推理力度: none/low/medium/high。留空表示不传该字段，沿用模型默认。')
    
    # --- 人名库与语言选项 ---
    parser.add_argument('--enable-names-db', action='store_true', help='启用人名数据库 (默认禁用)')
    parser.add_argument('--to-english', action='store_true', help='开启中译英模式 (默认英译中)')

    # --- 注释功能 ---
    parser.add_argument('--enable-annotations', action='store_true', help='启用全文注释生成（实验性功能）')

    # --- 一致性回查与后置质检 ---
    parser.add_argument('--enforce-consistency', dest='enforce_consistency', action='store_true', help='启用翻译后三级终审质检与逻辑对抗审校（默认）')
    parser.add_argument('--no-enforce-consistency', dest='enforce_consistency', action='store_false', help='关闭后置终审质检')
    parser.add_argument('--post-check-passes', type=int, default=5, help='Level 3 全局对抗审校最大轮数（默认 5 轮，支持早停）')
    parser.set_defaults(enforce_consistency=True)

    args = parser.parse_args()
    args.target_lang = "en" if args.to_english else "zh"

    asyncio.run(run_translation(args))

if __name__ == "__main__":
    main()