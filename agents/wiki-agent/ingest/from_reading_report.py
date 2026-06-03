"""Ingest PaperFlow reading reports into the local wiki."""

from __future__ import annotations

import importlib
import json
import re
from typing import Any, Dict, Iterable, List, Optional


wiki_db = importlib.import_module("skills.wiki-store.scripts.wiki_db")


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "using",
    "with",
    "we",
    "this",
    "that",
    "paper",
    "method",
    "model",
}


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


def _body_text(value: Any) -> str:
    items = _normalize_list(value)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return "\n".join(f"- {item}" for item in items)


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


def _pdf_url(paper: Dict[str, Any]) -> str:
    url = _first_url(paper, "pdf_url")
    if url:
        return url
    arxiv_id = _clean_text(paper.get("arxiv_id"))
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    return ""


def _keywords(paper: Dict[str, Any], payload: Dict[str, Any]) -> str:
    candidates: List[str] = []
    for key in ("keywords", "topics", "categories", "subjects"):
        candidates.extend(_normalize_list(payload.get(key)))
        candidates.extend(_normalize_list(paper.get(key)))
    if candidates:
        return " ".join(dict.fromkeys(item.lower() for item in candidates if item))

    source = " ".join(
        [
            _clean_text(paper.get("title")),
            _clean_text(paper.get("abstract")),
            _clean_text(payload.get("one_sentence_summary")),
        ]
    ).lower()
    tokens = re.findall(r"[a-z][a-z0-9\-]{2,}", source)
    counts: Dict[str, int] = {}
    for token in tokens:
        if token in STOPWORDS:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts, key=lambda item: (-counts[item], item))[:8]
    return " ".join(ranked)


def _paper_metadata(
    paper: Dict[str, Any],
    payload: Dict[str, Any],
    *,
    report_path: Optional[str],
    doc_url: Optional[str],
    doc_token: Optional[str],
) -> Dict[str, Any]:
    return {
        "arxiv_id": paper.get("arxiv_id"),
        "doi": paper.get("doi"),
        "authors": _normalize_list(paper.get("authors")),
        "institution": paper.get("institution"),
        "venue": paper.get("venue") or paper.get("journal") or paper.get("source"),
        "publish_date": paper.get("publish_date"),
        "subjects": _normalize_list(paper.get("subjects") or paper.get("categories")),
        "url": _paper_url(paper),
        "pdf_url": _pdf_url(paper),
        "pdf_path": paper.get("pdf_path"),
        "report_path": report_path,
        "doc_url": doc_url,
        "doc_token": doc_token,
        "recommendation_label": payload.get("recommendation_label"),
        "estimated_reading_minutes": payload.get("estimated_reading_minutes"),
        "generation_provider": payload.get("generation_provider"),
        "generation_model": payload.get("generation_model"),
    }


def ingest_reading_report(
    *,
    user_id: str,
    paper: Dict[str, Any],
    report_md: str,
    payload: Optional[Dict[str, Any]] = None,
    report_path: Optional[str] = None,
    doc_url: Optional[str] = None,
    doc_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Turn one reading report into paper and section wiki nodes."""
    payload = dict(payload or {})
    paper_key = _paper_key(paper)
    paper_node_id = f"paper:{paper_key}"
    keywords = _keywords(paper, payload)
    source_ref = report_path or doc_url or paper_node_id

    paper_body = "\n\n".join(
        item
        for item in (
            _clean_text(payload.get("one_sentence_summary")),
            _clean_text(paper.get("abstract")),
        )
        if item
    )
    if not paper_body:
        paper_body = _clean_text(report_md)[:4000]

    wiki_db.upsert_node(
        user_id=user_id,
        node_id=paper_node_id,
        node_type="paper",
        title=_clean_text(paper.get("title")) or "Untitled Paper",
        body=paper_body[:8000],
        metadata=_paper_metadata(paper, payload, report_path=report_path, doc_url=doc_url, doc_token=doc_token),
        keywords=keywords,
        source_type="reading_report",
        source_ref=source_ref,
    )
    wiki_db.upsert_edge(
        user_id=user_id,
        src_id=f"user:{user_id}",
        dst_id=paper_node_id,
        relation="read",
        weight=1.5,
        metadata={
            "source": "reading_report",
            "report_path": report_path,
            "doc_url": doc_url,
            "doc_token": doc_token,
        },
    )

    sections = [
        ("abstract", "Abstract", paper.get("abstract")),
        ("tldr", "TL;DR", payload.get("one_sentence_summary")),
        ("Q1-research-background", "Q1 Research background", payload.get("research_background")),
        ("Q2-core-method", "Q2 Core method", payload.get("core_method")),
        ("Q3-key-results", "Q3 Key results", payload.get("key_results")),
        ("Q4-contributions", "Q4 Contributions", payload.get("main_contributions")),
        ("Q5-limitations", "Q5 Limitations", payload.get("limitations")),
        ("Q6-relevance", "Q6 Relevance", payload.get("relevance_points")),
        ("Q7-reading-plan", "Q7 Reading plan", payload.get("reading_focus")),
        ("recommendation-reason", "Recommendation reason", payload.get("recommendation_reason")),
    ]

    section_count = 0
    for kind, title, raw_body in sections:
        body = _body_text(raw_body)
        if not body:
            continue
        section_id = f"section:{paper_key}#{kind}"
        wiki_db.upsert_node(
            user_id=user_id,
            node_id=section_id,
            node_type="section",
            title=title,
            body=body[:8000],
            metadata={
                "parent_paper_id": paper_node_id,
                "section_kind": kind,
                "anchor": f"#{kind}",
            },
            keywords=keywords,
            source_type="reading_report",
            source_ref=source_ref,
        )
        wiki_db.upsert_edge(
            user_id=user_id,
            src_id=paper_node_id,
            dst_id=section_id,
            relation="contains_section",
            weight=1.0,
        )
        wiki_db.upsert_citation(
            user_id=user_id,
            node_id=section_id,
            source="reading_report",
            source_id=source_ref,
            anchor=title,
            excerpt=body[:500],
        )
        section_count += 1

    paper_url = _paper_url(paper)
    if paper_url:
        wiki_db.upsert_citation(
            user_id=user_id,
            node_id=paper_node_id,
            source="external_url",
            source_id=paper_url,
            anchor="paper",
            excerpt=_clean_text(paper.get("abstract"))[:500],
        )

    return {
        "paper_node": paper_node_id,
        "section_count": section_count,
        "keywords": keywords,
    }
