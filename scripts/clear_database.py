#!/usr/bin/env python3
"""Reset the local SciTaste database while preserving role-level cold-start profiles."""

from __future__ import annotations

import argparse
import importlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "scitaste.db"
ROLES_FILE = PROJECT_ROOT / "data" / "roles.json"
BACKUP_DIR = PROJECT_ROOT / "data" / "db_backups"

ROLE_DIRECTION_OVERRIDES = {
    "rolea": ["data-native", "bio-molecular", "gui-agent"],
    "roleb": ["multimodal-reasoning", "vision", "language"],
    "rolec": ["deep-learning", "language"],
    "roled": ["reinforcement-learning", "embodied-ai"],
}

REDUNDANT_DIRECTION_MAP = {
    "gui-agent": {"agent"},
    "multimodal-reasoning": {"reasoning"},
}


def load_roles_meta(roles_path: Path = ROLES_FILE) -> Dict[str, Any]:
    """Load role metadata from disk."""
    if not roles_path.exists():
        raise FileNotFoundError(f"Roles file not found: {roles_path}")

    with roles_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def backup_database(db_path: Path = DB_PATH, backup_dir: Path = BACKUP_DIR) -> Path:
    """Create a timestamped database backup before mutating any records."""
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"scitaste_{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    return backup_path


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection."""
    return sqlite3.connect(db_path)


def get_table_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    """Return row counts for the main tables."""
    counts: Dict[str, int] = {}
    cursor = conn.cursor()

    for table_name in ("profiles", "papers", "behavior_logs", "task_status"):
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        counts[table_name] = int(cursor.fetchone()[0])

    return counts


def _prune_redundant_directions(direction_weights: Dict[str, float]) -> Dict[str, float]:
    """Drop generic directions when a more specific sibling exists."""
    pruned = dict(direction_weights)

    for primary, redundant_keys in REDUNDANT_DIRECTION_MAP.items():
        if primary not in pruned:
            continue
        for redundant_key in redundant_keys:
            pruned.pop(redundant_key, None)

    return pruned


def _select_seed_directions(role_name: str, parsed: Dict[str, Any]) -> Dict[str, float]:
    """Choose 2-3 stable seed directions for a role."""
    core_directions = _prune_redundant_directions(parsed.get("core_directions") or {})
    if not core_directions:
        return {}

    selected_keys = []
    for direction_key in ROLE_DIRECTION_OVERRIDES.get(role_name, []):
        if direction_key in core_directions and direction_key not in selected_keys:
            selected_keys.append(direction_key)

    if len(selected_keys) < 2:
        for direction_key, _weight in sorted(
            core_directions.items(),
            key=lambda item: (-float(item[1]), item[0]),
        ):
            if direction_key not in selected_keys:
                selected_keys.append(direction_key)
            if len(selected_keys) >= 3:
                break
    else:
        selected_keys = selected_keys[:3]

    if len(selected_keys) < 2:
        selected_keys = selected_keys[: min(3, len(core_directions))]

    return {
        direction_key: round(float(core_directions[direction_key]), 4)
        for direction_key in selected_keys
    }


def build_seed_profile(role_name: str, role_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build a fresh cold-start profile from role metadata."""
    coldstart_agent = importlib.import_module("agents.coldstart-agent.main")

    user_id = role_data.get("user_id") or f"user_{role_name}"
    bootstrap_text = (
        role_data.get("natural_language")
        or role_data.get("description")
        or ""
    ).strip()

    profile = coldstart_agent.build_empty_profile(user_id)
    parsed = coldstart_agent.parse_natural_language(bootstrap_text) if bootstrap_text else {}
    selected_directions = _select_seed_directions(role_name, parsed)

    profile["core_directions"] = selected_directions
    profile["topic_weights"] = {
        direction_key: round(
            float((parsed.get("topic_weights") or {}).get(direction_key, weight)),
            4,
        )
        for direction_key, weight in selected_directions.items()
    }
    profile["methodology_preferences"] = parsed.get("methodology_preferences") or {}
    profile["taste_profile"] = parsed.get("taste_profile") or {}
    profile["interest_vector"] = coldstart_agent.generate_interest_vector(selected_directions)
    profile["feishu_chat_id"] = role_data.get("feishu_chat_id")

    return profile


def reset_user_profiles(
    conn: sqlite3.Connection,
    roles_meta: Dict[str, Any],
    roles: Optional[Iterable[str]] = None,
) -> Dict[str, Dict[str, float]]:
    """Replace stored profiles with fresh role-specific seed profiles."""
    all_roles = roles_meta.get("roles", {})
    target_roles = list(roles) if roles else list(all_roles.keys())

    missing_roles = [role_name for role_name in target_roles if role_name not in all_roles]
    if missing_roles:
        raise ValueError(f"Unknown roles: {', '.join(missing_roles)}")

    cursor = conn.cursor()
    cursor.execute("DELETE FROM profiles")

    seeded_profiles: Dict[str, Dict[str, float]] = {}
    for role_name in target_roles:
        role_data = all_roles[role_name]
        profile = build_seed_profile(role_name, role_data)
        cursor.execute(
            """
            INSERT INTO profiles (user_id, profile_json, version, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                profile["user_id"],
                json.dumps(profile, ensure_ascii=False),
                profile.get("version", "0.1"),
            ),
        )
        seeded_profiles[role_name] = dict(profile.get("core_directions") or {})

    return seeded_profiles


def clear_tables(conn: sqlite3.Connection, table_names: Iterable[str]) -> None:
    """Delete all rows from the provided tables."""
    cursor = conn.cursor()
    for table_name in table_names:
        cursor.execute(f"DELETE FROM {table_name}")


def reset_sqlite_sequences(conn: sqlite3.Connection, table_names: Iterable[str]) -> None:
    """Reset autoincrement counters after destructive cleanup."""
    cursor = conn.cursor()
    for table_name in table_names:
        cursor.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table_name,))


def full_reset(
    db_path: Path = DB_PATH,
    roles_path: Path = ROLES_FILE,
    backup_dir: Path = BACKUP_DIR,
    roles: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Clear dynamic data and recreate clean role profiles."""
    backup_path = backup_database(db_path=db_path, backup_dir=backup_dir)
    roles_meta = load_roles_meta(roles_path=roles_path)

    conn = get_connection(db_path=db_path)
    try:
        before_counts = get_table_counts(conn)
        clear_tables(conn, ("behavior_logs", "papers", "task_status"))
        seeded_profiles = reset_user_profiles(conn, roles_meta, roles=roles)
        reset_sqlite_sequences(conn, ("profiles", "papers", "behavior_logs", "task_status"))
        conn.commit()
        after_counts = get_table_counts(conn)
    finally:
        conn.close()

    return {
        "backup_path": str(backup_path),
        "before_counts": before_counts,
        "after_counts": after_counts,
        "seeded_profiles": seeded_profiles,
    }


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Reset the SciTaste database while preserving role-specific cold-start profiles.",
    )
    parser.add_argument(
        "--action",
        choices=("full_reset", "reset_profiles", "clear_logs", "clear_papers", "clear_tasks"),
        default="full_reset",
        help="Cleanup action to perform.",
    )
    parser.add_argument("--roles", nargs="+", help="Only seed the specified role names.")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    return parser.parse_args()


def main() -> int:
    """CLI entrypoint."""
    args = parse_args()

    if not args.yes:
        print(f"Action: {args.action}")
        if args.roles:
            print(f"Roles: {', '.join(args.roles)}")
        confirmation = input("Continue? (yes/no): ").strip().lower()
        if confirmation != "yes":
            print("Cancelled.")
            return 1

    if args.action == "full_reset":
        result = full_reset(roles=args.roles)
        print(f"Backup: {result['backup_path']}")
        print(f"Before: {json.dumps(result['before_counts'], ensure_ascii=False)}")
        print(f"After: {json.dumps(result['after_counts'], ensure_ascii=False)}")
        print("Seeded profiles:")
        for role_name, directions in result["seeded_profiles"].items():
            print(f"  - {role_name}: {json.dumps(directions, ensure_ascii=False)}")
        return 0

    backup_path = backup_database()
    roles_meta = load_roles_meta()
    conn = get_connection()
    try:
        if args.action == "reset_profiles":
            seeded_profiles = reset_user_profiles(conn, roles_meta, roles=args.roles)
            reset_sqlite_sequences(conn, ("profiles",))
            conn.commit()
            print(f"Backup: {backup_path}")
            for role_name, directions in seeded_profiles.items():
                print(f"  - {role_name}: {json.dumps(directions, ensure_ascii=False)}")
        elif args.action == "clear_logs":
            clear_tables(conn, ("behavior_logs",))
            reset_sqlite_sequences(conn, ("behavior_logs",))
            conn.commit()
            print(f"Backup: {backup_path}")
            print("Cleared behavior_logs.")
        elif args.action == "clear_papers":
            clear_tables(conn, ("papers",))
            reset_sqlite_sequences(conn, ("papers",))
            conn.commit()
            print(f"Backup: {backup_path}")
            print("Cleared papers.")
        elif args.action == "clear_tasks":
            clear_tables(conn, ("task_status",))
            reset_sqlite_sequences(conn, ("task_status",))
            conn.commit()
            print(f"Backup: {backup_path}")
            print("Cleared task_status.")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
