"""Keyword-based topic flush for the local PaperFlow Wiki."""

from __future__ import annotations

import importlib
import re
from collections import Counter, defaultdict
from typing import Dict, List


wiki_db = importlib.import_module("skills.wiki-store.scripts.wiki_db")


def _slug(value: str, max_len: int = 80) -> str:
    text = re.sub(r"[^\w.\-]+", "-", str(value or "").strip(), flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return (text or "topic")[:max_len]


def _topic_body(keyword: str, member_papers: List[str]) -> str:
    papers = "\n".join(f"- {paper_id}" for paper_id in member_papers[:12]) or "- 暂无论文"
    return "\n".join(
        [
            "## Topic Signal",
            f"`{keyword}` appears in {len(member_papers)} PaperFlow wiki paper nodes.",
            "",
            "## Why This Page Exists",
            "该主题页由论文关键词聚合生成，用来把分散的 paper 节点组织成可追踪的研究主线。",
            "",
            "## Member Papers",
            papers,
        ]
    )


def flush_topics(user_id: str, *, min_count: int = 2, limit: int = 50) -> Dict[str, int]:
    """Create topic nodes from frequent paper keywords and connect member papers."""
    papers = wiki_db.list_nodes(user_id, node_type="paper", limit=5000)
    counts: Counter[str] = Counter()
    members: Dict[str, List[str]] = defaultdict(list)
    for paper in papers:
        keywords = [token for token in str(paper.get("keywords") or "").split() if token]
        for keyword in keywords:
            counts[keyword] += 1
            members[keyword].append(paper["node_id"])

    created = 0
    edges = 0
    for keyword, count in counts.most_common(limit):
        if count < min_count:
            continue
        topic_id = f"topic:{_slug(keyword)}"
        member_papers = sorted(set(members[keyword]))
        wiki_db.upsert_node(
            user_id=user_id,
            node_id=topic_id,
            node_type="topic",
            title=keyword.replace("-", " ").title(),
            body=_topic_body(keyword, member_papers),
            metadata={
                "slug": _slug(keyword),
                "canonical_name": keyword,
                "size": len(member_papers),
                "member_papers": member_papers[:100],
            },
            keywords=keyword,
            source_type="topic_clustering",
            source_ref="keyword_flush",
        )
        created += 1
        for paper_node_id in member_papers:
            wiki_db.upsert_edge(
                user_id=user_id,
                src_id=paper_node_id,
                dst_id=topic_id,
                relation="belongs_to",
                weight=1.0,
                metadata={"keyword": keyword},
            )
            edges += 1
    return {"topics": created, "belongs_to_edges": edges}
