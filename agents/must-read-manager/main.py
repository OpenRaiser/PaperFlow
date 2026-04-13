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
    text_lower = text.lower().strip()

    # 查看清单
    if any(kw in text_lower for kw in ["查看必读", "show must", "显示必读", "必读清单"]):
        return {"action": "list"}

    # 添加操作
    add_keywords = ["加", "添加", "add"]
    is_add = any(kw in text_lower for kw in add_keywords)

    # 移除操作
    remove_keywords = ["移除", "删除", "remove", "删掉"]
    is_remove = any(kw in text_lower for kw in remove_keywords)

    # 确定类型
    type_mapping = {
        "author": "author",
        "作者": "author",
        "institution": "institution",
        "机构": "institution",
        "keyword": "keyword",
        "关键词": "keyword",
    }

    item_type = None
    for key, value in type_mapping.items():
        if key in text_lower:
            item_type = value
            break

    if not item_type:
        return None

    if not (is_add or is_remove):
        return None

    # 提取值（冒号后面的内容）
    value = ""
    if ":" in text:
        value = text.split(":", 1)[1].strip()
    elif "：" in text:
        value = text.split("：", 1)[1].strip()
    else:
        # 尝试提取最后一个词
        parts = text.split()
        if parts:
            value = parts[-1].strip()

    if not value:
        return None

    return {
        "action": "add" if is_add else "remove",
        "type": item_type,
        "value": value.strip(),
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

    if value in current_list:
        return {"success": False, "message": f"{value} 已在必读清单中"}

    current_list.append(value)
    must_read[key] = current_list
    profile["must_read"] = must_read
    profile["updated_at"] = datetime.now().isoformat()

    return {"success": True, "message": f"已添加 {value} 到必读{item_type}清单"}


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

    if value not in current_list:
        return {"success": False, "message": f"{value} 不在必读清单中"}

    current_list.remove(value)
    must_read[key] = current_list
    profile["must_read"] = must_read
    profile["updated_at"] = datetime.now().isoformat()

    return {"success": True, "message": f"已从必读{item_type}清单中移除 {value}"}


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

    lines.append("=" * 60)
    lines.append("添加方式：")
    lines.append('  "加个必读作者：Mohammed AlQuraishi"')
    lines.append('  "添加必读机构：MIT"')
    lines.append('  "添加必读关键词：GUI Agent"')
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
    lines.append("")

    # 阅读历史
    reading_history = profile.get("reading_history", [])
    lines.append(f"阅读历史：{len(reading_history)} 篇论文")
    lines.append(f"最后更新：{profile.get('updated_at', 'unknown')}")
    lines.append("")

    lines.append("=" * 60)
    lines.append("你可以随时回复调整：")
    lines.append('  "加个必读作者：Mohammed AlQuraishi"')
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
    feishu_user_id = args.feishu_user_id or os.environ.get("FEISHU_USER_ID", "ou_c4f5d0e9c7185e943cbd4216c9b68de7")

    result = process_must_read_command(
        user_id=args.user_id,
        command_text=args.command,
        feishu_user_id=feishu_user_id,
        send_to_feishu=args.send_feishu
    )

    print(f"\nResult: {json.dumps(result, indent=2, ensure_ascii=False)}")
