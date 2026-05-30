"""Tests for the database cleanup utility."""

import importlib
import json
import sqlite3
from pathlib import Path


clear_database = importlib.import_module("scripts.clear_database")


def _create_test_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE NOT NULL,
            profile_json TEXT NOT NULL,
            version TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE papers (
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
        """
    )
    cursor.execute(
        """
        CREATE TABLE behavior_logs (
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
        """
    )
    cursor.execute(
        """
        CREATE TABLE task_status (
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
        """
    )

    cursor.execute(
        "INSERT INTO profiles (user_id, profile_json, version) VALUES (?, ?, ?)",
        ("legacy_user", json.dumps({"user_id": "legacy_user"}), "0.1"),
    )
    cursor.execute(
        "INSERT INTO papers (arxiv_id, title) VALUES (?, ?)",
        ("2404.00001", "Old paper"),
    )
    cursor.execute(
        """
        INSERT INTO behavior_logs (user_id, push_id, action, action_type)
        VALUES (?, ?, ?, ?)
        """,
        ("legacy_user", "push_1", "clicked", "select"),
    )
    cursor.execute(
        """
        INSERT INTO task_status (task_id, task_type, user_id, status)
        VALUES (?, ?, ?, ?)
        """,
        ("task_1", "reading_report", "legacy_user", "running"),
    )

    conn.commit()
    conn.close()


def test_build_seed_profile_limits_rolea_to_three_custom_directions():
    profile = clear_database.build_seed_profile(
        "rolea",
        {
            "user_id": "user_rolea",
            "description": "direction: data-native scientific discovery, bio-molecular data infrastructure, gui agent",
            "feishu_chat_id": "oc_test_rolea",
        },
    )

    assert set(profile["core_directions"]) == {"data-native", "bio-molecular", "gui-agent"}
    assert "agent" not in profile["core_directions"]
    assert "science-discovery" not in profile["core_directions"]
    assert profile["feishu_chat_id"] == "oc_test_rolea"


def test_full_reset_clears_dynamic_tables_and_reseeds_profiles(tmp_path):
    db_path = tmp_path / "paperflow.db"
    roles_path = tmp_path / "roles.json"
    backup_dir = tmp_path / "db_backups"

    _create_test_db(db_path)
    roles_path.write_text(
        json.dumps(
            {
                "roles": {
                    "rolea": {
                        "user_id": "user_rolea",
                        "description": "direction: data-native scientific discovery, bio-molecular data infrastructure, gui agent",
                        "feishu_chat_id": "oc_rolea",
                        "seed_directions": [
                            {"canonical_name": "data-native", "weight": 0.72},
                            {"canonical_name": "bio-molecular", "weight": 0.62},
                            {"canonical_name": "gui-agent", "weight": 0.56},
                        ],
                        "secondary_topics": ["lab automation"],
                        "must_read_authors": ["Alice"],
                        "must_read_institutions": ["OpenAI"],
                        "must_read_keywords": ["gui agent"],
                        "report_preferences": {"preferred_report_length": "detailed"},
                        "drift_plan": {"shift_topics": ["multimodal reasoning"], "downweight_topics": ["gui agent"]},
                    },
                    "roled": {
                        "user_id": "user_roled",
                        "description": "研究方向：reinforcement learning, robotics",
                        "feishu_chat_id": "oc_roled",
                    },
                },
                "current_role": "rolea",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    result = clear_database.full_reset(
        db_path=db_path,
        roles_path=roles_path,
        backup_dir=backup_dir,
    )

    assert Path(result["backup_path"]).exists()
    assert result["before_counts"] == {
        "profiles": 1,
        "papers": 1,
        "behavior_logs": 1,
        "task_status": 1,
    }
    assert result["after_counts"] == {
        "profiles": 2,
        "papers": 0,
        "behavior_logs": 0,
        "task_status": 0,
    }
    assert set(result["seeded_profiles"]["rolea"]) == {"data-native", "bio-molecular", "gui-agent"}
    assert set(result["seeded_profiles"]["roled"]) == {"reinforcement-learning", "embodied-ai"}

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, profile_json FROM profiles ORDER BY user_id")
    rows = cursor.fetchall()
    conn.close()

    stored_profiles = {user_id: json.loads(profile_json) for user_id, profile_json in rows}
    assert set(stored_profiles) == {"user_rolea", "user_roled"}
    assert set(stored_profiles["user_rolea"]["core_directions"]) == {
        "data-native",
        "bio-molecular",
        "gui-agent",
    }
    assert stored_profiles["user_rolea"]["secondary_topics"] == ["lab automation"]
    assert stored_profiles["user_rolea"]["must_read"]["authors"] == ["Alice"]
    assert stored_profiles["user_rolea"]["report_preferences"]["preferred_report_length"] == "detailed"
    assert stored_profiles["user_rolea"]["drift_plan"]["shift_topics"] == ["multimodal reasoning"]
    assert set(stored_profiles["user_roled"]["core_directions"]) == {
        "reinforcement-learning",
        "embodied-ai",
    }


def test_benchmark_reset_preserves_papers_and_reseeds_profiles(tmp_path):
    db_path = tmp_path / "paperflow.db"
    roles_path = tmp_path / "roles.json"
    backup_dir = tmp_path / "db_backups"

    _create_test_db(db_path)
    roles_path.write_text(
        json.dumps(
            {
                "roles": {
                    "rolea": {
                        "user_id": "user_rolea",
                        "description": "direction: data-native scientific discovery, bio-molecular data infrastructure, gui agent",
                        "seed_directions": [
                            {"canonical_name": "data-native", "weight": 0.72},
                            {"canonical_name": "bio-molecular", "weight": 0.62},
                            {"canonical_name": "gui-agent", "weight": 0.56},
                        ],
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    result = clear_database.benchmark_reset(
        db_path=db_path,
        roles_path=roles_path,
        backup_dir=backup_dir,
    )

    assert Path(result["backup_path"]).exists()
    assert result["after_counts"] == {
        "profiles": 1,
        "papers": 1,
        "behavior_logs": 0,
        "task_status": 0,
    }

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT arxiv_id, title FROM papers")
    papers = cursor.fetchall()
    cursor.execute("SELECT user_id, profile_json FROM profiles")
    profiles = cursor.fetchall()
    conn.close()

    assert papers == [("2404.00001", "Old paper")]
    assert [row[0] for row in profiles] == ["user_rolea"]
    assert set(json.loads(profiles[0][1])["core_directions"]) == {
        "data-native",
        "bio-molecular",
        "gui-agent",
    }
