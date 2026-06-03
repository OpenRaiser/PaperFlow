"""Ingest profile drift snapshots into the local PaperFlow Wiki."""

from __future__ import annotations

import importlib
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


wiki_db = importlib.import_module("skills.wiki-store.scripts.wiki_db")


def _slug(value: str, max_len: int = 80) -> str:
    text = re.sub(r"[^\w.\-]+", "-", str(value or "").strip(), flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return (text or "topic")[:max_len]


def _weight_mapping(profile: Dict[str, Any]) -> Dict[str, float]:
    merged: Dict[str, float] = {}
    for key in ("core_directions", "topic_weights"):
        value = profile.get(key)
        if not isinstance(value, dict):
            continue
        for topic, weight in value.items():
            try:
                merged[str(topic)] = max(float(weight), merged.get(str(topic), 0.0))
            except (TypeError, ValueError):
                continue
    return merged


def _period(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _render_body(deltas: List[Dict[str, Any]], evidence_papers: List[str], drift_state: Dict[str, Any]) -> str:
    lines = ["Profile drift snapshot:"]
    for item in deltas:
        sign = "+" if item["delta"] >= 0 else ""
        lines.append(
            f"- {item['topic']}: {item['before']:.3f} -> {item['after']:.3f} ({sign}{item['delta']:.3f})"
        )
    if drift_state:
        lines.append(f"- Drift status: {drift_state.get('status', 'stable')}")
        if drift_state.get("explanation"):
            lines.append(f"- Explanation: {drift_state.get('explanation')}")
    if evidence_papers:
        lines.append("- Evidence papers: " + ", ".join(evidence_papers[:12]))
    return "\n".join(lines)


def ingest_drift(
    *,
    user_id: str,
    before: Dict[str, Any],
    after: Dict[str, Any],
    evidence_papers: Optional[Iterable[Dict[str, Any] | str]] = None,
    source_ref: Optional[str] = None,
    threshold: float = 0.01,
) -> Optional[Dict[str, Any]]:
    """Create/update the current profile-drift trajectory node."""
    before_weights = _weight_mapping(before or {})
    after_weights = _weight_mapping(after or {})
    deltas: List[Dict[str, Any]] = []
    for topic in sorted(set(before_weights) | set(after_weights)):
        before_value = float(before_weights.get(topic, 0.0))
        after_value = float(after_weights.get(topic, 0.0))
        delta = after_value - before_value
        if abs(delta) >= threshold:
            deltas.append(
                {
                    "topic": topic,
                    "before": round(before_value, 4),
                    "after": round(after_value, 4),
                    "delta": round(delta, 4),
                }
            )
    if not deltas:
        return None

    now = datetime.now()
    period = _period(now)
    trajectory_id = f"trajectory:{_slug(user_id)}:{period}"
    evidence_ids: List[str] = []
    for item in evidence_papers or []:
        if isinstance(item, str):
            evidence_ids.append(item)
        elif isinstance(item, dict):
            key = item.get("arxiv_id") or item.get("doi") or item.get("id") or item.get("title")
            if key:
                evidence_ids.append(f"paper:{_slug(str(key))}")

    drift_state = after.get("drift_state") if isinstance(after.get("drift_state"), dict) else {}
    body = _render_body(deltas, evidence_ids, drift_state or {})
    wiki_db.upsert_node(
        user_id=user_id,
        node_id=trajectory_id,
        node_type="trajectory",
        title=f"Interest drift: {period}",
        body=body,
        metadata={
            "period": period,
            "window_days": 7,
            "before_directions": before_weights,
            "after_directions": after_weights,
            "deltas": deltas,
            "delta_summary": " / ".join(
                f"{item['topic']} {'+' if item['delta'] >= 0 else ''}{item['delta']:.2f}" for item in deltas
            ),
            "drift_state": drift_state,
            "evidence_papers": evidence_ids,
        },
        keywords=" ".join(item["topic"] for item in deltas),
        source_type="profile_drift",
        source_ref=source_ref or after.get("version") or now.isoformat(),
    )

    for item in deltas:
        topic_id = f"topic:{_slug(item['topic'])}"
        wiki_db.upsert_node(
            user_id=user_id,
            node_id=topic_id,
            node_type="topic",
            title=str(item["topic"]).replace("-", " ").title(),
            body=f"Topic node for {item['topic']}.",
            metadata={"canonical_name": item["topic"], "source": "profile_drift"},
            keywords=item["topic"],
            source_type="profile_drift",
            source_ref=trajectory_id,
        )
        wiki_db.upsert_edge(
            user_id=user_id,
            src_id=trajectory_id,
            dst_id=topic_id,
            relation="drifted_to" if item["delta"] > 0 else "drifted_from",
            weight=abs(float(item["delta"])),
            metadata={"period": period},
        )
    for paper_id in evidence_ids:
        wiki_db.upsert_edge(
            user_id=user_id,
            src_id=trajectory_id,
            dst_id=paper_id,
            relation="derived_from",
            weight=1.0,
            metadata={"period": period},
        )
    return {"trajectory_node": trajectory_id, "delta_count": len(deltas)}

