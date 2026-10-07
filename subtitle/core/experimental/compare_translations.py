# -*- coding: utf-8 -*-
"""
翻译质量对比测试工具
对比优化前后的翻译质量差异
"""

import os
import sys
import json
from typing import List, Dict
from collections import Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 确保 subtitle 目录在 sys.path
SUBTITLE_DIR = os.path.dirname(os.path.dirname(BASE_DIR))
if SUBTITLE_DIR not in sys.path:
    sys.path.insert(0, SUBTITLE_DIR)

try:
    from .quality_checker import TranslationQualityChecker
except ImportError:
    from core.experimental.quality_checker import TranslationQualityChecker
from core.srt_utils import parse_srt

class TranslationComparator:
    """翻译质量对比分析器"""
    
    def __init__(self):
        self.checker = TranslationQualityChecker()
    
    def analyze_single_file(self, srt_path: str, original_path: str = None) -> Dict:
        """
        分析单个翻译文件的质量
        
        Returns:
            {
                "total_blocks": 100,
                "avg_length": 45.2,
                "formal_word_count": 5,
                "emotion_loss_count": 3,
                "issue_summary": {...}
            }
        """
        if not os.path.exists(srt_path):
            return {"error": f"文件不存在: {srt_path}"}
        
        # 解析翻译后的字幕
        blocks = parse_srt(srt_path)
        
        if not blocks:
            return {"error": "无法解析字幕文件"}
        
        # 基础统计
        stats = {
            "total_blocks": len(blocks),
            "avg_length": sum(len(b.get('polished', b.get('content', ''))) for b in blocks) / len(blocks),
            "formal_word_count": 0,
            "emotion_loss_count": 0,
            "length_issues": 0,
            "machine_pattern_count": 0
        }
        
        # 如果有原文，进行质量检查
        if original_path and os.path.exists(original_path):
            original_blocks = parse_srt(original_path)
            issues = self.checker.check_batch(blocks, original_blocks)
            
            # 统计问题类型
            issue_types = Counter(issue['issue'] for issue in issues)
            stats["issue_summary"] = dict(issue_types)
            stats["total_issues"] = len(issues)
            
            # 细分统计
            stats["formal_word_count"] = issue_types.get("疑似书面语", 0)
            stats["emotion_loss_count"] = issue_types.get("情绪标记丢失", 0)
            stats["length_issues"] = issue_types.get("译文过长", 0) + issue_types.get("译文过短", 0)
            stats["machine_pattern_count"] = issue_types.get("机器翻译特征", 0)
        
        # 书面语词汇统计（即使没有原文也能检查）
        formal_words_found = []
        for block in blocks:
            text = block.get('polished', block.get('content', ''))
            for word in self.checker.formal_words:
                if word in text:
                    formal_words_found.append(word)
        
        stats["formal_words_detail"] = Counter(formal_words_found)
        
        return stats
    
    def compare_two_versions(self, version_a: str, version_b: str, original: str = None) -> Dict:
        """
        对比两个版本的翻译质量
        
        Args:
            version_a: 优化前的翻译
            version_b: 优化后的翻译
            original: 原始英文字幕（可选）
        
        Returns:
            对比报告
        """
        print("正在分析版本 A（优化前）...")
        stats_a = self.analyze_single_file(version_a, original)
        
        print("正在分析版本 B（优化后）...")
        stats_b = self.analyze_single_file(version_b, original)
        
        if "error" in stats_a or "error" in stats_b:
            return {"error": "分析失败", "details": {"a": stats_a, "b": stats_b}}
        
        # 计算改进比例
        comparison = {
            "version_a": stats_a,
            "version_b": stats_b,
            "improvements": {}
        }
        
        # 计算改进指标
        metrics = ["formal_word_count", "emotion_loss_count", "length_issues", "machine_pattern_count"]
        
        for metric in metrics:
            before = stats_a.get(metric, 0)
            after = stats_b.get(metric, 0)
            
            if before > 0:
                improvement_pct = ((before - after) / before) * 100
                comparison["improvements"][metric] = {
                    "before": before,
                    "after": after,
                    "change": after - before,
                    "improvement_pct": round(improvement_pct, 2)
                }
            else:
                comparison["improvements"][metric] = {
                    "before": before,
                    "after": after,
                    "change": after - before
                }
        
        return comparison
    
    def print_comparison_report(self, comparison: Dict):
        """打印格式化的对比报告"""
        if "error" in comparison:
            print(f"\n❌ {comparison['error']}")
            return
        
        print("\n" + "="*70)
        print("📊 翻译质量对比报告")
        print("="*70)
        
        stats_a = comparison["version_a"]
        stats_b = comparison["version_b"]
        improvements = comparison["improvements"]
        
        print(f"\n📈 基础统计:")
        print(f"  版本 A: {stats_a['total_blocks']} 条字幕, 平均长度 {stats_a['avg_length']:.1f} 字符")
        print(f"  版本 B: {stats_b['total_blocks']} 条字幕, 平均长度 {stats_b['avg_length']:.1f} 字符")
        
        print(f"\n🎯 质量改进:")
        
        metric_names = {
            "formal_word_count": "书面语出现次数",
            "emotion_loss_count": "情绪标记丢失",
            "length_issues": "长度异常",
            "machine_pattern_count": "机器翻译特征"
        }
        
        for metric, data in improvements.items():
            name = metric_names.get(metric, metric)
            before = data["before"]
            after = data["after"]
            change = data["change"]
            
            if "improvement_pct" in data:
                pct = data["improvement_pct"]
                if pct > 0:
                    print(f"  ✅ {name}: {before} → {after} (改善 {pct:.1f}%)")
                elif pct < 0:
                    print(f"  ⚠️  {name}: {before} → {after} (退步 {abs(pct):.1f}%)")
                else:
                    print(f"  ➖ {name}: {before} → {after} (无变化)")
            else:
                print(f"  ℹ️  {name}: {before} → {after}")
        
        # 书面语词汇详情
        if stats_a.get("formal_words_detail"):
            print(f"\n📝 版本 A 高频书面语:")
            for word, count in stats_a["formal_words_detail"].most_common(5):
                print(f"  - '{word}' 出现 {count} 次")
        
        if stats_b.get("formal_words_detail"):
            print(f"\n📝 版本 B 高频书面语:")
            for word, count in stats_b["formal_words_detail"].most_common(5):
                print(f"  - '{word}' 出现 {count} 次")
        
        # 总体评分
        total_issues_a = sum(d["before"] for d in improvements.values())
        total_issues_b = sum(d["after"] for d in improvements.values())
        
        if total_issues_a > 0:
            overall_improvement = ((total_issues_a - total_issues_b) / total_issues_a) * 100
            print(f"\n🏆 总体质量改善: {overall_improvement:.1f}%")
            
            if overall_improvement > 30:
                print("   评价: 🌟🌟🌟 显著提升")
            elif overall_improvement > 10:
                print("   评价: 🌟🌟 明显改善")
            elif overall_improvement > 0:
                print("   评价: 🌟 小幅优化")
            else:
                print("   评价: ⚠️  需要进一步调整")
        
        print("="*70)


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="翻译质量对比工具")
    parser.add_argument("--before", "-b", required=True, help="优化前的翻译文件")
    parser.add_argument("--after", "-a", required=True, help="优化后的翻译文件")
    parser.add_argument("--original", "-o", help="原始英文字幕（可选）")
    parser.add_argument("--output", help="保存对比报告（JSON）")
    
    args = parser.parse_args()
    
    comparator = TranslationComparator()
    comparison = comparator.compare_two_versions(args.before, args.after, args.original)
    
    comparator.print_comparison_report(comparison)
    
    # 保存报告
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(comparison, f, ensure_ascii=False, indent=2)
        print(f"\n💾 对比报告已保存: {args.output}")


if __name__ == "__main__":
    # 如果直接运行，使用示例
    if len(sys.argv) == 1:
        print("="*70)
        print("翻译质量对比工具")
        print("="*70)
        print("\n使用方法:")
        print("  python compare_translations.py -b 优化前.srt -a 优化后.srt [-o 原文.srt]")
        print("\n示例:")
        print("  python compare_translations.py \\")
        print("    -b old_translation.srt \\")
        print("    -a new_translation.srt \\")
        print("    -o original_english.srt \\")
        print("    --output report.json")
        print("\n💡 提示: 提供原文 (-o) 可以进行更详细的质量分析")
    else:
        main()
