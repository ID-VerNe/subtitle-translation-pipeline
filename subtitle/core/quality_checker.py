# -*- coding: utf-8 -*-
"""
翻译质量自动检查模块
在润色阶段后执行，捕获常见翻译问题
"""

import re
from typing import List, Dict, Tuple

# @lat: [[core-quality#Key Concepts#规则质量检查（TranslationQualityChecker）]]
class TranslationQualityChecker:
    """字幕翻译质量检查器"""
    
    def __init__(self):
        # 书面语黑名单
        self.formal_words = [
            "进行", "实施", "开展", "予以", "给予", 
            "关于", "针对", "基于", "鉴于",
            "显著", "充分", "有效", "积极",
            "此外", "因此", "所以", "然而"  # 过度使用
        ]
        
        # 机器翻译特征
        self.machine_patterns = [
            r'的\s*的',  # 连续的"的"
            r'了\s*了',  # 连续的"了"
            r'[，。！？]{2,}',  # 重复标点
        ]
    
    def check_batch(self, blocks: List[Dict], original_blocks: List[Dict]) -> List[Dict]:
        """
        批量检查翻译质量
        
        Args:
            blocks: 翻译后的字幕块 (包含 polished 字段)
            original_blocks: 原始英文字幕块
            
        Returns:
            问题列表 [{"id": 123, "issue": "书面语", "text": "..."}]
        """
        issues = []
        
        for trans_block, orig_block in zip(blocks, original_blocks):
            block_id = trans_block.get('index')
            polished = trans_block.get('polished', '')
            original = orig_block.get('content', '')
            
            # 1. 书面语检查
            formal_found = [w for w in self.formal_words if w in polished]
            if formal_found:
                issues.append({
                    "id": block_id,
                    "issue": "疑似书面语",
                    "text": polished,
                    "keywords": formal_found
                })
            
            # 2. 机器翻译腔检查
            for pattern in self.machine_patterns:
                if re.search(pattern, polished):
                    issues.append({
                        "id": block_id,
                        "issue": "机器翻译特征",
                        "text": polished,
                        "pattern": pattern
                    })
            
            # 3. 长度异常检查（译文过长或过短）
            orig_len = len(original)
            trans_len = len(polished)
            
            # 英文→中文通常 1:0.6 - 1:1.2 范围
            if trans_len < orig_len * 0.4:
                issues.append({
                    "id": block_id,
                    "issue": "译文过短",
                    "text": polished,
                    "ratio": trans_len / orig_len if orig_len > 0 else 0
                })
            elif trans_len > orig_len * 1.5:
                issues.append({
                    "id": block_id,
                    "issue": "译文过长",
                    "text": polished,
                    "ratio": trans_len / orig_len if orig_len > 0 else 0
                })
            
            # 4. 情绪词丢失检查
            emotion_markers = ['!', '?', '...', 'Oh', 'Well', 'God', 'Fuck', 'Shit']
            orig_has_emotion = any(m in original for m in emotion_markers)
            trans_has_emotion = any(p in polished for p in ['！', '？', '…', '哦', '嗯', '天', '该死', '操'])
            
            if orig_has_emotion and not trans_has_emotion:
                issues.append({
                    "id": block_id,
                    "issue": "情绪标记丢失",
                    "text": polished,
                    "original": original
                })
        
        return issues
    
    def check_consistency(self, all_blocks: List[Dict], glossary: Dict) -> List[Dict]:
        """
        检查术语一致性。

        方向修正：对每个 glossary 源词，找【英文原文】含该源词的 block，
        检查对应【中文译文】是否包含规定目标译法。原实现误在中文译文里找
        英文源词，永远查不出问题。
        Args:
            all_blocks: 全部翻译后的字幕 (含 original 与 polished 字段)
            glossary: 术语表 {source: {target: ...}}
        Returns:
            不一致问题列表
        """
        issues = []

        # term_usage: {原词: [(id, 中文译文), ...]} —— 仅当原文含该源词时记录
        term_usage = {}

        for block in all_blocks:
            block_id = block.get('index')
            original = block.get('original', block.get('content', ''))
            polished = block.get('polished', '')

            for src, info in glossary.items():
                if src.lower() in original.lower():
                    if src not in term_usage:
                        term_usage[src] = []
                    term_usage[src].append((block_id, polished))

        # 检查术语是否一致使用：译文必须包含规定目标译法
        for term, usages in term_usage.items():
            info = glossary[term]
            expected_trans = info.get('target', '') if isinstance(info, dict) else str(info)
            if not expected_trans:
                continue
            inconsistent = [
                (bid, text) for bid, text in usages
                if expected_trans not in text
            ]

            if inconsistent:
                issues.append({
                    "issue": "术语不一致",
                    "term": term,
                    "expected": expected_trans,
                    "cases": inconsistent[:3]  # 只显示前3个
                })

        return issues


# 使用示例
if __name__ == "__main__":
    checker = TranslationQualityChecker()
    
    # 模拟数据
    translated = [
        {"index": "1", "polished": "我们需要进行农业机械的维护工作"},
        {"index": "2", "polished": "操！这破机器又坏了"}
    ]
    
    originals = [
        {"index": "1", "content": "We need to fix the tractor"},
        {"index": "2", "content": "Fuck! This thing broke again"}
    ]
    
    issues = checker.check_batch(translated, originals)
    
    for issue in issues:
        print(f"[{issue['issue']}] ID {issue['id']}: {issue['text']}")
