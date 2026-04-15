#!/usr/bin/env python3
"""
Feedback Agent - 反馈处理代理

职责：解析用户回复（编号选择），记录行为日志，更新用户画像。
支持格式：
- "1 2 4 6 7 9 11" （空格分隔）
- "1-5 6 9 11" （范围 + 单个编号）
- "1,2,4,6,7,9,11" （逗号分隔）
"""

import sys
import os
import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
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

# 存储辅助
db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
log_behavior = db_ops.log_behavior
get_profile = db_ops.get_profile
update_profile = db_ops.update_profile
get_recent_selected_papers = getattr(db_ops, "get_recent_selected_papers", lambda *args, **kwargs: [])

profile_updater = importlib.import_module("skills.profile-updater.scripts.update_profile")
update_profile_with_feedback = profile_updater.update_profile_with_feedback
ensure_profile_schema = profile_updater.ensure_profile_schema
get_drift_blend_weights = profile_updater.get_drift_blend_weights

# 飞书报告器
feishu_reporter = importlib.import_module("skills.feishu-reporter.scripts.feishu_reporter")
send_text = feishu_reporter.send_text


CATEGORY_LABELS = {
    "must_read": "🔒 必读",
    "high_relevant": "🔴 高度相关",
    "maybe_interested": "🟡 可能感兴趣",
    "edge_relevant": "🔵 边缘相关",
}


def create_reading_reports_for_selection(
    user_id: str,
    selected: Set[int],
    papers: List[Dict],
    target_id: Optional[str],
    use_chat_id: bool,
    send_to_feishu: bool,
    selection_push_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Create reading reports for selected papers and route them back to the same chat."""
    if not selected or not send_to_feishu:
        return []

    paper_ids: List[int] = []
    for paper_num in sorted(selected):
        idx = int(paper_num) - 1
        if not (0 <= idx < len(papers)):
            continue
        paper = papers[idx]
        resolved_id = paper.get("id")
        paper_ids.append(int(resolved_id) if resolved_id is not None else int(paper_num))

    reading_agent = importlib.import_module("agents.reading-agent.main")
    kwargs: Dict[str, Any] = {
        "user_id": user_id,
        "paper_ids": paper_ids,
        "papers": papers,
        "send_to_feishu": True,
        "request_metadata": {
            "selection_push_id": selection_push_id,
        } if selection_push_id else None,
    }

    if use_chat_id and target_id:
        kwargs["chat_id"] = target_id
    elif target_id:
        kwargs["feishu_user_id"] = target_id

    return reading_agent.create_reading_report(**kwargs)


def parse_user_reply(reply: str, papers: List[Dict] = None) -> Set[int]:
    """
    解析用户回复，提取选中的论文编号

    支持格式：
    - "1 2 4 6 7 9 11" （空格分隔）
    - "1-5 6 9 11" （范围 + 单个编号）
    - "1,2,4,6,7,9,11" （逗号分隔）
    - 混合格式："1-3 5 7-9 11"
    - 快捷命令："all lock"（所有必读）、"all red"（所有高度相关）

    Args:
        reply: 用户回复文本
        papers: 论文列表（用于快捷命令）

    Returns:
        选中的编号集合
    """
    selected: Set[int] = set()
    max_paper_num = len(papers) if papers else 200

    # 快捷命令处理
    reply_lower = reply.lower().strip()

    if reply_lower == "all lock":
        # 选择必读清单论文
        if papers:
            for i, paper in enumerate(papers):
                if paper.get("category") == "must_read":
                    selected.add(i + 1)  # 编号从 1 开始
        return selected

    if reply_lower == "all red":
        # 选择所有高度相关论文
        if papers:
            for i, paper in enumerate(papers):
                if paper.get("category") == "high_relevant":
                    selected.add(i + 1)  # 编号从 1 开始
        return selected

    if reply_lower == "none":
        # 都不选
        return selected

    # 规范化：将逗号、顿号等替换为空格
    normalized = re.sub(r"[,，、;；]", " ", reply)

    # 提取所有 token（由空格分隔的部分）
    tokens = normalized.split()

    for token in tokens:
        token = token.strip()
        if not token:
            continue

        # 检查是否是范围格式（如 "1-5"）
        range_match = re.match(r"^(\d+)-(\d+)$", token)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            # 确保范围合理
            if start <= end and end <= max_paper_num:
                selected.update(range(start, end + 1))
        else:
            # 检查是否是单个数字
            num_match = re.match(r"^(\d+)$", token)
            if num_match:
                num = int(num_match.group(1))
                if 1 <= num <= max_paper_num:
                    selected.add(num)

    return selected


def normalize_authors(authors: Any) -> List[str]:
    """Normalize author field from list / JSON string / plain string."""
    if not authors:
        return []

    if isinstance(authors, list):
        return [str(author).strip() for author in authors if str(author).strip()]

    if isinstance(authors, str):
        authors_text = authors.strip()
        if not authors_text:
            return []
        try:
            parsed = json.loads(authors_text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(author).strip() for author in parsed if str(author).strip()]
        return [part.strip() for part in re.split(r"[;,，、]", authors_text) if part.strip()]

    return [str(authors).strip()]


def _build_interest_vector_descriptor(profile: Dict[str, Any]) -> str:
    """Compact descriptor for drift-aware interest fusion."""
    drift_state = (profile or {}).get("drift_state", {}) or {}
    status = str(drift_state.get("status", "stable"))
    weights = get_drift_blend_weights(status)
    return (
        f"status={status}|"
        f"explicit:{weights['explicit']:.2f},"
        f"long:{weights['long']:.2f},"
        f"short:{weights['short']:.2f}"
    )


def format_number_ranges(numbers: Set[int]) -> str:
    """Format selected numbers as compact ranges such as 01-03, 07, 09."""
    if not numbers:
        return "无"

    sorted_numbers = sorted(numbers)
    ranges = []
    start = end = sorted_numbers[0]

    for number in sorted_numbers[1:]:
        if number == end + 1:
            end = number
            continue
        ranges.append((start, end))
        start = end = number
    ranges.append((start, end))

    formatted = []
    for start, end in ranges:
        if start == end:
            formatted.append(f"{start:02d}")
        else:
            formatted.append(f"{start:02d}-{end:02d}")
    return ", ".join(formatted)


def build_learning_signals(selected: Set[int], skipped: Set[int], papers: List[Dict]) -> List[str]:
    """Generate lightweight feedback insights aligned with the PDF interaction."""
    selected_categories = {}
    skipped_categories = {}

    for paper_num in selected:
        paper = papers[paper_num - 1]
        category = paper.get("category", "unknown")
        selected_categories[category] = selected_categories.get(category, 0) + 1

    for paper_num in skipped:
        paper = papers[paper_num - 1]
        category = paper.get("category", "unknown")
        skipped_categories[category] = skipped_categories.get(category, 0) + 1

    signals = []

    lower_bucket_selected = selected_categories.get("maybe_interested", 0) + selected_categories.get("edge_relevant", 0)
    if lower_bucket_selected:
        signals.append(
            f"✓ 你选中了 {lower_bucket_selected} 篇原本靠后的候选，对应主题会被视为更强正信号"
        )

    top_bucket_skipped = skipped_categories.get("must_read", 0) + skipped_categories.get("high_relevant", 0)
    if top_bucket_skipped:
        signals.append(
            f"✓ 你这次跳过了 {top_bucket_skipped} 篇 🔒/🔴 候选，我会先按弱负信号处理，不会立刻重罚"
        )

    if not selected:
        signals.append("✓ 今天的“都不看”会被记为一次弱负信号，只有连续多天跳过同类论文才会明显降权")

    if selected_categories:
        dominant_category = max(selected_categories.items(), key=lambda item: item[1])[0]
        dominant_label = CATEGORY_LABELS.get(dominant_category, dominant_category)
        signals.append(f"✓ 本次选择主要集中在“{dominant_label}”分组，后续我会优先沿这条线细化推荐")

    return signals[:3]


def format_selection_summary(
    selected: Set[int],
    total_papers: int,
    papers: List[Dict]
) -> str:
    """
    格式化选择摘要

    Args:
        selected: 选中的编号集合
        total_papers: 推送的论文总数
        papers: 论文列表

    Returns:
        摘要文本
    """
    skipped = set(range(1, total_papers + 1)) - selected
    selection_rate = len(selected) / total_papers if total_papers > 0 else 0
    learning_signals = build_learning_signals(selected, skipped, papers)

    lines = []
    if selected:
        lines.append(f"收到，{len(selected)} 篇已进入偏好学习流程。")
    else:
        lines.append("收到，今天先都不看。")
    lines.append("📊 今日反馈已记录：")
    lines.append(f"选择：{format_number_ranges(selected)}（{len(selected)} 篇）")
    lines.append(f"跳过：{format_number_ranges(skipped)}（{len(skipped)} 篇）")
    lines.append(f"选择率：{selection_rate:.1%}")

    if learning_signals:
        lines.append("学到的信号：")
        lines.extend(learning_signals)

    lines.append("以上推断我会继续用后续行为自动校正；如果哪条明显不对，直接补一句纠正我就行。")
    lines.append("画像已更新，下次推送会据此调整。")

    return "\n".join(lines)


def update_profile_based_on_selection(
    user_id: str,
    selected_paper_ids: List[int],
    papers: List[Dict],
    skipped_paper_ids: Optional[List[int]] = None,
    historical_selected_papers: Optional[List[Dict[str, Any]]] = None,
    current_timestamp: Optional[datetime] = None,
) -> Dict:
    """Update the profile via the unified drift-aware updater."""
    profile = get_profile(user_id)
    if not profile:
        print(f"Warning: No profile found for user {user_id}")
        return {}

    now = current_timestamp or datetime.now()
    normalized_profile = ensure_profile_schema(profile, now=now)

    selected_papers: List[Dict[str, Any]] = []
    for paper_number in selected_paper_ids:
        idx = paper_number - 1
        if 0 <= idx < len(papers):
            selected_paper = dict(papers[idx])
            selected_paper["authors"] = normalize_authors(selected_paper.get("authors", []))
            selected_papers.append(selected_paper)

    skipped_papers: List[Dict[str, Any]] = []
    for paper_number in skipped_paper_ids or []:
        idx = paper_number - 1
        if 0 <= idx < len(papers):
            skipped_paper = dict(papers[idx])
            skipped_paper["authors"] = normalize_authors(skipped_paper.get("authors", []))
            skipped_papers.append(skipped_paper)

    updated_profile = update_profile_with_feedback(
        normalized_profile,
        selected_papers,
        skipped_papers,
        historical_selected_papers=historical_selected_papers or [],
        current_time=now,
    )
    update_profile(user_id, updated_profile)
    return updated_profile


def process_feedback(
    user_id: str,
    push_id: str,
    reply: str,
    papers: List[Dict],
    feishu_user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    send_to_feishu: bool = True,
    auto_create_reports: Optional[bool] = None
) -> Dict[str, Any]:
    """
    处理用户反馈

    Args:
        user_id: 用户 ID
        push_id: 推送 ID（用于关联行为日志）
        reply: 用户回复文本
        papers: 推送的论文列表
        feishu_user_id: 飞书用户 ID（open_id）
        chat_id: 聊天 ID（优先使用，发送到原对话框）

    Returns:
        处理结果
    """
    print(f"Processing feedback from user: {user_id}")
    print(f"Reply: {reply}")

    # 优先使用 chat_id，否则使用 feishu_user_id
    target_id = chat_id or feishu_user_id
    use_chat_id = chat_id is not None

    # 1. 解析用户回复
    selected = parse_user_reply(reply, papers)
    reply_lower = reply.lower().strip()
    is_none_command = reply_lower == "none"

    if not selected and not is_none_command:
        # 没有有效选择，发送提示
        message = "未识别到有效的论文编号。请回复数字，如：1 2 4 6、1-5 8 10，或直接回复 none。"
        if target_id and send_to_feishu:
            send_text(target_id, message, use_chat_id=use_chat_id)
        return {"status": "error", "message": message}

    print(f"Selected paper numbers: {sorted(selected)}")
    current_timestamp = datetime.now()
    history_before_update = get_recent_selected_papers(
        user_id,
        limit=60,
        days=60,
        before_timestamp=current_timestamp.isoformat(sep=" "),
    )

    # 2. 记录行为日志
    for paper_num in selected:
        idx = paper_num - 1
        if 0 <= idx < len(papers):
            paper = papers[idx]
            paper_id = paper.get("id")  # 假设有数据库 ID

            log_behavior(
                user_id=user_id,
                push_id=push_id,
                paper_id=paper_id,
                action="selected",
                action_type="selected",
                category=paper.get("category", "unknown"),
                metadata={
                    "paper_number": paper_num,
                    "arxiv_id": paper.get("arxiv_id"),
                    "push_context": "daily_push",
                }
            )

    # 记录未选择的论文（跳过的）
    all_numbers = set(range(1, len(papers) + 1))
    skipped = all_numbers - selected
    for paper_num in skipped:
        idx = paper_num - 1
        if 0 <= idx < len(papers):
            paper = papers[idx]
            paper_id = paper.get("id")

            log_behavior(
                user_id=user_id,
                push_id=push_id,
                paper_id=paper_id,
                action="skipped",
                action_type="skipped",
                category=paper.get("category", "unknown"),
                metadata={
                    "paper_number": paper_num,
                    "arxiv_id": paper.get("arxiv_id"),
                    "push_context": "daily_push",
                }
            )

    # 3. 更新画像
    updated_profile = update_profile_based_on_selection(
        user_id,
        list(selected),
        papers,
        skipped_paper_ids=list(skipped),
        historical_selected_papers=history_before_update,
        current_timestamp=current_timestamp,
    )
    drift_state = (updated_profile or {}).get("drift_state", {}) or {}
    log_behavior(
        user_id=user_id,
        push_id=push_id,
        paper_id=None,
        action="profile_updated",
        action_type="drift_update",
        category=drift_state.get("status", "stable"),
        metadata={
            "drift_status": drift_state.get("status", "stable"),
            "drift_score": drift_state.get("score", 0.0),
            "adaptive_alpha": drift_state.get("adaptive_alpha", 0.0),
            "top_shift_topics": drift_state.get("top_shift_topics", []),
            "interest_vector_descriptor": _build_interest_vector_descriptor(updated_profile or {}),
            "selected_count": len(selected),
            "skipped_count": len(skipped),
            "explanation": drift_state.get("explanation", ""),
        },
    )

    # 4. 发送确认消息
    summary = format_selection_summary(selected, len(papers), papers)

    if target_id and send_to_feishu:
        send_text(target_id, summary, use_chat_id=use_chat_id)
        print(f"Confirmation sent to Feishu target: {target_id}")

    created_docs: List[Dict[str, Any]] = []
    reading_report_error: Optional[str] = None
    should_create_reports = auto_create_reports if auto_create_reports is not None else send_to_feishu

    if should_create_reports and selected:
        try:
            created_docs = create_reading_reports_for_selection(
                user_id=user_id,
                selected=selected,
                papers=papers,
                target_id=target_id,
                use_chat_id=use_chat_id,
                send_to_feishu=send_to_feishu,
                selection_push_id=push_id,
            )
        except Exception as exc:
            reading_report_error = str(exc)
            print(f"Reading report generation failed: {reading_report_error}")
            if target_id and send_to_feishu:
                send_text(
                    target_id,
                    "Reading report generation failed for now, but your feedback was saved.",
                    use_chat_id=use_chat_id,
                )

    return {
        "status": "success",
        "selected_count": len(selected),
        "skipped_count": len(skipped),
        "selection_rate": len(selected) / len(papers) if papers else 0,
        "reading_reports_created": len(created_docs),
        "reading_report_urls": [doc.get("url") for doc in created_docs if doc.get("url")],
        "reading_report_error": reading_report_error,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Feedback Agent - 处理用户反馈")
    parser.add_argument("--user-id", type=str, default="user_001", help="用户 ID")
    parser.add_argument("--push-id", type=str, required=True, help="推送 ID")
    parser.add_argument("--reply", type=str, required=True, help="用户回复文本")
    parser.add_argument("--send-feishu", action="store_true", default=True, help="发送到飞书")
    parser.add_argument("--feishu-user-id", type=str, help="飞书用户 ID")

    args = parser.parse_args()

    # 从数据库获取推送的论文列表
    push_info = db_ops.get_push_papers(args.push_id)
    if not push_info:
        print(f"Error: Push record not found for {args.push_id}")
        sys.exit(1)

    papers = push_info["papers"]
    print(f"Found {len(papers)} papers in push {args.push_id}")

    # 统计各类别数量
    category_counts = {}
    for p in papers:
        cat = p.get("category", "unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1
    print(f"Category counts: {category_counts}")

    # 设置飞书用户 ID
    feishu_user_id = args.feishu_user_id or os.environ.get("FEISHU_USER_ID", "").strip()

    result = process_feedback(
        user_id=args.user_id,
        push_id=args.push_id,
        reply=args.reply,
        papers=papers,
        feishu_user_id=feishu_user_id if args.send_feishu else None
    )

    print(f"\nResult: {json.dumps(result, indent=2, ensure_ascii=False)}")
