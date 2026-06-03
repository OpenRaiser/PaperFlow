from __future__ import annotations

import threading
import time

import pytest

from deployments.desktop import server
from deployments.desktop.shared import agents


def test_desktop_server_routes_are_registered() -> None:
    assert "/api/health" in server.GET_ROUTES
    assert "/api/submit" in server.POST_ROUTES
    assert "/api/roles" in server.GET_ROUTES
    assert "/api/roles" in server.POST_ROUTES
    assert "/api/must-read" in server.GET_ROUTES
    assert "/api/must-read" in server.POST_ROUTES
    assert "/api/read/arxiv" in server.POST_ROUTES
    assert "/api/read/pdf" in server.POST_ROUTES
    assert "/api/provider-test" in server.POST_ROUTES
    assert "/api/daily/status" in server.GET_ROUTES
    assert "/api/daily/start" in server.POST_ROUTES
    assert callable(server.run_server)


def test_desktop_settings_exposes_storage_paths() -> None:
    settings = agents.settings()
    assert "paths" in settings
    assert "pdf_dir" in settings["paths"]
    assert "reading_reports_dir" in settings["paths"]
    assert "wiki_dir" in settings["paths"]


def test_desktop_health_is_json_ready() -> None:
    health = agents.health()
    assert health["ok"] is True
    assert "database" in health


def test_desktop_paper_card_backfills_arxiv_links() -> None:
    card = agents._paper_card(  # noqa: SLF001 - GUI payload normalization contract
        {"title": "Arxiv Paper", "arxiv_id": "2606.02556v1"},
        1,
    )

    assert card["url"] == "https://arxiv.org/abs/2606.02556v1"
    assert card["pdf_url"] == "https://arxiv.org/pdf/2606.02556v1"
    assert card["arxiv_id"] == "2606.02556v1"


def test_desktop_paper_card_extracts_arxiv_id_from_url() -> None:
    card = agents._paper_card(  # noqa: SLF001 - GUI payload normalization contract
        {"title": "Arxiv URL Paper", "url": "https://arxiv.org/abs/2606.03963v1"},
        1,
    )

    assert card["url"] == "https://arxiv.org/abs/2606.03963v1"
    assert card["pdf_url"] == "https://arxiv.org/pdf/2606.03963v1"
    assert card["arxiv_id"] == "2606.03963v1"


def test_desktop_paper_card_backfills_doi_link_from_metadata() -> None:
    card = agents._paper_card(  # noqa: SLF001 - GUI payload normalization contract
        {"title": "DOI Paper", "metadata": {"doi": "10.1038/example"}},
        1,
    )

    assert card["url"] == "https://doi.org/10.1038/example"
    assert card["pdf_url"] == ""
    assert card["doi"] == "10.1038/example"


def test_desktop_paper_card_prefers_explicit_url_over_fallbacks() -> None:
    card = agents._paper_card(  # noqa: SLF001 - GUI payload normalization contract
        {
            "title": "Publisher Paper",
            "url": "https://publisher.example/paper",
            "arxiv_id": "2606.02556v1",
            "metadata": {"doi": "10.1038/example"},
        },
        1,
    )

    assert card["url"] == "https://publisher.example/paper"
    assert card["pdf_url"] == "https://arxiv.org/pdf/2606.02556v1"


def test_desktop_must_read_payload_normalizes_missing_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agents.db_ops,
        "get_profile",
        lambda user_id: {"must_read": {"authors": ["Alice"], "keywords": ["agent"]}},
    )

    payload = agents.list_must_read("user_test")

    assert payload["must_read"]["authors"] == ["Alice"]
    assert payload["must_read"]["institutions"] == []
    assert payload["must_read"]["keywords"] == ["agent"]


def test_desktop_provider_test_uses_mock_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERFLOW_LLM_PROVIDER", "mock")
    monkeypatch.setenv("PAPERFLOW_LLM_MODEL", "mock-llm")

    result = agents.test_provider("llm")

    assert result["ok"] is True
    assert result["kind"] == "llm"
    assert result["provider"] == "mock"


def test_desktop_submit_and_read_forwards_feishu_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    monkeypatch.setattr(
        agents,
        "submit_gui_feedback",
        lambda **kwargs: {
            "selected_numbers": [1],
            "skipped_numbers": [],
            "profile": {},
        },
    )

    def fake_create_reading_reports(**kwargs):
        captured.update(kwargs)
        return {"created_docs": [], "count": 0}

    monkeypatch.setattr(agents, "create_reading_reports", fake_create_reading_reports)

    agents.submit_and_read(
        user_id="user_test",
        push_id="push_test",
        selected_numbers=[1],
        skipped_numbers=[],
        write_feishu=True,
    )

    assert captured["write_feishu"] is True


def test_desktop_daily_push_preserves_empty_push_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agents.daily_agent,
        "daily_push",
        lambda **kwargs: {
            "success": True,
            "push_id": "push_empty_001",
            "paper_count": 0,
            "total_fetched": 15,
            "reason": "all_candidates_filtered",
        },
    )
    monkeypatch.setattr(
        agents.db_ops,
        "get_push_papers",
        lambda push_id: {
            "push_id": push_id,
            "push_time": "2026-06-01 12:27:12",
            "papers": [],
            "metadata": {"paper_count": 0},
        },
    )
    monkeypatch.setattr(agents.db_ops, "get_latest_push", lambda user_id: None)

    payload = agents.run_daily_push("test_user", days=1)

    assert payload["push"]["push_id"] == "push_empty_001"
    assert payload["push"]["papers"] == []
    assert payload["push"]["metadata"]["paper_count"] == 0
    assert payload["push"]["metadata"]["total_fetched"] == 15
    assert payload["push"]["metadata"]["reason"] == "all_candidates_filtered"


def test_desktop_daily_push_preserves_fallback_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agents.daily_agent,
        "daily_push",
        lambda **kwargs: {
            "success": True,
            "push_id": "push_fallback_001",
            "paper_count": 1,
            "total_fetched": 7,
            "fallback_used": True,
            "fallback_days": 7,
            "fallback_total_fetched": 30,
            "fallback_filtered_already_handled": 2,
            "fallback_kept_candidates": 28,
            "fallback_relaxed": True,
            "fallback_source_scope": "arxiv",
        },
    )
    monkeypatch.setattr(
        agents.db_ops,
        "get_push_papers",
        lambda push_id: {
            "push_id": push_id,
            "push_time": "2026-06-02 12:00:00",
            "papers": [{"title": "Fallback Paper"}],
            "metadata": {},
        },
    )

    payload = agents.run_daily_push("test_user", days=1)

    assert payload["push"]["metadata"]["fallback_used"] is True
    assert payload["push"]["metadata"]["fallback_days"] == 7
    assert payload["push"]["metadata"]["fallback_relaxed"] is True


def test_desktop_daily_push_task_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agents,
        "run_daily_push",
        lambda *args, **kwargs: {
            "result": {"push_id": "push_task_complete"},
            "push": {"push_id": "push_task_complete", "papers": [], "metadata": {}},
        },
    )

    started = agents.start_daily_push_task("user_task_complete", days=1)
    task_id = started["task"]["task_id"]

    task = None
    for _ in range(50):
        task = agents.get_daily_push_task(task_id=task_id)["task"]
        if task and task["status"] == "completed":
            break
        time.sleep(0.02)

    assert task is not None
    assert task["status"] == "completed"
    assert task["push"]["push_id"] == "push_task_complete"


def test_desktop_daily_push_task_reuses_running_user_task(monkeypatch: pytest.MonkeyPatch) -> None:
    started_event = threading.Event()
    release_event = threading.Event()

    def fake_run_daily_push(*args, **kwargs):
        started_event.set()
        release_event.wait(timeout=2)
        return {
            "result": {"push_id": "push_task_running"},
            "push": {"push_id": "push_task_running", "papers": [], "metadata": {}},
        }

    monkeypatch.setattr(agents, "run_daily_push", fake_run_daily_push)

    first = agents.start_daily_push_task("user_task_running", days=1)
    assert started_event.wait(timeout=2)
    second = agents.start_daily_push_task("user_task_running", days=1)
    release_event.set()

    assert second["already_running"] is True
    assert second["task"]["task_id"] == first["task"]["task_id"]


def test_desktop_reports_payload_warns_on_feishu_failure() -> None:
    payload = agents._reports_payload(  # noqa: SLF001 - GUI warning contract
        [
            {
                "title": "Report",
                "report_path": "report.md",
                "feishu_error": "missing feishu config",
            }
        ],
        write_feishu_requested=True,
    )

    assert payload["write_feishu_requested"] is True
    assert "飞书文档发送失败" in payload["feishu_warning"]
    assert payload["created_docs"][0]["feishu_error"] == "missing feishu config"
