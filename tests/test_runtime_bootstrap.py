import importlib
import json
import sqlite3
from pathlib import Path


runtime_bootstrap = importlib.import_module("scripts.runtime_bootstrap")


def test_bootstrap_runtime_creates_roles_and_database(tmp_path):
    root_dir = tmp_path
    (root_dir / "config").mkdir(parents=True, exist_ok=True)
    (root_dir / "config" / "roles.example.json").write_text(
        json.dumps(
            {
                "roles": {
                    "rolea": {
                        "user_id": "user_rolea",
                        "description": "direction: test",
                        "feishu_chat_id": "",
                    }
                },
                "current_role": "rolea",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runtime_bootstrap.bootstrap_runtime(root_dir=root_dir, verbose=False)

    roles_path = result["roles_path"]
    db_path = result["db_path"]

    assert roles_path.exists()
    assert json.loads(roles_path.read_text(encoding="utf-8"))["current_role"] == "rolea"
    assert db_path.exists()

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()

    table_names = {row[0] for row in rows}
    assert {"profiles", "papers", "behavior_logs", "task_status"}.issubset(table_names)


def test_bootstrap_runtime_creates_profile_for_role_description(tmp_path):
    root_dir = tmp_path
    (root_dir / "config").mkdir(parents=True, exist_ok=True)
    (root_dir / "config" / "roles.example.json").write_text(
        json.dumps(
            {
                "roles": {
                    "rolea": {
                        "user_id": "user_rolea",
                        "description": "direction: gui agent, bio-molecular data infrastructure",
                        "feishu_chat_id": "",
                    }
                },
                "current_role": "rolea",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    result = runtime_bootstrap.bootstrap_runtime(root_dir=root_dir, verbose=False)
    db_path = result["db_path"]
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT profile_json FROM profiles WHERE user_id = ?",
            ("user_rolea",),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    profile = json.loads(row[0])
    assert profile["core_directions"]
    assert "gui-agent" in profile["core_directions"]
