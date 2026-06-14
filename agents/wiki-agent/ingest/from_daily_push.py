"""Ingest daily push candidates into the local PaperFlow Wiki."""

from __future__ import annotations

import importlib
import json
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


wiki_db = importlib.import_module("skills.wiki-store.scripts.wiki_db")


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        return [text]
    if isinstance(value, dict):
        return [str(item).strip() for item in value.values() if str(item).strip()]
    if isinstance(value, Iterable):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _slug(value: str, max_len: int = 80) -> str:
    text = re.sub(r"[^\w.\-]+", "-", str(value or "").strip(), flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return (text or "paper")[:max_len]


def _paper_key(paper: Dict[str, Any]) -> str:
    for key in ("arxiv_id", "doi", "id"):
        value = _clean_text(paper.get(key))
        if value:
            return _slug(value)
    return _slug(_clean_text(paper.get("title")) or "untitled")


def _keywords(paper: Dict[str, Any], metadata: Dict[str, Any]) -> str:
    values: List[str] = []
    for key in ("keywords", "topics", "categories", "subjects"):
        values.extend(_normalize_list(paper.get(key)))
        values.extend(_normalize_list(metadata.get(key)))
    return " ".join(dict.fromkeys(value.lower() for value in values if value))


def _first_url(paper: Dict[str, Any], metadata: Dict[str, Any], *keys: str) -> str:
    paper_metadata = paper.get("metadata") if isinstance(paper.get("metadata"), dict) else {}
    for key in keys:
        for container in (paper, metadata, paper_metadata):
            candidate = _clean_text(container.get(key))
            if candidate.startswith(("http://", "https://")):
                return candidate
    return ""


def _safe_float(value: Any, default: float = 1.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _paper_url(paper: Dict[str, Any], metadata: Dict[str, Any]) -> str:
    return _first_url(paper, metadata, "paper_url", "url", "openreview_url", "doi_url")


def _pdf_url(paper: Dict[str, Any], metadata: Dict[str, Any]) -> str:
    url = _first_url(paper, metadata, "pdf_url")
    if url:
        return url
    arxiv_id = _clean_text(paper.get("arxiv_id"))
    return f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""


def _candidate_body(paper: Dict[str, Any], metadata: Dict[str, Any], category: Any) -> str:
    abstract = _clean_text(paper.get("abstract")) or "暂无摘要。"
    paper_link = _paper_url(paper, metadata)
    pdf_link = _pdf_url(paper, metadata)
    lines = [
        "## Candidate Summary",
        abstract,
        "",
        "## Recommendation Context",
        f"- Category: {category or 'unknown'}",
        f"- Rank: {metadata.get('rank') or '?'}",
        f"- Score: {metadata.get('score') if metadata.get('score') is not None else '?'}",
        "",
        "## Links",
    ]
    if paper_link:
        lines.append(f"- Paper: [link]({paper_link})")
    if pdf_link:
        lines.append(f"- PDF: [link]({pdf_link})")
    if not paper_link and not pdf_link:
        lines.append("- 暂无链接")
    return "\n".join(lines)


def _push_body(user_id: str, push_id: str, paper: Dict[str, Any], metadata: Dict[str, Any], category: Any) -> str:
    title = _clean_text(paper.get("title")) or "Untitled Paper"
    arxiv_id = _clean_text(paper.get("arxiv_id"))
    return "\n".join(
        [
            "## Daily Push Snapshot",
            f"- User: {user_id}",
            f"- Push: {push_id}",
            f"- Latest candidate written: {title}",
            f"- arXiv: {arxiv_id or 'N/A'}",
            f"- Category: {category or 'unknown'}",
            f"- Rank: {metadata.get('rank') or '?'}",
            "",
            "## Purpose",
            "该节点记录一次每日推送写入 Wiki 的上下文。候选论文会作为 paper 节点沉淀，并通过 derived_from 关系连接到该推送。",
        ]
    )


def ingest_pushed_paper(
    *,
    user_id: str,
    push_id: str,
    paper: Dict[str, Any],
    category: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    behavior_log_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Persist one daily-push candidate as a paper node plus push trajectory edge."""
    metadata = dict(metadata or {})
    paper_key = _paper_key(paper)
    paper_node_id = f"paper:{paper_key}"
    trajectory_id = f"trajectory:{_slug(user_id)}:{_slug(push_id)}"
    push_time = metadata.get("timestamp") or datetime.now().isoformat()
    score = metadata.get("score")
    rank = metadata.get("rank")
    category_value = category or metadata.get("category") or paper.get("category")

    wiki_db.upsert_node(
        user_id=user_id,
        node_id=paper_node_id,
        node_type="paper",
        title=_clean_text(paper.get("title")) or "Untitled Paper",
        body=_candidate_body(paper, metadata, category_value),
        metadata={
            "paper_id": paper.get("id"),
            "arxiv_id": paper.get("arxiv_id"),
            "doi": paper.get("doi"),
            "authors": _normalize_list(paper.get("authors")),
            "venue": paper.get("venue") or paper.get("journal") or metadata.get("venue"),
            "publish_date": paper.get("publish_date") or metadata.get("publish_date"),
            "subjects": _normalize_list(paper.get("subjects") or paper.get("categories") or metadata.get("categories")),
            "url": _first_url(paper, metadata, "paper_url", "url", "openreview_url", "doi_url"),
            "pdf_url": _pdf_url(paper, metadata),
            "push_id": push_id,
            "category": category_value,
            "rank": rank,
            "score": score,
        },
        keywords=_keywords(paper, metadata),
        source_type="daily_push",
        source_ref=push_id,
    )
    wiki_db.upsert_node(
        user_id=user_id,
        node_id=trajectory_id,
        node_type="trajectory",
        title=f"Daily push {push_id}",
        body=_push_body(user_id, push_id, paper, metadata, category_value),
        metadata={
            "period": push_id,
            "push_id": push_id,
            "push_time": push_time,
            "source": "daily_push",
        },
        keywords="daily-push recommendation",
        source_type="daily_push",
        source_ref=push_id,
    )
    wiki_db.upsert_edge(
        user_id=user_id,
        src_id=trajectory_id,
        dst_id=paper_node_id,
        relation="derived_from",
        weight=_safe_float(score, 1.0),
        metadata={
            "push_id": push_id,
            "rank": rank,
            "category": category_value,
            "behavior_log_id": behavior_log_id,
        },
    )
    if behavior_log_id is not None:
        wiki_db.upsert_citation(
            user_id=user_id,
            node_id=paper_node_id,
            source="behavior_log",
            source_id=str(behavior_log_id),
            anchor="daily_push",
            excerpt=f"Rank {rank or '?'} in {push_id}; category={category_value or 'unknown'}",
        )
    return {"paper_node": paper_node_id, "trajectory_node": trajectory_id}
