#!/usr/bin/env python3
"""
Initialize User Metadata

从 roles.json 和数据库 profiles 表初始化用户元数据。

使用方法:
    python scripts/init_user_metadata.py \
      --roles-path data/roles.json \
      --db-path data/paperflow.db \
      --output-dir data/simulation_output
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_roles(roles_path: str) -> Dict[str, Dict[str, Any]]:
    """加载 roles.json"""
    path = Path(roles_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / roles_path

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("roles", {})


def load_profiles(db_path: str) -> Dict[str, Dict[str, Any]]:
    """从数据库加载 profiles"""
    path = Path(db_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / db_path

    conn = sqlite3.connect(path)
    profiles = conn.execute("SELECT user_id, profile_json, version FROM profiles").fetchall()
    conn.close()

    result = {}
    for row in profiles:
        result[row[0]] = {
            "profile": json.loads(row[1]),
            "version": row[2],
        }

    return result


def init_user_metadata(
    roles: Dict[str, Dict[str, Any]],
    profiles: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """初始化用户元数据列表"""
    users = []

    for role_name, role_data in sorted(roles.items()):
        user_id = role_data.get("user_id", f"user_{role_name}")
        profile_data = profiles.get(user_id, {})
        profile = profile_data.get("profile", {})

        users.append({
            "user_id": user_id,
            "role_name": role_name,
            "description": role_data.get("description") or profile.get("description", ""),
            "seed_directions": profile.get("core_directions", {}),
            "initial_topics": list(profile.get("core_directions", {}).keys()),
            "created_at": datetime.now().strftime("%Y-%m-%d"),
        })

    return users


def main():
    parser = argparse.ArgumentParser(description="Initialize User Metadata")
    parser.add_argument("--roles-path", type=str, default="data/roles.json", help="roles.json 路径")
    parser.add_argument("--db-path", type=str, default="data/paperflow.db", help="数据库路径")
    parser.add_argument("--output-dir", type=str, default="data/simulation_output", help="输出目录")
    args = parser.parse_args()

    # 加载数据
    print(f"Loading roles from {args.roles_path}...")
    roles = load_roles(args.roles_path)
    print(f"  Found {len(roles)} roles")

    print(f"Loading profiles from {args.db_path}...")
    profiles = load_profiles(args.db_path)
    print(f"  Found {len(profiles)} profiles")

    # 初始化用户元数据
    users = init_user_metadata(roles, profiles)

    # 输出
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "users.json"

    with output_path.open("w", encoding="utf-8") as f:
        json.dump({"users": users}, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print("User Metadata Initialized")
    print("=" * 60)
    print(f"Users: {len(users)}")
    print(f"Output: {output_path}")

    # 打印预览
    print()
    print("Preview:")
    for user in users[:5]:
        print(f"  - {user['user_id']} ({user['role_name']}): {len(user['seed_directions'])} directions")
    if len(users) > 5:
        print(f"  ... and {len(users) - 5} more")


if __name__ == "__main__":
    main()
