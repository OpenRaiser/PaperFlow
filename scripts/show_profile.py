#!/usr/bin/env python3
"""
Show Profile - Display current user profile
"""

import json
import sys
import io
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "storage-helper" / "scripts"))

from db_ops import get_profile


def format_profile(profile: dict) -> str:
    """Format profile for display"""

    lines = []
    lines.append("=" * 60)
    lines.append("你的学术画像")
    lines.append("=" * 60)
    lines.append(f"User ID: {profile['user_id']}")
    lines.append(f"Version: {profile['version']}")
    lines.append(f"Updated: {profile.get('updated_at', 'N/A')}")
    lines.append("")

    # Core directions
    lines.append("--- 核心方向 ---")
    for direction, weight in profile.get('core_directions', {}).items():
        bar_len = int(weight * 20)
        bar = "#" * bar_len + "-" * (20 - bar_len)
        lines.append(f"{direction:40} {bar} {weight:.2f}")
    lines.append("")

    # Methodology preferences
    lines.append("--- 方法论偏好 ---")
    prefs = profile.get('methodology_preferences', {})
    pref_labels = {
        'preference_data_driven_over_theory': '数据驱动 > 纯理论',
        'preference_systematic_work_over_incremental': '系统性工作 > 单点改进',
        'preference_open_source_code': '有开源代码',
        'preference_multimodal_application': '多模态应用场景'
    }
    for key, label in pref_labels.items():
        status = "Y" if prefs.get(key, False) else " "
        lines.append(f"  [{status}] {label}")
    lines.append("")

    # Must read
    lines.append("--- 必读清单 ---")
    must_read = profile.get('must_read', {})

    authors = must_read.get('authors', [])
    if authors:
        lines.append(f"作者：{', '.join(authors)}")
    else:
        lines.append("作者：(空)")

    institutions = must_read.get('institutions', [])
    if institutions:
        lines.append(f"机构：{', '.join(institutions)}")
    else:
        lines.append("机构：(空)")

    keywords = must_read.get('keywords', [])
    if keywords:
        lines.append(f"关键词：{', '.join(keywords)}")
    else:
        lines.append("关键词：(空)")
    lines.append("")

    # Topic weights
    lines.append("--- 主题权重 ---")
    for topic, weight in profile.get('topic_weights', {}).items():
        lines.append(f"  {topic}: {weight:.2f}")
    lines.append("")

    # Taste profile
    lines.append("--- 品味轮廓 ---")
    taste = profile.get('taste_profile', {})
    preferred = taste.get('preferred_work_type', [])
    dispreferred = taste.get('dispreferred_work_type', [])
    lines.append(f"偏好：{', '.join(preferred) if preferred else '(未设置)'}")
    lines.append(f"不偏好：{', '.join(dispreferred) if dispreferred else '(未设置)'}")
    lines.append("")

    lines.append("=" * 60)
    lines.append("修改方式：")
    lines.append('  "加个必读作者：XXX"')
    lines.append('  "加个机构：XXX"')
    lines.append('  "加个关键词：XXX"')
    lines.append('  "降低 XXX 权重到 0.5"')

    return "\n".join(lines)


def main():
    user_id = sys.argv[1] if len(sys.argv) > 1 else "user_001"

    profile = get_profile(user_id)

    if profile:
        print(format_profile(profile))
    else:
        print(f"[ERROR] No profile found for user: {user_id}")
        print("Run cold_start.py first to create a profile.")


if __name__ == "__main__":
    main()
