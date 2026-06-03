"""Backfill existing PaperFlow runtime data into the local wiki."""

from __future__ import annotations

import importlib
import json
from typing import Any, Dict, Iterable, List, Optional


db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
wiki_db = importlib.import_module("skills.wiki-store.scripts.wiki_db")
daily_ingest = importlib.import_module("agents.wiki-agent.ingest.from_daily_push")
feedback_ingest = importlib.import_module("agents.wiki-agent.ingest.from_feedback")
topic_ingest = importlib.import_module("agents.wiki-agent.ingest.from_topic_clustering")


def _load_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _paper_from_row(row: Any) -> Dict[str, Any]:
    paper = dict(row)
    metadata = _load_json(paper.get("metadata"))
    if metadata:
        paper.update({key: value for key, value in metadata.items() if paper.get(key) in (None, "", [], {})})
    return paper


def backfill_user(user_id: str, *, dry_run: bool = False) -> Dict[str, Any]:
    """Backfill push and feedback behavior logs for one user."""
    wiki_db.init_wiki_schema()
    counts: Dict[str, Any] = {"pushed": 0, "feedback": 0, "topics": 0, "embedded": 0}
    missing_tables = [
        table for table in ("behavior_logs", "papers") if not wiki_db.table_exists(table)
    ]
    if missing_tables:
        counts["missing_tables"] = missing_tables
        return counts

    conn = db_ops.get_connection()
    rows = conn.execute(
        """
        SELECT bl.id AS behavior_log_id, bl.user_id, bl.push_id, bl.paper_id,
               bl.action, bl.action_type, bl.category, bl.timestamp,
               bl.metadata AS behavior_metadata,
               p.*
        FROM behavior_logs bl
        LEFT JOIN papers p ON p.id = bl.paper_id
        WHERE bl.user_id = ?
        ORDER BY bl.id ASC
        """,
        (user_id,),
    ).fetchall()
    conn.close()

    for row in rows:
        metadata = _load_json(row["behavior_metadata"])
        paper = _paper_from_row(row)
        action = str(row["action"] or "")
        action_type = str(row["action_type"] or "")
        if dry_run:
            if action == "pushed":
                counts["pushed"] += 1
            elif action in {"selected", "skipped", "created_report"}:
                counts["feedback"] += 1
            continue
        if action == "pushed":
            daily_ingest.ingest_pushed_paper(
                user_id=user_id,
                push_id=row["push_id"],
                paper=paper,
                category=row["category"],
                metadata={**metadata, "timestamp": row["timestamp"]},
                behavior_log_id=row["behavior_log_id"],
            )
            counts["pushed"] += 1
        elif action in {"selected", "skipped", "created_report"}:
            feedback_ingest.ingest_feedback_event(
                user_id=user_id,
                push_id=row["push_id"],
                paper=paper,
                action=action,
                action_type=action_type,
                category=row["category"],
                metadata=metadata,
                behavior_log_id=row["behavior_log_id"],
            )
            counts["feedback"] += 1
    if not dry_run:
        topic_result = topic_ingest.flush_topics(user_id)
        embed_result = wiki_db.embed_nodes_for_user(user_id, force=False, limit=2000)
        counts["topics"] = topic_result.get("topics", 0)
        counts["embedded"] = embed_result.get("embedded", 0)
    return counts


def backfill_all(*, dry_run: bool = False) -> Dict[str, Any]:
    results = {}
    for user_id in wiki_db.all_user_ids():
        results[user_id] = backfill_user(user_id, dry_run=dry_run)
    return results
