#!/usr/bin/env python3
"""
SciTaste Database Operations

Provides CRUD operations for:
- User profiles
- Papers cache
- Behavior logs
- Task status
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "scitaste.db"


def get_connection() -> sqlite3.Connection:
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_identifier(value: Optional[str]) -> Optional[str]:
    """Normalize identifiers so empty strings do not poison UNIQUE columns."""
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _deserialize_json_list(value: Any) -> List[Any]:
    """Best-effort parse for JSON list fields stored in SQLite."""
    if isinstance(value, list):
        return value
    if not value:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return parsed if isinstance(parsed, list) else [parsed]
    return [value]


def _load_json_metadata(raw: Any) -> Dict[str, Any]:
    """Best-effort parse for JSON object metadata fields stored in SQLite."""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _build_paper_dict(
    row: sqlite3.Row,
    metadata_key: str = "metadata",
    extra_metadata_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Convert a joined paper row into a normalized dict."""
    paper = dict(row)
    paper["authors"] = _deserialize_json_list(paper.get("authors"))
    paper["embedding"] = _deserialize_json_list(paper.get("embedding"))

    metadata: Dict[str, Any] = {}
    for extra_key in extra_metadata_keys or []:
        metadata.update(_load_json_metadata(paper.get(extra_key)))

    metadata.update(_load_json_metadata(paper.get(metadata_key)))

    if metadata_key != "metadata":
        paper.pop(metadata_key, None)
    for extra_key in extra_metadata_keys or []:
        if extra_key != "metadata":
            paper.pop(extra_key, None)

    if metadata:
        paper["metadata"] = metadata
        if "category" in metadata:
            paper["category"] = metadata["category"]
        if "score" in metadata:
            paper["score"] = metadata["score"]
        if "rank" in metadata:
            paper["rank"] = metadata["rank"]
        for key, value in metadata.items():
            if key not in paper or paper.get(key) in (None, "", [], {}):
                paper[key] = value

    for list_key in ("categories", "keywords", "topics"):
        paper[list_key] = _deserialize_json_list(paper.get(list_key))

    return paper


def init_db() -> None:
    """Initialize database, create all tables"""
    conn = get_connection()
    cursor = conn.cursor()

    # Create profiles table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE NOT NULL,
            profile_json TEXT NOT NULL,
            version TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create papers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arxiv_id TEXT UNIQUE,
            doi TEXT,
            title TEXT NOT NULL,
            authors TEXT,
            institution TEXT,
            abstract TEXT,
            venue TEXT,
            publish_date DATE,
            embedding BLOB,
            embedding_model TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            pushed BOOLEAN DEFAULT FALSE,
            push_date DATE
        )
    """)

    # Create behavior_logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS behavior_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            push_id TEXT NOT NULL,
            paper_id INTEGER,
            action TEXT NOT NULL,
            action_type TEXT NOT NULL,
            category TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT,
            FOREIGN KEY (paper_id) REFERENCES papers(id)
        )
    """)

    # Create task_status table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT UNIQUE NOT NULL,
            task_type TEXT NOT NULL,
            user_id TEXT,
            status TEXT NOT NULL,
            progress_json TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            error_message TEXT
        )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_arxiv ON papers(arxiv_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_papers_pushed ON papers(pushed) WHERE pushed = FALSE")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_behavior_user ON behavior_logs(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_behavior_push ON behavior_logs(push_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_behavior_timestamp ON behavior_logs(timestamp)")

    conn.commit()
    conn.close()
    print("Database tables created successfully.")


# ============== Profile Operations ==============

def create_profile(user_id: str, profile_json: Dict) -> Optional[int]:
    """Create a new user profile"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO profiles (user_id, profile_json, version)
            VALUES (?, ?, ?)
        """, (user_id, json.dumps(profile_json), profile_json.get("version", "0.1")))
        conn.commit()
        profile_id = cursor.lastrowid
        print(f"Profile created with id: {profile_id}")
        return profile_id
    except sqlite3.IntegrityError:
        print(f"Profile already exists for user: {user_id}")
        return None
    finally:
        conn.close()


def save_paper(
    arxiv_id: str,
    doi: str = None,
    title: str = "",
    authors: List[str] = None,
    abstract: str = "",
    categories: List[str] = None,
    source: str = "arxiv",
    institution: str = None,
    venue: str = None,
    publish_date: str = None,
    embedding: List[float] = None,
    embedding_model: str = None,
) -> int:
    """
    Save a paper to database

    Returns:
        Paper ID (existing or new)
    """
    conn = get_connection()
    cursor = conn.cursor()

    normalized_arxiv_id = _normalize_identifier(arxiv_id)
    normalized_doi = _normalize_identifier(doi)
    normalized_title = (title or "").strip()

    # 检查是否已存在（优先使用 arxiv_id）
    if normalized_arxiv_id:
        cursor.execute("SELECT id FROM papers WHERE arxiv_id = ?", (normalized_arxiv_id,))
        row = cursor.fetchone()
        if row:
            conn.close()
            return row['id']

    # 如果 arxiv_id 为空，使用 doi 检查
    if normalized_doi:
        cursor.execute("SELECT id FROM papers WHERE doi = ?", (normalized_doi,))
        row = cursor.fetchone()
        if row:
            conn.close()
            return row['id']

    # 如果 arxiv_id 和 doi 都为空，使用 title 检查（避免完全重复）
    if normalized_title:
        cursor.execute("SELECT id FROM papers WHERE title = ?", (normalized_title,))
        row = cursor.fetchone()
        if row:
            conn.close()
            return row['id']

    try:
        # 插入新论文
        cursor.execute("""
            INSERT INTO papers (
                arxiv_id, doi, title, authors, institution, abstract,
                venue, publish_date, embedding, embedding_model, fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            normalized_arxiv_id,
            normalized_doi,
            normalized_title,
            json.dumps(authors or []),
            _normalize_identifier(institution),
            abstract or "",
            _normalize_identifier(venue) or _normalize_identifier(source),
            _normalize_identifier(publish_date),
            json.dumps(embedding) if embedding else None,
            _normalize_identifier(embedding_model) or "hash:hash:768",
            datetime.now()
        ))
        conn.commit()
        paper_id = cursor.lastrowid
        return paper_id
    except sqlite3.IntegrityError:
        # 数据库里可能已有同一论文，回退到查找现有记录。
        lookup_sql = None
        lookup_value = None
        if normalized_arxiv_id:
            lookup_sql = "SELECT id FROM papers WHERE arxiv_id = ?"
            lookup_value = normalized_arxiv_id
        elif normalized_doi:
            lookup_sql = "SELECT id FROM papers WHERE doi = ?"
            lookup_value = normalized_doi
        elif normalized_title:
            lookup_sql = "SELECT id FROM papers WHERE title = ?"
            lookup_value = normalized_title

        if lookup_sql and lookup_value is not None:
            cursor.execute(lookup_sql, (lookup_value,))
            row = cursor.fetchone()
            if row:
                return row["id"]
        raise
    finally:
        conn.close()


def get_profile(user_id: str) -> Optional[Dict]:
    """Get user profile by user_id"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT profile_json FROM profiles WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return json.loads(row["profile_json"])
    return None


def get_paper_by_arxiv_id(arxiv_id: str) -> Optional[Dict]:
    """Get paper by arxiv_id"""
    normalized_arxiv_id = _normalize_identifier(arxiv_id)
    if not normalized_arxiv_id:
        return None
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM papers WHERE arxiv_id = ?
    """, (normalized_arxiv_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return _build_paper_dict(row)
    return None


def update_profile(user_id: str, profile_json: Dict) -> bool:
    """Update user profile"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE profiles
        SET profile_json = ?, version = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    """, (json.dumps(profile_json), profile_json.get("version", "0.1"), user_id))
    conn.commit()
    conn.close()
    return True


def get_profile_history(user_id: str, days: int = 7) -> List[Dict]:
    """Get profile history for the past N days"""
    conn = get_connection()
    cursor = conn.cursor()
    since_date = datetime.now() - timedelta(days=days)
    cursor.execute("""
        SELECT profile_json, updated_at FROM profiles
        WHERE user_id = ? AND updated_at >= ?
        ORDER BY updated_at DESC
    """, (user_id, since_date.isoformat()))
    rows = cursor.fetchall()
    conn.close()
    return [json.loads(row["profile_json"]) for row in rows]


# ============== Paper Operations ==============

def add_paper(paper_data: Dict) -> Optional[int]:
    """Add a paper to the database"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO papers
            (arxiv_id, doi, title, authors, institution, abstract, venue,
             publish_date, embedding, embedding_model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paper_data.get("arxiv_id"),
            paper_data.get("doi"),
            paper_data.get("title"),
            json.dumps(paper_data.get("authors", [])),
            paper_data.get("institution"),
            paper_data.get("abstract"),
            paper_data.get("venue"),
            paper_data.get("publish_date"),
            json.dumps(paper_data.get("embedding", [])) if paper_data.get("embedding") else None,
            paper_data.get("embedding_model", "text-embedding-3-small")
        ))
        conn.commit()
        paper_id = cursor.lastrowid
        return paper_id
    except sqlite3.IntegrityError:
        print(f"Paper already exists: {paper_data.get('arxiv_id')}")
        return None
    finally:
        conn.close()


def add_papers_batch(papers_list: List[Dict]) -> int:
    """Add multiple papers in a batch"""
    count = 0
    for paper in papers_list:
        result = add_paper(paper)
        if result:
            count += 1
    return count


def get_paper_by_arxiv(arxiv_id: str) -> Optional[Dict]:
    """Get paper by arxiv_id"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM papers WHERE arxiv_id = ?
    """, (arxiv_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return _build_paper_dict(row)
    return None


def get_paper_by_doi(doi: str) -> Optional[Dict]:
    """Get paper by doi"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM papers WHERE doi = ?
    """, (doi,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return _build_paper_dict(row)
    return None


def get_unpushed_papers(limit: int = 100) -> List[Dict]:
    """Get papers that haven't been pushed yet"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM papers WHERE pushed = FALSE
        ORDER BY fetched_at DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_pushed(paper_ids: List[int]) -> int:
    """Mark papers as pushed"""
    conn = get_connection()
    cursor = conn.cursor()
    push_date = datetime.now().date().isoformat()
    cursor.executemany("""
        UPDATE papers
        SET pushed = TRUE, push_date = ?
        WHERE id = ?
    """, [(push_date, paper_id) for paper_id in paper_ids])
    conn.commit()
    count = cursor.rowcount
    conn.close()
    return count


# ============== Behavior Log Operations ==============

def log_behavior(
    user_id: str,
    push_id: str,
    paper_id: Optional[int],
    action: str,
    action_type: str,
    category: str = "",
    metadata: Optional[Dict] = None
) -> int:
    """Log user behavior"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO behavior_logs
        (user_id, push_id, paper_id, action, action_type, category, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, push_id, paper_id, action, action_type, category,
          json.dumps(metadata) if metadata else None))
    conn.commit()
    log_id = cursor.lastrowid
    conn.close()
    return log_id


def _build_created_report_record(row: sqlite3.Row, metadata: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Normalize a created_report behavior row into a reusable document record."""
    parsed_metadata = metadata or _load_json_metadata(row["metadata"])
    doc_url = _normalize_identifier(parsed_metadata.get("doc_url") or parsed_metadata.get("url"))
    doc_token = _normalize_identifier(parsed_metadata.get("doc_token"))

    if not doc_url and not doc_token:
        return None

    paper_title = _normalize_identifier(
        row["paper_title"]
        if "paper_title" in row.keys()
        else parsed_metadata.get("paper_title")
    )
    doc_title = _normalize_identifier(parsed_metadata.get("doc_title"))

    return {
        "paper_id": row["paper_id"] if "paper_id" in row.keys() else None,
        "timestamp": row["timestamp"],
        "paper_title": paper_title,
        "doc_title": doc_title or (f"[精读] {paper_title}" if paper_title else None),
        "doc_url": doc_url,
        "doc_token": doc_token,
        "metadata": parsed_metadata,
    }


def get_existing_reading_reports_for_papers(user_id: str, paper_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """
    Return the latest created reading-report document for each paper_id.

    Args:
        user_id: User ID
        paper_ids: Paper IDs to look up

    Returns:
        Mapping: paper_id -> report record
    """
    normalized_paper_ids: List[int] = []
    for paper_id in paper_ids or []:
        try:
            normalized_paper_ids.append(int(paper_id))
        except (TypeError, ValueError):
            continue

    normalized_paper_ids = list(dict.fromkeys(normalized_paper_ids))
    if not normalized_paper_ids:
        return {}

    placeholders = ",".join("?" for _ in normalized_paper_ids)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT bl.paper_id, bl.timestamp, bl.metadata, p.title AS paper_title
        FROM behavior_logs bl
        LEFT JOIN papers p ON p.id = bl.paper_id
        WHERE bl.user_id = ?
          AND bl.action = 'created_report'
          AND bl.action_type = 'reading'
          AND bl.paper_id IN ({placeholders})
        ORDER BY bl.timestamp DESC, bl.id DESC
        """,
        (user_id, *normalized_paper_ids),
    )
    rows = cursor.fetchall()
    conn.close()

    results: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        paper_id = int(row["paper_id"])
        if paper_id in results:
            continue
        record = _build_created_report_record(row)
        if record:
            results[paper_id] = record

    return results


def get_recent_created_report_by_source(
    user_id: str,
    source_type: str,
    source_key: str,
    days: int = 30,
) -> Optional[Dict[str, Any]]:
    """
    Find the latest created reading-report document for a source descriptor.

    Source metadata is stored in behavior_logs.metadata under:
    - report_source_type
    - report_source_key
    """
    normalized_source_type = _normalize_identifier(source_type)
    normalized_source_key = _normalize_identifier(source_key)
    if not normalized_source_type or not normalized_source_key:
        return None

    since_date = (datetime.now() - timedelta(days=max(1, int(days)))).isoformat(sep=" ")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT bl.paper_id, bl.timestamp, bl.metadata, p.title AS paper_title
        FROM behavior_logs bl
        LEFT JOIN papers p ON p.id = bl.paper_id
        WHERE bl.user_id = ?
          AND bl.action = 'created_report'
          AND bl.action_type = 'reading'
          AND bl.timestamp >= ?
        ORDER BY bl.timestamp DESC, bl.id DESC
        """,
        (user_id, since_date),
    )
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        metadata = _load_json_metadata(row["metadata"])
        if _normalize_identifier(metadata.get("report_source_type")) != normalized_source_type:
            continue
        if _normalize_identifier(metadata.get("report_source_key")) != normalized_source_key:
            continue
        record = _build_created_report_record(row, metadata=metadata)
        if record:
            return record

    return None


def get_recent_created_report(
    user_id: str,
    *,
    minutes: int = 180,
) -> Optional[Dict[str, Any]]:
    """
    Return the latest created reading report for a user.
    """
    since_timestamp = (datetime.now() - timedelta(minutes=max(1, int(minutes)))).isoformat(sep=" ")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT bl.paper_id, bl.timestamp, bl.metadata, p.title AS paper_title
        FROM behavior_logs bl
        LEFT JOIN papers p ON p.id = bl.paper_id
        WHERE bl.user_id = ?
          AND bl.action = 'created_report'
          AND bl.action_type = 'reading'
          AND bl.timestamp >= ?
        ORDER BY bl.timestamp DESC, bl.id DESC
        LIMIT 1
        """,
        (user_id, since_timestamp),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return _build_created_report_record(row)


def get_pending_doc_open_for_dwell(
    user_id: str,
    *,
    within_minutes: int = 240,
) -> Optional[Dict[str, Any]]:
    """
    Return the latest tracked doc-open event that has not yet produced a dwell proxy.
    """
    since_timestamp = (datetime.now() - timedelta(minutes=max(1, int(within_minutes)))).isoformat(sep=" ")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, user_id, push_id, paper_id, action, action_type, category, timestamp, metadata
        FROM behavior_logs
        WHERE user_id = ?
          AND action = 'opened_report'
          AND action_type = 'doc_open'
          AND timestamp >= ?
        ORDER BY timestamp DESC, id DESC
        LIMIT 20
        """,
        (user_id, since_timestamp),
    )
    open_rows = cursor.fetchall()
    if not open_rows:
        conn.close()
        return None

    for row in open_rows:
        metadata = _load_json_metadata(row["metadata"])
        doc_token = _normalize_identifier(metadata.get("doc_token"))
        doc_url = _normalize_identifier(metadata.get("doc_url"))
        already_consumed = False
        cursor.execute(
            """
            SELECT metadata
            FROM behavior_logs
            WHERE user_id = ?
              AND action = 'doc_dwell_proxy'
              AND action_type = 'doc_engagement'
              AND timestamp >= ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 20
            """,
            (user_id, row["timestamp"]),
        )
        for dwell_row in cursor.fetchall():
            dwell_metadata = _load_json_metadata(dwell_row["metadata"])
            if doc_token and _normalize_identifier(dwell_metadata.get("doc_token")) == doc_token:
                already_consumed = True
                break
            if doc_url and _normalize_identifier(dwell_metadata.get("doc_url")) == doc_url:
                already_consumed = True
                break
        if already_consumed:
            continue
        conn.close()
        record = dict(row)
        record["metadata"] = metadata
        return record

    conn.close()
    return None


def get_doc_engagement_stats(user_id: str, days: int = 7) -> Dict[str, Any]:
    """
    Aggregate lightweight doc engagement proxies.
    """
    since_timestamp = (datetime.now() - timedelta(days=max(1, int(days)))).isoformat(sep=" ")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT action, action_type, metadata, timestamp
        FROM behavior_logs
        WHERE user_id = ?
          AND timestamp >= ?
          AND (
            (action = 'opened_report' AND action_type = 'doc_open')
            OR (action = 'doc_dwell_proxy' AND action_type = 'doc_engagement')
          )
        ORDER BY timestamp ASC, id ASC
        """,
        (user_id, since_timestamp),
    )
    rows = cursor.fetchall()
    conn.close()

    unique_docs = set()
    total_opens = 0
    dwell_values: List[float] = []
    for row in rows:
        metadata = _load_json_metadata(row["metadata"])
        doc_key = _normalize_identifier(metadata.get("doc_token")) or _normalize_identifier(metadata.get("doc_url"))
        if row["action"] == "opened_report":
            total_opens += 1
            if doc_key:
                unique_docs.add(doc_key)
        elif row["action"] == "doc_dwell_proxy":
            try:
                dwell_seconds = float(metadata.get("dwell_seconds") or 0.0)
            except (TypeError, ValueError):
                dwell_seconds = 0.0
            if dwell_seconds > 0:
                dwell_values.append(dwell_seconds)

    average_dwell_seconds = round(sum(dwell_values) / len(dwell_values), 2) if dwell_values else 0.0
    return {
        "total_doc_opens": total_opens,
        "unique_doc_opens": len(unique_docs),
        "avg_dwell_proxy_seconds": average_dwell_seconds,
        "dwell_proxy_count": len(dwell_values),
    }


def get_behavior_logs(user_id: str, start_date: str, end_date: str) -> List[Dict]:
    """Get behavior logs for a date range"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM behavior_logs
        WHERE user_id = ? AND date(timestamp) BETWEEN ? AND ?
        ORDER BY timestamp ASC
    """, (user_id, start_date, end_date))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_selection_stats(user_id: str, days: int = 7) -> Dict:
    """Get selection statistics for the past N days"""
    conn = get_connection()
    cursor = conn.cursor()
    since_date = (datetime.now() - timedelta(days=days)).date().isoformat()
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN action_type = 'selected' THEN 1 ELSE 0 END) as selected,
            SUM(CASE WHEN action_type = 'skipped' THEN 1 ELSE 0 END) as skipped
        FROM behavior_logs
        WHERE user_id = ? AND date(timestamp) >= ?
    """, (user_id, since_date))
    row = cursor.fetchone()
    conn.close()

    total = row["total"] or 0
    selected = row["selected"] or 0
    skipped = row["skipped"] or 0

    return {
        "total": total,
        "selected": selected,
        "skipped": skipped,
        "selection_rate": selected / total if total > 0 else 0.0
    }


def get_selection_stats_by_category(user_id: str, days: int = 7) -> Dict[str, Dict]:
    """Get selection statistics broken down by category (🔴🟡🔵) for the past N days"""
    conn = get_connection()
    cursor = conn.cursor()
    since_date = (datetime.now() - timedelta(days=days)).date().isoformat()

    cursor.execute("""
        SELECT
            category,
            COUNT(*) as total,
            SUM(CASE WHEN action_type = 'selected' THEN 1 ELSE 0 END) as selected,
            SUM(CASE WHEN action_type = 'skipped' THEN 1 ELSE 0 END) as skipped
        FROM behavior_logs
        WHERE user_id = ? AND date(timestamp) >= ? AND category != ''
        GROUP BY category
    """, (user_id, since_date))

    rows = cursor.fetchall()
    conn.close()

    stats = {}
    for row in rows:
        category = row["category"] or "unknown"
        total = row["total"] or 0
        selected = row["selected"] or 0
        skipped = row["skipped"] or 0

        stats[category] = {
            "total": total,
            "selected": selected,
            "skipped": skipped,
            "selection_rate": selected / total if total > 0 else 0.0
        }

    return stats


def get_profile_snapshot(user_id: str, days_ago: int) -> Optional[Dict]:
    """Get user profile snapshot from N days ago"""
    conn = get_connection()
    cursor = conn.cursor()

    target_date = datetime.now() - timedelta(days=days_ago)
    target_date_str = target_date.date().isoformat()

    cursor.execute("""
        SELECT profile_json, updated_at FROM profiles
        WHERE user_id = ? AND date(updated_at) <= ?
        ORDER BY updated_at DESC
        LIMIT 1
    """, (user_id, target_date_str))

    row = cursor.fetchone()
    conn.close()

    if row:
        return json.loads(row["profile_json"])
    return None


def get_direction_changes(user_id: str, days: int = 7) -> List[Dict]:
    """
    Get direction weight changes compared to previous period

    Args:
        user_id: User ID
        days: Days to look back

    Returns:
        List of direction changes with delta information
    """
    current_profile = get_profile(user_id)
    previous_profile = get_profile_snapshot(user_id, days)

    if not current_profile or not previous_profile:
        return []

    current_directions = current_profile.get("core_directions", {})
    previous_directions = previous_profile.get("core_directions", {})

    changes = []
    all_directions = set(current_directions.keys()) | set(previous_directions.keys())

    for direction in all_directions:
        current_weight = current_directions.get(direction, 0.0)
        previous_weight = previous_directions.get(direction, 0.0)
        delta = current_weight - previous_weight

        changes.append({
            "direction": direction,
            "current_weight": current_weight,
            "previous_weight": previous_weight,
            "delta": delta,
            "trend": "up" if delta > 0.001 else ("down" if delta < -0.001 else "stable")
        })

    changes.sort(key=lambda x: abs(x["delta"]), reverse=True)
    return changes


# ============== Recent Push Operations ==============

def get_recent_pushes(user_id: str, limit: int = 50) -> List[Dict]:
    """
    Get recently pushed papers for a user

    Args:
        user_id: User ID
        limit: Maximum number of papers to return

    Returns:
        List of papers with push information
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get papers pushed in the last 7 days
    since_date = (datetime.now() - timedelta(days=7)).date().isoformat()

    cursor.execute("""
        SELECT p.*, bl.push_id, bl.timestamp as pushed_at, bl.metadata
        FROM papers p
        JOIN behavior_logs bl ON p.id = bl.paper_id
        WHERE bl.user_id = ?
          AND bl.action = 'pushed'
          AND date(bl.timestamp) >= ?
        ORDER BY bl.timestamp DESC
        LIMIT ?
    """, (user_id, since_date, limit))

    rows = cursor.fetchall()
    conn.close()

    return [_build_paper_dict(row) for row in rows]


def get_latest_push(user_id: str) -> Optional[Dict]:
    """
    Get the latest push information for a user

    Args:
        user_id: User ID

    Returns:
        Push information with papers list
    """
    import json
    conn = get_connection()
    cursor = conn.cursor()

    # Get the latest real push_id from behavior logs
    cursor.execute("""
        SELECT push_id, MAX(timestamp) as timestamp
        FROM behavior_logs
        WHERE user_id = ?
          AND action = 'pushed'
        GROUP BY push_id
        ORDER BY timestamp DESC, push_id DESC
        LIMIT 1
    """, (user_id,))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    push_id = row['push_id']
    push_time = row['timestamp']

    # Get all papers in this push with their category and rank from metadata.
    cursor.execute("""
        SELECT p.*, bl.id as behavior_log_id, bl.metadata as bl_metadata FROM papers p
        JOIN behavior_logs bl ON p.id = bl.paper_id
        WHERE bl.user_id = ? AND bl.push_id = ? AND bl.action = 'pushed'
        ORDER BY bl.id ASC
    """, (user_id, push_id))

    papers = [_build_paper_dict(row, metadata_key="bl_metadata") for row in cursor.fetchall()]
    papers.sort(key=lambda paper: (paper.get("rank", 10**9), paper.get("behavior_log_id", 10**9)))

    conn.close()

    return {
        "push_id": push_id,
        "push_time": push_time,
        "papers": papers
    }


def _get_latest_selection_clear_log_id(cursor: sqlite3.Cursor, user_id: str) -> Optional[int]:
    """Return the latest marker that clears the pending reading queue."""
    cursor.execute(
        """
        SELECT MAX(id) AS clear_id
        FROM behavior_logs
        WHERE user_id = ?
          AND action = 'selection_cleared'
          AND action_type = 'selection_queue'
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    clear_id = row["clear_id"]
    return int(clear_id) if clear_id is not None else None


def get_latest_selected_papers(user_id: str) -> Optional[Dict]:
    """
    Get the latest selected-paper batch for a user.

    Returns:
        Dict with push_id / selection_time / papers, or None when no selection exists.
    """
    conn = get_connection()
    cursor = conn.cursor()

    clear_after_log_id = _get_latest_selection_clear_log_id(cursor, user_id)
    latest_batch_sql = """
        SELECT push_id, MAX(timestamp) AS timestamp
        FROM behavior_logs
        WHERE user_id = ?
          AND action = 'selected'
    """
    latest_batch_params: List[Any] = [user_id]
    if clear_after_log_id is not None:
        latest_batch_sql += " AND id > ?"
        latest_batch_params.append(clear_after_log_id)
    latest_batch_sql += """
        GROUP BY push_id
        ORDER BY timestamp DESC, push_id DESC
        LIMIT 1
    """
    cursor.execute(latest_batch_sql, latest_batch_params)

    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    push_id = row["push_id"]
    selection_time = row["timestamp"]

    cursor.execute(
        """
        SELECT p.*, bl.id AS behavior_log_id, bl.metadata AS bl_metadata,
               push_bl.metadata AS push_metadata
        FROM papers p
        JOIN behavior_logs bl ON p.id = bl.paper_id
        LEFT JOIN behavior_logs push_bl
          ON push_bl.user_id = bl.user_id
         AND push_bl.push_id = bl.push_id
         AND push_bl.paper_id = bl.paper_id
         AND push_bl.action = 'pushed'
        WHERE bl.user_id = ?
          AND bl.push_id = ?
          AND bl.action = 'selected'
        ORDER BY bl.id ASC
        """,
        (user_id, push_id),
    )

    papers = [
        _build_paper_dict(
            row,
            metadata_key="bl_metadata",
            extra_metadata_keys=["push_metadata"],
        )
        for row in cursor.fetchall()
    ]
    papers.sort(
        key=lambda paper: (
            paper.get("paper_number", paper.get("rank", 10**9)),
            paper.get("behavior_log_id", 10**9),
        )
    )

    conn.close()

    if not papers:
        return None

    return {
        "push_id": push_id,
        "selection_time": selection_time,
        "papers": papers,
    }


def clear_pending_selected_papers(user_id: str) -> Dict[str, Any]:
    """
    Clear the current pending reading queue without deleting selection history.

    This inserts a queue-clear marker so historical selections remain available
    for analytics and profile learning, while future `get_latest_selected_papers`
    calls only consider selections made after the clear action.
    """
    pending = get_latest_selected_papers(user_id)
    if not pending:
        return {
            "cleared": False,
            "cleared_count": 0,
            "push_id": None,
            "selection_time": None,
            "papers": [],
        }

    papers = list(pending.get("papers") or [])
    metadata = {
        "cleared_push_id": pending.get("push_id"),
        "selection_time": pending.get("selection_time"),
        "cleared_count": len(papers),
        "paper_ids": [paper.get("id") for paper in papers if paper.get("id") is not None],
        "paper_titles": [str(paper.get("title")).strip() for paper in papers if str(paper.get("title")).strip()],
    }
    log_behavior(
        user_id=user_id,
        push_id=str(pending.get("push_id") or "selection_queue"),
        paper_id=None,
        action="selection_cleared",
        action_type="selection_queue",
        category="reading_queue",
        metadata=metadata,
    )
    return {
        "cleared": True,
        "cleared_count": len(papers),
        "push_id": pending.get("push_id"),
        "selection_time": pending.get("selection_time"),
        "papers": papers,
    }


def get_recent_selected_papers(
    user_id: str,
    limit: int = 30,
    days: int = 60,
    before_timestamp: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Return recent selected papers with paper data and selected timestamp.

    Args:
        user_id: User ID
        limit: Max number of selected papers to fetch
        days: Max lookback window in days
        before_timestamp: Optional upper-bound timestamp (exclusive)

    Returns:
        Most recent selected papers ordered from old to new.
    """
    normalized_limit = max(1, int(limit))
    normalized_days = max(1, int(days))
    since_timestamp = (datetime.now() - timedelta(days=normalized_days)).isoformat(sep=" ")

    conn = get_connection()
    cursor = conn.cursor()

    sql = """
        SELECT p.*,
               bl.id AS behavior_log_id,
               bl.timestamp AS selected_at,
               bl.metadata AS selected_metadata,
               push_bl.metadata AS push_metadata
        FROM behavior_logs bl
        JOIN papers p ON p.id = bl.paper_id
        LEFT JOIN behavior_logs push_bl
          ON push_bl.user_id = bl.user_id
         AND push_bl.push_id = bl.push_id
         AND push_bl.paper_id = bl.paper_id
         AND push_bl.action = 'pushed'
        WHERE bl.user_id = ?
          AND bl.action = 'selected'
          AND bl.action_type = 'selected'
          AND bl.timestamp >= ?
    """
    params: List[Any] = [user_id, since_timestamp]

    if before_timestamp:
        sql += " AND bl.timestamp < ?"
        params.append(before_timestamp)

    sql += """
        ORDER BY bl.timestamp DESC, bl.id DESC
        LIMIT ?
    """
    params.append(normalized_limit)

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    papers = [
        _build_paper_dict(
            row,
            metadata_key="selected_metadata",
            extra_metadata_keys=["push_metadata"],
        )
        for row in rows
    ]
    for paper in papers:
        paper["selected_at"] = paper.get("selected_at")

    papers.reverse()
    return papers


def get_recent_drift_updates(user_id: str, days: int = 7) -> List[Dict[str, Any]]:
    """
    Return recent drift-update behavior logs for a user.

    Args:
        user_id: User ID
        days: Lookback days

    Returns:
        Parsed drift update records ordered from old to new.
    """
    since_timestamp = (datetime.now() - timedelta(days=max(1, int(days)))).isoformat(sep=" ")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, user_id, push_id, paper_id, action, action_type, category, timestamp, metadata
        FROM behavior_logs
        WHERE user_id = ?
          AND action = 'profile_updated'
          AND action_type = 'drift_update'
          AND timestamp >= ?
        ORDER BY timestamp ASC, id ASC
        """,
        (user_id, since_timestamp),
    )
    rows = cursor.fetchall()
    conn.close()

    results: List[Dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        metadata = _load_json_metadata(record.get("metadata"))
        record["metadata"] = metadata
        if "drift_status" in metadata:
            record["drift_status"] = metadata.get("drift_status")
        if "drift_score" in metadata:
            record["drift_score"] = metadata.get("drift_score")
        if "adaptive_alpha" in metadata:
            record["adaptive_alpha"] = metadata.get("adaptive_alpha")
        if "top_shift_topics" in metadata:
            record["top_shift_topics"] = metadata.get("top_shift_topics")
        if "explanation" in metadata:
            record["explanation"] = metadata.get("explanation")
        results.append(record)

    return results


def get_recent_reading_signal(
    user_id: str,
    minutes: int = 30,
    *,
    source_prefix: str = "feishu_",
) -> Optional[Dict[str, Any]]:
    """
    Return the latest reading-signal profile update for a user.

    This is used to reinforce the most recent direct-upload PDF topics when the
    user follows up with a generic phrase like "这类我最近想多看".
    """
    since_timestamp = (datetime.now() - timedelta(minutes=max(1, int(minutes)))).isoformat(sep=" ")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, user_id, push_id, paper_id, action, action_type, category, timestamp, metadata
        FROM behavior_logs
        WHERE user_id = ?
          AND action = 'profile_updated'
          AND action_type = 'reading_signal'
          AND timestamp >= ?
        ORDER BY timestamp DESC, id DESC
        LIMIT 20
        """,
        (user_id, since_timestamp),
    )
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        record = dict(row)
        metadata = _load_json_metadata(record.get("metadata"))
        source_type = _normalize_identifier(metadata.get("source_type") or metadata.get("report_source_type"))
        if source_prefix and (not source_type or not source_type.startswith(source_prefix)):
            continue

        topics = _deserialize_json_list(metadata.get("signal_topics") or metadata.get("topics"))
        activated_topics = _deserialize_json_list(metadata.get("activated_topics"))
        if not topics:
            continue

        record["metadata"] = metadata
        record["topics"] = topics
        record["activated_topics"] = activated_topics
        record["source_type"] = source_type
        record["source_key"] = _normalize_identifier(metadata.get("source_key") or metadata.get("report_source_key"))
        record["signal_strength"] = str(metadata.get("signal_strength") or metadata.get("strength") or "").strip()
        return record

    return None


def get_push_papers(push_id: str) -> Optional[Dict]:
    """
    Get all papers for a specific push ID

    Args:
        push_id: Push ID

    Returns:
        Push information with papers list
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get push time
    cursor.execute("""
        SELECT DISTINCT push_id, timestamp
        FROM behavior_logs
        WHERE push_id = ?
        ORDER BY timestamp ASC
        LIMIT 1
    """, (push_id,))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    push_time = row['timestamp']

    # Get all papers in this push with metadata.
    cursor.execute("""
        SELECT p.*, bl.id as behavior_log_id, bl.metadata
        FROM papers p
        JOIN behavior_logs bl ON p.id = bl.paper_id
        WHERE bl.push_id = ? AND bl.action = 'pushed'
        ORDER BY bl.id ASC
    """, (push_id,))

    papers = [_build_paper_dict(row) for row in cursor.fetchall()]
    papers.sort(key=lambda paper: (paper.get("rank", 10**9), paper.get("behavior_log_id", 10**9)))

    conn.close()

    return {
        "push_id": push_id,
        "push_time": push_time,
        "papers": papers
    }


# ============== Task Status Operations ==============

def create_task(task_id: str, task_type: str, user_id: Optional[str] = None) -> int:
    """Create a new task record"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO task_status
        (task_id, task_type, user_id, status, started_at)
        VALUES (?, ?, ?, 'running', CURRENT_TIMESTAMP)
    """, (task_id, task_type, user_id))
    conn.commit()
    conn.close()
    return cursor.lastrowid


def update_task_status(
    task_id: str,
    status: str,
    progress_json: Optional[Dict] = None
) -> bool:
    """Update task status"""
    conn = get_connection()
    cursor = conn.cursor()

    if status in ("completed", "failed"):
        cursor.execute("""
            UPDATE task_status
            SET status = ?, progress_json = ?, completed_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
        """, (status, json.dumps(progress_json) if progress_json else None, task_id))
    else:
        cursor.execute("""
            UPDATE task_status
            SET status = ?, progress_json = ?
            WHERE task_id = ?
        """, (status, json.dumps(progress_json) if progress_json else None, task_id))

    conn.commit()
    conn.close()
    return True


def get_task(task_id: str) -> Optional[Dict]:
    """Get task by task_id"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM task_status WHERE task_id = ?
    """, (task_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_user_tasks(user_id: str, days: int = 7) -> List[Dict]:
    """Get user tasks for the past N days"""
    conn = get_connection()
    cursor = conn.cursor()
    since_date = (datetime.now() - timedelta(days=days)).isoformat()
    cursor.execute("""
        SELECT * FROM task_status
        WHERE user_id = ? AND started_at >= ?
        ORDER BY started_at DESC
    """, (user_id, since_date))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "init":
            init_db()
        elif command == "create_profile":
            if len(sys.argv) < 3:
                print("Usage: python db_ops.py create_profile <user_id>")
                sys.exit(1)
            user_id = sys.argv[2]
            profile = {
                "user_id": user_id,
                "version": "0.1",
                "core_directions": {},
                "methodology_preferences": {},
                "must_read": {"authors": [], "institutions": [], "keywords": []},
                "topic_weights": {},
                "author_heat": {},
                "institution_heat": {},
                "interest_vector": [],
                "taste_profile": {}
            }
            create_profile(user_id, profile)
        elif command == "get_profile":
            if len(sys.argv) < 3:
                print("Usage: python db_ops.py get_profile <user_id>")
                sys.exit(1)
            user_id = sys.argv[2]
            profile = get_profile(user_id)
            if profile:
                print(json.dumps(profile, indent=2))
            else:
                print(f"No profile found for user: {user_id}")
        else:
            print(f"Unknown command: {command}")
            print("Usage: python db_ops.py [init|create_profile|get_profile]")
    else:
        init_db()
