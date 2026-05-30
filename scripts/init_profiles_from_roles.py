#!/usr/bin/env python3
"""
Initialize Profiles from Roles

从 roles.json 创建初始用户画像到数据库 profiles 表。

使用方法:
    python scripts/init_profiles_from_roles.py --roles-path data/roles.json --db-path data/paperflow.db
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "storage-helper" / "scripts"))

import db_ops
from db_ops import init_db, create_profile


def resolve_project_path(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def configure_db_path(db_path: str) -> Path:
    resolved = resolve_project_path(db_path)
    db_ops.DB_PATH = resolved
    return resolved


def load_roles(roles_path: str) -> Dict[str, Dict[str, Any]]:
    """加载 roles.json"""
    path = resolve_project_path(roles_path)

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("roles", {})


def backup_profiles(db_path: Path) -> Path:
    backup_dir = PROJECT_ROOT / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"profiles_backup_{timestamp}.json"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute("SELECT * FROM profiles ORDER BY user_id")]
    conn.close()

    backup_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return backup_path


def clear_profiles_only(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM profiles")
    before_count = int(cursor.fetchone()[0] or 0)
    cursor.execute("DELETE FROM profiles")
    conn.commit()
    conn.close()
    return before_count


def build_profile_from_role(role_name: str, role_data: Dict[str, Any]) -> Dict[str, Any]:
    """从单个 role 构建 profile"""
    user_id = role_data.get("user_id", f"user_{role_name}")
    now = datetime.now().isoformat()

    # 从 seed_directions 构建 core_directions
    core_directions = {}
    seed_directions = role_data.get("seed_directions", [])
    for sd in seed_directions:
        canonical_name = sd.get("canonical_name", sd.get("bootstrap_phrase", ""))
        weight = float(sd.get("weight", 0.5))
        if canonical_name:
            core_directions[canonical_name] = weight

    # 构建 must_read
    must_read = {
        "authors": role_data.get("must_read_authors", []) or [],
        "institutions": role_data.get("must_read_institutions", []) or [],
        "keywords": role_data.get("must_read_keywords", []) or [],
    }

    # 构建 topic_weights (从 core_directions 复制)
    topic_weights = {
        k.replace(" ", "_").lower(): v
        for k, v in core_directions.items()
    }

    profile = {
        "user_id": user_id,
        "version": "0.1",
        "created_at": now,
        "updated_at": now,
        "core_directions": core_directions,
        "methodology_preferences": role_data.get("methodology_preferences") or {},
        "must_read": must_read,
        "topic_weights": topic_weights,
        "author_heat": {},
        "institution_heat": {},
        "interest_vector": [0.0] * 768,
        "taste_profile": {
            "preferred_work_type": role_data.get("preferred_work_type", []) or [],
            "dispreferred_work_type": role_data.get("dispreferred_work_type", []) or [],
        },
        "reading_history": [],
        "behavior_logs_summary": {
            "total_pushes": 0,
            "total_selected": 0,
            "total_skipped": 0,
            "selection_rate": 0.0,
        },
        "description": role_data.get("description", ""),
        "secondary_topics": role_data.get("secondary_topics", []) or [],
        "report_preferences": role_data.get("report_preferences") or {},
        "drift_plan": role_data.get("drift_plan") or {},
        "drift_state": {
            "status": "stable",
            "score": 0.0,
            "last_drift_date": None,
            "drift_enabled": None,
            "hidden_anchor": None,
            "hidden_anchor_source": None,
            "intent_score": 0.0,
            "anchor_topic": None,
            "anchor_topics": [],
            "anchor_source": None,
            "anchor_confidence": 0.0,
            "anchor_progress": 0.0,
            "anchor_set_date": None,
            "commitment_days_remaining": 0,
            "signal_window": [],
            "top_shift_topics": [],
            "episode_index": 0,
            "completed_drift_cycles": 0,
            "max_drift_cycles": None,
        },
    }

    return profile


def main():
    parser = argparse.ArgumentParser(description="Initialize Profiles from roles.json")
    parser.add_argument("--roles-path", type=str, default="data/roles.json", help="roles.json 路径")
    parser.add_argument("--db-path", type=str, default="data/paperflow.db", help="数据库路径")
    parser.add_argument(
        "--overwrite-profiles",
        action="store_true",
        help="Back up and recreate profiles from roles.json. This deletes only profile rows and keeps papers intact.",
    )
    args = parser.parse_args()

    # 加载 roles
    print(f"Loading roles from {args.roles_path}...")
    roles = load_roles(args.roles_path)
    print(f"  Found {len(roles)} roles")

    # 初始化数据库
    resolved_db_path = configure_db_path(args.db_path)
    print(f"\nInitializing database: {resolved_db_path}...")
    init_db()

    if args.overwrite_profiles:
        backup_path = backup_profiles(resolved_db_path)
        removed_count = clear_profiles_only(resolved_db_path)
        print("\nOverwriting profiles only.")
        print(f"  Backup: {backup_path}")
        print(f"  Removed profile rows: {removed_count}")
        print("  Papers table was not modified.")

    # 创建 profile
    print("\nCreating profiles...")
    created_count = 0
    existing_count = 0

    for role_name, role_data in sorted(roles.items()):
        profile = build_profile_from_role(role_name, role_data)
        user_id = profile["user_id"]

        profile_id = create_profile(user_id, profile)
        if profile_id:
            created_count += 1
            print(f"  + {user_id} ({role_name}): {len(profile['core_directions'])} directions")
        else:
            existing_count += 1
            print(f"  ~ {user_id} ({role_name}): already exists")

    print()
    print("=" * 60)
    print("Profiles Initialized")
    print("=" * 60)
    print(f"Created: {created_count}")
    print(f"Already exists: {existing_count}")
    print(f"Total: {created_count + existing_count}")


if __name__ == "__main__":
    main()
