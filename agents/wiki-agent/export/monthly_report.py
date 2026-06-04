"""Export Obsidian-friendly monthly reports from the local PaperFlow Wiki."""

from __future__ import annotations

import importlib
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from paperflow import roles as role_utils


PROJECT_ROOT = Path(__file__).resolve().parents[3]

wiki_db = importlib.import_module("skills.wiki-store.scripts.wiki_db")


MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _parse_month(value: Optional[str]) -> str:
    text = _clean_text(value) or datetime.now().strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-\d{2}", text):
        raise ValueError("month must use YYYY-MM format, for example 2026-05")
    year, month = text.split("-")
    number = int(month)
    if number < 1 or number > 12:
        raise ValueError("month must be between 01 and 12")
    return f"{int(year):04d}-{number:02d}"


def _month_label(month: str) -> str:
    year, month_number = month.split("-")
    return f"{MONTH_NAMES[int(month_number) - 1]} {year}"


def _resolve_dir(
    explicit: Optional[str],
    env_name: str,
    *,
    fallback: Path,
    user_id: str,
    category: str = "",
) -> Path:
    raw = _clean_text(explicit) or os.environ.get(env_name, "").strip()
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
    else:
        path = fallback
    path = role_utils.apply_output_scope(
        path,
        user_id,
        category=category,
        project_root=PROJECT_ROOT,
    )
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _export_filename(prefix: str, user_id: str, month: str) -> str:
    role_label = role_utils.storage_label_for_user_id(user_id, project_root=PROJECT_ROOT)
    return f"{prefix} - {role_label} - {month}.md"


def _parse_date(value: Any) -> Optional[datetime]:
    text = _clean_text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    for candidate in (normalized, normalized[:19], normalized[:10]):
        if not candidate:
            continue
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            pass
    return None


def _node_dates(node: Dict[str, Any]) -> List[Tuple[str, datetime]]:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    candidates: List[Tuple[str, Any]] = []
    for key in (
        "saved_at",
        "read_at",
        "report_created_at",
        "push_time",
        "feedback_time",
        "timestamp",
        "publish_date",
        "published",
        "updated",
        "fetched_at",
    ):
        candidates.append((key, metadata.get(key)))
    candidates.extend(
        [
            ("updated_at", node.get("updated_at")),
            ("created_at", node.get("created_at")),
        ]
    )
    parsed: List[Tuple[str, datetime]] = []
    seen: set[str] = set()
    for label, value in candidates:
        date = _parse_date(value)
        if not date:
            continue
        key = f"{label}:{date.isoformat()}"
        if key in seen:
            continue
        seen.add(key)
        parsed.append((label, date))
    return parsed


def _matches_month(node: Dict[str, Any], month: str) -> bool:
    return any(date.strftime("%Y-%m") == month for _, date in _node_dates(node))


def _display_date(node: Dict[str, Any], month: str) -> str:
    matching = [(label, date) for label, date in _node_dates(node) if date.strftime("%Y-%m") == month]
    candidates = matching or _node_dates(node)
    if not candidates:
        return month
    # Prefer the paper date when this is a publication-month export, otherwise
    # keep the first matching activity date.
    for label, date in candidates:
        if label in {"publish_date", "published"}:
            return date.strftime("%Y-%m-%d")
    return candidates[0][1].strftime("%Y-%m-%d")


def _normalize_keywords(value: Any) -> List[str]:
    if isinstance(value, list):
        raw = " ".join(str(item) for item in value)
    else:
        raw = _clean_text(value)
    tokens = [
        token.strip().lower()
        for token in re.split(r"[\s,;，；]+", raw)
        if token.strip()
    ]
    return list(dict.fromkeys(tokens))


def _first_sentence(text: str, *, max_chars: int = 220) -> str:
    body = re.sub(r"\s+", " ", _clean_text(text))
    if not body:
        return ""
    match = re.search(r"(.{20,}?[。.!?])\s", body + " ")
    sentence = match.group(1) if match else body
    if len(sentence) <= max_chars:
        return sentence
    return sentence[: max_chars - 1].rstrip() + "..."


def _markdown_link(label: str, target: str) -> str:
    target = _clean_text(target)
    if not target:
        return label
    if target.startswith(("http://", "https://")):
        return f"[{label}]({target})"
    return f"[{label}](<{Path(target).expanduser().as_posix()}>)"


def _paper_links(node: Dict[str, Any]) -> str:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    links: List[str] = []
    url = _clean_text(metadata.get("url"))
    if url:
        links.append(_markdown_link("论文", url))
    pdf_path = _clean_text(metadata.get("pdf_path"))
    pdf_url = _clean_text(metadata.get("pdf_url"))
    if pdf_path:
        links.append(_markdown_link("PDF", pdf_path))
    elif pdf_url:
        links.append(_markdown_link("PDF", pdf_url))
    report_path = _clean_text(metadata.get("report_path"))
    if report_path:
        links.append(_markdown_link("精读", report_path))
    doc_url = _clean_text(metadata.get("doc_url"))
    if doc_url:
        links.append(_markdown_link("飞书文档", doc_url))
    file_path = _clean_text(node.get("file_path"))
    if file_path:
        wiki_root = Path(wiki_db.stats(node["user_id"])["wiki_dir"])
        links.append(_markdown_link("Wiki", str(wiki_root / file_path)))
    return " · ".join(links)


def _paper_identifier(node: Dict[str, Any]) -> str:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    for key in ("arxiv_id", "doi", "paper_id"):
        value = _clean_text(metadata.get(key))
        if value:
            return value
    return _clean_text(node.get("node_id"))


def _paper_summary(node: Dict[str, Any]) -> str:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    for key in ("one_sentence_summary", "summary", "abstract"):
        summary = _first_sentence(_clean_text(metadata.get(key)))
        if summary:
            return summary
    return _first_sentence(_clean_text(node.get("body")))


def _paper_rows(papers: Iterable[Dict[str, Any]], month: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for node in papers:
        metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        keywords = _normalize_keywords(node.get("keywords") or metadata.get("keywords"))
        rows.append(
            {
                "node": node,
                "node_id": node["node_id"],
                "title": _clean_text(node.get("title")) or node["node_id"],
                "identifier": _paper_identifier(node),
                "date": _display_date(node, month),
                "venue": _clean_text(metadata.get("venue")),
                "authors": metadata.get("authors") if isinstance(metadata.get("authors"), list) else [],
                "keywords": keywords,
                "summary": _paper_summary(node),
                "links": _paper_links(node),
            }
        )
    return sorted(rows, key=lambda item: (item["date"], item["title"]))


def _build_topic_groups(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for keyword in row["keywords"]:
            grouped[keyword].append(row)
    return {
        topic: sorted(items, key=lambda item: (item["date"], item["title"]))
        for topic, items in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    }


def _render_monthly_report(user_id: str, month: str, rows: List[Dict[str, Any]]) -> str:
    label = _month_label(month)
    topic_groups = _build_topic_groups(rows)
    topic_counts = Counter({topic: len(items) for topic, items in topic_groups.items()})
    lines = [
        f"# PaperFlow Monthly Report - {month}",
        "",
        "## 本月阅读概览",
        "",
        f"- 用户：`{user_id}`",
        f"- 月份：{label}",
        f"- 论文数：{len(rows)}",
        f"- 主要主题：{', '.join(topic for topic, _ in topic_counts.most_common(8)) or '暂无'}",
        "",
        "## 主题趋势",
        "",
    ]
    if topic_counts:
        for topic, count in topic_counts.most_common(10):
            titles = "；".join(item["title"] for item in topic_groups[topic][:3])
            lines.append(f"- **{topic}**：{count} 篇。代表论文：{titles}")
    else:
        lines.append("- 暂无足够主题信号。")
    lines.extend(["", "## 论文列表", ""])
    if not rows:
        lines.append("本月还没有可导出的 PaperFlow wiki 论文节点。")
    for index, row in enumerate(rows, start=1):
        heading_bits = [f"{index}. **{row['title']}**"]
        if row["identifier"]:
            heading_bits.append(f"`{row['identifier']}`")
        heading_bits.append(row["date"])
        if row["venue"]:
            heading_bits.append(row["venue"])
        lines.append(" · ".join(heading_bits))
        if row["links"]:
            lines.append(f"   - 链接：{row['links']}")
        if row["summary"]:
            lines.append(f"   - 简介：{row['summary']}")
        if row["keywords"]:
            lines.append(f"   - 关键词：{', '.join(row['keywords'][:8])}")
    lines.append("")
    return "\n".join(lines)


def _render_topic_index(user_id: str, month: str, rows: List[Dict[str, Any]]) -> str:
    topic_groups = _build_topic_groups(rows)
    lines = [
        f"# Topic Index - {month}",
        "",
        f"用户：`{user_id}`",
        "",
    ]
    if not topic_groups:
        lines.append("暂无可索引主题。")
        lines.append("")
        return "\n".join(lines)
    for topic, items in topic_groups.items():
        lines.extend([f"## {topic}", ""])
        for item in items:
            link = item["links"] or item["title"]
            lines.append(f"- {item['date']} · {link} · {item['title']}")
        lines.append("")
    return "\n".join(lines)


def export_monthly_report(
    user_id: str,
    *,
    month: Optional[str] = None,
    output_dir: Optional[str] = None,
    topic_index_dir: Optional[str] = None,
    write_topic_index: bool = True,
) -> Dict[str, Any]:
    """Write a monthly report and optional topic index from wiki paper nodes."""
    user_id = _clean_text(user_id)
    if not user_id:
        raise ValueError("user_id is required")
    month_value = _parse_month(month)
    wiki_db.init_wiki_schema()

    fallback_dir = Path(wiki_db.stats(user_id)["wiki_dir"]).parent / "exports"
    report_dir = _resolve_dir(
        output_dir,
        "PAPERFLOW_MONTHLY_REPORT_DIR",
        fallback=fallback_dir,
        user_id=user_id,
        category="monthly_reports",
    )
    topic_dir = _resolve_dir(
        topic_index_dir,
        "PAPERFLOW_TOPIC_INDEX_DIR",
        fallback=fallback_dir,
        user_id=user_id,
        category="topic_index",
    )

    papers = [
        node
        for node in wiki_db.list_nodes(user_id, node_type="paper", limit=10000)
        if _matches_month(node, month_value)
    ]
    rows = _paper_rows(papers, month_value)

    report_path = report_dir / _export_filename("PaperFlow Monthly Report", user_id, month_value)
    report_path.write_text(_render_monthly_report(user_id, month_value, rows), encoding="utf-8")

    topic_index_path: Optional[Path] = None
    if write_topic_index:
        topic_index_path = topic_dir / _export_filename("Topic Index", user_id, month_value)
        topic_index_path.write_text(_render_topic_index(user_id, month_value, rows), encoding="utf-8")

    return {
        "user_id": user_id,
        "month": month_value,
        "paper_count": len(rows),
        "topic_count": len(_build_topic_groups(rows)),
        "report_path": str(report_path),
        "topic_index_path": str(topic_index_path) if topic_index_path else None,
    }
