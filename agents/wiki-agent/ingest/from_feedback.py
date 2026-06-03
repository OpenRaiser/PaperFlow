"""Ingest user feedback events into the local PaperFlow Wiki."""

from __future__ import annotations

import importlib
import re
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
                import json

                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                pass
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


def _first_url(paper: Dict[str, Any], *keys: str) -> str:
    metadata = paper.get("metadata") if isinstance(paper.get("metadata"), dict) else {}
    for key in keys:
        for container in (paper, metadata):
            candidate = _clean_text(container.get(key))
            if candidate.startswith(("http://", "https://")):
                return candidate
    return ""


def _paper_url(paper: Dict[str, Any]) -> str:
    url = _first_url(
        paper,
        "paper_url",
        "openreview_url",
        "cvf_url",
        "ecva_url",
        "dblp_url",
        "doi_url",
        "url",
    )
    if url:
        return url
    arxiv_id = _clean_text(paper.get("arxiv_id"))
    if arxiv_id:
        return f"https://arxiv.org/abs/{arxiv_id}"
    doi = _clean_text(paper.get("doi"))
    if doi:
        return f"https://doi.org/{doi}"
    return ""


def _keywords(paper: Dict[str, Any]) -> str:
    candidates: List[str] = []
    for key in ("keywords", "topics", "categories", "subjects"):
        candidates.extend(_normalize_list(paper.get(key)))
    return " ".join(dict.fromkeys(item.lower() for item in candidates if item))


def _relation_for_action(action: str, action_type: str) -> Optional[str]:
    normalized = f"{action} {action_type}".lower()
    if "skipped" in normalized:
        return "skipped"
    if "created_report" in normalized or "reading" in normalized or "read" in normalized:
        return "read"
    if "selected" in normalized or "interested" in normalized:
        return "interested_in"
    return None


def _weight_for_relation(relation: str) -> float:
    if relation == "read":
        return 1.5
    if relation == "interested_in":
        return 1.0
    if relation == "skipped":
        return -0.5
    return 0.0


def _ensure_feedback_paper_node(
    *,
    user_id: str,
    paper: Dict[str, Any],
    push_id: str,
    category: Optional[str],
) -> str:
    paper_key = _paper_key(paper)
    node_id = f"paper:{paper_key}"
    abstract = _clean_text(paper.get("abstract"))
    title = _clean_text(paper.get("title")) or "Untitled Paper"
    body = abstract or f"Paper surfaced by PaperFlow feedback in push {push_id}."
    wiki_db.upsert_node(
        user_id=user_id,
        node_id=node_id,
        node_type="paper",
        title=title,
        body=body[:8000],
        metadata={
            "paper_id": paper.get("id"),
            "arxiv_id": paper.get("arxiv_id"),
            "doi": paper.get("doi"),
            "authors": _normalize_list(paper.get("authors")),
            "venue": paper.get("venue") or paper.get("journal") or paper.get("source"),
            "publish_date": paper.get("publish_date"),
            "subjects": _normalize_list(paper.get("subjects") or paper.get("categories")),
            "url": _paper_url(paper),
            "push_id": push_id,
            "category": category or paper.get("category"),
            "rank": paper.get("rank"),
        },
        keywords=_keywords(paper),
        source_type="feedback",
        source_ref=push_id,
    )
    return node_id


def ingest_feedback_event(
    *,
    user_id: str,
    push_id: str,
    paper: Dict[str, Any],
    action: str,
    action_type: str,
    category: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    behavior_log_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Persist one selected/skipped/read feedback event as a wiki edge."""
    relation = _relation_for_action(action, action_type)
    if not relation:
        return None

    paper_node_id = _ensure_feedback_paper_node(
        user_id=user_id,
        paper=paper,
        push_id=push_id,
        category=category,
    )
    edge_metadata = dict(metadata or {})
    edge_metadata.update(
        {
            "action": action,
            "action_type": action_type,
            "category": category,
            "push_id": push_id,
            "behavior_log_id": behavior_log_id,
        }
    )
    wiki_db.upsert_edge(
        user_id=user_id,
        src_id=f"user:{user_id}",
        dst_id=paper_node_id,
        relation=relation,
        weight=_weight_for_relation(relation),
        metadata=edge_metadata,
    )
    if behavior_log_id is not None:
        wiki_db.upsert_citation(
            user_id=user_id,
            node_id=paper_node_id,
            source="behavior_log",
            source_id=str(behavior_log_id),
            anchor=relation,
            excerpt=f"{action_type}:{action} in {push_id}",
        )
    return {
        "paper_node": paper_node_id,
        "relation": relation,
        "weight": _weight_for_relation(relation),
    }

