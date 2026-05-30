import sys

from experiments.simulation import simulate_case_episodes as case_script


class _DummyConn:
    def close(self):
        return None


class _DummyOutputManager:
    def __init__(self, output_dir, *_args, **_kwargs):
        from pathlib import Path

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        self.saved_users = None
        self.saved_paper_pools = []

    def save_user_metadata(self, users):
        self.saved_users = users

    def save_paper_pool(self, date, papers, new_papers_count=0, total_papers=None):
        self.saved_paper_pools.append(
            {
                "date": date,
                "papers": papers,
                "new_papers_count": new_papers_count,
                "total_papers": total_papers,
            }
        )

    def close(self):
        return None


def test_case_simulation_uses_only_same_day_papers(monkeypatch, tmp_path):
    today_papers = [
        {"paper_id": 2, "title": "today-1"},
        {"paper_id": 3, "title": "today-2"},
    ]
    cumulative_papers = [
        {"paper_id": 1, "title": "old-paper"},
        *today_papers,
    ]
    captured = {}

    monkeypatch.setattr(case_script.random, "seed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(case_script.random, "randint", lambda a, _b: a)
    monkeypatch.setattr(case_script.random, "sample", lambda seq, n: list(seq)[:n])
    monkeypatch.setattr(case_script.sqlite3, "connect", lambda *_args, **_kwargs: _DummyConn())

    monkeypatch.setattr(case_script.sim, "_patch_real_usage_logging", lambda: None)
    monkeypatch.setattr(case_script.sim, "get_all_users", lambda _conn: [{"user_id": "user_role1", "profile": {"core_directions": {}}, "version": "0.1"}])
    monkeypatch.setattr(case_script.sim, "load_checkfiles", lambda _path: [])
    monkeypatch.setattr(case_script.sim, "DriftEngine", lambda _checkfiles: object())
    monkeypatch.setattr(case_script.sim, "load_resume_state", lambda *_args, **_kwargs: {"resume": False, "generated_report_keys": set(), "existing_summary": None, "user_metadata": None})
    monkeypatch.setattr(case_script.sim, "clear_simulation_output_files", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(case_script.sim, "OutputManager", _DummyOutputManager)
    monkeypatch.setattr(case_script.sim, "load_roles_meta", lambda: {})
    monkeypatch.setattr(case_script.sim, "collect_papers_for_day", lambda *_args, **_kwargs: len(today_papers))
    monkeypatch.setattr(case_script.sim, "get_papers_by_date", lambda *_args, **_kwargs: today_papers)
    monkeypatch.setattr(case_script.sim, "get_papers_up_to_date", lambda *_args, **_kwargs: cumulative_papers)

    def fake_simulate_one_day(**kwargs):
        captured["papers"] = kwargs["papers"]
        captured["new_papers"] = kwargs["new_papers"]
        captured["total_papers_count"] = kwargs["total_papers_count"]
        captured["skip_reading_reports"] = kwargs["skip_reading_reports"]
        captured["show_count"] = kwargs["show_count"]
        return {"episodes": 1, "drift_count": 0, "tokens": {"embedding": 0, "llm": 0}}

    monkeypatch.setattr(case_script.sim, "simulate_one_day", fake_simulate_one_day)
    monkeypatch.setattr(case_script.sim, "merge_summary_with_previous", lambda *_args, **_kwargs: {"total_episodes": 1, "total_drifts": 0})

    output_dir = tmp_path / "daily_case"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "simulate_case_episodes.py",
            "--start-date",
            "20260301",
            "--end-date",
            "20260301",
            "--min-users",
            "1",
            "--max-users",
            "1",
            "--skip-reading-reports",
            "--show-count",
            "30",
            "--output-dir",
            str(output_dir),
        ],
    )

    case_script.main()

    assert captured["papers"] == today_papers
    assert captured["new_papers"] == today_papers
    assert captured["total_papers_count"] == len(cumulative_papers)
    assert captured["skip_reading_reports"] is True
    assert captured["show_count"] == 30


def test_case_simulation_writes_empty_paper_pool_for_no_paper_day(monkeypatch, tmp_path):
    cumulative_papers = [{"paper_id": 1, "title": "old-paper"}]
    captured = {"simulate_called": False, "output_manager": None}

    monkeypatch.setattr(case_script.random, "seed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(case_script.random, "randint", lambda a, _b: a)
    monkeypatch.setattr(case_script.random, "sample", lambda seq, n: list(seq)[:n])
    monkeypatch.setattr(case_script.sqlite3, "connect", lambda *_args, **_kwargs: _DummyConn())

    monkeypatch.setattr(case_script.sim, "_patch_real_usage_logging", lambda: None)
    monkeypatch.setattr(case_script.sim, "get_all_users", lambda _conn: [{"user_id": "user_role1", "profile": {"core_directions": {}}, "version": "0.1"}])
    monkeypatch.setattr(case_script.sim, "load_checkfiles", lambda _path: [])
    monkeypatch.setattr(case_script.sim, "DriftEngine", lambda _checkfiles: object())
    monkeypatch.setattr(case_script.sim, "load_resume_state", lambda *_args, **_kwargs: {"resume": False, "generated_report_keys": set(), "existing_summary": None, "user_metadata": None})
    monkeypatch.setattr(case_script.sim, "clear_simulation_output_files", lambda *_args, **_kwargs: None)

    class CapturingOutputManager(_DummyOutputManager):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            captured["output_manager"] = self

    monkeypatch.setattr(case_script.sim, "OutputManager", CapturingOutputManager)
    monkeypatch.setattr(case_script.sim, "load_roles_meta", lambda: {})
    monkeypatch.setattr(case_script.sim, "collect_papers_for_day", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(case_script.sim, "get_papers_by_date", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(case_script.sim, "get_papers_up_to_date", lambda *_args, **_kwargs: cumulative_papers)

    def fake_simulate_one_day(**_kwargs):
        captured["simulate_called"] = True
        return {"episodes": 1, "drift_count": 0, "tokens": {"embedding": 0, "llm": 0}}

    monkeypatch.setattr(case_script.sim, "simulate_one_day", fake_simulate_one_day)
    monkeypatch.setattr(case_script.sim, "merge_summary_with_previous", lambda *_args, **_kwargs: {"total_episodes": 0, "total_drifts": 0})

    output_dir = tmp_path / "daily_case_empty"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "simulate_case_episodes.py",
            "--start-date",
            "20260304",
            "--end-date",
            "20260304",
            "--min-users",
            "1",
            "--max-users",
            "1",
            "--output-dir",
            str(output_dir),
        ],
    )

    case_script.main()

    assert captured["simulate_called"] is False
    assert captured["output_manager"].saved_paper_pools == [
        {
            "date": "2026-03-04",
            "papers": [],
            "new_papers_count": 0,
            "total_papers": len(cumulative_papers),
        }
    ]
