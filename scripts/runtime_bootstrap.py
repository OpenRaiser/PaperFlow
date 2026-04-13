#!/usr/bin/env python3
"""Bootstrap runtime files required for a fresh local deployment."""

from __future__ import annotations

import importlib
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROLES_TEMPLATE = {
    "roles": {
        "rolea": {
            "user_id": "user_rolea",
            "description": "direction: data-native scientific discovery, bio-molecular data infrastructure, gui agent",
            "feishu_chat_id": "",
        }
    },
    "current_role": "rolea",
}
REQUIRED_TABLES = {"profiles", "papers", "behavior_logs", "task_status"}


def ensure_runtime_dirs(root_dir: Path = PROJECT_ROOT) -> Dict[str, Path]:
    data_dir = root_dir / "data"
    models_dir = root_dir / "models"
    paths = {
        "data_dir": data_dir,
        "db_backups_dir": data_dir / "db_backups",
        "embeddings_cache_dir": data_dir / "embeddings_cache",
        "webhook_task_locks_dir": data_dir / "webhook_task_locks",
        "models_dir": models_dir,
    }

    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)

    for keep_path in (data_dir / ".gitkeep", models_dir / ".gitkeep"):
        keep_path.touch(exist_ok=True)

    return paths


def ensure_roles_file(root_dir: Path = PROJECT_ROOT) -> Path:
    data_dir = root_dir / "data"
    roles_path = data_dir / "roles.json"
    if roles_path.exists():
        return roles_path

    template_path = root_dir / "config" / "roles.example.json"
    if template_path.exists():
        shutil.copyfile(template_path, roles_path)
        return roles_path

    roles_path.write_text(
        json.dumps(DEFAULT_ROLES_TEMPLATE, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return roles_path


def _database_has_required_tables(db_path: Path) -> bool:
    if not db_path.exists():
        return False

    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return False

    table_names = {row[0] for row in rows}
    return REQUIRED_TABLES.issubset(table_names)


def ensure_database(root_dir: Path = PROJECT_ROOT) -> Path:
    db_path = root_dir / "data" / "scitaste.db"
    if _database_has_required_tables(db_path):
        return db_path

    db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
    original_db_path = getattr(db_ops, "DB_PATH", None)
    try:
        db_ops.DB_PATH = db_path
        db_ops.init_db()
    finally:
        if original_db_path is not None:
            db_ops.DB_PATH = original_db_path

    return db_path


def ensure_role_profiles(root_dir: Path = PROJECT_ROOT) -> Dict[str, Any]:
    roles_path = root_dir / "data" / "roles.json"
    if not roles_path.exists():
        return {"created": [], "updated": []}

    try:
        roles_meta = json.loads(roles_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"created": [], "updated": []}

    db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
    coldstart_agent = importlib.import_module("agents.coldstart-agent.main")
    db_path = root_dir / "data" / "scitaste.db"
    original_db_path = getattr(db_ops, "DB_PATH", None)

    created: list[str] = []
    updated: list[str] = []
    try:
        db_ops.DB_PATH = db_path
        for role_name, role_data in (roles_meta.get("roles") or {}).items():
            if not isinstance(role_data, dict):
                continue

            user_id = str(role_data.get("user_id") or f"user_{role_name}").strip()
            if not user_id:
                continue

            profile = db_ops.get_profile(user_id)
            is_new_profile = profile is None
            if profile is None:
                profile = coldstart_agent.build_empty_profile(user_id)
            else:
                profile = coldstart_agent.ensure_profile_shape(profile, user_id)

            feishu_chat_id = str(role_data.get("feishu_chat_id") or "").strip()
            if feishu_chat_id:
                profile["feishu_chat_id"] = feishu_chat_id

            bootstrap_text = str(
                role_data.get("natural_language") or role_data.get("description") or ""
            ).strip()
            if bootstrap_text and not profile.get("core_directions") and not profile.get("topic_weights"):
                parsed = coldstart_agent.parse_natural_language(bootstrap_text, use_llm=False)
                coldstart_agent.merge_parsed_profile_into_profile(profile, parsed)

            if is_new_profile:
                db_ops.create_profile(user_id, profile)
                created.append(user_id)
            else:
                db_ops.update_profile(user_id, profile)
                updated.append(user_id)
    finally:
        if original_db_path is not None:
            db_ops.DB_PATH = original_db_path

    return {"created": created, "updated": updated}


def bootstrap_runtime(root_dir: Path = PROJECT_ROOT, verbose: bool = True) -> Dict[str, Any]:
    ensure_runtime_dirs(root_dir)
    roles_path = ensure_roles_file(root_dir)
    db_path = ensure_database(root_dir)
    profile_result = ensure_role_profiles(root_dir)

    result = {
        "root_dir": root_dir,
        "roles_path": roles_path,
        "db_path": db_path,
        "profile_result": profile_result,
    }

    if verbose:
        print(f"[OK] Runtime directories ready: {root_dir}")
        print(f"[OK] Roles config ready: {roles_path}")
        print(f"[OK] Database ready: {db_path}")
        if profile_result["created"]:
            print(f"[OK] Created role profiles: {', '.join(profile_result['created'])}")

    return result


if __name__ == "__main__":
    bootstrap_runtime()
