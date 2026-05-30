import json
from datetime import datetime
from pathlib import Path

import pytest

from experiments.simulation.simulate_historical_episodes import OutputManager, load_resume_state


def test_output_manager_resets_stale_jsonl_files(tmp_path: Path):
    output_dir = tmp_path / "simulation_case"
    output_dir.mkdir()

    stale_paper_pool = output_dir / "paper_pools.jsonl"
    stale_paper_pool.write_text('{"date":"2026-03-01","total":1}\n', encoding="utf-8")
    (output_dir / "simulation_summary.json").write_text('{"old": true}\n', encoding="utf-8")

    manager = OutputManager(str(output_dir), reset_existing=True)
    manager.save_paper_pool(
        "2026-03-02",
        [{"paper_id": 1, "title": "Fresh paper"}],
        new_papers_count=1,
        total_papers=5,
    )
    manager.close()

    rows = [json.loads(line) for line in stale_paper_pool.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows == [
        {
            "date": "2026-03-02",
            "total": 5,
            "new_papers_count": 1,
            "papers": [{"paper_id": 1, "title": "Fresh paper"}],
        }
    ]
    assert not (output_dir / "simulation_summary.json").exists()


def test_write_profile_hides_full_interest_vector_in_human_readable_output(tmp_path: Path):
    output_dir = tmp_path / "simulation_case"
    output_dir.mkdir()

    manager = OutputManager(str(output_dir), reset_existing=True)
    manager.write_profile(
        {
            "date": "2026-03-02",
            "user_id": "user_role1",
            "version": "0.1",
            "profile_json": {
                "core_directions": {"gui-agent": 0.72},
                "interest_vector": [0.0, 1.0, 0.0],
                "drift_state": {"status": "stable", "score": 0.0},
            },
        }
    )
    manager.close()

    visible_row = json.loads((output_dir / "profiles.jsonl").read_text(encoding="utf-8").strip())
    state_row = json.loads((output_dir / "profiles_state.jsonl").read_text(encoding="utf-8").strip())

    assert "interest_vector" not in visible_row["profile_json"]
    assert visible_row["profile_json"]["interest_vector_summary"] == {
        "dim": 3,
        "nonzero_count": 1,
        "l2_norm": 1.0,
    }
    assert state_row["profile_json"]["interest_vector"] == [0.0, 1.0, 0.0]


def test_write_episode_paper_creates_per_paper_log(tmp_path: Path):
    output_dir = tmp_path / "simulation_case"
    output_dir.mkdir()

    manager = OutputManager(str(output_dir), reset_existing=True)
    manager.write_episode_paper(
        {
            "date": "2026-03-02",
            "episode_id": "user_role1::2026-03-02",
            "user_id": "user_role1",
            "paper_id": 11,
            "title": "Fresh paper",
            "shown": True,
            "selected": False,
            "system_rank": 1,
            "oracle_label": "relevant",
        }
    )
    manager.close()

    rows = [
        json.loads(line)
        for line in (output_dir / "episode_papers.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows == [
        {
            "date": "2026-03-02",
            "episode_id": "user_role1::2026-03-02",
            "user_id": "user_role1",
            "paper_id": 11,
            "title": "Fresh paper",
            "shown": True,
            "selected": False,
            "system_rank": 1,
            "oracle_label": "relevant",
        }
    ]


def test_write_reading_report_persists_jsonl_and_markdown(tmp_path: Path):
    output_dir = tmp_path / "simulation_case"
    output_dir.mkdir()

    manager = OutputManager(str(output_dir), reset_existing=True)
    manager.write_reading_report(
        {
            "date": "2026-03-02",
            "episode_id": "user_role1::2026-03-02",
            "user_id": "user_role1",
            "role_name": "role1",
            "paper_id": 11,
            "title": "Fresh Paper: A Test",
            "report_payload": {"analysis_source": "abstract"},
            "report_content": "# Fresh Paper\n\nThis is the local report.",
        }
    )
    manager.close()

    rows = [
        json.loads(line)
        for line in (output_dir / "reading_reports.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report_files = list((output_dir / "reading_reports_md").glob("*.md"))

    assert rows[0]["title"] == "Fresh Paper: A Test"
    assert rows[0]["report_content"].startswith("# Fresh Paper")
    assert len(report_files) == 1
    assert report_files[0].read_text(encoding="utf-8").startswith("# Fresh Paper")


def test_output_manager_reset_removes_stale_reading_reports(tmp_path: Path):
    output_dir = tmp_path / "simulation_case"
    report_dir = output_dir / "reading_reports_md"
    report_dir.mkdir(parents=True)
    (output_dir / "reading_reports.jsonl").write_text('{"old":true}\n', encoding="utf-8")
    (report_dir / "old.md").write_text("# old", encoding="utf-8")

    manager = OutputManager(str(output_dir), reset_existing=True)
    manager.close()

    assert not (output_dir / "reading_reports.jsonl").exists()
    assert not report_dir.exists()


def test_load_resume_state_uses_previous_day_profiles_and_report_keys(tmp_path: Path):
    output_dir = tmp_path / "simulation_case"
    output_dir.mkdir()

    (output_dir / "profiles.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "date": "2026-03-05",
                        "user_id": "user_role1",
                        "version": "0.1",
                        "profile_json": {"drift_state": {"status": "shifting", "score": 0.4}},
                    }
                ),
                json.dumps(
                    {
                        "date": "2026-03-05",
                        "user_id": "user_role2",
                        "version": "0.1",
                        "profile_json": {"drift_state": {"status": "stable", "score": 0.0}},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "episodes.jsonl").write_text(
        json.dumps(
            {
                "date": "2026-03-05",
                "user_id": "user_role1",
                "selected_paper_ids": [11, 12],
                "selected_paper_titles": ["Older Paper"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "users.json").write_text(
        json.dumps({"users": [{"user_id": "user_role1"}, {"user_id": "user_role2"}]}),
        encoding="utf-8",
    )

    state = load_resume_state(output_dir, datetime.strptime("20260306", "%Y%m%d"))

    assert state["resume"] is True
    assert state["profiles_by_user"]["user_role1"]["profile"]["drift_state"]["score"] == 0.4
    assert "user_role1::paper::11" in state["generated_report_keys"]
    assert "user_role1::title::older paper" in state["generated_report_keys"]


def test_load_resume_state_rejects_missing_previous_day(tmp_path: Path):
    output_dir = tmp_path / "simulation_case"
    output_dir.mkdir()
    (output_dir / "profiles.jsonl").write_text(
        json.dumps(
            {
                "date": "2026-03-04",
                "user_id": "user_role1",
                "version": "0.1",
                "profile_json": {"drift_state": {"status": "stable", "score": 0.0}},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError):
        load_resume_state(output_dir, datetime.strptime("20260306", "%Y%m%d"))
