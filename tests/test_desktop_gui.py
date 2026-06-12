from __future__ import annotations

import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

from deployments.desktop import server
from deployments.desktop.shared import agents

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_desktop_server_routes_are_registered() -> None:
    assert "/api/health" in server.GET_ROUTES
    assert "/api/source-options" in server.GET_ROUTES
    assert "/api/settings" in server.POST_ROUTES
    assert "/api/submit" in server.POST_ROUTES
    assert "/api/export" in server.POST_ROUTES
    assert "/api/roles" in server.GET_ROUTES
    assert "/api/roles" in server.POST_ROUTES
    assert "/api/must-read" in server.GET_ROUTES
    assert "/api/must-read" in server.POST_ROUTES
    assert "/api/read/arxiv" in server.POST_ROUTES
    assert "/api/read/pdf" in server.POST_ROUTES
    assert "/api/provider-test" in server.POST_ROUTES
    assert "/api/daily/status" in server.GET_ROUTES
    assert "/api/daily/start" in server.POST_ROUTES


def test_desktop_daily_target_date_controls_backend_fetch_window() -> None:
    today = server.datetime.now().date()

    assert server._daily_days_from_body({"days": 7}) == 7  # noqa: SLF001 - GUI date contract
    assert server._daily_days_from_body({"target_date": today.isoformat(), "days": 9}) == 1  # noqa: SLF001
    assert server._daily_days_from_body({"target_date": (today - timedelta(days=2)).isoformat()}) == 3  # noqa: SLF001
    assert server._daily_days_from_body({"target_date": (today.replace(year=today.year + 1)).isoformat(), "days": 3}) == 1  # noqa: SLF001
    assert server._daily_days_from_body({"target_date": (today.replace(year=today.year - 1)).isoformat()}) == 14  # noqa: SLF001
    assert "/api/wiki/graph" in server.GET_ROUTES
    assert "/api/wiki/node" in server.POST_ROUTES
    assert callable(server.run_server)


def test_desktop_settings_exposes_storage_paths() -> None:
    settings = agents.settings()
    assert "paths" in settings
    assert "editable_env" in settings
    assert "pdf_dir" in settings["paths"]
    assert "reading_reports_dir" in settings["paths"]
    assert "wiki_dir" in settings["paths"]


def test_desktop_wiki_graph_uses_user_nodes_and_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agents.wiki_db,
        "list_nodes",
        lambda user_id, limit: [
            {
                "node_id": "paper:1",
                "node_type": "paper",
                "title": "Graph RAG Paper",
                "body": "A graph RAG paper.",
                "metadata": {},
                "keywords": "graph rag",
                "file_path": "papers/graph-rag.md",
                "score": 0.8,
                "updated_at": "2026-06-01",
            },
            {
                "node_id": "topic:rag",
                "node_type": "topic",
                "title": "RAG",
                "body": "Retrieval augmented generation.",
                "metadata": {},
                "keywords": "retrieval",
                "file_path": "topics/rag.md",
                "score": 0.7,
                "updated_at": "2026-06-01",
            },
        ],
    )

    class FakeRows:
        def fetchall(self):
            return [
                {
                    "src_id": "paper:1",
                    "dst_id": "topic:rag",
                    "relation": "same_topic",
                    "weight": 0.9,
                    "metadata_json": '{"reason": "keyword"}',
                    "created_at": "2026-06-01",
                },
                {
                    "src_id": "user:user_test",
                    "dst_id": "paper:1",
                    "relation": "interested_in",
                    "weight": 1.0,
                    "metadata_json": "{}",
                    "created_at": "2026-06-01",
                },
            ]

    class FakeConnection:
        def execute(self, *_args, **_kwargs):
            return FakeRows()

        def close(self):
            return None

    monkeypatch.setattr(agents.db_ops, "get_connection", lambda: FakeConnection())

    graph = agents.wiki_graph("user_test")

    assert graph["source"] == "wiki_db"
    assert {node["node_id"] for node in graph["nodes"]} == {"user:user_test", "paper:1", "topic:rag"}
    assert [edge["relation"] for edge in graph["edges"]] == ["same_topic", "interested_in"]


def test_desktop_wiki_graph_prefers_edge_connected_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents.wiki_db, "list_nodes", lambda user_id, limit: [])

    class FakeRows:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class FakeConnection:
        def execute(self, sql, *_args, **_kwargs):
            if "FROM wiki_edges" in sql:
                return FakeRows(
                    [
                        {
                            "src_id": "paper:important",
                            "dst_id": "topic:rag",
                            "relation": "cites_method",
                            "weight": 0.95,
                            "metadata_json": "{}",
                            "created_at": "2026-06-01",
                        }
                    ]
                )
            if "FROM wiki_nodes" in sql:
                return FakeRows(
                    [
                        {
                            "node_id": "paper:important",
                            "node_type": "paper",
                            "title": "Important Paper",
                            "body": "A highly connected paper.",
                            "metadata_json": "{}",
                            "keywords": "rag",
                            "file_path": "papers/important.md",
                            "score": 0.9,
                            "updated_at": "2026-06-01",
                        },
                        {
                            "node_id": "topic:rag",
                            "node_type": "topic",
                            "title": "RAG",
                            "body": "Retrieval augmented generation.",
                            "metadata_json": "{}",
                            "keywords": "retrieval",
                            "file_path": "topics/rag.md",
                            "score": 0.8,
                            "updated_at": "2026-06-01",
                        },
                    ]
                )
            return FakeRows([])

        def close(self):
            return None

    monkeypatch.setattr(agents.db_ops, "get_connection", lambda: FakeConnection())

    graph = agents.wiki_graph("user_test")

    assert {node["node_id"] for node in graph["nodes"]} == {"paper:important", "topic:rag"}
    assert graph["edges"][0]["relation"] == "cites_method"


def test_desktop_wiki_node_update_preserves_node_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = {
        "node_id": "topic:rag",
        "node_type": "topic",
        "title": "Old RAG",
        "body": "old body",
        "metadata": {"rank": 1},
        "keywords": "rag",
        "source_type": "topic_clustering",
        "source_ref": "keyword_flush",
        "file_path": "topics/rag.md",
    }
    captured = {}

    monkeypatch.setattr(agents.wiki_db, "get_node", lambda user_id, node_id: existing)

    def fake_upsert_node(**kwargs):
        captured.update(kwargs)
        return {**existing, **kwargs}

    monkeypatch.setattr(agents.wiki_db, "upsert_node", fake_upsert_node)

    result = agents.update_wiki_node("user_test", "topic:rag", title="New RAG", body="new body")

    assert result["node"]["title"] == "New RAG"
    assert captured["body"] == "new body"
    assert captured["metadata"] == {"rank": 1}
    assert captured["file_path"] == "topics/rag.md"


def test_desktop_source_options_exposes_push_sources() -> None:
    options = agents.source_options()

    assert any(item["id"] == "cs.LG" for item in options["arxiv_categories"])
    assert any(item["id"] == "ICLR" for item in options["conferences"])
    iclr = next(item for item in options["conferences"] if item["id"] == "ICLR")
    assert iclr["source"]
    assert iclr["venue_id"]
    assert "acceptance_timeline" in iclr
    assert "conference_date" in iclr
    assert options["journals"]


def test_desktop_save_settings_updates_env_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("PAPERFLOW_LLM_MODEL=old-model\nOPENAI_API_KEY=sk-existing\n", encoding="utf-8")
    monkeypatch.setattr(agents, "ENV_PATH", env_path)

    result = agents.save_settings(
        {
            "PAPERFLOW_LLM_MODEL": "new-model",
            "OPENAI_API_KEY": "***",
            "PAPERFLOW_WRITE_FEISHU": "true",
            "PAPERFLOW_ENABLE_ARXIV": "false",
            "PAPERFLOW_CUSTOM_RSS_URLS": "https://example.com/rss.xml",
            "PAPERFLOW_CONFERENCE_ACCESS_MODE": "credential",
            "PAPERFLOW_CONFERENCE_COOKIE_FILE": r"C:\paperflow\cookies\neurips.txt",
            "SEMANTIC_SCHOLAR_API_KEY": "s2-test-key",
            "OPENREVIEW_TOKEN": "or-test-token",
            "UNSUPPORTED_KEY": "ignored",
        }
    )

    text = env_path.read_text(encoding="utf-8")
    assert "PAPERFLOW_LLM_MODEL=new-model" in text
    assert "OPENAI_API_KEY=sk-existing" in text
    assert "PAPERFLOW_WRITE_FEISHU=true" in text
    assert "PAPERFLOW_ENABLE_ARXIV=false" in text
    assert "PAPERFLOW_CUSTOM_RSS_URLS=https://example.com/rss.xml" in text
    assert "PAPERFLOW_CONFERENCE_ACCESS_MODE=credential" in text
    assert r"PAPERFLOW_CONFERENCE_COOKIE_FILE=C:\paperflow\cookies\neurips.txt" in text
    assert "SEMANTIC_SCHOLAR_API_KEY=s2-test-key" in text
    assert "OPENREVIEW_TOKEN=or-test-token" in text
    assert "UNSUPPORTED_KEY" not in text
    assert result["paths"]["write_feishu"] is True
    assert result["source_preferences"]["conference_access_mode"] == "credential"
    assert result["source_preferences"]["auth_status"]["semantic_scholar_api_key"] is True


def test_desktop_source_settings_explain_conference_auth() -> None:
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert 'name="conferenceAccessMode"' in html
    assert 'value="credential"' in html
    assert 'data-env-key="SEMANTIC_SCHOLAR_API_KEY"' in html
    assert 'data-env-key="OPENREVIEW_TOKEN"' in html
    assert 'data-env-key="PAPERFLOW_CONFERENCE_COOKIE_FILE"' in html
    assert 'id="settingConferenceList"' in html
    assert "settingConferenceSelect" not in html
    assert "settings-model" in html
    assert "settings-source" in html
    assert "settings-storage" in html
    assert "模型与密钥" in html
    assert "论文来源" in html
    assert "需要登录的会议源不要混在普通下拉框里" in html
    assert "updateSourceAuthStatus(sourcePrefs, env)" in script
    assert "renderConferenceSettings(sourcePrefs)" in script
    assert "selectedSettingConferences().join(\",\")" in script
    assert "conferenceAccessInfo(item)" in script
    assert "syncConferenceAccessUi(input.value)" in script
    assert "settingEnableCustomRss" in script
    assert 'input.disabled = normalized !== "credential"' in script
    assert "PAPERFLOW_CONFERENCE_ACCESS_MODE" in script
    assert ".source-auth-panel" in css
    assert ".conference-source-list" in css
    assert ".conference-source-item.active" in css
    assert ".settings-source .source-auth-panel" in css
    assert "grid-template-columns: minmax(0, 1fr) minmax(320px, 360px)" in css
    assert '[data-mode="credential"]' in css
    assert "label:has(input:checked)" in css


def test_desktop_health_is_json_ready() -> None:
    health = agents.health()
    assert health["ok"] is True
    assert "database" in health


def test_desktop_paper_card_backfills_arxiv_links() -> None:
    card = agents._paper_card(  # noqa: SLF001 - GUI payload normalization contract
        {"title": "Arxiv Paper", "arxiv_id": "2606.02556v1", "source": "arxiv"},
        1,
    )

    assert card["url"] == "https://arxiv.org/abs/2606.02556v1"
    assert card["pdf_url"] == "https://arxiv.org/pdf/2606.02556v1"
    assert card["arxiv_id"] == "2606.02556v1"
    assert card["source"] == "arxiv"


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


def test_desktop_backfills_reused_reading_report_to_wiki(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    report_path = tmp_path / "reading-report.md"
    report_path.write_text(
        "---\n"
        'title: "Reused Report"\n'
        'arxiv_id: "2606.12087v1"\n'
        "---\n"
        "# Reused Report\n\nImportant report body.",
        encoding="utf-8",
    )
    captured = {}

    def fake_ingest(**kwargs):
        captured.update(kwargs)
        return {"paper_node": "paper:2606.12087v1", "section_count": 0}

    monkeypatch.setattr(agents.reading_agent, "ingest_reading_report_to_wiki", fake_ingest)

    docs = [{"paper": {"title": "Fallback title"}, "report_path": str(report_path), "reused": True}]
    count = agents._backfill_docs_to_wiki("user_test", docs)  # noqa: SLF001 - GUI backfill contract

    assert count == 1
    assert captured["user_id"] == "user_test"
    assert captured["paper"]["arxiv_id"] == "2606.12087v1"
    assert "Important report body." in captured["report_content"]
    assert docs[0]["wiki_ingest"]["paper_node"] == "paper:2606.12087v1"


def test_desktop_paper_card_read_button_generates_single_report() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")

    assert 'data-action="read"' in script
    assert '"加载中"' in script
    assert '"精读报告"' in script
    assert "readSinglePaper" in script
    assert "selected_numbers: [number]" in script
    assert 'button.dataset.action === "select"' not in script


def test_desktop_wiki_frontend_derives_architecture_from_backend_graph() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert "buildWikiMap" in script
    assert "conceptEntriesFromGraph" in script
    assert "candidateLabelsForNode" in script
    assert "architecture:core" in script
    assert "知识库架构" in script
    assert "原始节点" in script
    assert "related_papers" in script
    assert "setWikiMapFocus(\"architecture:core\")" in script
    assert "wikiMapCatalog" not in script
    assert "concept:structured-memory" not in script
    assert "concept:agent" not in script
    assert "&limit=48" in script
    assert "const query = rawQuery ||" not in script
    assert 'DEMO_MODE ? demoWikiNodes : []' in script
    assert 'class="wiki-entry-body"' in html
    assert "Wiki 架构图" in html
    assert "grid-template-columns: minmax(760px, 1fr) 292px" in css
    assert "repeating-linear-gradient(115deg" in css
    assert ".wiki-evidence-pane" in css
    assert "position: sticky" in css
    assert "left: calc(100% + 9px)" in css
    assert 'setWikiEntry("结构化记忆", "跨论文沉淀的 memory slot' not in script


def test_desktop_wiki_frontend_recovers_when_graph_is_empty() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")

    assert "wiki_search_fallback" in script
    assert "!state.wikiNodes.length && Number(stats.nodes || 0) > 0" in script
    assert "/api/wiki/search?user_id=" in script


def test_desktop_feedback_submit_shows_user_confirmation() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert 'id="feedbackToast"' in html
    assert 'id="paperFeedbackResult"' in html
    assert ".feedback-toast.success" in css
    assert ".paper-feedback-result.success" in css
    assert ".paper-feedback-result.pending" in css
    assert "showSubmitResult(data, generateReports)" in script
    assert "showPaperFeedback(result.type, result.title, result.detail)" in script
    assert "setSubmitButtonsBusy(true, generateReports)" in script
    assert "正在提交反馈" in script
    assert "反馈已提交" in script
    assert "已写入本地反馈" in script
    assert "反馈提交失败" in script
    assert "await loadWiki()" in script


def test_desktop_paper_date_and_metrics_sync_with_backend() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert '<strong id="candidateStat">-</strong>' in html
    assert '<strong id="filteredStat">-</strong>' in html
    assert 'id="cacheSizeStat"' in html
    assert "2.8GB" not in html
    assert "cache_display" in script
    assert "storage_stats" in script
    assert 'new Date("2026-06-10")' not in script
    assert "function todayDateValue()" in script
    assert "function syncDateControls()" in script
    assert '$("paperDate").value = todayDateValue()' in script
    assert "selectedDateFetchDays()" in script
    assert 'target_date: $("paperDate").value' in script
    assert "/api/daily/status?task_id=" in script
    assert "pollDailyTask(data.task?.task_id" in script
    assert "metadata.total_fetched ?? metadata.fetched_count ?? papers.length ?? 0" in script
    assert "metadata.paper_count ?? metadata.filtered_count ?? metadata.ranked_count ?? papers.length ?? 0" in script
    assert 'task.status === "completed"' in script
    assert "renderPush(task.push || task.preview_push" not in script
    assert "后台仍在拉取和排序论文" in script
    assert ".paper-list.empty.syncing" in css
    assert "|| 247" not in script


def test_desktop_settings_exposes_backend_storage_stats(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_dir = tmp_path / "pdf"
    reports_dir = tmp_path / "reports"
    wiki_dir = tmp_path / "wiki"
    for path in (pdf_dir, reports_dir, wiki_dir):
        path.mkdir()
    (pdf_dir / "a.pdf").write_bytes(b"a" * 1024)
    (reports_dir / "b.md").write_bytes(b"b" * 1024)
    (wiki_dir / "c.md").write_bytes(b"c" * 1024)

    monkeypatch.setenv("PAPERFLOW_PDF_DIR", str(pdf_dir))
    monkeypatch.setenv("PAPERFLOW_READING_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("PAPERFLOW_WIKI_DIR", str(wiki_dir))

    payload = agents.settings()

    assert payload["storage_stats"]["cache_bytes"] == 3072
    assert payload["storage_stats"]["cache_display"] == "3.0KB"


def test_desktop_chat_sources_do_not_fallback_to_demo_in_real_mode() -> None:
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")

    assert "Efficient Test-Time Scaling</span>" not in html
    assert "Multi-Modal RAG</span>" not in html
    assert "Wiki: 结构化记忆</span>" not in html
    assert "function renderChatSources(sources = DEMO_MODE ? demoSources : [])" in script
    assert "data.sources || demoSources" not in script
    assert "暂无后端引用来源" in script


def test_desktop_daily_push_preserves_empty_push_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_daily_push(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "push_id": "push_empty_001",
            "paper_count": 0,
            "total_fetched": 15,
            "reason": "all_candidates_filtered",
        }

    monkeypatch.setattr(
        agents.daily_agent,
        "daily_push",
        fake_daily_push,
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

    payload = agents.run_daily_push(
        "test_user",
        days=1,
        arxiv_categories=["cs.LG", "cs.CV"],
        conferences=["ICLR"],
        journals=[],
    )

    assert payload["push"]["push_id"] == "push_empty_001"
    assert payload["push"]["papers"] == []
    assert payload["push"]["metadata"]["paper_count"] == 0
    assert payload["push"]["metadata"]["total_fetched"] == 15
    assert payload["push"]["metadata"]["reason"] == "all_candidates_filtered"
    assert captured["arxiv_categories"] == ["cs.LG", "cs.CV"]
    assert captured["conferences"] == ["ICLR"]
    assert captured["journals"] == []


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
