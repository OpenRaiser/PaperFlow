#!/usr/bin/env python3
"""
Role Manager - 角色管理代理

职责：管理多角色系统
- 创建新角色
- 切换当前角色
- 查看角色列表
- 删除角色
- 设置角色描述

角色命名规则：
- roleA, roleB, roleC...
- 或自定义：role_xxx
"""

import sys
import os
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any

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
create_profile = db_ops.create_profile
update_profile = db_ops.update_profile

# 飞书报告器
feishu_reporter = importlib.import_module("skills.feishu-reporter.scripts.feishu_reporter")
send_text = feishu_reporter.send_text
send_post = feishu_reporter.send_post


# 角色元数据存储（ SQLite 扩展或文件存储）
ROLE_META_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "roles.json"
)


def load_roles_meta() -> Dict[str, Any]:
    """加载角色元数据"""
    if os.path.exists(ROLE_META_FILE):
        with open(ROLE_META_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"roles": {}, "current_role": None}


def save_roles_meta(meta: Dict[str, Any]) -> None:
    """保存角色元数据"""
    os.makedirs(os.path.dirname(ROLE_META_FILE), exist_ok=True)
    with open(ROLE_META_FILE, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def create_role(role_name: str, description: str = "", natural_language: str = "", feishu_chat_id: str = None) -> Dict[str, Any]:
    """
    创建新角色

    Args:
        role_name: 角色名（如 roleA, roleB）
        description: 角色描述
        natural_language: 研究方向描述（用于冷启动）
        feishu_chat_id: 飞书群 ID（可选，用于绑定对话框）

    Returns:
        创建结果
    """
    meta = load_roles_meta()

    if role_name in meta["roles"]:
        return {"success": False, "message": f"角色 {role_name} 已存在"}

    # 生成 user_id
    user_id = f"user_{role_name}"

    bootstrap_text = (natural_language or description or "").strip()

    # 创建角色元数据
    meta["roles"][role_name] = {
        "user_id": user_id,
        "description": description or bootstrap_text,
        "created_at": datetime.now().isoformat(),
        "natural_language": bootstrap_text,
        "feishu_chat_id": feishu_chat_id,  # 飞书群 ID
    }

    # 如果是第一个角色，设为当前角色
    if meta["current_role"] is None:
        meta["current_role"] = role_name

    save_roles_meta(meta)

    # 创建用户画像
    profile = {
        "user_id": user_id,
        "version": "0.1",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "core_directions": {},
        "methodology_preferences": {},
        "must_read": {"authors": [], "institutions": [], "keywords": []},
        "topic_weights": {},
        "author_heat": {},
        "institution_heat": {},
        "interest_vector": [],
        "taste_profile": {},
        "reading_history": [],
        "behavior_logs": [],
        "feishu_chat_id": feishu_chat_id,  # 画像中也存储飞书群 ID
    }

    create_profile(user_id, profile)

    # 如果有研究方向描述，执行冷启动
    if bootstrap_text:
        try:
            coldstart_agent = importlib.import_module("agents.coldstart-agent.main")
            coldstart_agent.cold_start(
                user_id=user_id,
                natural_language=bootstrap_text,
                send_to_feishu=False
            )
        except Exception as e:
            print(f"冷启动失败：{e}")

    return {
        "success": True,
        "message": f"角色 {role_name} 创建成功",
        "user_id": user_id,
    }


def switch_role(role_name: str) -> Dict[str, Any]:
    """
    切换当前角色

    Args:
        role_name: 角色名

    Returns:
        切换结果
    """
    meta = load_roles_meta()

    if role_name not in meta["roles"]:
        return {"success": False, "message": f"角色 {role_name} 不存在"}

    old_role = meta["current_role"]
    meta["current_role"] = role_name
    save_roles_meta(meta)

    return {
        "success": True,
        "message": f"已从 {old_role} 切换到 {role_name}",
        "old_role": old_role,
        "new_role": role_name,
    }


def list_roles() -> Dict[str, Any]:
    """
    查看所有角色

    Returns:
        角色列表
    """
    meta = load_roles_meta()

    roles = meta.get("roles", {})
    current = meta.get("current_role")

    if not roles:
        return {"success": True, "roles": [], "current_role": None, "message": "暂无角色"}

    role_list = []
    for name, info in roles.items():
        role_list.append({
            "name": name,
            "user_id": info.get("user_id"),
            "description": info.get("description", ""),
            "is_current": name == current,
        })

    return {
        "success": True,
        "roles": role_list,
        "current_role": current,
    }


def delete_role(role_name: str) -> Dict[str, Any]:
    """
    删除角色

    Args:
        role_name: 角色名

    Returns:
        删除结果
    """
    meta = load_roles_meta()

    if role_name not in meta["roles"]:
        return {"success": False, "message": f"角色 {role_name} 不存在"}

    # 不能删除当前角色
    if meta["current_role"] == role_name:
        return {"success": False, "message": "不能删除当前角色，请先切换到其他角色"}

    # 删除角色元数据
    del meta["roles"][role_name]
    save_roles_meta(meta)

    # 删除用户画像（可选，这里只标记删除）
    user_id = f"user_{role_name}"
    # 实际删除需要 db_ops 支持，这里暂不实现

    return {
        "success": True,
        "message": f"角色 {role_name} 已删除",
    }


def get_current_role() -> Optional[str]:
    """获取当前角色"""
    meta = load_roles_meta()
    return meta.get("current_role")


def format_role_list(roles_result: Dict) -> str:
    """格式化角色列表"""
    lines = []
    lines.append("=" * 60)
    lines.append("Role List")
    lines.append("=" * 60)
    lines.append("")

    roles = roles_result.get("roles", [])
    current = roles_result.get("current_role")

    if not roles:
        lines.append("(no roles yet)")
    else:
        for role in roles:
            marker = "[CURRENT]" if role["is_current"] else " "
            lines.append(f"{marker} {role['name']} - {role.get('description', 'no description')}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("Commands:")
    lines.append('  Create: "create role roleB, direction: ..."')
    lines.append('  Switch: "switch to roleB"')
    lines.append('  Delete: "delete role roleA"')
    lines.append("=" * 60)

    return "\n".join(lines)


def bind_chat_id(role_name: str, feishu_chat_id: str) -> Dict[str, Any]:
    """
    绑定飞书群 ID 到角色

    Args:
        role_name: 角色名
        feishu_chat_id: 飞书群 ID

    Returns:
        绑定结果
    """
    meta = load_roles_meta()

    if role_name not in meta["roles"]:
        return {"success": False, "message": f"角色 {role_name} 不存在"}

    meta["roles"][role_name]["feishu_chat_id"] = feishu_chat_id
    save_roles_meta(meta)

    # 同时更新画像
    user_id = f"user_{role_name}"
    profile = get_profile(user_id)
    if profile:
        profile["feishu_chat_id"] = feishu_chat_id
        profile["updated_at"] = datetime.now().isoformat()
        update_profile(user_id, profile)

    return {
        "success": True,
        "message": f"已将角色 {role_name} 绑定到飞书群 {feishu_chat_id}",
    }


def parse_role_command(text: str) -> Optional[Dict[str, Any]]:
    """
    解析角色命令

    支持格式：
    - "创建角色 roleB，研究方向：GUI Agent"
    - "切换到 roleB"
    - "查看角色列表"
    - "删除角色 roleA"
    - "绑定飞书群 roleA chat_xxx"

    Args:
        text: 用户输入

    Returns:
        命令字典
    """
    text_lower = text.lower().strip()

    # 绑定飞书群
    if any(kw in text_lower for kw in ["绑定", "bind", "关联"]):
        match = re.search(r'(?:绑定 |bind| 关联)\s*(?:飞书)?(?:群 |chat)?\s*(\w+)\s*(\w+)', text_lower)
        if match:
            return {
                "action": "bind",
                "role_name": match.group(1),
                "feishu_chat_id": match.group(2),
            }

    # 创建角色
    if any(kw in text_lower for kw in ["创建角色", "create role", "新建角色"]):
        # 提取角色名和描述
        match = re.search(r'(?:创建角色 | 新建角色|create role)\s*(\w+)[, ，]*(.*)', text_lower)
        if match:
            return {
                "action": "create",
                "role_name": match.group(1),
                "natural_language": match.group(2).strip() if match.group(2) else "",
            }

    # 切换角色
    if any(kw in text_lower for kw in ["切换", "switch", "转到", "转到"]):
        match = re.search(r'(?:切换到 | 转到|switch to)\s*(\w+)', text_lower)
        if match:
            return {
                "action": "switch",
                "role_name": match.group(1),
            }

    # 查看列表
    if any(kw in text_lower for kw in ["查看角色", "list roles", "角色列表", "我的角色"]):
        return {"action": "list"}

    # 删除角色
    if any(kw in text_lower for kw in ["删除角色", "delete role", "移除角色"]):
        match = re.search(r'(?:删除 | 移除|delete)\s*(?:角色)?\s*(\w+)', text_lower)
        if match:
            return {
                "action": "delete",
                "role_name": match.group(1),
            }

    return None


def process_role_command(
    command_text: str,
    feishu_user_id: Optional[str] = None,
    send_to_feishu: bool = True
) -> Dict[str, Any]:
    """
    处理角色命令

    Args:
        command_text: 用户命令
        feishu_user_id: 飞书用户 ID
        send_to_feishu: 是否发送飞书

    Returns:
        处理结果
    """
    import re

    command = parse_role_command(command_text)

    if not command:
        return {"success": False, "message": "未识别到有效命令"}

    action = command.get("action")

    if action == "create":
        result = create_role(
            role_name=command["role_name"],
            natural_language=command.get("natural_language", ""),
            feishu_chat_id=command.get("feishu_chat_id"),
        )
    elif action == "bind":
        result = bind_chat_id(
            role_name=command["role_name"],
            feishu_chat_id=command["feishu_chat_id"],
        )
    elif action == "switch":
        result = switch_role(command["role_name"])
    elif action == "list":
        result = list_roles()
        if result["success"]:
            result["formatted"] = format_role_list(result)
    elif action == "delete":
        result = delete_role(command["role_name"])
    else:
        result = {"success": False, "message": "未知命令"}

    # 发送到飞书
    if send_to_feishu and feishu_user_id and result.get("success"):
        if "formatted" in result:
            send_text(feishu_user_id, result["formatted"])
        else:
            send_text(feishu_user_id, result.get("message", "操作完成"))

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Role Manager - 角色管理")
    parser.add_argument("--command", type=str, required=True, help="命令文本")
    parser.add_argument("--feishu-user-id", type=str, help="飞书用户 ID")
    parser.add_argument("--no-feishu", action="store_true", help="不发送飞书")

    args = parser.parse_args()

    result = process_role_command(
        command_text=args.command,
        feishu_user_id=args.feishu_user_id if not args.no_feishu else None,
        send_to_feishu=not args.no_feishu
    )

    # 使用 GBK 兼容的输出
    try:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except UnicodeEncodeError:
        # 降级为简单输出
        for key, value in result.items():
            print(f"{key}: {value}")
