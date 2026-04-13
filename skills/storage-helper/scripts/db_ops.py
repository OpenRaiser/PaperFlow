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


def _build_paper_dict(row: sqlite3.Row, metadata_key: str = "metadata") -> Dict[str, Any]:
    """Convert a joined paper row into a normalized dict."""
    paper = dict(row)
    paper["authors"] = _deserialize_json_list(paper.get("authors"))

    metadata_raw = paper.get(metadata_key)
    metadata = {}
    if metadata_raw:
        try:
            metadata = json.loads(metadata_raw)
        except (json.JSONDecodeError, TypeError):
            metadata = {}

    if metadata_key != "metadata":
        paper.pop(metadata_key, None)

    if metadata:
        paper["metadata"] = metadata
        if "category" in metadata:
            paper["category"] = metadata["category"]
        if "score" in metadata:
            paper["score"] = metadata["score"]
        if "rank" in metadata:
            paper["rank"] = metadata["rank"]

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
        return dict(row)
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
        return dict(row)
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
        return dict(row)
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
