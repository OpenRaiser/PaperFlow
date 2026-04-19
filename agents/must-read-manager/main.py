#!/usr/bin/env python3
"""
Must-Read Manager - 必读清单管理代理

职责：管理用户的必读清单（作者、机构、关键词）
支持命令：
- 添加必读作者："/add-must-read author 姓名"
- 添加必读机构："/add-must-read institution 名称"
- 添加必读关键词："/add-must-read keyword 关键词"
- 移除必读项："/remove-must-read author 姓名"
- 查看必读清单："/show-must-read"
"""

import sys
import os
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Literal

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 使用 importlib 导入带连字符的模块
import importlib

# 数据库操作
db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
get_profile = db_ops.get_profile
update_profile = db_ops.update_profile
log_behavior = db_ops.log_behavior

# 飞书报告器
feishu_reporter = importlib.import_module("skills.feishu-reporter.scripts.feishu_reporter")
send_text = feishu_reporter.send_text


LIST_COMMAND_HINTS = ("查看必读", "显示必读", "必读清单", "show must")
ADD_ACTION_HINTS = ("加个", "加上", "添加", "增加", "加", "add")
REMOVE_ACTION_HINTS = ("去掉", "去除", "取消", "移除", "删除", "删掉", "remove", "delete")
ITEM_TYPE_ALIASES = {
    "author": ("必读作者", "作者", "author"),
    "institution": ("必读机构", "机构", "institution"),
    "keyword": ("必读关键词", "关键词", "keyword"),
}
ITEM_TYPE_LABELS = {
    "author": "作者",
    "institution": "机构",
    "keyword": "关键词",
}
COLD_START_MUST_READ_NOTE = "说明：普通“冷启动”会保留这份必读清单；只有“重新冷启动”才会重置。"
CLEAR_READING_LIST_HINT = '  "清空精读列表"'
COMMAND_RE = re.compile(
    r"^\s*(?:请\s*)?(?:把\s*)?"
    r"(?P<action>加个|加上|添加|增加|加|去掉|去除|取消|移除|删除|删掉|add|remove|delete)"
    r"\s*(?:必读|must\s*read\s*)?"
    r"(?P<item_type>作者|机构|关键词|author|institution|keyword)"
    r"\s*(?:[:：]\s*|\s+)?(?P<value>.+?)\s*$",
    flags=re.IGNORECASE,
)


def clean_must_read_value(value: str) -> str:
    """Normalize user-provided must-read values while preserving readable output."""
    cleaned = re.sub(r"\s+", " ", (value or "").strip().strip("\"'`"))
    connector_patterns = (
        r"^(?:的)\s*",
        r"^(?:是|为)\s*",
        r"^(?:叫做|叫|名为)\s*",
    )
    previous = None
    while cleaned and cleaned != previous:
        previous = cleaned
        for pattern in connector_patterns:
            cleaned = re.sub(pattern, "", cleaned, count=1)
        cleaned = cleaned.strip()
    return cleaned


def normalize_must_read_value(value: str) -> str:
    """Build a tolerant lookup key for must-read matching."""
    return clean_must_read_value(value).casefold()


def parse_command(text: str) -> Optional[Dict[str, Any]]:
    """
    解析用户命令

    支持的命令格式：
    - "加个必读作者：Mohammed AlQuraishi"
    - "添加必读作者：张三"
    - "add must read author: John Doe"
    - "移除必读作者：张三"
    - "remove must read author: John Doe"
    - "查看必读清单"
    - "show must read"

    Args:
        text: 用户输入文本

    Returns:
        命令字典 {"action": "add/remove/list", "type": "author/institution/keyword", "value": "..."}
    """
    text = (text or "").strip()
    text_lower = text.lower()

    # 查看清单
    if any(kw in text_lower for kw in LIST_COMMAND_HINTS):
        return {"action": "list"}

    match = COMMAND_RE.match(text)
    if match:
        action_text = match.group("action").lower()
        item_text = match.group("item_type").lower()
        value = clean_must_read_value(match.group("value"))

        for canonical_type, aliases in ITEM_TYPE_ALIASES.items():
            if item_text in {alias.lower() for alias in aliases}:
                return {
                    "action": "add" if action_text in ADD_ACTION_HINTS else "remove",
                    "type": canonical_type,
                    "value": value,
                }

    is_add = any(kw in text_lower for kw in ADD_ACTION_HINTS)
    is_remove = any(kw in text_lower for kw in REMOVE_ACTION_HINTS)
    if not (is_add or is_remove):
        return None

    item_type = None
    matched_alias = None
    for canonical_type, aliases in ITEM_TYPE_ALIASES.items():
        for alias in aliases:
            alias_lower = alias.lower()
            if alias_lower in text_lower:
                item_type = canonical_type
                matched_alias = alias
                break
        if item_type:
            break

    if not item_type or not matched_alias:
        return None

    value = ""
    if ":" in text:
        value = text.split(":", 1)[1]
    elif "：" in text:
        value = text.split("：", 1)[1]
    else:
        alias_index = text_lower.find(matched_alias.lower())
        if alias_index >= 0:
            value = text[alias_index + len(matched_alias):]

    value = clean_must_read_value(value)
    if not value:
        return None

    return {
        "action": "add" if is_add else "remove",
        "type": item_type,
        "value": value,
    }


def add_must_read(profile: Dict, item_type: str, value: str) -> Dict[str, Any]:
    """
    添加必读项

    Args:
        profile: 用户画像
        item_type: 类型 (author/institution/keyword)
        value: 值

    Returns:
        结果字典
    """
    must_read = profile.get("must_read", {"authors": [], "institutions": [], "keywords": []})

    key = f"{item_type}s"
    current_list = must_read.get(key, [])
    item_label = ITEM_TYPE_LABELS.get(item_type, item_type)

    cleaned_value = clean_must_read_value(value)
    normalized_value = normalize_must_read_value(cleaned_value)
    existing_value = next(
        (item for item in current_list if normalize_must_read_value(str(item)) == normalized_value),
        None,
    )
    if existing_value is not None:
        return {"success": False, "message": f"{existing_value} 已在必读清单中"}

    current_list.append(cleaned_value)
    must_read[key] = current_list
    profile["must_read"] = must_read
    profile["updated_at"] = datetime.now().isoformat()

    return {"success": True, "message": f"已添加 {cleaned_value} 到必读{item_label}清单"}


def remove_must_read(profile: Dict, item_type: str, value: str) -> Dict[str, Any]:
    """
    移除必读项

    Args:
        profile: 用户画像
        item_type: 类型
        value: 值

    Returns:
        结果字典
    """
    must_read = profile.get("must_read", {"authors": [], "institutions": [], "keywords": []})

    key = f"{item_type}s"
    current_list = must_read.get(key, [])
    item_label = ITEM_TYPE_LABELS.get(item_type, item_type)
    cleaned_value = clean_must_read_value(value)
    normalized_value = normalize_must_read_value(cleaned_value)
    matched_value = next(
        (item for item in current_list if normalize_must_read_value(str(item)) == normalized_value),
        None,
    )

    if matched_value is None:
        return {"success": False, "message": f"{cleaned_value} 不在必读清单中"}

    current_list.remove(matched_value)
    must_read[key] = current_list
    profile["must_read"] = must_read
    profile["updated_at"] = datetime.now().isoformat()

    return {"success": True, "message": f"已从必读{item_label}清单中移除 {matched_value}"}


def format_must_read_list(profile: Dict) -> str:
    """
    格式化必读清单列表

    Args:
        profile: 用户画像

    Returns:
        格式化文本
    """
    lines = []
    lines.append("=" * 60)
    lines.append("📋 必读清单")
    lines.append("=" * 60)
    lines.append("")

    must_read = profile.get("must_read", {"authors": [], "institutions": [], "keywords": []})

    # 作者
    authors = must_read.get("authors", [])
    lines.append(f"━━━ 👥 作者 ({len(authors)}) ━━━")
    if authors:
        for author in authors:
            lines.append(f"  • {author}")
    else:
        lines.append("  （空，待添加）")
    lines.append("")

    # 机构
    institutions = must_read.get("institutions", [])
    lines.append(f"━━━ 🏛️ 机构 ({len(institutions)}) ━━━")
    if institutions:
        for inst in institutions:
            lines.append(f"  • {inst}")
    else:
        lines.append("  （空，待添加）")
    lines.append("")

    # 关键词
    keywords = must_read.get("keywords", [])
    lines.append(f"━━━ 🔑 关键词 ({len(keywords)}) ━━━")
    if keywords:
        for kw in keywords:
            lines.append(f"  • {kw}")
    else:
        lines.append("  （空，待添加）")
    lines.append("")

    lines.append(COLD_START_MUST_READ_NOTE)
    lines.append("")
    lines.append("=" * 60)
    lines.append("添加方式：")
    lines.append('  "加个必读作者：Mohammed AlQuraishi"')
    lines.append('  "添加必读机构：MIT"')
    lines.append('  "添加必读关键词：GUI Agent"')
    lines.append(CLEAR_READING_LIST_HINT)
    lines.append("")
    lines.append("移除方式：")
    lines.append('  "移除必读作者：张三"')
    lines.append("=" * 60)

    return "\n".join(lines)


def format_profile_update(profile: Dict) -> str:
    """
    格式化画像更新确认消息

    Args:
        profile: 用户画像字典

    Returns:
        格式化文本
    """
    # 研究方向翻译
    translations = {
        "gui-agent": "GUI Agent",
        "multimodal-reasoning": "多模态推理",
        "vision": "视觉",
        "language": "语言",
        "machine-learning": "机器学习",
        "deep-learning": "深度学习",
        "reinforcement-learning": "强化学习",
        "reasoning": "推理",
        "agent": "智能体",
        "optimization": "优化",
        "retrieval": "检索",
        "generation": "生成",
        "data-native": "数据原生",
        "bio-molecular": "生物分子",
        "science-discovery": "科学发现",
    }

    lines = []
    lines.append("=" * 60)
    lines.append("📊 学术画像已更新")
    lines.append("=" * 60)
    lines.append("")

    # 核心方向
    lines.append("━━━ 核心方向 ━━━")
    core_directions = profile.get("core_directions", {})
    if core_directions:
        for direction, weight in sorted(core_directions.items(), key=lambda x: -x[1]):
            direction_cn = translations.get(direction, direction)
            bar_length = max(1, int(weight * 20))
            bar = "█" * bar_length + "░" * (20 - bar_length)
            lines.append(f"{direction_cn} [{bar}] {weight:.2f}")
    else:
        lines.append("（未检测到明确方向，待学习）")
    lines.append("")

    # 必读清单
    lines.append("━━━ 必读清单 ━━━")
    must_read = profile.get("must_read", {"authors": [], "institutions": [], "keywords": []})
    authors = must_read.get("authors", [])
    institutions = must_read.get("institutions", [])
    keywords = must_read.get("keywords", [])

    lines.append(f"作者：{', '.join(authors) or '（空，待添加）'}")
    lines.append(f"机构：{', '.join(institutions) or '（空，待添加）'}")
    lines.append(f"关键词：{', '.join(keywords) or '（空，待添加）'}")
    lines.append(COLD_START_MUST_READ_NOTE)
    lines.append("")

    # 阅读历史
    reading_history = profile.get("reading_history", [])
    lines.append(f"阅读历史：{len(reading_history)} 篇论文")
    lines.append(f"最后更新：{profile.get('updated_at', 'unknown')}")
    lines.append("")

    lines.append("=" * 60)
    lines.append("你可以随时回复调整：")
    lines.append('  "加个必读作者：Mohammed AlQuraishi"')
    lines.append(CLEAR_READING_LIST_HINT)
    lines.append('  "降低 GUI Agent 权重"')
    lines.append('  "我最近对 protein language model 更感兴趣"')
    lines.append("=" * 60)

    return "\n".join(lines)


def process_must_read_command(
    user_id: str,
    command_text: str,
    feishu_user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    send_to_feishu: bool = True
) -> Dict[str, Any]:
    """
    处理必读清单命令

    Args:
        user_id: 用户 ID
        command_text: 用户命令文本
        feishu_user_id: 飞书用户 ID（open_id，用于发送消息）
        chat_id: 聊天 ID（优先使用，发送到原对话框）
        send_to_feishu: 是否发送飞书

    Returns:
        处理结果
    """
    print(f"Processing must-read command: {command_text!r}")

    # 解析命令
    command = parse_command(command_text)

    # 优先使用 chat_id，否则使用 feishu_user_id
    target_id = chat_id or feishu_user_id
    use_chat_id = chat_id is not None

    if not command:
        message = "未识别到有效命令。支持：\n  • 添加必读作者/机构/关键词\n  • 移除必读作者/机构/关键词\n  • 查看必读清单"
        if send_to_feishu and target_id:
            send_text(target_id, message, use_chat_id=use_chat_id)
        return {"success": False, "message": message}

    # 获取用户画像
    profile = get_profile(user_id)
    if not profile:
        message = "未找到用户画像"
        if send_to_feishu and target_id:
            send_text(target_id, message, use_chat_id=use_chat_id)
        return {"success": False, "message": message}

    # 执行操作
    if command["action"] == "list":
        result_text = format_must_read_list(profile)
        if send_to_feishu and target_id:
            send_text(target_id, result_text, use_chat_id=use_chat_id)
        return {"success": True, "action": "list"}

    elif command["action"] == "add":
        result = add_must_read(profile, command["type"], command["value"])
        if result["success"]:
            # 保存更新
            update_profile(user_id, profile)

            # 记录行为日志
            log_behavior(
                user_id=user_id,
                push_id="must_read_manager",
                paper_id=None,
                action=f"add_{command['type']}",
                action_type="must_read_update",
                category="must_read_manager",
                metadata={"value": command["value"]}
            )

            # 发送画像更新确认
            if send_to_feishu and target_id:
                update_text = format_profile_update(profile)
                send_text(target_id, update_text, use_chat_id=use_chat_id)
        return result

    elif command["action"] == "remove":
        result = remove_must_read(profile, command["type"], command["value"])
        if result["success"]:
            # 保存更新
            update_profile(user_id, profile)

            # 记录行为日志
            log_behavior(
                user_id=user_id,
                push_id="must_read_manager",
                paper_id=None,
                action=f"remove_{command['type']}",
                action_type="must_read_update",
                category="must_read_manager",
                metadata={"value": command["value"]}
            )

            # 发送画像更新确认
            if send_to_feishu and target_id:
                update_text = format_profile_update(profile)
                send_text(target_id, update_text, use_chat_id=use_chat_id)
        return result

    return {"success": False, "message": "Unknown command"}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Must-Read Manager - 管理必读清单")
    parser.add_argument("--user-id", type=str, default="user_001", help="用户 ID")
    parser.add_argument("--command", type=str, required=True, help="命令文本")
    parser.add_argument("--send-feishu", action="store_true", default=True, help="发送到飞书")
    parser.add_argument("--feishu-user-id", type=str, help="飞书用户 ID")

    args = parser.parse_args()

    # 设置飞书用户 ID
    feishu_user_id = args.feishu_user_id or os.environ.get("FEISHU_USER_ID", "").strip()

    result = process_must_read_command(
        user_id=args.user_id,
        command_text=args.command,
        feishu_user_id=feishu_user_id,
        send_to_feishu=args.send_feishu
    )

    print(f"\nResult: {json.dumps(result, indent=2, ensure_ascii=False)}")
