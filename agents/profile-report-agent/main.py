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
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
from urllib.parse import quote

import requests

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
feishu_reporter = importlib.import_module("deployments.feishu.feishu-reporter.scripts.feishu_reporter")
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
get_doc_engagement_stats = getattr(db_ops, "get_doc_engagement_stats", lambda *args, **kwargs: {})
get_paper_by_arxiv_id = db_ops.get_paper_by_arxiv_id
direction_lexicon = importlib.import_module("config.direction_lexicon")


def translate_direction(direction: str) -> str:
    """翻译研究方向为中文"""
    formatter = getattr(direction_lexicon, "format_direction_label", None)
    if callable(formatter):
        return str(formatter(direction, prefer_chinese=True) or direction)
    return direction


OPENALEX_TIMEOUT = float(os.environ.get("PAPERFLOW_WEEKLY_OPENALEX_TIMEOUT", "12"))
OPENALEX_HEADERS = {"User-Agent": "PaperFlow/0.1 WeeklyReport"}


def _normalize_title_key(value: Any) -> str:
    lowered = str(value or "").strip().casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", lowered)


def _extract_doi(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"(10\.\d{4,9}/\S+)", text, flags=re.I)
    return match.group(1).rstrip(")>.,; ") if match else ""


def _normalize_author_key(value: Any) -> str:
    lowered = str(value or "").strip().casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", lowered)


def _fetch_openalex_impact_signal(paper: Dict[str, Any]) -> Dict[str, Any]:
    doi = _extract_doi(paper.get("doi") or paper.get("doi_url") or paper.get("url"))
    title = str(paper.get("title") or "").strip()

    try:
        if doi:
            response = requests.get(
                f"https://api.openalex.org/works?filter=doi:{quote(doi, safe='')}",
                timeout=OPENALEX_TIMEOUT,
                headers=OPENALEX_HEADERS,
            )
        elif title:
            response = requests.get(
                f"https://api.openalex.org/works?search={quote(title, safe='')}&per-page=1",
                timeout=OPENALEX_TIMEOUT,
                headers=OPENALEX_HEADERS,
            )
        else:
            return {}
        response.raise_for_status()
        results = (response.json() or {}).get("results") or []
        if not results:
            return {}
        work = results[0]
    except Exception:
        return {}

    work_title = str(work.get("display_name") or work.get("title") or "").strip()
    if title and not doi and _normalize_title_key(work_title) != _normalize_title_key(title):
        return {}

    return {
        "cited_by_count": int(work.get("cited_by_count") or 0),
        "is_open_access": bool((work.get("open_access") or {}).get("is_oa")),
        "venue": str((((work.get("primary_location") or {}).get("source") or {}).get("display_name")) or "").strip(),
        "publication_year": work.get("publication_year"),
        "openalex_id": str(work.get("id") or "").strip(),
        "cited_by_api_url": str(work.get("cited_by_api_url") or "").strip(),
    }


def _cached_openalex_impact_signal(
    paper: Dict[str, Any],
    cache: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    doi = _extract_doi(paper.get("doi") or paper.get("doi_url") or paper.get("url"))
    title = str(paper.get("title") or "").strip()
    cache_key = doi or _normalize_title_key(title)
    if not cache_key:
        return {}
    if cache_key not in cache:
        cache[cache_key] = _fetch_openalex_impact_signal(paper)
    return cache.get(cache_key, {}) or {}


def _fetch_citing_author_matches(
    impact_signal: Dict[str, Any],
    must_read_authors: List[str],
) -> List[Dict[str, Any]]:
    cited_by_api_url = str(impact_signal.get("cited_by_api_url") or "").strip()
    if not cited_by_api_url or not must_read_authors:
        return []

    try:
        response = requests.get(
            f"{cited_by_api_url}&per-page=10" if "?" in cited_by_api_url else f"{cited_by_api_url}?per-page=10",
            timeout=OPENALEX_TIMEOUT,
            headers=OPENALEX_HEADERS,
        )
        response.raise_for_status()
        results = (response.json() or {}).get("results") or []
    except Exception:
        return []

    normalized_targets = {
        _normalize_author_key(author): str(author).strip()
        for author in must_read_authors
        if str(author).strip()
    }
    matches: List[Dict[str, Any]] = []
    for work in results:
        authorships = work.get("authorships") or []
        citing_authors = [
            str(((authorship.get("author") or {}).get("display_name")) or "").strip()
            for authorship in authorships
        ]
        matched_authors = []
        for author in citing_authors:
            normalized = _normalize_author_key(author)
            if normalized and normalized in normalized_targets:
                matched_authors.append(normalized_targets[normalized])
        if not matched_authors:
            continue
        matches.append(
            {
                "title": str(work.get("display_name") or work.get("title") or "").strip(),
                "matched_authors": matched_authors,
                "cited_by_count": int(work.get("cited_by_count") or 0),
            }
        )
    return matches[:3]


def _build_accuracy_explanations(stats_by_category: Dict[str, Dict[str, Any]]) -> List[str]:
    if not stats_by_category:
        return ["当前样本不足，暂时无法形成稳定的推荐准确率解释。"]

    high = float((stats_by_category.get("high_relevant") or {}).get("selection_rate", 0.0) or 0.0)
    maybe = float((stats_by_category.get("maybe_interested") or {}).get("selection_rate", 0.0) or 0.0)
    edge = float((stats_by_category.get("edge_relevant") or {}).get("selection_rate", 0.0) or 0.0)
    must_read = float((stats_by_category.get("must_read") or {}).get("selection_rate", 0.0) or 0.0)

    explanations: List[str] = []
    if high >= maybe >= edge and high > 0:
        explanations.append("高相关分组的选择率高于中低相关分组，说明当前排序主链路整体有效。")
    if edge >= maybe and edge > 0.05:
        explanations.append("边缘相关分组的选择率偏高，说明系统仍存在一定的漏排空间。")
    if maybe > high and maybe > 0:
        explanations.append("你更常从“可能感兴趣”中选文，说明系统对中间层候选的排序还可以继续优化。")
    if must_read > 0 and high > 0 and must_read < high:
        explanations.append("必读命中率低于高相关分组，说明当前 must_read 更适合作为软加分而非硬优先级。")

    return explanations[:3] or ["当前分组之间的选择率差异不明显，建议继续积累更多反馈后再观察。"]


def _build_trend_explanations(direction_changes: List[Dict[str, Any]], drift_summary: Dict[str, Any]) -> List[str]:
    explanations: List[str] = []
    significant_changes = [
        change for change in direction_changes
        if abs(float(change.get("delta", 0.0) or 0.0)) >= 0.03
    ]
    for change in significant_changes[:2]:
        direction_cn = translate_direction(change.get("direction", ""))
        delta = float(change.get("delta", 0.0) or 0.0)
        if delta > 0:
            explanations.append(f"{direction_cn} 本周持续上升，说明该方向正在被更多真实阅读行为强化。")
        elif delta < 0:
            explanations.append(f"{direction_cn} 本周出现回落，说明你近期对该方向的持续关注在减弱。")

    status = str((drift_summary or {}).get("status", "stable"))
    if status == "shifting":
        explanations.append("系统检测到近期偏好与长期画像明显拉开，因此推荐排序已更偏向短期兴趣。")
    elif status == "recovered":
        explanations.append("系统判断新兴趣正在稳定化，因此开始重新平衡短期与长期画像。")

    return explanations[:3]


def _detect_missed_papers(logs: List[Dict], recent_pushes: List[Dict]) -> List[Dict]:
    """
    检测遗漏的论文（用户跳过但可能重要的）

    Args:
        logs: 行为日志
        recent_pushes: 最近推送的论文

    Returns:
        遗漏论文列表
    """
    selected_ids = {
        int(log.get("paper_id"))
        for log in logs
        if str(log.get("action_type") or "") == "selected" and log.get("paper_id") is not None
    }

    candidates: List[Dict[str, Any]] = []
    seen_titles = set()
    for paper in recent_pushes:
        paper_id = paper.get("id")
        if paper_id in selected_ids:
            continue

        title_key = _normalize_title_key(paper.get("title"))
        if not title_key or title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        category = str(paper.get("category") or "")
        score = float(paper.get("score") or 0.0)
        if category not in {"high_relevant", "maybe_interested", "must_read"} and score < 0.35:
            continue

        impact = _fetch_openalex_impact_signal(paper)
        cited_by_count = int(impact.get("cited_by_count") or 0)
        if cited_by_count <= 0 and category != "must_read":
            continue

        candidates.append(
            {
                "title": paper.get("title", "Unknown"),
                "category": category,
                "score": score,
                "cited_by_count": cited_by_count,
                "impact_venue": impact.get("venue", ""),
                "is_open_access": impact.get("is_open_access", False),
            }
        )

    candidates.sort(
        key=lambda item: (
            int(item.get("cited_by_count", 0)),
            float(item.get("score", 0.0)),
        ),
        reverse=True,
    )
    return candidates[:3]


def _build_external_impact_summary(
    profile: Dict[str, Any],
    logs: List[Dict[str, Any]],
    recent_pushes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    selected_ids = {
        int(log.get("paper_id"))
        for log in logs
        if str(log.get("action_type") or "") == "selected" and log.get("paper_id") is not None
    }
    must_read_authors = [str(author).strip() for author in ((profile or {}).get("must_read", {}) or {}).get("authors", []) if str(author).strip()]

    impact_cache: Dict[str, Dict[str, Any]] = {}
    selected_impacts: List[Dict[str, Any]] = []
    skipped_impacts: List[Dict[str, Any]] = []
    cited_by_must_read: List[Dict[str, Any]] = []

    for paper in recent_pushes[:25]:
        impact = _cached_openalex_impact_signal(paper, impact_cache)
        cited_by_count = int(impact.get("cited_by_count") or 0)
        if cited_by_count > 0:
            item = {
                "title": paper.get("title", "Unknown"),
                "cited_by_count": cited_by_count,
                "impact_venue": impact.get("venue", ""),
                "category": str(paper.get("category") or ""),
            }
            if paper.get("id") in selected_ids:
                selected_impacts.append(item)
            else:
                skipped_impacts.append(item)

        if must_read_authors and impact.get("cited_by_api_url"):
            author_matches = _fetch_citing_author_matches(impact, must_read_authors)
            if author_matches:
                cited_by_must_read.append(
                    {
                        "title": paper.get("title", "Unknown"),
                        "matches": author_matches,
                        "cited_by_count": cited_by_count,
                    }
                )

    selected_impacts.sort(key=lambda item: int(item.get("cited_by_count", 0)), reverse=True)
    skipped_impacts.sort(key=lambda item: int(item.get("cited_by_count", 0)), reverse=True)
    cited_by_must_read.sort(
        key=lambda item: (
            int(item.get("cited_by_count", 0)),
            len(item.get("matches") or []),
        ),
        reverse=True,
    )

    explanations: List[str] = []
    if selected_impacts:
        top_selected = selected_impacts[0]
        explanations.append(
            f"你本周选中的论文里，外部引用积累最高的是《{top_selected['title']}》"
            f"（cited_by={top_selected['cited_by_count']}）。"
        )

    if selected_impacts and skipped_impacts:
        avg_selected = sum(int(item.get("cited_by_count", 0)) for item in selected_impacts) / max(1, len(selected_impacts))
        avg_skipped = sum(int(item.get("cited_by_count", 0)) for item in skipped_impacts) / max(1, len(skipped_impacts))
        if avg_selected > avg_skipped * 1.2:
            explanations.append("你本周选中的论文整体引用积累高于跳过论文，说明当前选择对外部影响力信号也较敏感。")
        elif avg_skipped > avg_selected * 1.2:
            explanations.append("你本周跳过的论文里有一批外部引用更高的候选，说明周报里的“遗漏但重要”仍值得继续补看。")

    if cited_by_must_read:
        top_relation = cited_by_must_read[0]
        matched_authors = top_relation.get("matches", [{}])[0].get("matched_authors", []) or []
        if matched_authors:
            explanations.append(
                f"《{top_relation['title']}》已被你的必读作者 {', '.join(matched_authors[:2])} 的后续工作引用，属于更强的引用关系信号。"
            )

    return {
        "selected_impacts": selected_impacts[:3],
        "skipped_impacts": skipped_impacts[:3],
        "cited_by_must_read": cited_by_must_read[:3],
        "explanations": explanations[:3],
    }


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
    doc_engagement = get_doc_engagement_stats(user_id, days)

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
    drift_summary = _build_drift_summary(profile, drift_updates)
    external_impact = _build_external_impact_summary(profile, logs, recent_pushes)

    return {
        "user_id": user_id,
        "period": f"{start_date.isoformat()} ~ {end_date.isoformat()}",
        "direction_changes": direction_changes,
        "stats": stats,
        "stats_by_category": stats_by_category,
        "accuracy_explanations": _build_accuracy_explanations(stats_by_category),
        "recent_reads_count": len(recent_reads),
        "top_authors": top_authors,
        "top_institutions": top_institutions,
        "top_directions": top_directions,
        "missed_papers": _detect_missed_papers(logs, recent_pushes),
        "profile_version": profile.get("version", "unknown"),
        "drift_summary": drift_summary,
        "trend_explanations": _build_trend_explanations(direction_changes, drift_summary),
        "doc_engagement": doc_engagement,
        "external_impact": external_impact,
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
            topic_labels = [translate_direction(topic) for topic in drift_summary.get("top_shift_topics", [])[:3]]
            lines.append(f"最近漂移主题：{', '.join(topic_labels)}")
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
    doc_engagement = report.get("doc_engagement", {}) or {}
    if doc_engagement.get("total_doc_opens"):
        lines.append(
            f"精读文档打开：{doc_engagement.get('total_doc_opens', 0)} 次"
            f"（去重后 {doc_engagement.get('unique_doc_opens', 0)} 篇）"
        )
    if doc_engagement.get("dwell_proxy_count"):
        lines.append(
            f"精读阅读停留代理：平均 {float(doc_engagement.get('avg_dwell_proxy_seconds', 0.0)):.0f} 秒"
        )
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
        for explanation in report.get("accuracy_explanations", [])[:3]:
            lines.append(f"  · {explanation}")
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
            impact_text = ""
            if paper.get("cited_by_count"):
                impact_text = f" | OpenAlex cited_by={paper.get('cited_by_count')}"
            lines.append(f"[{paper.get('title', 'Unknown')}] {impact_text}")
        lines.append("→ 要补读吗？")
        lines.append("")

    external_impact = report.get("external_impact", {}) or {}
    if external_impact:
        selected_impacts = external_impact.get("selected_impacts", []) or []
        cited_by_must_read = external_impact.get("cited_by_must_read", []) or []
        explanations = external_impact.get("explanations", []) or []
        if selected_impacts or cited_by_must_read or explanations:
            lines.append("━━━ 外部影响信号 ━━━")
            for explanation in explanations[:3]:
                lines.append(f"  · {explanation}")
            for paper in selected_impacts[:2]:
                lines.append(
                    f"  · 已选高影响论文：《{paper.get('title', 'Unknown')}》"
                    f" | cited_by={paper.get('cited_by_count', 0)}"
                )
            for relation in cited_by_must_read[:2]:
                match = (relation.get("matches") or [{}])[0]
                matched_authors = match.get("matched_authors", []) or []
                if matched_authors:
                    lines.append(
                        f"  · 必读作者引用：《{relation.get('title', 'Unknown')}》"
                        f" ← {', '.join(matched_authors[:2])}"
                    )
            lines.append("")

    trend_explanations = report.get("trend_explanations", [])
    if trend_explanations:
        lines.append("━━━ 趋势解释 ━━━")
        for item in trend_explanations[:3]:
            lines.append(f"  · {item}")
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
