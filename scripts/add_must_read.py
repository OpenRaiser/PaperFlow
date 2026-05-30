#!/usr/bin/env python3
"""
Add Must Read - Add author/institution/keyword to must-read list
"""

import json
import sys
import io
import re
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "storage-helper" / "scripts"))

from db_ops import get_profile, update_profile
from config.direction_lexicon import normalize_direction_key, resolve_canonical_direction


SOFT_DIRECTION_WEIGHT = 0.62
BROAD_MUST_READ_KEYWORD_DIRECTIONS = {
    "agent",
    "ai-for-science",
    "computer-vision",
    "deep-learning",
    "embodied-ai",
    "language",
    "machine-learning",
    "multimodal-learning",
    "multimodal-reasoning",
    "nlp",
    "optimization",
    "reasoning",
    "reinforcement-learning",
    "retrieval",
    "science-discovery",
    "scientific-reasoning",
    "vision",
    "vision-language",
    "vision-language-model",
}
BROAD_MUST_READ_KEYWORD_ALIASES = {
    "ai": "machine-learning",
    "artificial-intelligence": "machine-learning",
    "large-language-model": "large-language-model",
    "large-language-models": "large-language-model",
    "llm": "large-language-model",
    "llms": "large-language-model",
}


def _coerce_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_broad_must_read_keyword(value):
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    normalized_key = normalize_direction_key(cleaned)
    if normalized_key in BROAD_MUST_READ_KEYWORD_ALIASES:
        return BROAD_MUST_READ_KEYWORD_ALIASES[normalized_key]

    resolved = resolve_canonical_direction(cleaned, include_paper_terms=True)
    if not resolved:
        return None
    canonical = str(resolved.get("canonical_name") or "").strip()
    if canonical in BROAD_MUST_READ_KEYWORD_DIRECTIONS:
        return canonical
    return None


def _keyword_resolves_to_direction(value, canonical_direction):
    resolved = resolve_canonical_direction(str(value or "").strip(), include_paper_terms=True)
    if resolved:
        return resolved.get("canonical_name") == canonical_direction
    return normalize_direction_key(value) == canonical_direction


def _route_keyword_to_interest_direction(profile, current_keywords, raw_value, canonical_direction):
    current_keywords[:] = [
        keyword for keyword in current_keywords
        if not _keyword_resolves_to_direction(keyword, canonical_direction)
    ]
    core_directions = profile.get("core_directions")
    if not isinstance(core_directions, dict):
        core_directions = {}
    topic_weights = profile.get("topic_weights")
    if not isinstance(topic_weights, dict):
        topic_weights = {}

    previous_core = _coerce_float(core_directions.get(canonical_direction), 0.0)
    previous_topic = _coerce_float(topic_weights.get(canonical_direction), 0.0)
    core_directions[canonical_direction] = max(previous_core, SOFT_DIRECTION_WEIGHT)
    topic_weights[canonical_direction] = max(previous_topic, SOFT_DIRECTION_WEIGHT)
    profile["core_directions"] = core_directions
    profile["topic_weights"] = topic_weights
    return f"{raw_value} -> {canonical_direction}"


def parse_input(user_input: str):
    """Parse user input to extract operation type and entities"""

    # Check for list/query operations first
    list_patterns = [r'.*必读.*清单.*', r'.*当前.*清单.*', r'.*有什么.*', r'.*看看.*']
    for pattern in list_patterns:
        if re.search(pattern, user_input, re.IGNORECASE):
            return ('list', None, None)

    # Patterns for adding
    add_patterns = [
        (r'.*作者.*[:：]\s*(.+)', 'add', 'authors'),
        (r'.*机构.*[:：]\s*(.+)', 'add', 'institutions'),
        (r'.*关键词.*[:：]\s*(.+)', 'add', 'keywords'),
    ]
    for pattern, op, entity_type in add_patterns:
        match = re.search(pattern, user_input, re.IGNORECASE)
        if match:
            entities = [e.strip() for e in re.split(r'[,，]', match.group(1))]
            return (op, entity_type, entities)

    # Patterns for removing
    remove_patterns = [
        (r'.*删除.*作者.*[:：]\s*(.+)', 'remove', 'authors'),
        (r'.*删除.*机构.*[:：]\s*(.+)', 'remove', 'institutions'),
        (r'.*删除.*关键词.*[:：]\s*(.+)', 'remove', 'keywords'),
        (r'.*去掉.*作者.*[:：]\s*(.+)', 'remove', 'authors'),
        (r'.*去掉.*机构.*[:：]\s*(.+)', 'remove', 'institutions'),
        (r'.*去掉.*关键词.*[:：]\s*(.+)', 'remove', 'keywords'),
    ]
    for pattern, op, entity_type in remove_patterns:
        match = re.search(pattern, user_input, re.IGNORECASE)
        if match:
            entities = [e.strip() for e in re.split(r'[,，]', match.group(1))]
            return (op, entity_type, entities)

    # Patterns for updating weights
    weight_patterns = [
        (r'.*降低.*?(.+?)?权重.*?(到 | 为 | 至)\s*(.+)', 'update_weight', 'down'),
        (r'.*提高.*?(.+?)?权重.*?(到 | 为 | 至)\s*(.+)', 'update_weight', 'up'),
        (r'.*调整.*?(.+?)?权重.*?(到 | 为 | 至)\s*(.+)', 'update_weight', 'set'),
        (r'.*?权重.*?(到 | 为 | 至)\s*([0-9.]+)', 'update_weight', 'set'),
    ]
    for pattern, op, direction in weight_patterns:
        match = re.search(pattern, user_input, re.IGNORECASE)
        if match:
            topic = match.group(1).strip() if match.group(1) else None
            weight = float(match.group(3).strip())
            return ('update_weight', direction, {'topic': topic, 'weight': weight})

    return None


def add_must_read(profile, entity_type, entities):
    """Add entities to must-read list"""
    must_read = profile.get('must_read', {})
    current_list = must_read.get(entity_type, [])
    added, already_exists, routed_to_interest = [], [], []
    for entity in entities:
        if entity_type == "keywords":
            broad_direction = _resolve_broad_must_read_keyword(entity)
            if broad_direction:
                routed_to_interest.append(
                    _route_keyword_to_interest_direction(profile, current_list, entity, broad_direction)
                )
                continue
        if entity in current_list:
            already_exists.append(entity)
        else:
            added.append(entity)
            current_list.append(entity)

    must_read[entity_type] = current_list
    updated = profile.copy()
    updated['must_read'] = must_read
    updated['version'] = f"0.{int(profile.get('version', '0.1').split('.')[1]) + 1}"
    updated['updated_at'] = datetime.now().isoformat()

    type_labels = {'authors': '作者', 'institutions': '机构', 'keywords': '关键词'}
    label = type_labels.get(entity_type, entity_type)

    if added or routed_to_interest:
        msg = f"[OK] 已添加 {label}：" + ", ".join(added)
        if not added:
            msg = "[OK] 已更新兴趣方向"
        if routed_to_interest:
            msg += "\n[提示] 以下宽泛关键词已转为软兴趣方向，不进入硬必读："
            msg += "\n" + "\n".join(f"  - {item}" for item in routed_to_interest)
        if already_exists:
            msg += f"\n[提示] 已存在：" + ", ".join(already_exists)
        msg += f"\n\n当前必读{label}清单：\n" + "\n".join(f"  - {e}" for e in current_list)
    elif already_exists:
        msg = f"[提示] {', '.join(already_exists)} 已在必读{label}清单中"
    else:
        msg = "[错误] 未添加任何内容"
    return (bool(added or routed_to_interest), msg, updated if (added or routed_to_interest) else None)


def remove_must_read(profile, entity_type, entities):
    """Remove entities from must-read list"""
    must_read = profile.get('must_read', {})
    current_list = must_read.get(entity_type, [])
    removed, not_found = [], []
    for entity in entities:
        if entity in current_list:
            current_list.remove(entity)
            removed.append(entity)
        else:
            not_found.append(entity)

    updated = profile.copy()
    updated['must_read'] = must_read
    updated['version'] = f"0.{int(profile.get('version', '0.1').split('.')[1]) + 1}"
    updated['updated_at'] = datetime.now().isoformat()

    type_labels = {'authors': '作者', 'institutions': '机构', 'keywords': '关键词'}
    label = type_labels.get(entity_type, entity_type)

    if removed:
        msg = f"[OK] 已删除 {label}：" + ", ".join(removed)
        if current_list:
            msg += f"\n\n当前必读{label}清单：\n" + "\n".join(f"  - {e}" for e in current_list)
        else:
            msg += f"\n当前必读{label}清单为空"
    elif not_found:
        msg = f"[提示] {', '.join(not_found)} 不在必读{label}清单中"
    else:
        msg = "[错误] 未删除任何内容"
    return (len(removed) > 0, msg, updated if removed else None)


def list_must_read(profile):
    """List current must-read items"""
    must_read = profile.get('must_read', {})
    lines = ["当前必读清单：", ""]
    for key, label in [('authors', '作者'), ('institutions', '机构'), ('keywords', '关键词')]:
        items = must_read.get(key, [])
        lines.append(f"{label} ({len(items)}):")
        for item in items:
            lines.append(f"  🔒 {item}")
        if not items:
            lines.append("  (空)")
        lines.append("")
    return "\n".join(lines)


def update_weight(profile, direction, params):
    """Update direction weight"""
    topic = params.get('topic')
    new_weight = params.get('weight', 0.5)
    core_directions = profile.get('core_directions', {})

    matched_topic = None
    if topic:
        for t in core_directions.keys():
            if topic.lower() in t.lower() or t.lower() in topic.lower():
                matched_topic = t
                break

    if not matched_topic:
        topic_weights = profile.get('topic_weights', {})
        for t in topic_weights.keys():
            if topic.lower() in t.lower() or t.lower() in topic.lower():
                matched_topic = t
                core_directions = topic_weights
                break

    if not matched_topic:
        return (False, f"[错误] 未找到方向：{topic}", None)

    old_weight = core_directions.get(matched_topic, 0.5)
    if direction == 'down':
        new_weight = max(0.1, old_weight - 0.1)
    elif direction == 'up':
        new_weight = min(1.0, old_weight + 0.1)

    updated = profile.copy()
    if matched_topic in profile.get('core_directions', {}):
        updated['core_directions'] = profile['core_directions'].copy()
        updated['core_directions'][matched_topic] = new_weight
    if matched_topic in profile.get('topic_weights', {}):
        updated['topic_weights'] = profile['topic_weights'].copy()
        updated['topic_weights'][matched_topic] = new_weight
    updated['version'] = f"0.{int(profile.get('version', '0.1').split('.')[1]) + 1}"
    updated['updated_at'] = datetime.now().isoformat()

    msg = f"[OK] 已调整 {matched_topic} 权重：{old_weight:.2f} → {new_weight:.2f}"
    return (True, msg, updated)


def main():
    user_id = "user_001"
    user_input = sys.argv[1] if len(sys.argv) > 1 else ""

    if not user_input:
        print("用法：python add_must_read.py \"加个必读作者：XXX\"")
        print("示例:")
        print('  python add_must_read.py "加个必读作者：Mohammed AlQuraishi"')
        print('  python add_must_read.py "加个机构：Shanghai AI Lab"')
        print('  python add_must_read.py "加个关键词：phase transition"')
        print('  python add_must_read.py "查看必读清单"')
        print('  python add_must_read.py "降低 Multimodal 权重到 0.5"')
        return

    profile = get_profile(user_id)
    if not profile:
        print(f"[错误] 未找到用户画像：{user_id}")
        return

    result = parse_input(user_input)
    if not result:
        print("[错误] 未识别操作类型")
        print("请使用以下格式:")
        print('  "加个必读作者：XXX"')
        print('  "加个机构：XXX"')
        print('  "加个关键词：XXX"')
        print('  "删除必读作者：XXX"')
        print('  "查看必读清单"')
        print('  "降低 XXX 权重到 0.5"')
        return

    op, entity_type, entities = result

    if op == 'add':
        success, msg, updated = add_must_read(profile, entity_type, entities)
    elif op == 'remove':
        success, msg, updated = remove_must_read(profile, entity_type, entities)
    elif op == 'list':
        msg = list_must_read(profile)
        updated = None
    elif op == 'update_weight':
        success, msg, updated = update_weight(profile, entity_type, entities)
    else:
        msg = "[错误] 未知操作"
        updated = None

    print(msg)

    if updated:
        update_profile(user_id, updated)
        print(f"\n[已更新] 画像版本：{updated['version']}")


if __name__ == "__main__":
    main()
