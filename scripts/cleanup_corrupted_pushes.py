#!/usr/bin/env python3
"""
Clean corrupted push batches from the SciTaste SQLite database.

Current corruption signature:
- a push contains multiple `pushed` logs
- but every pushed row points to the same `paper_id`

This script backs up the database first, then deletes the matching
behavior_logs rows for the selected user(s).
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "scitaste.db"
BACKUP_DIR = PROJECT_ROOT / "data" / "db_backups"


def backup_database() -> Path:
    """Create a timestamped SQLite backup before mutating the DB."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"scitaste_before_cleanup_{timestamp}.db"
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


def find_corrupted_pushes(conn: sqlite3.Connection, user_id: str | None = None) -> list[sqlite3.Row]:
    """Locate push batches that are provably corrupted."""
    cursor = conn.cursor()
    params = []
    user_clause = ""
    if user_id:
        user_clause = "WHERE user_id = ?"
        params.append(user_id)

    cursor.execute(
        f"""
        SELECT
            user_id,
            push_id,
            SUM(CASE WHEN action='pushed' THEN 1 ELSE 0 END) AS pushed_logs,
            COUNT(DISTINCT CASE WHEN action='pushed' THEN paper_id END) AS uniq_pushed_papers,
            MIN(timestamp) AS first_ts,
            MAX(timestamp) AS last_ts
        FROM behavior_logs
        {user_clause}
        GROUP BY user_id, push_id
        HAVING pushed_logs > 1 AND uniq_pushed_papers = 1
        ORDER BY user_id, last_ts DESC
        """
    , params)
    return cursor.fetchall()


def delete_push_batches(conn: sqlite3.Connection, push_rows: list[sqlite3.Row]) -> int:
    """Delete all behavior_logs for the corrupted push IDs."""
    if not push_rows:
        return 0

    cursor = conn.cursor()
    total_deleted = 0
    for row in push_rows:
        cursor.execute(
            "DELETE FROM behavior_logs WHERE user_id = ? AND push_id = ?",
            (row["user_id"], row["push_id"]),
        )
        total_deleted += cursor.rowcount

    conn.commit()
    return total_deleted


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean corrupted push batches from scitaste.db")
    parser.add_argument("--user-id", help="Only clean pushes for this user")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without changing the DB")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        push_rows = find_corrupted_pushes(conn, args.user_id)
        if not push_rows:
            print("No corrupted push batches found.")
            return

        print(f"Found {len(push_rows)} corrupted push batches:")
        for row in push_rows:
            print(
                f"  {row['user_id']} | {row['push_id']} | "
                f"pushed={row['pushed_logs']} | uniq_pushed={row['uniq_pushed_papers']} | "
                f"{row['first_ts']} -> {row['last_ts']}"
            )

        if args.dry_run:
            print("Dry run only; no rows deleted.")
            return

        backup_path = backup_database()
        deleted_rows = delete_push_batches(conn, push_rows)
        print(f"Backup written to: {backup_path}")
        print(f"Deleted {deleted_rows} behavior_logs rows.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
