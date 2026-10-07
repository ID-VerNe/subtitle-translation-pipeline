# -*- coding: utf-8 -*-
"""
Few-Shot 示例管理器
为翻译任务动态注入高质量示例
"""

from typing import List, Dict

# @lat: [[core-context#Key Concepts#Few-Shot 示例引导（FewShotExampleManager）]]
class FewShotExampleManager:
    """管理分类的 Few-Shot 翻译示例"""
    
    def __init__(self):
        # 按场景类型分类的示例
        self.examples = {
            "humor_sarcasm": [
                {
                    "original": "Yeah, but these things will never take over man.",
                    "literal": "是的，但这些东西永远不会接管人类。",
                    "polished": "对，但这些玩意儿永远取代不了人。",
                    "note": "口语化，'things'→'玩意儿'更生动"
                },
                {
                    "original": "Fucking fly-tippers, honestly.",
                    "literal": "该死的乱扔垃圾的人，说实话。",
                    "polished": "那帮该死的垃圾虫，真是。",
                    "note": "俚语本地化，保留粗口情绪"
                }
            ],
            
            "technical_farming": [
                {
                    "original": "The AgBot's Presbyterian work ethic meant farming was going on day and night.",
                    "literal": "农业机器人的长老会工作伦理意味着农业日夜不停。",
                    "polished": "而农业机器人那没完没了的苦行僧式干劲，让农活日夜不停。",
                    "note": "文化意译，Presbyterian work ethic→苦行僧式干劲"
                }
            ],
            
            "dialogue_casual": [
                {
                    "original": "So you're not sold on this, Gerald?",
                    "literal": "所以你不买账，杰拉德？",
                    "polished": "所以你还没被它说服吗，杰拉德？",
                    "note": "问句语气更自然，符合对话场景"
                },
                {
                    "original": "Pull up a chair, I'll talk you through it.",
                    "literal": "拉把椅子，我给你讲一遍。",
                    "polished": "拉把椅子，我给你讲讲。",
                    "note": "叠词更口语化"
                }
            ],
            
            "emotion_strong": [
                {
                    "original": "Oh my God, I have. I missed all that.",
                    "literal": "哦，我的上帝，我确实错过了。我错过了所有那些。",
                    "polished": "天啊，还真是。那一片我全漏了。",
                    "note": "情绪词简化，避免重复"
                }
            ]
        }
    
    def get_examples_for_scene(self, scene_tone: List[str], max_examples: int = 3) -> str:
        """
        根据场景语气动态选择示例
        
        Args:
            scene_tone: 场景语气标签 ["humorous", "technical", "casual"]
            max_examples: 最多返回几个示例
            
        Returns:
            格式化的示例文本
        """
        selected = []
        
        # 映射场景语气到示例类型
        tone_mapping = {
            "humorous": "humor_sarcasm",
            "sarcastic": "humor_sarcasm",
            "technical": "technical_farming",
            "casual": "dialogue_casual",
            "conversational": "dialogue_casual",
            "emotional": "emotion_strong",
            "frustrated": "emotion_strong"
        }
        
        # 收集匹配的示例
        for tone in scene_tone:
            category = tone_mapping.get(tone.lower())
            if category and category in self.examples:
                selected.extend(self.examples[category])
        
        # 如果没有匹配，使用通用示例
        if not selected:
            selected = self.examples["dialogue_casual"]
        
        # 限制数量
        selected = selected[:max_examples]
        
        # 格式化输出
        output = "# Few-Shot Translation Examples\n\n"
        for i, ex in enumerate(selected, 1):
            output += f"## Example {i}\n"
            output += f"**Original:** {ex['original']}\n"
            output += f"**Literal (直译):** {ex['literal']}\n"
            output += f"**Polished (意译):** {ex['polished']}\n"
            output += f"*Note:* {ex['note']}\n\n"
        
        return output
    
    def add_custom_example(self, category: str, example: Dict):
        """添加自定义示例（用于用户手动优化）"""
        if category not in self.examples:
            self.examples[category] = []
        self.examples[category].append(example)


# 使用示例
if __name__ == "__main__":
    manager = FewShotExampleManager()
    
    # 模拟场景：幽默+技术
    scene_tone = ["humorous", "technical"]
    examples_text = manager.get_examples_for_scene(scene_tone, max_examples=2)
    
    print(examples_text)
