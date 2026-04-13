#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Direction Lexicon - 研究方向词典管理

支持：
1. 加载持久化的方向词典
2. 保存新识别的方向
3. 合并到 DIRECTION_KEYWORDS
"""

import json
import os
from typing import Dict, List, Any

# 持久化文件路径
LEXICON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "config",
    "direction_lexicon.json"
)

# 默认词典（启动时加载）
DEFAULT_LEXICON = {
    "quantum-computing": {
        "name": "Quantum Computing",
        "name_cn": "量子计算",
        "keywords": ["quantum", "quantum computing", "quantum algorithm", "qubit", "量子", "量子算法"]
    },
    "embodied-ai": {
        "name": "Embodied AI",
        "name_cn": "具身智能",
        "keywords": ["embodied", "robot", "robotics", "physical agent", "具身", "机器人"]
    },
    "neuro-symbolic": {
        "name": "Neuro-Symbolic AI",
        "name_cn": "神经符号 AI",
        "keywords": ["neuro-symbolic", "symbolic", "neural symbolic", "hybrid ai", "神经符号", "符号 AI"]
    },
}


def load_lexicon() -> Dict[str, Any]:
    """加载方向词典（合并默认和持久化）"""
    lexicon = dict(DEFAULT_LEXICON)

    if os.path.exists(LEXICON_PATH):
        try:
            with open(LEXICON_PATH, 'r', encoding='utf-8') as f:
                user_lexicon = json.load(f)
                lexicon.update(user_lexicon)
        except Exception as e:
            print(f"Failed to load user lexicon: {e}")

    return lexicon


def save_lexicon(lexicon: Dict[str, Any]) -> bool:
    """保存用户词典（仅保存用户添加的部分）"""
    try:
        # 只保存用户添加的方向（不在 DEFAULT_LEXICON 中的）
        user_lexicon = {
            k: v for k, v in lexicon.items()
            if k not in DEFAULT_LEXICON
        }

        os.makedirs(os.path.dirname(LEXICON_PATH), exist_ok=True)
        with open(LEXICON_PATH, 'w', encoding='utf-8') as f:
            json.dump(user_lexicon, f, indent=2, ensure_ascii=False)

        return True
    except Exception as e:
        print(f"Failed to save lexicon: {e}")
        return False


def add_new_direction(
    direction_key: str,
    name: str,
    name_cn: str,
    keywords: List[str],
    source_text: str = ""
) -> bool:
    """
    添加新方向到词典

    Args:
        direction_key: 方向键（英文，连字符格式）
        name: 英文显示名
        name_cn: 中文显示名
        keywords: 关键词列表
        source_text: 触发学习的原文（可选）

    Returns:
        是否成功
    """
    lexicon = load_lexicon()

    if direction_key in lexicon:
        # 已存在，追加关键词
        existing_keywords = lexicon[direction_key].get("keywords", [])
        for kw in keywords:
            if kw not in existing_keywords:
                existing_keywords.append(kw)
        lexicon[direction_key]["keywords"] = existing_keywords
        print(f"[Lexicon] Updated existing direction: {direction_key}")
    else:
        # 新方向
        lexicon[direction_key] = {
            "name": name,
            "name_cn": name_cn,
            "keywords": keywords,
        }
        if source_text:
            lexicon[direction_key]["source_text"] = source_text
        print(f"[Lexicon] Added new direction: {direction_key}")

    return save_lexicon(lexicon)


def get_lexicon_keywords() -> Dict[str, List[str]]:
    """
    获取词典关键词映射（用于合并到 DIRECTION_KEYWORDS）

    Returns:
        {direction_key: [keywords...]}
    """
    lexicon = load_lexicon()
    return {
        key: data.get("keywords", [])
        for key, data in lexicon.items()
    }


if __name__ == "__main__":
    # 测试
    print("Loading lexicon...")
    lexicon = load_lexicon()
    print(f"Loaded {len(lexicon)} directions")

    print("\nAdding test direction...")
    add_new_direction(
        "test-direction",
        "Test Direction",
        "测试方向",
        ["test", "testing", "测试"],
        "我最近对测试方向很感兴趣"
    )

    print("\nKeywords mapping:")
    keywords = get_lexicon_keywords()
    for key, kws in keywords.items():
        print(f"  {key}: {kws}")
