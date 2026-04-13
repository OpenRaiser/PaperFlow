#!/usr/bin/env python3
"""
Profile Report Agent - 画像周报代理

职责：生成用户一周的兴趣变化总结，通过飞书发送周报。
报告包含：
- 本周阅读统计
- 兴趣方向变化
- 高频作者/机构
- 下周推荐重点
"""

import sys
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 使用 importlib 导入带连字符的模块
import importlib

# 飞书报告器
feishu_reporter = importlib.import_module("skills.feishu-reporter.scripts.feishu_reporter")
send_text = feishu_reporter.send_text
send_post = feishu_reporter.send_post
send_text_to_chat = feishu_reporter.send_text_to_chat

# 数据库操作
db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
get_profile = db_ops.get_profile
get_behavior_logs = db_ops.get_behavior_logs
get_selection_stats = db_ops.get_selection_stats
get_selection_stats_by_category = db_ops.get_selection_stats_by_category
get_direction_changes = db_ops.get_direction_changes
get_recent_pushes = db_ops.get_recent_pushes
get_paper_by_arxiv_id = db_ops.get_paper_by_arxiv_id


def translate_direction(direction: str) -> str:
    """翻译研究方向为中文"""
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
    return translations.get(direction, direction)


def generate_weekly_report(user_id: str, days: int = 7) -> Dict[str, Any]:
    """
    生成周报

    Args:
        user_id: 用户 ID
        days: 统计天数（默认 7 天）

    Returns:
        周报字典
    """
    # 获取用户画像
    profile = get_profile(user_id)
    if not profile:
        return {"error": "Profile not found"}

    # 获取方向权重变化
    direction_changes = get_direction_changes(user_id, days)

    # 获取统计数据
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)

    stats = get_selection_stats(user_id, days)
    stats_by_category = get_selection_stats_by_category(user_id, days)

    # 获取行为日志
    logs = get_behavior_logs(
        user_id,
        start_date.isoformat(),
        end_date.isoformat()
    )

    # 获取最近推送
    recent_pushes = get_recent_pushes(user_id, limit=100)

    # 分析阅读历史
    reading_history = profile.get("reading_history", [])
    recent_reads = [
        r for r in reading_history
        if datetime.fromisoformat(r.get("selected_at", "2000-01-01")) >= datetime.combine(start_date, datetime.min.time())
    ]

    # 统计作者热度变化
    author_heat = profile.get("author_heat", {})
    top_authors = sorted(author_heat.items(), key=lambda x: -x[1])[:5]

    # 统计机构热度变化
    institution_heat = profile.get("institution_heat", {})
    top_institutions = sorted(institution_heat.items(), key=lambda x: -x[1])[:5]

    # 核心方向
    core_directions = profile.get("core_directions", {})
    top_directions = sorted(core_directions.items(), key=lambda x: -x[1])[:7]

    # 检测遗漏的论文（跳过但后来被高引的）
    missed_papers = _detect_missed_papers(logs, recent_pushes)

    return {
        "user_id": user_id,
        "period": f"{start_date.isoformat()} ~ {end_date.isoformat()}",
        "direction_changes": direction_changes,
        "stats": stats,
        "stats_by_category": stats_by_category,
        "recent_reads_count": len(recent_reads),
        "top_authors": top_authors,
        "top_institutions": top_institutions,
        "top_directions": top_directions,
        "missed_papers": missed_papers,
        "profile_version": profile.get("version", "unknown"),
    }


def _detect_missed_papers(logs: List[Dict], recent_pushes: List[Dict]) -> List[Dict]:
    """
    检测遗漏的论文（用户跳过但可能重要的）

    Args:
        logs: 行为日志
        recent_pushes: 最近推送的论文

    Returns:
        遗漏论文列表
    """
    # 简化版：返回空列表（完整版需要调用外部 API 获取引用情况）
    # TODO: 集成 arxiv-fetcher 获取引用次数
    return []


def format_report_card(report: Dict) -> str:
    """
    格式化周报卡片（按照 spec 格式）

    Args:
        report: 周报字典

    Returns:
        格式化文本
    """
    lines = []
    lines.append("=" * 60)
    lines.append(f"📊 你的学术画像周度报告 | {report.get('period', 'N/A')}")
    lines.append("=" * 60)
    lines.append("")

    # 方向权重变化
    direction_changes = report.get("direction_changes", [])
    if direction_changes:
        lines.append("━━━ 方向权重变化 ━━━")
        for change in direction_changes[:7]:  # 最多显示 7 个方向
            direction = change["direction"]
            direction_cn = translate_direction(direction)
            current = change["current_weight"]
            previous = change["previous_weight"]
            delta = change["delta"]
            trend = change["trend"]

            # 进度条（20 格满格）
            bar_len = int(current * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)

            if trend == "up":
                trend_str = f"→{previous:.2f} ↑"
            elif trend == "down":
                trend_str = f"→{previous:.2f} ↓"
            else:
                trend_str = "不变"

            # 新增方向
            if previous == 0 and current > 0:
                lines.append(f"【新增】{direction_cn}  [{bar}]  {current:.2f} ← 新出现的兴趣")
            else:
                lines.append(f"{direction_cn}  [{bar}]  {current:.2f} ({trend_str})")

                # 下降方向标注
                if trend == "down" and delta < -0.05:
                    lines[-1] += " ← 权重下降"
        lines.append("")

    # 本周阅读统计
    stats = report.get("stats", {})
    lines.append("━━━ 本周阅读统计 ━━━")
    lines.append(f"推送论文总数：{stats.get('total', 0)}")
    lines.append(f"你选择精读：{stats.get('selected', 0)}（选择率 {stats.get('selection_rate', 0):.1%}）")
    lines.append("")

    # 推荐准确率（按🔴🟡🔵分类）
    stats_by_category = report.get("stats_by_category", {})
    if stats_by_category:
        lines.append("━━━ 推荐准确率 ━━━")
        # 映射 category key 到 emoji
        category_map = {
            "high_relevant": "🔴",
            "maybe_interested": "🟡",
            "edge_relevant": "🔵",
            "must_read_manager": "🔒",
        }
        category_names = {
            "high_relevant": "高度相关",
            "maybe_interested": "可能感兴趣",
            "edge_relevant": "边缘相关",
            "must_read_manager": "必读清单",
        }
        for cat_key, emoji in category_map.items():
            if cat_key in stats_by_category:
                cat_stats = stats_by_category[cat_key]
                rate = cat_stats.get("selection_rate", 0)
                cat_name = category_names.get(cat_key, cat_key)
                lines.append(f"{emoji}{cat_name}中你选择了：{rate:.0%}")
        lines.append("")

    # 高频作者
    top_authors = report.get("top_authors", [])
    if top_authors:
        lines.append("━━━ 👥 高频作者 ━━━")
        for author, heat in top_authors:
            lines.append(f"  • {author} (热度：{heat:.2f})")
        lines.append("")

    # 高频机构
    top_institutions = report.get("top_institutions", [])
    if top_institutions:
        lines.append("━━━ 🏛️ 高频机构 ━━━")
        for inst, heat in top_institutions:
            lines.append(f"  • {inst} (热度：{heat:.2f})")
        lines.append("")

    # 遗漏检测
    missed_papers = report.get("missed_papers", [])
    if missed_papers:
        lines.append("━━━ 你可能遗漏的 ━━━")
        for paper in missed_papers[:3]:  # 最多显示 3 篇
            lines.append(f"[{paper.get('title', 'Unknown')}]")
        lines.append("→ 要补读吗？")
        lines.append("")

    # 画像调整建议
    lines.append("━━━ 画像调整建议 ━━━")
    suggestions = _generate_suggestions(report)
    if suggestions:
        for sug in suggestions[:5]:  # 最多 5 条建议
            lines.append(f"• {sug}")
    else:
        lines.append("画像状态良好，继续保持！")
    lines.append("")

    lines.append("=" * 60)
    lines.append("新的一周，继续探索！")
    lines.append("=" * 60)

    return "\n".join(lines)


def _generate_suggestions(report: Dict) -> List[str]:
    """
    生成画像调整建议

    Args:
        report: 周报字典

    Returns:
        建议列表
    """
    suggestions = []
    direction_changes = report.get("direction_changes", [])

    # 检测持续下降的方向
    for change in direction_changes:
        if change["trend"] == "down" and change["delta"] < -0.1:
            direction_cn = translate_direction(change["direction"])
            suggestions.append(f"{direction_cn}权重持续下降，是否还保留？")

    # 检测新增方向
    for change in direction_changes:
        if change["previous_weight"] == 0 and change["current_weight"] > 0.3:
            direction_cn = translate_direction(change["direction"])
            suggestions.append(f"建议将\"{direction_cn}\"正式加入关注方向")

    return suggestions


def load_roles_meta() -> Dict[str, Any]:
    """加载角色元数据"""
    role_meta_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data", "roles.json"
    )
    if os.path.exists(role_meta_file):
        with open(role_meta_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"roles": {}, "current_role": None}


def get_role_chat_id(role_name: str) -> Optional[str]:
    """获取角色的飞书聊天 ID"""
    meta = load_roles_meta()
    role_data = meta.get("roles", {}).get(role_name, {})
    return role_data.get("feishu_chat_id")


def get_role_name_by_user_id(user_id: str) -> Optional[str]:
    """根据 user_id 反查角色名。"""
    meta = load_roles_meta()
    for role_name, role_data in meta.get("roles", {}).items():
        if role_data.get("user_id") == user_id:
            return role_name
    return None


def resolve_chat_id_for_user(user_id: str, role_name: Optional[str] = None) -> Optional[str]:
    """优先从画像和角色配置中解析角色 chat_id。"""
    profile = get_profile(user_id) or {}
    if profile.get("feishu_chat_id"):
        return profile["feishu_chat_id"]

    resolved_role_name = role_name or get_role_name_by_user_id(user_id)
    if resolved_role_name:
        return get_role_chat_id(resolved_role_name)

    return None


def send_weekly_report(
    user_id: str,
    days: int = 7,
    feishu_chat_id: Optional[str] = None,
    role_name: Optional[str] = None,
    send_to_feishu: bool = True
) -> Dict[str, Any]:
    """
    发送周报

    Args:
        user_id: 用户 ID
        days: 统计天数
        feishu_chat_id: 飞书聊天 ID（优先使用）
        role_name: 角色名（可选，用于查找 feishu_chat_id）
        send_to_feishu: 是否发送

    Returns:
        报告结果
    """
    print(f"Generating weekly report for user: {user_id}")

    # 生成报告
    report = generate_weekly_report(user_id, days)

    if "error" in report:
        print(f"Error: {report['error']}")
        return report

    # 格式化
    report_card = format_report_card(report)

    # 发送到飞书
    if send_to_feishu:
        # 优先使用传入的 chat_id，否则按 user_id / role_name 解析角色 chat_id
        target_chat = feishu_chat_id
        if not target_chat:
            target_chat = resolve_chat_id_for_user(user_id, role_name)

        if target_chat:
            try:
                # 使用 chat_id 发送到群聊
                send_text_to_chat(target_chat, report_card)
                print(f"Weekly report sent to Feishu chat: {target_chat}")
            except Exception as e:
                print(f"Failed to send to Feishu: {e}")
                return {"error": str(e)}
        else:
            print("Warning: No Feishu chat ID provided")

    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Profile Report Agent - 生成周报")
    parser.add_argument("--user-id", type=str, help="用户 ID")
    parser.add_argument("--days", type=int, default=7, help="统计天数")
    parser.add_argument("--send-feishu", action="store_true", help="发送到飞书")
    parser.add_argument("--role", type=str, help="角色名（如 rolea, roleb 等），用于查找对应的飞书聊天 ID")
    parser.add_argument("--feishu-chat-id", type=str, help="飞书聊天 ID（优先于 --role）")
    parser.add_argument("--all-roles", action="store_true", help="为所有角色生成并发送周报")

    args = parser.parse_args()

    if args.all_roles:
        # 为所有角色发送周报
        meta = load_roles_meta()
        roles = meta.get("roles", {})
        print(f"Sending weekly reports for all {len(roles)} roles...")

        for role_name, role_data in roles.items():
            user_id = role_data.get("user_id", f"user_{role_name}")
            chat_id = role_data.get("feishu_chat_id")
            print(f"\n--- {role_name} ---")

            result = send_weekly_report(
                user_id=user_id,
                days=args.days,
                feishu_chat_id=chat_id,
                role_name=role_name,
                send_to_feishu=args.send_feishu
            )

            if "error" in result:
                print(f"Error for {role_name}: {result['error']}")
            else:
                print(f"Success for {role_name}")
    else:
        # 单个角色：根据 --role 或 --user-id 确定 user_id
        if args.role:
            meta = load_roles_meta()
            role_data = meta.get("roles", {}).get(args.role, {})
            if not role_data:
                print(f"Error: Role '{args.role}' not found")
                sys.exit(1)
            user_id = role_data.get("user_id", f"user_{args.role}")
            chat_id = role_data.get("feishu_chat_id")
            print(f"Using role: {args.role}, user_id: {user_id}, chat_id: {chat_id}")
        else:
            user_id = args.user_id or "user_001"
            chat_id = args.feishu_chat_id

        result = send_weekly_report(
            user_id=user_id,
            days=args.days,
            feishu_chat_id=chat_id,
            send_to_feishu=args.send_feishu
        )

        print(f"\nResult: {json.dumps(result, indent=2, ensure_ascii=False)}")
