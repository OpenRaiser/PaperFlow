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
get_recent_drift_updates = getattr(db_ops, "get_recent_drift_updates", lambda *args, **kwargs: [])
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


def _build_drift_summary(profile: Dict[str, Any], drift_updates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate current and recent drift signals for the weekly report."""
    drift_state = (profile or {}).get("drift_state", {}) or {}
    status = drift_state.get("status", "stable")
    max_score = float(drift_state.get("score", 0.0) or 0.0)
    explanation = drift_state.get("explanation", "")
    top_shift_topics = list(drift_state.get("top_shift_topics", []) or [])
    detected_at = drift_state.get("detected_at")

    for update in drift_updates:
        metadata = update.get("metadata", {}) or {}
        max_score = max(max_score, float(metadata.get("drift_score", update.get("drift_score", 0.0)) or 0.0))
        if not explanation and metadata.get("explanation"):
            explanation = metadata.get("explanation")
        if not top_shift_topics and metadata.get("top_shift_topics"):
            top_shift_topics = list(metadata.get("top_shift_topics") or [])
        if not detected_at and metadata.get("drift_status") == "shifting":
            detected_at = update.get("timestamp")

    return {
        "status": status,
        "status_label": {
            "stable": "稳定",
            "shifting": "迁移中",
            "recovered": "已恢复",
        }.get(status, "稳定"),
        "max_score": round(max_score, 4),
        "detected_at": detected_at,
        "top_shift_topics": top_shift_topics[:3],
        "explanation": explanation or "近期兴趣稳定，系统继续以长期画像为主。",
    }


def generate_weekly_report(user_id: str, days: int = 7) -> Dict[str, Any]:
    """Generate the weekly report, including drift-awareness summary."""
    profile = get_profile(user_id)
    if not profile:
        return {"error": "Profile not found"}

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)

    direction_changes = get_direction_changes(user_id, days)
    stats = get_selection_stats(user_id, days)
    stats_by_category = get_selection_stats_by_category(user_id, days)
    logs = get_behavior_logs(user_id, start_date.isoformat(), end_date.isoformat())
    recent_pushes = get_recent_pushes(user_id, limit=100)
    drift_updates = get_recent_drift_updates(user_id, days)

    reading_history = profile.get("reading_history", [])
    recent_reads = [
        item for item in reading_history
        if datetime.fromisoformat(item.get("selected_at", "2000-01-01")) >= datetime.combine(start_date, datetime.min.time())
    ]

    author_heat = profile.get("author_heat", {})
    top_authors = sorted(author_heat.items(), key=lambda item: -item[1])[:5]

    institution_heat = profile.get("institution_heat", {})
    top_institutions = sorted(institution_heat.items(), key=lambda item: -item[1])[:5]

    core_directions = profile.get("core_directions", {})
    top_directions = sorted(core_directions.items(), key=lambda item: -item[1])[:7]

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
        "missed_papers": _detect_missed_papers(logs, recent_pushes),
        "profile_version": profile.get("version", "unknown"),
        "drift_summary": _build_drift_summary(profile, drift_updates),
    }


def format_report_card(report: Dict) -> str:
    """Format the weekly report card with a drift-awareness section."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"📋 你的学术画像周度报告 | {report.get('period', 'N/A')}")
    lines.append("=" * 60)
    lines.append("")

    drift_summary = report.get("drift_summary", {})
    if drift_summary:
        lines.append("━━━ 兴趣迁移状态 ━━━")
        lines.append(f"当前状态：{drift_summary.get('status_label', '稳定')}")
        lines.append(f"本周最高漂移分数：{drift_summary.get('max_score', 0.0):.2f}")
        if drift_summary.get("detected_at"):
            lines.append(f"最近一次检测时间：{drift_summary.get('detected_at')}")
        if drift_summary.get("top_shift_topics"):
            lines.append(f"最近漂移主题：{', '.join(drift_summary.get('top_shift_topics', [])[:3])}")
        lines.append(f"更新器解释：{drift_summary.get('explanation', '')}")
        lines.append("")

    direction_changes = report.get("direction_changes", [])
    if direction_changes:
        lines.append("━━━ 方向权重变化 ━━━")
        for change in direction_changes[:7]:
            direction_cn = translate_direction(change["direction"])
            current = change["current_weight"]
            previous = change["previous_weight"]
            delta = change["delta"]
            trend = change["trend"]
            bar_len = int(current * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            if trend == "up":
                trend_str = f"{previous:.2f} → {current:.2f}"
            elif trend == "down":
                trend_str = f"{previous:.2f} → {current:.2f}"
            else:
                trend_str = "不变"
            if previous == 0 and current > 0:
                lines.append(f"【新增】{direction_cn} [{bar}] {current:.2f} → 新出现的兴趣")
            else:
                text = f"{direction_cn} [{bar}] {current:.2f} ({trend_str})"
                if trend == "down" and delta < -0.05:
                    text += " → 权重下降"
                lines.append(text)
        lines.append("")

    stats = report.get("stats", {})
    lines.append("━━━ 本周阅读统计 ━━━")
    lines.append(f"推送论文总数：{stats.get('total', 0)}")
    lines.append(f"你选择精读：{stats.get('selected', 0)}（选择率 {stats.get('selection_rate', 0):.1%}）")
    lines.append("")

    stats_by_category = report.get("stats_by_category", {})
    if stats_by_category:
        lines.append("━━━ 推荐准确率 ━━━")
        category_map = {
            "high_relevant": ("🔴", "高度相关"),
            "maybe_interested": ("🟡", "可能感兴趣"),
            "edge_relevant": ("🔵", "边缘相关"),
            "must_read": ("🔒", "必读清单"),
            "must_read_manager": ("🔒", "必读清单"),
        }
        for cat_key, (emoji, label) in category_map.items():
            if cat_key not in stats_by_category:
                continue
            rate = stats_by_category[cat_key].get("selection_rate", 0)
            lines.append(f"{emoji}{label}中你选择了：{rate:.0%}")
        lines.append("")

    top_authors = report.get("top_authors", [])
    if top_authors:
        lines.append("━━━ 👥 高频作者 ━━━")
        for author, heat in top_authors:
            lines.append(f"  · {author} (热度：{heat:.2f})")
        lines.append("")

    top_institutions = report.get("top_institutions", [])
    if top_institutions:
        lines.append("━━━ 🏛️ 高频机构 ━━━")
        for institution, heat in top_institutions:
            lines.append(f"  · {institution} (热度：{heat:.2f})")
        lines.append("")

    missed_papers = report.get("missed_papers", [])
    if missed_papers:
        lines.append("━━━ 你可能遗漏的 ━━━")
        for paper in missed_papers[:3]:
            lines.append(f"[{paper.get('title', 'Unknown')}]")
        lines.append("→ 要补读吗？")
        lines.append("")

    lines.append("━━━ 画像调整建议 ━━━")
    suggestions = _generate_suggestions(report)
    if suggestions:
        for suggestion in suggestions[:5]:
            lines.append(f"· {suggestion}")
    else:
        lines.append("画像状态良好，继续保持。")
    lines.append("")

    lines.append("=" * 60)
    lines.append("新的一周，继续探索！")
    lines.append("=" * 60)
    return "\n".join(lines)


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
