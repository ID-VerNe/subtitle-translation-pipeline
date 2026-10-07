# -*- coding: utf-8 -*-
import asyncio
import logging
import re
from typing import List, Dict

logger = logging.getLogger(__name__)

REFUSAL_SENTINEL = '__CONTENT_REFUSAL_SENTINEL__'

class SafetyFuzzer:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SafetyFuzzer, cls).__new__(cls)
            cls._instance.global_blocks = []
            cls._instance.known_toxic_words = set()
            cls._instance.config = None
        return cls._instance

    def initialize(self, global_blocks: List[Dict], config):
        self.global_blocks = global_blocks
        self.config = config

    def obfuscate_word(self, word: str) -> str:
        if len(word) <= 2:
            return word[0] + 'x' * max(1, len(word) - 1)
        return word[0] + 'x' * (len(word) - 2) + word[-1]

    async def probe_safety(self, text: str) -> bool:
        if not text.strip():
            return True
            
        from network.llm_client import _do_llm_request, get_session, ContentRefusalError
        
        session = get_session(self.config, use_smart_balancer=True)
        messages = [{'role': 'user', 'content': f'Please exactly repeat this text, nothing else: {text}'}]
        
        payload = {
            'model': self.config.model_name,
            'messages': messages,
            'temperature': 0.1,
            'max_tokens': 100,
            'stream': False
        }
        
        try:
            if hasattr(session, 'execute'):
                async def task_func(sess):
                    return await _do_llm_request(sess, self.config, payload)
                await session.execute(task_func)
            else:
                await _do_llm_request(session, self.config, payload)
            return True
        except ContentRefusalError:
            return False
        except Exception:
            return True

    async def bisect_words(self, text: str) -> str:
        words = re.split(r'([^a-zA-Z0-9\u4e00-\u9fa5]+)', text)
        words = [w for w in words if w]
        
        if len(words) <= 2:
            for w in words:
                if re.match(r'[a-zA-Z0-9\u4e00-\u9fa5]+', w):
                    if not await self.probe_safety(w):
                        return w
            return text
            
        mid = len(words) // 2
        left_text = ''.join(words[:mid])
        right_text = ''.join(words[mid:])
        
        if not await self.probe_safety(left_text):
            return await self.bisect_words(left_text)
        elif not await self.probe_safety(right_text):
            return await self.bisect_words(right_text)
            
        return left_text + right_text

    async def bisect_blocks(self, blocks: List[Dict]) -> None:
        if len(blocks) == 1:
            block = blocks[0]
            logger.warning(f'🔍 探雷器已锁定嫌疑行 ID {block["index"]}，正在进行词级微观排雷...')
            toxic_word = await self.bisect_words(block['content'])
            if toxic_word and toxic_word.strip():
                clean_word = self.obfuscate_word(toxic_word)
                logger.warning(f'💣 发现违禁词: "{toxic_word}", 已脱敏为: "{clean_word}"')
                self.known_toxic_words.add((toxic_word, clean_word))
                self.apply_global_replacement()
            return

        mid = len(blocks) // 2
        left_blocks = blocks[:mid]
        right_blocks = blocks[mid:]

        left_text = '\n'.join([b['content'] for b in left_blocks])
        if not await self.probe_safety(left_text):
            await self.bisect_blocks(left_blocks)

        right_text = '\n'.join([b['content'] for b in right_blocks])
        if not await self.probe_safety(right_text):
            await self.bisect_blocks(right_blocks)

    def apply_global_replacement(self):
        count = 0
        for b in self.global_blocks:
            original = b.get('content', '')
            if not original:
                continue
            for toxic, clean in self.known_toxic_words:
                if toxic in original:
                    b['content'] = original.replace(toxic, clean)
                    count += 1
        logger.info(f'🔄 已将脱敏词同步至全局，共修复 {count} 处残留。')

    async def heal_blocks(self, blocks_chunk: List[Dict]) -> bool:
        if not self.config:
            logger.error('SafetyFuzzer 尚未初始化 config')
            return False
            
        logger.warning(f'🛡️ 触发防审查自愈机制，正在二分探测 {len(blocks_chunk)} 行文本...')
        await self.bisect_blocks(blocks_chunk)
        return True

safety_fuzzer = SafetyFuzzer()
