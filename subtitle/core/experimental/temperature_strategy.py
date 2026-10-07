# -*- coding: utf-8 -*-
"""
动态温度调整策略
根据场景类型、内容难度自动调整 LLM temperature
"""

from typing import Dict, List

# @lat: [[core-context#Key Concepts#动态温度策略（DynamicTemperatureStrategy）]]
class DynamicTemperatureStrategy:
    """根据场景智能调整模型温度"""
    
    def __init__(self, base_temp_literal: float = 0.3, base_temp_polish: float = 0.5):
        self.base_literal = base_temp_literal
        self.base_polish = base_temp_polish
        
        # 场景类型对温度的影响
        self.tone_modifiers = {
            # 需要精确翻译的场景 → 降低温度
            "technical": -0.1,
            "instructional": -0.15,
            "factual": -0.1,
            
            # 需要创意表达的场景 → 提高温度
            "humorous": +0.15,
            "sarcastic": +0.15,
            "emotional": +0.1,
            "dramatic": +0.1,
            
            # 中性场景
            "casual": 0.0,
            "conversational": 0.0
        }
        
        # 内容特征对温度的影响
        self.content_modifiers = {
            "has_numbers": -0.1,      # 包含数字→降低温度保证准确
            "has_proper_names": -0.05, # 包含人名地名→稍微降低
            "has_slang": +0.1,         # 包含俚语→提高创造性
            "has_cultural_ref": +0.1,  # 文化梗→需要灵活转化
            "short_utterance": +0.05   # 短句→可以更灵活
        }
    
    def calculate_temperature(
        self, 
        stage: str,  # "literal" or "polish"
        scene_tone: List[str],
        content_features: List[str]
    ) -> float:
        """
        计算当前批次的最优温度
        
        Args:
            stage: 翻译阶段 ("literal" / "polish")
            scene_tone: 场景语气标签 ["humorous", "technical"]
            content_features: 内容特征 ["has_numbers", "has_slang"]
            
        Returns:
            调整后的温度值 (范围 0.0 - 1.0)
        """
        base = self.base_literal if stage == "literal" else self.base_polish
        
        # 累加场景修正
        tone_adjustment = sum(
            self.tone_modifiers.get(tone.lower(), 0.0) 
            for tone in scene_tone
        )
        
        # 累加内容特征修正
        content_adjustment = sum(
            self.content_modifiers.get(feat.lower(), 0.0)
            for feat in content_features
        )
        
        # 计算最终温度
        final_temp = base + tone_adjustment + content_adjustment
        
        # 限制范围 [0.0, 1.0]
        final_temp = max(0.0, min(1.0, final_temp))
        
        return round(final_temp, 2)
    
    def analyze_content_features(self, text: str) -> List[str]:
        """
        自动分析文本特征
        
        Args:
            text: 原始英文文本
            
        Returns:
            特征标签列表
        """
        import re
        features = []
        
        # 检查是否包含数字
        if re.search(r'\d', text):
            features.append("has_numbers")
        
        # 检查是否包含大写专有名词 (简单判断)
        if re.search(r'\b[A-Z][a-z]+\b', text):
            features.append("has_proper_names")
        
        # 检查常见俚语标志
        slang_markers = ['fuck', 'shit', 'bloody', 'damn', 'gonna', 'wanna']
        if any(marker in text.lower() for marker in slang_markers):
            features.append("has_slang")
        
        # 检查是否为短句 (少于5个词)
        if len(text.split()) < 5:
            features.append("short_utterance")
        
        return features
    
    def get_recommendation(
        self, 
        scene_tone: List[str], 
        sample_text: str
    ) -> Dict:
        """
        获取完整的温度建议
        
        Returns:
            {
                "literal_temp": 0.25,
                "polish_temp": 0.65,
                "reason": "场景为幽默+对话，提高润色创造性"
            }
        """
        content_features = self.analyze_content_features(sample_text)
        
        literal_temp = self.calculate_temperature("literal", scene_tone, content_features)
        polish_temp = self.calculate_temperature("polish", scene_tone, content_features)
        
        # 生成解释
        reason_parts = []
        if scene_tone:
            reason_parts.append(f"场景语气: {', '.join(scene_tone)}")
        if content_features:
            reason_parts.append(f"内容特征: {', '.join(content_features)}")
        
        return {
            "literal_temp": literal_temp,
            "polish_temp": polish_temp,
            "reason": " | ".join(reason_parts) if reason_parts else "使用默认温度"
        }


# 使用示例
if __name__ == "__main__":
    strategy = DynamicTemperatureStrategy()
    
    # 场景1：技术对话 + 包含数字
    scene1 = ["technical", "instructional"]
    text1 = "The AgBot covers 6,000 square meters per hour."
    rec1 = strategy.get_recommendation(scene1, text1)
    print(f"场景1: {rec1}")
    
    # 场景2：幽默讽刺 + 俚语
    scene2 = ["humorous", "sarcastic"]
    text2 = "Fucking fly-tippers, honestly."
    rec2 = strategy.get_recommendation(scene2, text2)
    print(f"场景2: {rec2}")
