"""SQLite and Markdown mirror storage for PaperFlow Wiki."""

from __future__ import annotations

import importlib
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
from paperflow import roles as role_utils


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WIKI_DIR = PROJECT_ROOT / "data" / "wiki"

db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _wiki_root() -> Path:
    configured = os.environ.get("PAPERFLOW_WIKI_DIR", "").strip()
    if configured:
        root = Path(configured).expanduser()
        if not root.is_absolute():
            root = PROJECT_ROOT / root
        return root
    return DEFAULT_WIKI_DIR


def _json_dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _json_loads(value: Any) -> Dict[str, Any]:
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


def _slug(value: str, *, max_len: int = 96) -> str:
    return role_utils.slug(value, max_len=max_len)


def role_name_for_user_id(user_id: str) -> str:
    return role_utils.role_name_for_user_id(user_id, project_root=PROJECT_ROOT)


def storage_label_for_user_id(user_id: str) -> str:
    return role_utils.storage_label_for_user_id(user_id, project_root=PROJECT_ROOT)


def _node_folder(node_type: str) -> str:
    return {
        "paper": "papers",
        "section": "sections",
        "trajectory": "trajectories",
        "topic": "topics",
    }.get(node_type, "nodes")


def _relative_file_path(user_id: str, node_type: str, node_id: str) -> str:
    return (Path(storage_label_for_user_id(user_id)) / _node_folder(node_type) / f"{_slug(node_id)}.md").as_posix()


def _row_to_node(row: sqlite3.Row) -> Dict[str, Any]:
    node = dict(row)
    node["metadata"] = _json_loads(node.pop("metadata_json", None))
    return node


def _rows_to_nodes(rows: Iterable[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [_row_to_node(row) for row in rows]


def table_exists(table_name: str) -> bool:
    """Return whether a SQLite table exists in the PaperFlow database."""
    conn = db_ops.get_connection()
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    conn.close()
    return row is not None


def _vector_to_blob(vector: List[float]) -> bytes:
    array = np.array(vector or [], dtype=np.float32)
    norm = float(np.linalg.norm(array))
    if norm > 0:
        array = array / norm
    return array.astype(np.float32).tobytes()


def _blob_to_vector(blob: Any) -> np.ndarray:
    if blob is None:
        return np.array([], dtype=np.float32)
    if isinstance(blob, memoryview):
        blob = blob.tobytes()
    array = np.frombuffer(blob, dtype=np.float32)
    norm = float(np.linalg.norm(array))
    if norm > 0:
        array = array / norm
    return array


def _node_embedding_text(node: Dict[str, Any]) -> str:
    return "\n".join(
        part
        for part in (
            str(node.get("title") or ""),
            str(node.get("keywords") or ""),
            str(node.get("body") or "")[:4000],
        )
        if part.strip()
    )


def init_wiki_schema() -> None:
    """Create wiki tables, indexes, and FTS mirrors if needed."""
    conn = db_ops.get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS wiki_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            node_type TEXT NOT NULL
                CHECK (node_type IN ('paper','section','trajectory','topic')),
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            metadata_json TEXT,
            embedding BLOB,
            embedding_model TEXT,
            keywords TEXT,
            file_path TEXT,
            source_type TEXT,
            source_ref TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, node_id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS wiki_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            src_id TEXT NOT NULL,
            dst_id TEXT NOT NULL,
            relation TEXT NOT NULL
                CHECK (relation IN (
                    'cites','same_topic','interested_in','skipped','read',
                    'pinned_must_read','drifted_from','drifted_to',
                    'derived_from','belongs_to','contains_section'
                )),
            weight REAL DEFAULT 1.0,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, src_id, dst_id, relation)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS wiki_citations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            source TEXT NOT NULL
                CHECK (source IN ('reading_report','pdf','behavior_log','profile','external_url')),
            source_id TEXT NOT NULL,
            anchor TEXT,
            excerpt TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, node_id, source, source_id, anchor)
        )
        """
    )

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wiki_nodes_user_type ON wiki_nodes(user_id, node_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wiki_nodes_user_updated ON wiki_nodes(user_id, updated_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wiki_edges_src ON wiki_edges(user_id, src_id, relation)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wiki_edges_dst ON wiki_edges(user_id, dst_id, relation)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wiki_citations_node ON wiki_citations(user_id, node_id)")

    try:
        cursor.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS wiki_nodes_fts USING fts5(
                node_id,
                user_id UNINDEXED,
                title,
                body,
                keywords,
                content='wiki_nodes',
                content_rowid='id',
                tokenize='unicode61 remove_diacritics 1'
            )
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS wiki_nodes_ai AFTER INSERT ON wiki_nodes BEGIN
                INSERT INTO wiki_nodes_fts(rowid, node_id, user_id, title, body, keywords)
                VALUES (new.id, new.node_id, new.user_id, new.title, new.body, new.keywords);
            END
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS wiki_nodes_ad AFTER DELETE ON wiki_nodes BEGIN
                INSERT INTO wiki_nodes_fts(wiki_nodes_fts, rowid, node_id, user_id, title, body, keywords)
                VALUES ('delete', old.id, old.node_id, old.user_id, old.title, old.body, old.keywords);
            END
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER IF NOT EXISTS wiki_nodes_au AFTER UPDATE ON wiki_nodes BEGIN
                INSERT INTO wiki_nodes_fts(wiki_nodes_fts, rowid, node_id, user_id, title, body, keywords)
                VALUES ('delete', old.id, old.node_id, old.user_id, old.title, old.body, old.keywords);
                INSERT INTO wiki_nodes_fts(rowid, node_id, user_id, title, body, keywords)
                VALUES (new.id, new.node_id, new.user_id, new.title, new.body, new.keywords);
            END
            """
        )
    except sqlite3.OperationalError:
        # Some embedded SQLite builds omit FTS5. LIKE fallback search still works.
        pass

    conn.commit()
    conn.close()
    _wiki_root().mkdir(parents=True, exist_ok=True)


def write_node_mirror(node: Dict[str, Any]) -> str:
    """Write a human-readable Markdown mirror for a wiki node."""
    relative_path = node.get("file_path") or _relative_file_path(
        node["user_id"],
        node["node_type"],
        node["node_id"],
    )
    output_path = _wiki_root() / relative_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata = node.get("metadata") or _json_loads(node.get("metadata_json"))
    lines = [
        "---",
        f"node_id: {node['node_id']}",
        f"user_id: {node['user_id']}",
        f"node_type: {node['node_type']}",
        f"updated_at: {node.get('updated_at') or _now()}",
        "---",
        "",
        f"# {node['title']}",
        "",
    ]
    keywords = str(node.get("keywords") or "").strip()
    if keywords:
        lines.extend([f"Keywords: {keywords}", ""])
    if metadata:
        lines.extend(["## Metadata", "", "```json", json.dumps(metadata, ensure_ascii=False, indent=2), "```", ""])
    lines.extend(["## Body", "", str(node.get("body") or "").strip(), ""])
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return relative_path


def upsert_node(
    *,
    user_id: str,
    node_id: str,
    node_type: str,
    title: str,
    body: str,
    metadata: Optional[Dict[str, Any]] = None,
    keywords: Optional[str] = None,
    source_type: Optional[str] = None,
    source_ref: Optional[str] = None,
    file_path: Optional[str] = None,
    write_mirror: bool = True,
) -> Dict[str, Any]:
    """Insert or update a wiki node and optionally refresh its Markdown mirror."""
    init_wiki_schema()
    now = _now()
    relative_path = file_path or _relative_file_path(user_id, node_type, node_id)
    conn = db_ops.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO wiki_nodes
            (node_id, user_id, node_type, title, body, metadata_json,
             keywords, file_path, source_type, source_ref, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, node_id) DO UPDATE SET
            node_type=excluded.node_type,
            title=excluded.title,
            body=excluded.body,
            metadata_json=excluded.metadata_json,
            keywords=excluded.keywords,
            file_path=excluded.file_path,
            source_type=excluded.source_type,
            source_ref=excluded.source_ref,
            updated_at=excluded.updated_at
        """,
        (
            node_id,
            user_id,
            node_type,
            title or node_id,
            body or "",
            _json_dumps(metadata),
            keywords or "",
            relative_path,
            source_type,
            source_ref,
            now,
            now,
        ),
    )
    conn.commit()
    row = cursor.execute(
        "SELECT * FROM wiki_nodes WHERE user_id = ? AND node_id = ?",
        (user_id, node_id),
    ).fetchone()
    conn.close()
    node = _row_to_node(row)
    if write_mirror:
        write_node_mirror(node)
    return node


def embed_nodes_for_user(
    user_id: str,
    node_ids: Optional[List[str]] = None,
    *,
    force: bool = False,
    limit: int = 500,
) -> Dict[str, Any]:
    """Embed wiki nodes with the configured embedding provider."""
    init_wiki_schema()
    from paperflow.providers import build_embedding_provider

    params: List[Any] = [user_id]
    where = "WHERE user_id = ?"
    if node_ids:
        placeholders = ",".join("?" for _ in node_ids)
        where += f" AND node_id IN ({placeholders})"
        params.extend(node_ids)
    if not force:
        where += " AND embedding IS NULL"
    params.append(max(1, int(limit)))

    conn = db_ops.get_connection()
    rows = conn.execute(
        f"""
        SELECT * FROM wiki_nodes
        {where}
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    if not rows:
        conn.close()
        return {"embedded": 0, "model": None}

    nodes = _rows_to_nodes(rows)
    provider = build_embedding_provider()
    texts = [_node_embedding_text(node) for node in nodes]
    vectors = provider.embed_batch(texts)
    model_name = f"{provider.name}:{provider.model}"
    for node, vector in zip(nodes, vectors):
        conn.execute(
            """
            UPDATE wiki_nodes
            SET embedding = ?, embedding_model = ?, updated_at = ?
            WHERE user_id = ? AND node_id = ?
            """,
            (_vector_to_blob(vector), model_name, _now(), user_id, node["node_id"]),
        )
    conn.commit()
    conn.close()
    return {"embedded": len(nodes), "model": model_name}


def upsert_edge(
    *,
    user_id: str,
    src_id: str,
    dst_id: str,
    relation: str,
    weight: float = 1.0,
    metadata: Optional[Dict[str, Any]] = None,
) -> int:
    init_wiki_schema()
    conn = db_ops.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO wiki_edges (user_id, src_id, dst_id, relation, weight, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, src_id, dst_id, relation) DO UPDATE SET
            weight=excluded.weight,
            metadata_json=excluded.metadata_json
        """,
        (user_id, src_id, dst_id, relation, float(weight), _json_dumps(metadata)),
    )
    conn.commit()
    edge_id = int(cursor.lastrowid or 0)
    conn.close()
    return edge_id


def upsert_citation(
    *,
    user_id: str,
    node_id: str,
    source: str,
    source_id: str,
    anchor: Optional[str] = None,
    excerpt: Optional[str] = None,
) -> int:
    init_wiki_schema()
    conn = db_ops.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO wiki_citations (user_id, node_id, source, source_id, anchor, excerpt)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, node_id, source, source_id, anchor) DO UPDATE SET
            excerpt=excluded.excerpt
        """,
        (user_id, node_id, source, source_id, anchor, (excerpt or "")[:500]),
    )
    conn.commit()
    citation_id = int(cursor.lastrowid or 0)
    conn.close()
    return citation_id


def get_citations_for_nodes(user_id: str, node_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    init_wiki_schema()
    if not node_ids:
        return {}
    placeholders = ",".join("?" for _ in node_ids)
    conn = db_ops.get_connection()
    rows = conn.execute(
        f"""
        SELECT * FROM wiki_citations
        WHERE user_id = ? AND node_id IN ({placeholders})
        ORDER BY id ASC
        """,
        (user_id, *node_ids),
    ).fetchall()
    conn.close()
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        item = dict(row)
        grouped.setdefault(item["node_id"], []).append(item)
    return grouped


def list_nodes(user_id: str, node_type: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    init_wiki_schema()
    conn = db_ops.get_connection()
    cursor = conn.cursor()
    params: List[Any] = [user_id]
    where = "WHERE user_id = ?"
    if node_type:
        where += " AND node_type = ?"
        params.append(node_type)
    params.append(max(1, int(limit)))
    rows = cursor.execute(
        f"""
        SELECT * FROM wiki_nodes
        {where}
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    conn.close()
    return _rows_to_nodes(rows)


def get_node(user_id: str, node_id: str) -> Optional[Dict[str, Any]]:
    init_wiki_schema()
    conn = db_ops.get_connection()
    row = conn.execute(
        "SELECT * FROM wiki_nodes WHERE user_id = ? AND node_id = ?",
        (user_id, node_id),
    ).fetchone()
    conn.close()
    return _row_to_node(row) if row else None


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[\w.\-]+", query or "", flags=re.UNICODE)
    return " ".join(token for token in tokens if token)


def _keyword_search_nodes(
    user_id: str,
    query_text: str,
    node_type: Optional[str],
    limit: int,
) -> List[Dict[str, Any]]:
    conn = db_ops.get_connection()
    cursor = conn.cursor()
    params: List[Any] = [_fts_query(query_text), user_id]
    type_filter = ""
    if node_type:
        type_filter = " AND n.node_type = ?"
        params.append(node_type)
    params.append(max(1, int(limit)))
    try:
        rows = cursor.execute(
            f"""
            SELECT n.*, bm25(wiki_nodes_fts) AS search_rank
            FROM wiki_nodes_fts
            JOIN wiki_nodes n ON n.id = wiki_nodes_fts.rowid
            WHERE wiki_nodes_fts MATCH ?
              AND n.user_id = ?
              {type_filter}
            ORDER BY search_rank, n.updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        conn.close()
        nodes = _rows_to_nodes(rows)
        for index, node in enumerate(nodes):
            node["keyword_score"] = 1.0 - (index / max(1, len(nodes)))
        return nodes
    except sqlite3.OperationalError:
        like = f"%{query_text}%"
        params = [user_id, like, like, like]
        type_filter = ""
        if node_type:
            type_filter = " AND node_type = ?"
            params.append(node_type)
        params.append(max(1, int(limit)))
        rows = cursor.execute(
            f"""
            SELECT * FROM wiki_nodes
            WHERE user_id = ?
              AND (title LIKE ? OR body LIKE ? OR keywords LIKE ?)
              {type_filter}
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        conn.close()
        nodes = _rows_to_nodes(rows)
        for index, node in enumerate(nodes):
            node["keyword_score"] = 1.0 - (index / max(1, len(nodes)))
        return nodes


def vector_search_nodes(
    user_id: str,
    query: str,
    node_type: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    init_wiki_schema()
    conn = db_ops.get_connection()
    params: List[Any] = [user_id]
    type_filter = ""
    if node_type:
        type_filter = " AND node_type = ?"
        params.append(node_type)
    rows = conn.execute(
        f"""
        SELECT * FROM wiki_nodes
        WHERE user_id = ?
          AND embedding IS NOT NULL
          {type_filter}
        """,
        params,
    ).fetchall()
    conn.close()
    if not rows:
        return []

    from paperflow.providers import build_embedding_provider

    provider = build_embedding_provider()
    query_vector = np.array(provider.embed(query), dtype=np.float32)
    query_norm = float(np.linalg.norm(query_vector))
    if query_norm > 0:
        query_vector = query_vector / query_norm

    scored: List[Dict[str, Any]] = []
    for row in rows:
        node = _row_to_node(row)
        vector = _blob_to_vector(row["embedding"])
        if vector.size == 0:
            continue
        dim = min(vector.size, query_vector.size)
        if dim <= 0:
            continue
        score = float(np.dot(vector[:dim], query_vector[:dim]))
        node["vector_score"] = score
        scored.append(node)
    scored.sort(key=lambda item: float(item.get("vector_score", 0.0)), reverse=True)
    return scored[: max(1, int(limit))]


def search_nodes(
    user_id: str,
    query: str,
    node_type: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    init_wiki_schema()
    query_text = (query or "").strip()
    if not query_text:
        return list_nodes(user_id, node_type=node_type, limit=limit)

    keyword_hits = _keyword_search_nodes(user_id, query_text, node_type, max(limit, 30))
    try:
        vector_hits = vector_search_nodes(user_id, query_text, node_type=node_type, limit=max(limit, 30))
    except Exception:
        vector_hits = []
    merged: Dict[str, Dict[str, Any]] = {}

    for node in keyword_hits:
        merged[node["node_id"]] = node
    vector_scores = [float(node.get("vector_score", 0.0)) for node in vector_hits]
    vector_min = min(vector_scores) if vector_scores else 0.0
    vector_max = max(vector_scores) if vector_scores else 1.0
    vector_range = max(vector_max - vector_min, 1e-6)
    for node in vector_hits:
        existing = merged.setdefault(node["node_id"], node)
        existing["vector_score"] = float(node.get("vector_score", 0.0))
        existing["vector_score_norm"] = (existing["vector_score"] - vector_min) / vector_range

    for node in merged.values():
        keyword_score = float(node.get("keyword_score", 0.0))
        vector_score = float(node.get("vector_score_norm", 0.0))
        interaction_bonus = _interaction_bonus(user_id, node)
        type_weight = {"section": 1.0, "paper": 0.9, "trajectory": 0.8, "topic": 0.75}.get(
            str(node.get("node_type")),
            0.7,
        )
        node["score"] = (0.45 * keyword_score + 0.55 * vector_score + interaction_bonus) * type_weight

    results = sorted(merged.values(), key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return results[: max(1, int(limit))]


def _interaction_bonus(user_id: str, node: Dict[str, Any]) -> float:
    paper_node = node["node_id"] if node.get("node_type") == "paper" else (node.get("metadata") or {}).get("parent_paper_id")
    if not paper_node:
        return 0.0
    conn = db_ops.get_connection()
    rows = conn.execute(
        """
        SELECT relation, weight
        FROM wiki_edges
        WHERE user_id = ?
          AND src_id = ?
          AND dst_id = ?
          AND relation IN ('interested_in', 'read', 'skipped')
        """,
        (user_id, f"user:{user_id}", paper_node),
    ).fetchall()
    conn.close()
    bonus = 0.0
    for row in rows:
        if row["relation"] == "read":
            bonus += 0.20
        elif row["relation"] == "interested_in":
            bonus += 0.14
        elif row["relation"] == "skipped":
            bonus -= 0.16
    return bonus


def all_user_ids() -> List[str]:
    init_wiki_schema()
    candidate_tables = [table for table in ("profiles", "behavior_logs", "wiki_nodes") if table_exists(table)]
    if not candidate_tables:
        return []
    query = "\nUNION\n".join(f"SELECT user_id FROM {table}" for table in candidate_tables)
    conn = db_ops.get_connection()
    rows = conn.execute(f"{query}\nORDER BY user_id").fetchall()
    conn.close()
    return [str(row["user_id"]) for row in rows if str(row["user_id"] or "").strip()]


def stats(user_id: str) -> Dict[str, Any]:
    init_wiki_schema()
    conn = db_ops.get_connection()
    cursor = conn.cursor()
    node_rows = cursor.execute(
        """
        SELECT node_type, COUNT(*) AS count
        FROM wiki_nodes
        WHERE user_id = ?
        GROUP BY node_type
        """,
        (user_id,),
    ).fetchall()
    edge_count = cursor.execute(
        "SELECT COUNT(*) AS count FROM wiki_edges WHERE user_id = ?",
        (user_id,),
    ).fetchone()["count"]
    citation_count = cursor.execute(
        "SELECT COUNT(*) AS count FROM wiki_citations WHERE user_id = ?",
        (user_id,),
    ).fetchone()["count"]
    latest = cursor.execute(
        "SELECT MAX(updated_at) AS latest FROM wiki_nodes WHERE user_id = ?",
        (user_id,),
    ).fetchone()["latest"]
    conn.close()
    by_type = {row["node_type"]: row["count"] for row in node_rows}
    return {
        "user_id": user_id,
        "nodes": sum(by_type.values()),
        "nodes_by_type": by_type,
        "edges": int(edge_count or 0),
        "citations": int(citation_count or 0),
        "latest_update": latest,
        "wiki_dir": str(_wiki_root()),
    }
