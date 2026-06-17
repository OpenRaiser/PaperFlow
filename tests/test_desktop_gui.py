from __future__ import annotations

import threading
import time
import importlib
from datetime import timedelta
from pathlib import Path

import pytest

from deployments.desktop import server
from deployments.desktop.shared import agents

reading_agent = importlib.import_module("agents.reading-agent.main")

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_desktop_server_routes_are_registered() -> None:
    server_source = (PROJECT_ROOT / "deployments/desktop/server.py").read_text(encoding="utf-8")

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
    assert "/api/wiki/mentions" in server.GET_ROUTES
    assert "/api/wiki/ask/stream" in server.POST_ROUTES
    assert "/api/github/sync" in server.POST_ROUTES
    assert "/api/chat/sessions" in server.GET_ROUTES
    assert "/api/chat/session" in server.GET_ROUTES
    assert "/api/chat/session" in server.POST_ROUTES
    assert "/api/chat/session/delete" in server.POST_ROUTES
    assert "/api/chat/sessions/clear" in server.POST_ROUTES
    assert 'self.send_header("Cache-Control", "no-store")' in server_source


def test_desktop_wiki_stream_helpers_emit_sse_frames() -> None:
    frame = server._sse_bytes("chunk", {"text": "引用 [1]"})  # noqa: SLF001 - stream wire contract

    assert frame.decode("utf-8") == 'event: chunk\ndata: {"text": "引用 [1]"}\n\n'
    assert server._stream_chunks("abcdef", size=2) == ["ab", "cd", "ef"]  # noqa: SLF001
    source = (PROJECT_ROOT / "deployments/desktop/server.py").read_text(encoding="utf-8")
    assert "agents.wiki_ask_stream" in source
    assert "_api_wiki_ask({}, body)" not in source


def test_desktop_language_selector_and_response_language_contract() -> None:
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert 'class="language-picker"' in html
    assert 'id="languageSelect"' in html
    assert 'value="zh"' in html
    assert 'value="en"' in html
    assert ".language-picker select" in css
    assert "toggleLocale" not in script
    assert "function setLocale(locale)" in script
    assert "function responseLanguage()" in script
    assert "response_language: responseLanguage()" in script
    assert 'response_language: responseLanguage() })' in script
    assert '$("languageSelect")?.addEventListener("change", (event) => setLocale(event.target.value))' in script


def test_desktop_locale_covers_settings_and_wiki_dynamic_text() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")

    assert 'setText("#syncGithubBtn", text.wiki.githubSync.button);' in script
    assert 'setLabelTexts(".source-auth-fields label", text.settings.sourceFieldLabels);' in script
    assert 'sourceFieldLabels: ["Semantic Scholar API Key", "OpenReview username", "OpenReview token", "Conference cookie file"]' in script
    assert "text.settings.notesGitReview" in script

    assert '["当前用户画像", "Current User Profile"]' in script
    assert '["多模态推理", "Multimodal Reasoning"]' in script
    assert '["结构化记忆", "Structured Memory"]' in script
    assert "function localizeWikiText(value)" in script
    assert "return localizeWikiText(rawGraphTitle(node));" in script
    assert "return localizeWikiText(rawGraphBody(node));" in script
    assert "return [rawGraphTitle(node), rawGraphBody(node), node?.keywords, node?.node_type, graphId(node)]" in script
    assert 'data-node-title="${escapeHtml(rawGraphTitle(node))}"' in script
    assert '$("wikiEntryTitle").dataset.rawTitle = rawTitle;' in script
    assert 'title: $("wikiEntryTitle").dataset.rawTitle || $("wikiEntryTitle").textContent,' in script


def test_desktop_server_forwards_response_language_to_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(agents, "wiki_ask", lambda **kwargs: captured.setdefault("wiki", kwargs) or {"text": ""})
    monkeypatch.setattr(agents, "create_reading_reports", lambda **kwargs: captured.setdefault("read", kwargs) or {"created_docs": []})
    monkeypatch.setattr(agents, "sync_reading_notes_github", lambda user_id, response_language="zh": captured.setdefault("github", {"user_id": user_id, "response_language": response_language}) or {"ok": True})

    server.POST_ROUTES["/api/wiki/ask"]({}, {"user_id": "user_test", "question": "What is RAG?", "response_language": "en"})
    server.POST_ROUTES["/api/read"]({}, {"user_id": "user_test", "push_id": "push_test", "selected_numbers": [1], "response_language": "en"})
    server.POST_ROUTES["/api/github/sync"]({}, {"user_id": "user_test", "response_language": "en"})

    assert captured["wiki"]["response_language"] == "en"
    assert captured["read"]["response_language"] == "en"
    assert captured["github"]["response_language"] == "en"


def test_desktop_daily_target_date_controls_backend_fetch_window() -> None:
    today = server.datetime.now().date()
    server_source = (PROJECT_ROOT / "deployments/desktop/server.py").read_text(encoding="utf-8")

    assert server._daily_days_from_body({"days": 7}) == 7  # noqa: SLF001 - GUI date contract
    assert server._daily_days_from_body({"target_date": today.isoformat(), "days": 9}) == 1  # noqa: SLF001
    assert server._daily_days_from_body({"target_date": (today - timedelta(days=2)).isoformat()}) == 3  # noqa: SLF001
    assert server._daily_days_from_body({"target_date": (today.replace(year=today.year + 1)).isoformat(), "days": 3}) == 1  # noqa: SLF001
    assert server._daily_days_from_body({"target_date": (today.replace(year=today.year - 1)).isoformat()}) == 14  # noqa: SLF001
    assert "/api/wiki/graph" in server.GET_ROUTES
    assert "daily_scope" in server_source
    assert "daily_month" in server_source
    assert "/api/wiki/node" in server.POST_ROUTES
    assert callable(server.run_server)


def test_desktop_settings_exposes_storage_paths() -> None:
    settings = agents.settings()
    assert "paths" in settings
    assert "editable_env" in settings
    assert "pdf_dir" in settings["paths"]
    assert "reading_reports_dir" in settings["paths"]
    assert "wiki_dir" in settings["paths"]
    assert "notes_root_dir" in settings["paths"]
    assert "reading_notes_git_dir" in settings["paths"]


def test_desktop_settings_page_renders_storage_paths_as_inputs() -> None:
    html = (PROJECT_ROOT / "deployments" / "desktop" / "static" / "index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deployments" / "desktop" / "static" / "desktop.js").read_text(encoding="utf-8")

    assert '<script src="desktop.js"></script>' in html
    assert 'id="saveStorageSettingsBtn" class="primary" type="button">保存设置</button>' in html
    assert 'data-env-key="${escapeHtml(row.envKey)}"' in script
    assert "editable-path-row" in script
    assert '$("refreshSettingsBtn")?.addEventListener("click", () => runAction(loadSettings, "加载设置"));' in script
    assert '$("saveStorageSettingsBtn").addEventListener("click", () => runAction(saveSettings, "保存设置"));' in script
    assert "PAPERFLOW_NOTES_ROOT_DIR" in script
    assert 'data-derived-path="${escapeHtml(row.derivedRole)}"' in script
    assert "readonly autocomplete" in script
    assert "updateDerivedNotesPathsPreview" in script
    assert "Daily Note ${currentYear}" in script
    assert "PAPERFLOW_READING_NOTES_GIT_REMOTE" in script
    assert "PAPERFLOW_READING_NOTES_GIT_BRANCH" in script
    assert 'id="syncGithubBtn"' in html
    assert 'id="notesGitLlmReviewSetting"' in html


def test_desktop_wiki_graph_uses_user_nodes_and_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents, "_configured_wiki_root", lambda: None)
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
                "keywords": "rag",
                "file_path": "papers/graph-rag.md",
                "score": 0.8,
                "source_type": "reading_report",
                "updated_at": "2026-06-01",
            },
            {
                "node_id": "topic:rag",
                "node_type": "topic",
                "title": "RAG",
                "body": "Retrieval augmented generation.",
                "metadata": {},
                "keywords": "rag",
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

    graph = agents.wiki_graph("user_test", daily_scope="wiki_db")

    assert graph["source"] == "wiki_db"
    assert {node["node_id"] for node in graph["nodes"]} == {"user:user_test", "paper:1", "topic:rag"}
    assert {"same_topic", "interested_in", "belongs_to"}.issubset({edge["relation"] for edge in graph["edges"]})


def test_desktop_wiki_graph_prefers_edge_connected_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents, "_configured_wiki_root", lambda: None)
    monkeypatch.setattr(
        agents.wiki_db,
        "list_nodes",
        lambda user_id, limit: [
            {
                "node_id": "paper:important",
                "node_type": "paper",
                "title": "Important Paper",
                "body": "A highly connected paper.",
                "metadata": {"report_path": "/tmp/important.md"},
                "keywords": "rag",
                "file_path": "papers/important.md",
                "score": 0.9,
                "source_type": "reading_report",
                "updated_at": "2026-06-01",
            },
            {
                "node_id": "paper:candidate",
                "node_type": "paper",
                "title": "Candidate Paper",
                "body": "A daily candidate paper.",
                "metadata": {"category": "maybe_interested"},
                "keywords": "rag",
                "file_path": "papers/candidate.md",
                "score": 0.99,
                "source_type": "daily_push",
                "updated_at": "2026-06-01",
            },
            {
                "node_id": "topic:rag",
                "node_type": "topic",
                "title": "RAG",
                "body": "Retrieval augmented generation.",
                "metadata": {"canonical_name": "rag"},
                "keywords": "rag",
                "file_path": "topics/rag.md",
                "score": 0.8,
                "updated_at": "2026-06-01",
            },
        ],
    )

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

    graph = agents.wiki_graph("user_test", daily_scope="wiki_db")

    assert {node["node_id"] for node in graph["nodes"]} == {"paper:important", "topic:rag"}
    assert "paper:candidate" not in {node["node_id"] for node in graph["nodes"]}
    assert {"cites_method", "belongs_to"}.issubset({edge["relation"] for edge in graph["edges"]})


def test_desktop_wiki_graph_excludes_section_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents, "_configured_wiki_root", lambda: None)
    monkeypatch.setattr(
        agents.wiki_db,
        "list_nodes",
        lambda user_id, limit: [
            {
                "node_id": "paper:1",
                "node_type": "paper",
                "title": "Paper",
                "body": "Paper body",
                "metadata": {"report_path": "/tmp/paper.md"},
                "keywords": "",
                "file_path": "papers/paper.md",
                "score": 1,
                "source_type": "reading_report",
                "updated_at": "2026-06-01",
            },
            {
                "node_id": "section:1#abstract",
                "node_type": "section",
                "title": "Abstract",
                "body": "Abstract body",
                "metadata": {"parent_paper_id": "paper:1"},
                "keywords": "",
                "file_path": "sections/abstract.md",
                "score": 1,
                "source_type": "reading_report",
                "updated_at": "2026-06-01",
            },
        ],
    )

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
                            "src_id": "paper:1",
                            "dst_id": "section:1#abstract",
                            "relation": "contains_section",
                            "weight": 1.0,
                            "metadata_json": "{}",
                            "created_at": "2026-06-01",
                        },
                        {
                            "src_id": "user:user_test",
                            "dst_id": "paper:1",
                            "relation": "read",
                            "weight": 1.0,
                            "metadata_json": "{}",
                            "created_at": "2026-06-01",
                        },
                    ]
                )
            if "FROM wiki_nodes" in sql:
                return FakeRows(
                    [
                        {
                            "node_id": "paper:1",
                            "node_type": "paper",
                            "title": "Paper",
                            "body": "Paper body",
                            "metadata_json": "{}",
                            "keywords": "",
                            "file_path": "papers/paper.md",
                            "score": 1,
                            "updated_at": "2026-06-01",
                        },
                        {
                            "node_id": "section:1#abstract",
                            "node_type": "section",
                            "title": "Abstract",
                            "body": "Abstract body",
                            "metadata_json": "{}",
                            "keywords": "",
                            "file_path": "sections/abstract.md",
                            "score": 1,
                            "updated_at": "2026-06-01",
                        },
                    ]
                )
            return FakeRows([])

        def close(self):
            return None

    monkeypatch.setattr(agents.db_ops, "get_connection", lambda: FakeConnection())

    graph = agents.wiki_graph("user_test", daily_scope="wiki_db")

    assert {node["node_id"] for node in graph["nodes"]} == {"user:user_test", "paper:1"}
    assert [edge["relation"] for edge in graph["edges"]] == ["read"]


def test_desktop_wiki_graph_defaults_to_reading_reports_and_topics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents, "_configured_wiki_root", lambda: None)
    monkeypatch.setattr(
        agents.wiki_db,
        "list_nodes",
        lambda user_id, limit, node_type=None: [
            {
                "node_id": "paper:read",
                "node_type": "paper",
                "title": "Read Paper",
                "body": "Summary",
                "metadata": {"report_path": "/tmp/read.md"},
                "keywords": "retrieval agent",
                "file_path": "papers/read.md",
                "source_type": "reading_report",
            },
            {
                "node_id": "paper:candidate",
                "node_type": "paper",
                "title": "Candidate Paper",
                "body": "Candidate",
                "metadata": {"category": "maybe_interested"},
                "keywords": "retrieval",
                "file_path": "papers/candidate.md",
                "source_type": "daily_push",
            },
            {
                "node_id": "topic:retrieval",
                "node_type": "topic",
                "title": "Retrieval",
                "body": "Topic",
                "metadata": {"canonical_name": "retrieval"},
                "keywords": "retrieval",
                "file_path": "topics/retrieval.md",
                "source_type": "topic_clustering",
            },
            {
                "node_id": "section:read#abstract",
                "node_type": "section",
                "title": "Abstract",
                "body": "Abstract",
                "metadata": {"parent_paper_id": "paper:read"},
                "keywords": "retrieval",
                "file_path": "sections/abstract.md",
                "source_type": "reading_report",
            },
        ],
    )

    class FakeRows:
        def fetchall(self):
            return []

    class FakeConnection:
        def execute(self, *_args, **_kwargs):
            return FakeRows()

        def close(self):
            return None

    monkeypatch.setattr(agents.db_ops, "get_connection", lambda: FakeConnection())

    graph = agents.wiki_graph("user_test", daily_scope="wiki_db")

    assert {node["node_id"] for node in graph["nodes"]} == {"paper:read", "topic:retrieval"}
    assert "paper:candidate" not in {node["node_id"] for node in graph["nodes"]}
    assert "section:read#abstract" not in {node["node_id"] for node in graph["nodes"]}
    assert graph["edges"] == [
        {
            "src_id": "paper:read",
            "dst_id": "topic:retrieval",
            "relation": "belongs_to",
            "weight": 0.75,
            "metadata": {"source": "keyword_match"},
        }
    ]


def test_desktop_wiki_graph_can_use_daily_note_scope(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    daily_root = tmp_path / "Daily Note"
    year_dir = daily_root / "Daily Note 2026"
    year_dir.mkdir(parents=True)
    may_note = year_dir / "Daily Note - May 2026.md"
    jun_note = year_dir / "Daily Note - Jun 2026.md"
    may_note.write_text(
        "# Older Topic\n\n## Older Paper\n\n- **Older summary.**\n",
        encoding="utf-8",
    )
    jun_note.write_text(
        "# AI Agents\n\n"
        "<!-- paperflow-topic-summary:start -->\n"
        "## PaperFlow Summary\n"
        "- 概念：AI Agents\n"
        "- 方法：reward modeling, orchestration\n"
        "- 论文/报告：1 篇\n"
        "- Reward Modeling for Multi-Agent Orchestration\n"
        "- 画像/前沿：多智能体编排是当前前沿。\n"
        "<!-- paperflow-topic-summary:end -->\n\n"
        "## Reward Modeling for Multi-Agent Orchestration\n\n"
        "- **OrchRM summary.**\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PAPERFLOW_READING_REPORTS_DIR", str(daily_root))
    monkeypatch.setenv("PAPERFLOW_PDF_DIR", str(daily_root))
    monkeypatch.setattr(agents, "_configured_wiki_root", lambda: None)
    monkeypatch.setattr(
        agents.wiki_db,
        "list_nodes",
        lambda user_id, limit: [
            {
                "node_id": "paper:orchrm",
                "node_type": "paper",
                "title": "Reward Modeling for Multi-Agent Orchestration",
                "body": "Old body",
                "metadata": {"report_path": "/tmp/orchrm.md"},
                "keywords": "agent",
                "file_path": "papers/orchrm.md",
                "source_type": "reading_report",
            }
        ],
    )

    latest = agents.wiki_graph("cheng tan", daily_scope="latest")
    month = agents.wiki_graph("cheng tan", daily_scope="month", daily_month="2026-05")
    all_notes = agents.wiki_graph("cheng tan", daily_scope="all")

    assert latest["source"] == "daily_note"
    latest_titles = {node["title"] for node in latest["nodes"]}
    latest_types = {node["node_type"] for node in latest["nodes"]}
    assert {"AI Agents", "Reward Modeling for Multi-Agent Orchestration", "reward modeling", "orchestration"}.issubset(latest_titles)
    assert {"topic", "paper", "method"}.issubset(latest_types)
    assert "trajectory" not in latest_types
    assert any(node["body"] == "OrchRM summary." for node in latest["nodes"])
    assert {node["title"] for node in month["nodes"]} == {"Older Topic", "Older Paper"}
    assert {
        "Older Topic",
        "Older Paper",
        "AI Agents",
        "Reward Modeling for Multi-Agent Orchestration",
    }.issubset({node["title"] for node in all_notes["nodes"]})


def test_desktop_wiki_search_filters_to_configured_wiki_directory(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    wiki_root = tmp_path / "wiki"
    kept = wiki_root / "user_test" / "papers" / "kept.md"
    kept.parent.mkdir(parents=True)
    kept.write_text("# kept", encoding="utf-8")
    monkeypatch.setattr(agents, "_configured_wiki_root", lambda: wiki_root)
    monkeypatch.setattr(
        agents.wiki_db,
        "search_nodes",
        lambda *_args, **_kwargs: [
            {
                "node_id": "paper:kept",
                "node_type": "paper",
                "title": "Kept",
                "body": "exists in configured wiki dir",
                "metadata": {},
                "keywords": "",
                "file_path": "user_test/papers/kept.md",
                "updated_at": "2026-06-01",
            },
            {
                "node_id": "paper:old",
                "node_type": "paper",
                "title": "Old",
                "body": "old mirror path",
                "metadata": {},
                "keywords": "",
                "file_path": "user_test/papers/old.md",
                "updated_at": "2026-06-01",
            },
        ],
    )

    result = agents.wiki_search("user_test", query="paper")

    assert [node["node_id"] for node in result["nodes"]] == ["paper:kept"]


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


def test_desktop_wiki_ask_routes_mentions_into_local_cited_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents, "ENV_PATH", PROJECT_ROOT / ".missing-test-env")
    monkeypatch.delenv("PAPERFLOW_WIKI_DIR", raising=False)
    selected_node = {
        "node_id": "paper:structured-memory",
        "node_type": "paper",
        "title": "Structured Memory Paper",
        "body": "Memory slots improve grounded retrieval.",
        "metadata": {"url": "https://example.com/paper"},
        "keywords": "memory rag",
        "file_path": "reports/structured-memory.md",
        "score": 0.95,
        "updated_at": "2026-06-01",
    }
    captured = {}

    monkeypatch.setattr(agents.wiki_db, "get_node", lambda user_id, node_id: selected_node if node_id == selected_node["node_id"] else None)
    monkeypatch.setattr(agents.wiki_db, "search_nodes", lambda user_id, query, limit=5, node_type=None: [selected_node])

    def fake_answer_question(user_id, question, *, limit=8, pinned_nodes=None, **_kwargs):
        captured["question"] = question
        captured["limit"] = limit
        captured["pinned_nodes"] = pinned_nodes or []
        return {
            "text": "结构化记忆方法更强调长期证据槽。[1]",
            "citations": [
                {
                    "index": 1,
                    "node_id": selected_node["node_id"],
                    "title": selected_node["title"],
                    "node_type": selected_node["node_type"],
                    "excerpt": "Memory slots improve grounded retrieval.",
                    "source_type": "reading_report",
                    "source_id": "report-1",
                    "metadata": selected_node["metadata"],
                }
            ],
        }

    monkeypatch.setattr(agents.wiki_answer, "answer_question", fake_answer_question)

    payload = agents.wiki_ask(
        "user_test",
        "对比 @[Structured Memory Paper](paper:structured-memory) 的方法",
        mentions=[{"node_id": "paper:structured-memory", "title": "Structured Memory Paper"}],
    )

    assert payload["mode"] == "wiki"
    assert payload["retrieval_required"] is True
    assert payload["routing_reason"] == "explicit_mention"
    assert captured["pinned_nodes"][0]["node_id"] == "paper:structured-memory"
    assert payload["sources"][0]["title"] == "Structured Memory Paper"
    assert payload["sources"][0]["url"] == "https://example.com/paper"


def test_desktop_wiki_mentions_use_daily_note_deep_reading_entries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    report = tmp_path / "deep-reading.md"
    report.write_text("# Deep report\n\nDetailed report body.", encoding="utf-8")
    monkeypatch.setattr(
        agents,
        "_daily_note_reading_entries",
        lambda **_kwargs: [
            {
                "title": "Daily Note Deep Reading Paper",
                "topic": "Language Models",
                "summary": "A paper selected from Daily Note deep reading.",
                "report_path": str(report),
                "daily_note": "/vault/Daily Note - Jun 2026.md",
            }
        ],
    )

    payload = agents.daily_note_mentions("user_test", query="Daily", limit=6)

    assert payload["source"] == "daily_note_deep_reading"
    assert payload["nodes"][0]["title"] == "Daily Note Deep Reading Paper"
    assert payload["nodes"][0]["metadata"]["source"] == "daily_note_deep_reading"
    assert payload["nodes"][0]["metadata"]["report_path"] == str(report)


def test_desktop_wiki_ask_pins_daily_note_readings_for_trend_questions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    first_report = tmp_path / "agentic-memory.md"
    first_report.write_text("Agentic memory improves long horizon paper triage and report grounding.", encoding="utf-8")
    second_report = tmp_path / "multimodal-retrieval.md"
    second_report.write_text("Retrieval agents connect paper figures, text, and user feedback.", encoding="utf-8")
    daily_entries = [
        {
            "title": "Agentic Memory for Scientific Reading",
            "topic": "Memory, Personalization & Long-Horizon Agents",
            "summary": "Agentic memory improves long horizon paper triage.",
            "report_path": str(first_report),
            "daily_note": "/vault/Daily Note - Jun 2026.md",
        },
        {
            "title": "Multimodal Retrieval Agents",
            "topic": "Multimodal Models & Visual Reasoning",
            "summary": "Retrieval agents connect paper figures, text, and user feedback.",
            "report_path": str(second_report),
            "daily_note": "/vault/Daily Note - Jun 2026.md",
        },
    ]
    captured = {}

    monkeypatch.setattr(agents, "_daily_note_reading_entries", lambda **_kwargs: daily_entries)

    def fake_answer_question(user_id, question, *, limit=8, pinned_nodes=None, **_kwargs):
        captured["question"] = question
        captured["pinned_nodes"] = pinned_nodes or []
        return {
            "text": "最近推送集中在 agentic memory 和 multimodal retrieval。[1][2]",
            "citations": [],
        }

    monkeypatch.setattr(agents.wiki_answer, "answer_question", fake_answer_question)

    payload = agents.wiki_ask("user_test", "总结一下我的论文趋势")

    assert payload["mode"] == "wiki"
    assert payload["routing_reason"] == "local_research_context"
    assert [node["title"] for node in captured["pinned_nodes"]] == [
        "Agentic Memory for Scientific Reading",
        "Multimodal Retrieval Agents",
    ]
    first = captured["pinned_nodes"][0]
    second = captured["pinned_nodes"][1]
    assert first["node_type"] == "paper"
    assert first["metadata"]["source"] == "daily_note_deep_reading"
    assert "Agentic memory improves long horizon" in first["body"]
    assert first["metadata"]["report_path"] == str(first_report)
    assert "Retrieval agents connect paper figures" in second["body"]


def test_desktop_wiki_ask_stream_pins_daily_note_readings_for_trend_questions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    report = tmp_path / "personalized-trend.md"
    report.write_text("User feedback is aggregated into daily research trend summaries.", encoding="utf-8")
    daily_entry = {
        "title": "Personalized Research Trend Mining",
        "topic": "Memory, Personalization & Long-Horizon Agents",
        "summary": "User feedback is aggregated into daily research trend summaries.",
        "report_path": str(report),
        "daily_note": "/vault/Daily Note - Jun 2026.md",
    }
    captured = {}

    monkeypatch.setattr(agents, "_daily_note_reading_entries", lambda **_kwargs: [daily_entry])

    def fake_answer_question_stream(user_id, question, *, limit=8, pinned_nodes=None, **_kwargs):
        captured["pinned_nodes"] = pinned_nodes or []
        yield {"event": "meta", "data": {"citations": [], "streaming": {"provider": True, "transport": "sse"}}}
        yield {"event": "chunk", "data": {"text": "趋势摘要"}}
        yield {"event": "done", "data": {"text": "趋势摘要", "citations": [], "streaming": {"provider": True, "transport": "sse"}}}

    monkeypatch.setattr(agents.wiki_answer, "answer_question_stream", fake_answer_question_stream)

    events = list(agents.wiki_ask_stream("user_test", "最近论文趋势是什么"))

    assert [event["event"] for event in events] == ["meta", "chunk", "done"]
    assert captured["pinned_nodes"][0]["title"] == "Personalized Research Trend Mining"
    assert captured["pinned_nodes"][0]["metadata"]["source"] == "daily_note_deep_reading"
    assert events[-1]["data"]["mode"] == "wiki"


def test_desktop_wiki_ask_pins_filtered_daily_note_readings_for_rag_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rag_report = tmp_path / "rag-agents.md"
    rag_report.write_text("Retrieval augmented generation agents summarize recent papers with citations.", encoding="utf-8")
    daily_entries = [
        {
            "title": "RAG Agents for Literature Review",
            "topic": "Language Models",
            "summary": "Retrieval augmented generation agents summarize recent papers with citations.",
            "report_path": str(rag_report),
            "daily_note": "/vault/Daily Note - Jun 2026.md",
        },
        {
            "title": "Vision Transformers for Segmentation",
            "topic": "Multimodal Models & Visual Reasoning",
            "summary": "A segmentation model unrelated to retrieval augmented generation.",
            "report_path": str(tmp_path / "missing-vision.md"),
            "daily_note": "/vault/Daily Note - Jun 2026.md",
        },
    ]
    captured = {}

    monkeypatch.setattr(agents, "_daily_note_reading_entries", lambda **_kwargs: daily_entries[:1])

    def fake_answer_question(user_id, question, *, limit=8, pinned_nodes=None, **_kwargs):
        captured["pinned_nodes"] = pinned_nodes or []
        return {"text": "RAG 相关论文集中在带引用的综述代理。[1]", "citations": []}

    monkeypatch.setattr(agents.wiki_answer, "answer_question", fake_answer_question)

    payload = agents.wiki_ask("user_test", "总结最近一周和 RAG 相关的论文")

    assert payload["mode"] == "wiki"
    assert [node["title"] for node in captured["pinned_nodes"]] == ["RAG Agents for Literature Review"]
    assert "Retrieval augmented generation" in captured["pinned_nodes"][0]["body"]


def test_desktop_wiki_ask_forwards_response_language(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    monkeypatch.setattr(agents, "_visible_wiki_node_ids", lambda _user_id: [])

    def fake_answer_question(user_id, question, *, limit=8, pinned_nodes=None, response_language="zh", **_kwargs):
        captured["response_language"] = response_language
        captured["question"] = question
        return {"text": "English answer [1]", "citations": []}

    monkeypatch.setattr(agents.wiki_answer, "answer_question", fake_answer_question)

    payload = agents.wiki_ask("user_test", "Summarize my research profile", scope="profile", response_language="en")

    assert captured["response_language"] == "en"
    assert "Prioritize profile" in captured["question"]
    assert payload["response_language"] == "en"


def test_desktop_wiki_ask_requires_mentions_for_ambiguous_two_paper_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents.wiki_answer, "answer_question", lambda *_args, **_kwargs: pytest.fail("ambiguous comparisons should not call LLM"))

    payload = agents.wiki_ask("user_test", "对比这两篇论文的方法差异")

    assert payload["mode"] == "wiki"
    assert payload["routing_reason"] == "mention_required"
    assert payload["citations"] == []
    assert "@ 选择两篇具体论文" in payload["text"]


def test_desktop_wiki_ask_stream_requires_mentions_for_ambiguous_two_paper_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents.wiki_answer, "answer_question_stream", lambda *_args, **_kwargs: pytest.fail("ambiguous comparisons should not stream LLM"))

    events = list(agents.wiki_ask_stream("user_test", "对比这两篇论文的方法差异"))

    assert events[0]["event"] == "meta"
    assert events[-1]["event"] == "done"
    assert any(event["event"] == "chunk" for event in events)
    assert events[-1]["data"]["routing_reason"] == "mention_required"
    assert "@ 选择两篇具体论文" in events[-1]["data"]["text"]


def test_desktop_wiki_ask_rolls_section_citations_up_to_paper_reference(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents, "ENV_PATH", PROJECT_ROOT / ".missing-test-env")
    monkeypatch.delenv("PAPERFLOW_WIKI_DIR", raising=False)
    section_node = {
        "node_id": "section:paper-1#Q1-problem-analysis",
        "node_type": "section",
        "title": "Q1 Problem analysis",
        "body": "The paper frames retrieval grounding as a factuality problem.",
        "metadata": {"parent_paper_id": "paper:paper-1", "section_kind": "Q1-problem-analysis"},
        "keywords": "retrieval grounding",
        "file_path": "reports/paper-1.md",
    }
    paper_node = {
        "node_id": "paper:paper-1",
        "node_type": "paper",
        "title": "Grounded Retrieval for Scientific QA",
        "body": "A paper about grounded retrieval.",
        "metadata": {"url": "https://example.com/grounded"},
        "keywords": "retrieval grounding",
        "file_path": "reports/paper-1.md",
    }

    monkeypatch.setattr(agents.wiki_db, "embed_nodes_for_user", lambda *_args, **_kwargs: {"embedded": 0})
    monkeypatch.setattr(agents.wiki_db, "search_nodes", lambda *_args, **_kwargs: [section_node])
    monkeypatch.setattr(agents.wiki_db, "get_node", lambda _user_id, node_id: paper_node if node_id == "paper:paper-1" else None)
    monkeypatch.setattr(agents.wiki_db, "get_citations_for_nodes", lambda *_args, **_kwargs: {})

    class FakeLLM:
        name = "fake"
        model = "fake-model"

        def generate(self, *_args, **_kwargs):
            class Response:
                text = "这篇论文从事实性角度分析检索增强。[1]"
                prompt_tokens = 0
                completion_tokens = 0

            return Response()

    monkeypatch.setattr(agents.wiki_answer, "build_llm_provider", lambda: FakeLLM())

    payload = agents.wiki_ask("user_test", "总结这篇论文的问题分析")

    assert payload["citations"][0]["title"] == "Grounded Retrieval for Scientific QA"
    assert payload["citations"][0]["node_id"] == "paper:paper-1"
    assert payload["sources"][0]["title"] == "Grounded Retrieval for Scientific QA"
    assert "Q1" not in payload["sources"][0]["title"]


def test_desktop_wiki_ask_stream_uses_native_wiki_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    selected_node = {
        "node_id": "paper:structured-memory",
        "node_type": "paper",
        "title": "Structured Memory Paper",
        "body": "Memory slots improve grounded retrieval.",
        "metadata": {"url": "https://example.com/paper"},
        "keywords": "memory rag",
        "file_path": "reports/structured-memory.md",
        "score": 0.95,
        "updated_at": "2026-06-01",
    }
    monkeypatch.setattr(agents.wiki_db, "get_node", lambda user_id, node_id: selected_node)
    monkeypatch.setattr(agents.wiki_db, "search_nodes", lambda user_id, query, limit=5, node_type=None: [selected_node])

    def fake_answer_question_stream(user_id, question, *, limit=8, pinned_nodes=None, **_kwargs):
        yield {
            "event": "meta",
            "data": {
                "citations": [
                    {
                        "index": 1,
                        "node_id": selected_node["node_id"],
                        "title": selected_node["title"],
                        "node_type": selected_node["node_type"],
                        "excerpt": "Memory slots improve grounded retrieval.",
                        "metadata": selected_node["metadata"],
                    }
                ],
                "streaming": {"provider": True, "transport": "sse"},
            },
        }
        yield {"event": "chunk", "data": {"text": "结构化"}}
        yield {"event": "chunk", "data": {"text": "记忆"}}
        yield {
            "event": "done",
            "data": {
                "text": "结构化记忆",
                "citations": [
                    {
                        "index": 1,
                        "node_id": selected_node["node_id"],
                        "title": selected_node["title"],
                        "node_type": selected_node["node_type"],
                        "excerpt": "Memory slots improve grounded retrieval.",
                        "metadata": selected_node["metadata"],
                    }
                ],
                "streaming": {"provider": True, "transport": "sse"},
            },
        }

    monkeypatch.setattr(agents.wiki_answer, "answer_question_stream", fake_answer_question_stream)

    events = list(
        agents.wiki_ask_stream(
            "user_test",
            "对比 @[Structured Memory Paper](paper:structured-memory) 的方法",
            mentions=[{"node_id": "paper:structured-memory", "title": "Structured Memory Paper"}],
        )
    )

    assert [event["event"] for event in events] == ["meta", "chunk", "chunk", "done"]
    assert events[0]["data"]["mode"] == "wiki"
    assert events[0]["data"]["sources"][0]["url"] == "https://example.com/paper"
    assert "".join(event["data"].get("text", "") for event in events if event["event"] == "chunk") == "结构化记忆"
    assert events[-1]["data"]["streaming"]["provider"] is True


def test_desktop_wiki_ask_can_answer_general_question_without_local_retrieval(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMockLLM:
        name = "mock"
        model = "mock-llm"

    monkeypatch.setattr(agents, "build_llm_provider", lambda: FakeMockLLM())
    monkeypatch.setattr(agents.wiki_db, "search_nodes", lambda *_args, **_kwargs: pytest.fail("direct questions should not search wiki"))

    payload = agents.wiki_ask("user_test", "什么是 RAG？")

    assert payload["mode"] == "direct"
    assert payload["retrieval_required"] is False
    assert payload["citations"] == []
    assert payload["sources"] == []


def test_desktop_wiki_ask_stream_can_direct_answer_without_wiki(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class FakeStreamingLLM:
        name = "fake"
        model = "fake-stream"

        def stream_generate(self, *_args, **_kwargs):
            captured.update(_kwargs)
            yield "RAG"
            yield " 是检索增强生成"

    monkeypatch.setattr(agents, "build_llm_provider", lambda: FakeStreamingLLM())
    monkeypatch.setattr(agents.wiki_db, "search_nodes", lambda *_args, **_kwargs: pytest.fail("direct stream should not search wiki"))

    events = list(agents.wiki_ask_stream("user_test", "什么是 RAG？"))

    assert [event["event"] for event in events] == ["meta", "chunk", "chunk", "done"]
    assert events[0]["data"]["mode"] == "direct"
    assert events[0]["data"]["retrieval_required"] is False
    assert "".join(event["data"].get("text", "") for event in events if event["event"] == "chunk") == "RAG 是检索增强生成"
    assert events[-1]["data"]["text"] == "RAG 是检索增强生成"
    assert captured["max_tokens"] >= 1400


def test_desktop_chat_history_persists_json_answers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(agents.db_ops, "DB_PATH", tmp_path / "paperflow-chat.db")
    agents.db_ops.init_db()

    class FakeMockLLM:
        name = "mock"
        model = "mock-llm"

    monkeypatch.setattr(agents, "build_llm_provider", lambda: FakeMockLLM())
    monkeypatch.setattr(agents.wiki_db, "search_nodes", lambda *_args, **_kwargs: pytest.fail("direct questions should not search wiki"))

    payload = agents.wiki_ask("user_test", "什么是 RAG？", persist_chat=True)

    assert payload["session_id"].startswith("chat_")
    listing = agents.chat_sessions("user_test", days=90)
    assert listing["sessions"][0]["session_id"] == payload["session_id"]
    assert listing["groups"][0]["sessions"][0]["message_count"] == 2

    session = agents.chat_session("user_test", payload["session_id"])
    assert [message["role"] for message in session["messages"]] == ["user", "assistant"]
    assert session["messages"][0]["content"] == "什么是 RAG？"
    assert session["messages"][1]["metadata"]["mode"] == "direct"
    assert session["messages"][1]["metadata"]["retrieval_required"] is False


def test_desktop_chat_history_persists_streaming_answers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(agents.db_ops, "DB_PATH", tmp_path / "paperflow-chat-stream.db")
    agents.db_ops.init_db()

    class FakeStreamingLLM:
        name = "fake"
        model = "fake-stream"

        def stream_generate(self, *_args, **_kwargs):
            yield "RAG"
            yield " 是检索增强生成"

    monkeypatch.setattr(agents, "build_llm_provider", lambda: FakeStreamingLLM())
    monkeypatch.setattr(agents.wiki_db, "search_nodes", lambda *_args, **_kwargs: pytest.fail("direct stream should not search wiki"))

    events = list(agents.wiki_ask_stream("user_test", "什么是 RAG？", persist_chat=True))
    session_id = events[-1]["data"]["session_id"]

    session = agents.chat_session("user_test", session_id)
    assert len(session["messages"]) == 2
    assert session["messages"][1]["content"] == "RAG 是检索增强生成"
    assert session["messages"][1]["metadata"]["streaming"]["transport"] == "sse"


def test_desktop_chat_history_can_be_cleared(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(agents.db_ops, "DB_PATH", tmp_path / "paperflow-chat-clear.db")
    agents.db_ops.init_db()

    first = agents.db_ops.create_chat_session(user_id="user_test", title="first")
    second = agents.db_ops.create_chat_session(user_id="user_test", title="second")
    agents.db_ops.save_chat_message(
        user_id="user_test",
        session_id=first["session_id"],
        role="user",
        content="hello",
    )
    agents.db_ops.save_chat_message(
        user_id="user_test",
        session_id=second["session_id"],
        role="assistant",
        content="world",
    )

    result = agents.clear_chat_sessions("user_test")

    assert result == {"deleted": 2}
    assert agents.chat_sessions("user_test")["sessions"] == []
    assert agents.db_ops.get_chat_session("user_test", first["session_id"]) is None


def test_desktop_wiki_answer_stream_uses_longer_default_completion_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}
    node = {
        "node_id": "paper:rag",
        "node_type": "paper",
        "title": "RAG Paper",
        "body": "Retrieval augmented generation needs enough answer budget.",
        "metadata": {},
    }

    class FakeStreamingLLM:
        name = "fake"
        model = "fake-stream"

        def stream_generate(self, *_args, **_kwargs):
            captured.update(_kwargs)
            yield "完整回答"

    monkeypatch.delenv("PAPERFLOW_WIKI_ANSWER_MAX_TOKENS", raising=False)
    monkeypatch.setattr(agents.wiki_answer.wiki_db, "embed_nodes_for_user", lambda *_args, **_kwargs: {"embedded": 1})
    monkeypatch.setattr(agents.wiki_answer.wiki_db, "search_nodes", lambda *_args, **_kwargs: [node])
    monkeypatch.setattr(agents.wiki_answer.wiki_db, "get_citations_for_nodes", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(agents.wiki_answer, "build_llm_provider", lambda: FakeStreamingLLM())

    events = list(agents.wiki_answer.answer_question_stream("user_test", "总结 RAG", limit=4))

    assert events[-1]["data"]["text"] == "完整回答"
    assert captured["max_tokens"] >= 1800


def test_desktop_wiki_answer_stream_recovers_obviously_incomplete_text(monkeypatch: pytest.MonkeyPatch) -> None:
    node = {
        "node_id": "paper:weekly-work",
        "node_type": "paper",
        "title": "Weekly Work",
        "body": "The user accepted paper recommendations and drafted a reading plan this week.",
        "metadata": {},
    }
    captured = {"fallback_called": False}

    class FakeStreamingLLM:
        name = "fake"
        model = "fake-stream"

        def stream_generate(self, *_args, **_kwargs):
            yield "您本周的工作主要集中在论文推荐接收与阅读计划制定：在2026年6月"

        def generate(self, *_args, **_kwargs):
            captured["fallback_called"] = True

            class Response:
                text = "您本周的工作主要集中在论文推荐接收与阅读计划制定：在2026年6月12日和6月14日接收了推荐论文，并围绕阅读计划推进了后续精读。"
                prompt_tokens = 0
                completion_tokens = 0

            return Response()

    monkeypatch.setattr(agents.wiki_answer.wiki_db, "embed_nodes_for_user", lambda *_args, **_kwargs: {"embedded": 1})
    monkeypatch.setattr(agents.wiki_answer.wiki_db, "search_nodes", lambda *_args, **_kwargs: [node])
    monkeypatch.setattr(agents.wiki_answer.wiki_db, "get_citations_for_nodes", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(agents.wiki_answer, "build_llm_provider", lambda: FakeStreamingLLM())

    events = list(agents.wiki_answer.answer_question_stream("user_test", "总结一下我这一周的工作", limit=4))

    assert captured["fallback_called"] is True
    assert events[-1]["data"]["text"].endswith("后续精读。")


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
            "PAPERFLOW_FALLBACK_LLM_MODEL": "backup-model",
            "OPENAI_API_KEY": "***",
            "PAPERFLOW_WRITE_FEISHU": "true",
            "PAPERFLOW_ENABLE_ARXIV": "false",
            "PAPERFLOW_CUSTOM_RSS_URLS": "https://example.com/rss.xml",
            "PAPERFLOW_CONFERENCE_ACCESS_MODE": "credential",
            "PAPERFLOW_CONFERENCE_COOKIE_FILE": r"C:\paperflow\cookies\neurips.txt",
            "SEMANTIC_SCHOLAR_API_KEY": "s2-test-key",
            "OPENREVIEW_TOKEN": "or-test-token",
            "PAPERFLOW_REPORT_STYLE": "deep",
            "PAPERFLOW_DAILY_LIMIT": "17",
            "PAPERFLOW_RELEVANCE_THRESHOLD": "72",
            "PAPERFLOW_MAX_CONCURRENCY": "4",
            "PAPERFLOW_NOTES_ROOT_DIR": str(tmp_path / "Daily Note"),
            "PAPERFLOW_READING_NOTES_GIT_REMOTE": "https://github.com/example/notes.git",
            "PAPERFLOW_READING_NOTES_GIT_BRANCH": "main",
            "PAPERFLOW_READING_NOTES_GIT_LLM_REVIEW": "false",
            "HTTP_PROXY": "http://127.0.0.1:18080",
            "UNSUPPORTED_KEY": "ignored",
        }
    )

    text = env_path.read_text(encoding="utf-8")
    assert "PAPERFLOW_LLM_MODEL=new-model" in text
    assert "PAPERFLOW_FALLBACK_LLM_MODEL=backup-model" in text
    assert "OPENAI_API_KEY=sk-existing" in text
    assert "PAPERFLOW_WRITE_FEISHU=true" in text
    assert "PAPERFLOW_ENABLE_ARXIV=false" in text
    assert "PAPERFLOW_CUSTOM_RSS_URLS=https://example.com/rss.xml" in text
    assert f'PAPERFLOW_NOTES_ROOT_DIR="{tmp_path / "Daily Note"}"' in text
    assert "PAPERFLOW_READING_NOTES_GIT_REMOTE=https://github.com/example/notes.git" in text
    assert "PAPERFLOW_READING_NOTES_GIT_BRANCH=main" in text
    assert "PAPERFLOW_READING_NOTES_GIT_LLM_REVIEW=false" in text
    assert result["paths"]["notes_root_dir"] == str(tmp_path / "Daily Note")
    assert result["paths"]["pdf_dir"] == str(tmp_path / "Daily Note")
    assert result["paths"]["reading_reports_dir"] == str(tmp_path / "Daily Note")
    assert result["paths"]["wiki_dir"] == str(tmp_path / "Daily Note" / "wiki")
    assert result["paths"]["reading_notes_git_dir"] == str(tmp_path / "Daily Note" / "Daily Note 2026")
    assert result["paths"]["reading_notes_git_remote"] == "https://github.com/example/notes.git"
    assert result["paths"]["reading_notes_git_branch"] == "main"
    assert result["paths"]["reading_notes_git_llm_review"] is False
    assert "PAPERFLOW_CONFERENCE_ACCESS_MODE=credential" in text
    assert r"PAPERFLOW_CONFERENCE_COOKIE_FILE=C:\paperflow\cookies\neurips.txt" in text
    assert "SEMANTIC_SCHOLAR_API_KEY=s2-test-key" in text
    assert "OPENREVIEW_TOKEN=or-test-token" in text
    assert "PAPERFLOW_REPORT_STYLE=deep" in text
    assert "PAPERFLOW_DAILY_LIMIT=17" in text
    assert "PAPERFLOW_RELEVANCE_THRESHOLD=72" in text
    assert "PAPERFLOW_MAX_CONCURRENCY=4" in text
    assert "HTTP_PROXY=http://127.0.0.1:18080" in text
    assert "UNSUPPORTED_KEY" not in text
    assert result["paths"]["write_feishu"] is True
    assert result["report_preferences"]["style"] == "deep"
    assert result["advanced"]["daily_limit"] == 17
    assert result["advanced"]["relevance_threshold"] == 72
    assert result["advanced"]["http_proxy"] == "http://127.0.0.1:18080"
    assert result["source_preferences"]["conference_access_mode"] == "credential"
    assert result["source_preferences"]["auth_status"]["semantic_scholar_api_key"] is True


def test_desktop_github_sync_commits_notes_with_llm_review(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    bare = tmp_path / "notes.git"
    seed = tmp_path / "seed"
    notes = tmp_path / "Daily Note 2026"
    agents._run_git(["init", "--bare", str(bare)], tmp_path)  # noqa: SLF001 - git sync contract
    seed.mkdir()
    agents._run_git(["init"], seed)  # noqa: SLF001
    agents._run_git(["checkout", "-b", "main"], seed)  # noqa: SLF001
    agents._run_git(["config", "user.email", "paperflow@example.com"], seed)  # noqa: SLF001
    agents._run_git(["config", "user.name", "PaperFlow Test"], seed)  # noqa: SLF001
    (seed / "Table of Content - 2026.md").write_text("# Daily Note - Jun 2026\n[[Daily Note - Jun 2026]]\n", encoding="utf-8")
    agents._run_git(["add", "."], seed)  # noqa: SLF001
    agents._run_git(["commit", "-m", "Initialize reading notes"], seed)  # noqa: SLF001
    agents._run_git(["remote", "add", "origin", str(bare)], seed)  # noqa: SLF001
    agents._run_git(["push", "-u", "origin", "main"], seed)  # noqa: SLF001

    agents._run_git(["clone", "-b", "main", str(bare), str(notes)], tmp_path)  # noqa: SLF001
    agents._run_git(["config", "user.email", "paperflow@example.com"], notes)  # noqa: SLF001
    agents._run_git(["config", "user.name", "PaperFlow Test"], notes)  # noqa: SLF001
    (notes / "Daily Note - Jun 2026.md").write_text(
        "# Reward Models & Reinforcement Learning\n\n## PaperFlow Summary\n- 论文/报告：1 篇\n",
        encoding="utf-8",
    )

    class FakeResponse:
        text = '{"risk_level":"low","summary":"新增 Daily Note，未发现删除风险。","suggested_action":"commit"}'

    class FakeLLM:
        name = "fake"
        model = "test"

        def generate(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(agents, "build_llm_provider", lambda: FakeLLM())
    monkeypatch.setattr(agents, "_configured_reading_notes_git_dir", lambda: notes)
    monkeypatch.setattr(agents, "_configured_reading_notes_git_remote", lambda: str(bare))
    monkeypatch.setattr(agents, "_configured_reading_notes_git_branch", lambda: "main")
    monkeypatch.setenv("PAPERFLOW_READING_NOTES_GIT_LLM_REVIEW", "true")

    result = agents.sync_reading_notes_github("user_test")

    assert result["committed"] is True
    assert result["pushed"] is True
    assert result["llm_review"]["reviewed"] is True
    assert result["commit"]
    clone_check = tmp_path / "check"
    agents._run_git(["clone", "-b", "main", str(bare), str(clone_check)], tmp_path)  # noqa: SLF001
    assert (clone_check / "Daily Note - Jun 2026.md").exists()
    assert "*.bak-*" in (clone_check / ".gitignore").read_text(encoding="utf-8")


def test_desktop_github_sync_applies_local_changes_after_remote_first_sync(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    bare = tmp_path / "notes.git"
    seed = tmp_path / "seed"
    remote_work = tmp_path / "remote-work"
    notes = tmp_path / "Daily Note 2026"
    agents._run_git(["init", "--bare", str(bare)], tmp_path)  # noqa: SLF001 - git sync contract
    seed.mkdir()
    agents._run_git(["init"], seed)  # noqa: SLF001
    agents._run_git(["checkout", "-b", "main"], seed)  # noqa: SLF001
    agents._run_git(["config", "user.email", "paperflow@example.com"], seed)  # noqa: SLF001
    agents._run_git(["config", "user.name", "PaperFlow Test"], seed)  # noqa: SLF001
    (seed / "Table of Content - 2026.md").write_text("# Reading Notes\n", encoding="utf-8")
    agents._run_git(["add", "."], seed)  # noqa: SLF001
    agents._run_git(["commit", "-m", "Initialize reading notes"], seed)  # noqa: SLF001
    agents._run_git(["remote", "add", "origin", str(bare)], seed)  # noqa: SLF001
    agents._run_git(["push", "-u", "origin", "main"], seed)  # noqa: SLF001

    agents._run_git(["clone", "-b", "main", str(bare), str(notes)], tmp_path)  # noqa: SLF001
    agents._run_git(["config", "user.email", "paperflow@example.com"], notes)  # noqa: SLF001
    agents._run_git(["config", "user.name", "PaperFlow Test"], notes)  # noqa: SLF001

    agents._run_git(["clone", "-b", "main", str(bare), str(remote_work)], tmp_path)  # noqa: SLF001
    agents._run_git(["config", "user.email", "paperflow@example.com"], remote_work)  # noqa: SLF001
    agents._run_git(["config", "user.name", "PaperFlow Test"], remote_work)  # noqa: SLF001
    (remote_work / "Daily Note - May 2026.md").write_text("# Remote May Note\n", encoding="utf-8")
    agents._run_git(["add", "."], remote_work)  # noqa: SLF001
    agents._run_git(["commit", "-m", "Add remote May note"], remote_work)  # noqa: SLF001
    agents._run_git(["push", "origin", "main"], remote_work)  # noqa: SLF001

    (notes / "Daily Note - Jun 2026.md").write_text("# Local Jun Note\n", encoding="utf-8")
    monkeypatch.setattr(agents, "_configured_reading_notes_git_dir", lambda: notes)
    monkeypatch.setattr(agents, "_configured_reading_notes_git_remote", lambda: str(bare))
    monkeypatch.setattr(agents, "_configured_reading_notes_git_branch", lambda: "main")
    monkeypatch.setenv("PAPERFLOW_READING_NOTES_GIT_LLM_REVIEW", "false")

    result = agents.sync_reading_notes_github("user_test")

    assert result["committed"] is True
    assert result["pulled"] is True
    assert result["rebased"] is False
    assert result["pushed"] is True
    assert result["pull_warning"] == ""
    clone_check = tmp_path / "check-rebased"
    agents._run_git(["clone", "-b", "main", str(bare), str(clone_check)], tmp_path)  # noqa: SLF001
    assert (clone_check / "Daily Note - May 2026.md").exists()
    assert (clone_check / "Daily Note - Jun 2026.md").exists()


def test_desktop_github_sync_keeps_remote_on_note_conflict_without_branch(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare = tmp_path / "notes.git"
    seed = tmp_path / "seed"
    remote_work = tmp_path / "remote-work"
    notes = tmp_path / "Daily Note 2026"
    agents._run_git(["init", "--bare", str(bare)], tmp_path)  # noqa: SLF001 - git sync contract
    seed.mkdir()
    agents._run_git(["init"], seed)  # noqa: SLF001
    agents._run_git(["checkout", "-b", "main"], seed)  # noqa: SLF001
    agents._run_git(["config", "user.email", "paperflow@example.com"], seed)  # noqa: SLF001
    agents._run_git(["config", "user.name", "PaperFlow Test"], seed)  # noqa: SLF001
    (seed / "Daily Note - Jun 2026.md").write_text("# Base\n", encoding="utf-8")
    agents._run_git(["add", "."], seed)  # noqa: SLF001
    agents._run_git(["commit", "-m", "Initialize reading notes"], seed)  # noqa: SLF001
    agents._run_git(["remote", "add", "origin", str(bare)], seed)  # noqa: SLF001
    agents._run_git(["push", "-u", "origin", "main"], seed)  # noqa: SLF001

    agents._run_git(["clone", "-b", "main", str(bare), str(notes)], tmp_path)  # noqa: SLF001
    agents._run_git(["config", "user.email", "paperflow@example.com"], notes)  # noqa: SLF001
    agents._run_git(["config", "user.name", "PaperFlow Test"], notes)  # noqa: SLF001

    agents._run_git(["clone", "-b", "main", str(bare), str(remote_work)], tmp_path)  # noqa: SLF001
    agents._run_git(["config", "user.email", "paperflow@example.com"], remote_work)  # noqa: SLF001
    agents._run_git(["config", "user.name", "PaperFlow Test"], remote_work)  # noqa: SLF001
    (remote_work / "Daily Note - Jun 2026.md").write_text("# Remote\n", encoding="utf-8")
    agents._run_git(["add", "."], remote_work)  # noqa: SLF001
    agents._run_git(["commit", "-m", "Remote update"], remote_work)  # noqa: SLF001
    agents._run_git(["push", "origin", "main"], remote_work)  # noqa: SLF001

    (notes / "Daily Note - Jun 2026.md").write_text("# Local\n", encoding="utf-8")
    monkeypatch.setattr(agents, "_configured_reading_notes_git_dir", lambda: notes)
    monkeypatch.setattr(agents, "_configured_reading_notes_git_remote", lambda: str(bare))
    monkeypatch.setattr(agents, "_configured_reading_notes_git_branch", lambda: "main")
    monkeypatch.setenv("PAPERFLOW_READING_NOTES_GIT_LLM_REVIEW", "false")

    result = agents.sync_reading_notes_github("user_test")

    assert result["ok"] is True
    assert result["committed"] is False
    assert result["pushed"] is False
    assert "远端版本" in result["pull_warning"]
    assert (notes / "Daily Note - Jun 2026.md").read_text(encoding="utf-8") == "# Remote\n"
    assert "backup/" not in agents._git_output(["branch"], notes)  # noqa: SLF001


def test_desktop_reading_agent_receives_derived_output_dirs(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    notes_root = tmp_path / "Daily Note"
    env_path.write_text(f'PAPERFLOW_NOTES_ROOT_DIR="{notes_root}"\n', encoding="utf-8")
    monkeypatch.setattr(agents, "ENV_PATH", env_path)
    monkeypatch.delenv("PAPERFLOW_NOTES_ROOT_DIR", raising=False)
    monkeypatch.delenv("PAPERFLOW_READING_REPORTS_DIR", raising=False)
    monkeypatch.delenv("PAPERFLOW_PDF_DIR", raising=False)

    with agents._reading_agent_output_env_patch():  # noqa: SLF001 - output env bridge contract
        assert agents.os.environ["PAPERFLOW_READING_REPORTS_DIR"] == str(notes_root)
        assert agents.os.environ["PAPERFLOW_PDF_DIR"] == str(notes_root)

    assert agents.os.environ.get("PAPERFLOW_READING_REPORTS_DIR") is None
    assert agents.os.environ.get("PAPERFLOW_PDF_DIR") is None


def test_desktop_report_dirs_include_legacy_exports_for_recent_generated_reports(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "project"
    configured = tmp_path / "Daily Note"
    legacy_exports = project_root / "data" / "exports"
    configured.mkdir()
    legacy_exports.mkdir(parents=True)
    monkeypatch.setattr(agents, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(agents, "_configured_path", lambda _env_name, _default_relative: str(configured))
    monkeypatch.setattr(agents, "_env_text", lambda _name, default="": "")

    dirs = agents._reading_report_dirs()  # noqa: SLF001 - report discovery contract

    assert configured.resolve() in dirs
    assert legacy_exports.resolve() in dirs


def test_desktop_daily_push_uses_saved_settings_when_gui_omits_filters(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "PAPERFLOW_DAILY_LIMIT=17",
                "PAPERFLOW_RELEVANCE_THRESHOLD=60",
                "PAPERFLOW_ENABLE_ARXIV=false",
                "PAPERFLOW_ENABLE_OPENREVIEW=false",
                "PAPERFLOW_ENABLE_SEMANTIC_SCHOLAR=true",
                "PAPERFLOW_ENABLE_CUSTOM_RSS=true",
                "PAPERFLOW_DEFAULT_ARXIV_CATEGORIES=cs.LG,cs.CV",
                "PAPERFLOW_DEFAULT_CONFERENCES=ICLR,NeurIPS",
                "PAPERFLOW_DEFAULT_JOURNALS=Nature",
                "PAPERFLOW_CUSTOM_RSS_URLS=https://example.com/feed.xml",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(agents, "ENV_PATH", env_path)
    captured: dict[str, object] = {}

    def fake_daily_push(**kwargs):
        captured.update(kwargs)
        return {"push_id": "push_settings_effect"}

    monkeypatch.setattr(agents.daily_agent, "daily_push", fake_daily_push)
    monkeypatch.setattr(agents.db_ops, "get_push_papers", lambda push_id: None)
    monkeypatch.setattr(agents.db_ops, "get_latest_push", lambda user_id: None)

    agents.run_daily_push("user_settings", days=2)

    assert captured["limit_per_source"] == 17
    assert captured["push_limit"] == 17
    assert captured["arxiv_categories"] == []
    assert captured["conferences"] == []
    assert captured["journals"] == ["Nature"]
    assert captured["enable_semantic_scholar"] is True
    assert captured["enable_custom_rss"] is True
    assert captured["custom_rss_urls"] == ["https://example.com/feed.xml"]


def test_desktop_relevance_threshold_changes_daily_push_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    base = {
        "threshold_high_relevant": 0.40,
        "threshold_maybe_interested": 0.25,
        "threshold_edge_relevant": 0.15,
        "min_relevance_signal": 0.08,
    }

    monkeypatch.setenv("PAPERFLOW_RELEVANCE_THRESHOLD", "90")
    monkeypatch.setenv("PAPERFLOW_DAILY_LIMIT", "12")
    strict = agents.daily_agent.apply_relevance_threshold_override(base)
    monkeypatch.setenv("PAPERFLOW_RELEVANCE_THRESHOLD", "30")
    monkeypatch.setenv("PAPERFLOW_DAILY_LIMIT", "8")
    relaxed = agents.daily_agent.apply_relevance_threshold_override(base)
    monkeypatch.setenv("PAPERFLOW_DAILY_LIMIT", "1200")
    capped = agents.daily_agent.apply_relevance_threshold_override(base)

    assert strict["threshold_edge_relevant"] > base["threshold_edge_relevant"]
    assert relaxed["threshold_edge_relevant"] < base["threshold_edge_relevant"]
    assert strict["paperflow_relevance_threshold"] == 90
    assert strict["push_target_count"] == 12
    assert strict["push_max_count"] == 12
    assert relaxed["push_target_count"] == 8
    assert capped["push_target_count"] == 1000
    assert capped["push_max_count"] == 1000


def test_daily_push_custom_rss_fetcher_builds_paper_cards(monkeypatch: pytest.MonkeyPatch) -> None:
    rss = b"""<?xml version="1.0"?>
    <rss><channel><item>
      <title>RSS Paper</title>
      <link>https://example.com/paper</link>
      <description>RSS abstract</description>
      <pubDate>Mon, 01 Jun 2026 00:00:00 GMT</pubDate>
    </item></channel></rss>
    """

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return rss

    monkeypatch.setattr(agents.daily_agent.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())

    papers = agents.daily_agent.fetch_custom_rss_papers(["https://example.com/rss.xml"], 5)

    assert papers[0]["title"] == "RSS Paper"
    assert papers[0]["source"] == "custom_rss"
    assert papers[0]["paper_url"] == "https://example.com/paper"


def test_daily_push_semantic_scholar_fetcher_uses_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = (
        b'{"data":[{"title":"Semantic Paper","abstract":"Graph result",'
        b'"authors":[{"name":"Ada"}],"publicationDate":"2026-06-01",'
        b'"url":"https://semanticscholar.org/paper/1","venue":"ACL",'
        b'"externalIds":{"ArXiv":"2606.00001","DOI":"10.0000/test"}}]}'
    )
    captured_headers = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return payload

    def fake_urlopen(request, timeout=20):
        captured_headers.update(dict(request.header_items()))
        return FakeResponse()

    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "s2-live-test")
    monkeypatch.setattr(agents.daily_agent.urllib.request, "urlopen", fake_urlopen)

    papers = agents.daily_agent.fetch_semantic_scholar_papers(["retrieval"], days=30, limit_per_source=5)

    assert captured_headers["X-api-key"] == "s2-live-test"
    assert papers[0]["title"] == "Semantic Paper"
    assert papers[0]["source"] == "semantic_scholar"
    assert papers[0]["arxiv_id"] == "2606.00001"


def test_latest_push_metadata_lifts_generation_settings_from_paper_rows() -> None:
    metadata = agents.db_ops._derive_push_metadata_from_papers(  # noqa: SLF001 - persisted GUI metadata contract
        [
            {
                "metadata": {
                    "paper_count": 17,
                    "total_fetched": 50,
                    "daily_limit": 17,
                    "push_target_count": 17,
                    "push_max_count": 17,
                    "limit_per_source": 17,
                    "fetch_days": 1,
                    "relevance_threshold": 72,
                    "arxiv_categories": ["cs.LG"],
                    "conferences": [],
                    "journals": ["Nature"],
                    "enable_semantic_scholar": True,
                    "enable_custom_rss": True,
                    "custom_rss_urls": ["https://example.com/feed.xml"],
                }
            }
        ]
    )

    assert metadata["paper_count"] == 17
    assert metadata["total_fetched"] == 50
    assert metadata["daily_limit"] == 17
    assert metadata["push_target_count"] == 17
    assert metadata["push_max_count"] == 17
    assert metadata["limit_per_source"] == 17
    assert metadata["relevance_threshold"] == 72
    assert metadata["custom_rss_urls"] == ["https://example.com/feed.xml"]


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
    assert "function formatConferenceTimeline(value)" in script
    assert "englishMonthNames" in script
    assert "formatConferenceTimeline(item.acceptance_timeline)" in script
    assert "formatConferenceTimeline(item.conference_date)" in script
    assert "renderConferenceSettings(sourcePrefs);" in script
    assert "updateSourceAuthStatus(sourcePrefs, envMap(state.settings));" in script
    assert "syncConferenceAccessUi(input.value)" in script
    assert "settingEnableCustomRss" in script
    assert 'input.disabled = normalized !== "credential"' in script
    assert "PAPERFLOW_CONFERENCE_ACCESS_MODE" in script
    assert "state.settings = data || {}" in script
    assert "syncDailySourceControls(sourcePrefs)" in script
    assert "limit_per_source: configuredDailyLimit()" in script
    assert 'id="dailyLimitInput" type="number" min="1" max="1000" value="30"' in html
    assert "Math.min(1000, Math.round(value))" in script
    assert "PAPERFLOW_LLM_MODEL" in script
    assert "PAPERFLOW_FALLBACK_LLM_MODEL" in script
    assert 'input?.dataset.envKey === "PAPERFLOW_LLM_MODEL"' not in script
    assert '[data-env-key="PAPERFLOW_LLM_MODEL"]' not in script
    assert ".source-auth-panel" in css
    assert ".conference-source-list" in css
    assert ".conference-source-item.active" in css
    assert ".settings-source .source-auth-panel" in css
    assert "grid-template-columns: minmax(0, 1fr) minmax(320px, 360px)" in css
    assert '[data-mode="credential"]' in css
    assert "label:has(input:checked)" in css


def test_desktop_paper_source_defaults_are_arxiv_only() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    collect_daily_options = script.split("function collectDailyOptions() {", 1)[1].split("function paperReportKey", 1)[0]

    assert 'renderChoiceList("arxivCategories", data.arxiv_categories || [], { defaultChecked: "all" })' in script
    assert 'renderChoiceList("conferenceSources", data.conferences || [], { defaultChecked: "none" })' in script
    assert 'renderChoiceList("journalSources", data.journals || [], { defaultChecked: "none" })' in script
    assert 'const conferences = openReviewEnabled ? selectedSourceValues("conferenceSources") : [];' in collect_daily_options
    assert 'selectedSourceValues("conferenceSources").length' not in collect_daily_options
    assert "selectedSettingConferences()" not in collect_daily_options


def test_desktop_settings_controls_use_compact_typography() -> None:
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert ".setting-card {\n  display: grid;\n  gap: 11px;\n  padding: 15px;" in css
    assert ".setting-card button,\n.setting-card input,\n.setting-card select,\n.setting-card textarea {\n  font-size: 13px;" in css
    assert ".setting-card input,\n.setting-card select,\n.setting-card textarea {\n  min-height: 34px;\n  padding: 7px 9px;" in css
    assert ".setting-card button {\n  min-height: 34px;\n  padding: 7px 10px;" in css
    assert ".setting-card-head h2 {\n  margin: 0;\n  font-size: 15px;" in css
    assert ".settings-source .source-edit-row {\n  grid-column: 2;\n  grid-row: 5;\n  display: grid;\n  grid-template-columns: minmax(0, 1fr) 74px;" in css
    assert ".settings-source .source-edit-row button {\n  white-space: normal;\n  line-height: 1.2;" in css
    assert ".settings-storage .button-row button,\n.settings-advanced > button,\n.profile-card #saveProfileBtn {\n  min-height: 34px;\n  font-size: 13px;" in css


def test_desktop_reports_view_uses_compact_reading_typography() -> None:
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert ".report-list-pane .pane-head h2 {\n  font-size: 14px;" in css
    assert ".report-list-pane .pane-head select,\n.report-list-pane .pane-head button,\n.report-filter-row input,\n.filter-actions button {\n  min-height: 32px;\n  padding: 6px 8px;\n  font-size: 12.5px;" in css
    assert ".report-list-pane .pane-head button,\n.filter-actions button,\n.report-reader .reader-head .button-row button {\n  white-space: nowrap;" in css
    assert ".report-row {\n  width: 100%;\n  display: block;\n  text-align: left;\n  border-color: #e0e9f6;\n  background: #fff;\n  padding: 8px 9px;\n  font-size: 12px;" in css
    assert ".reader-head h2 {\n  margin: 0 0 4px;\n  font-size: 18px;" in css
    assert ".markdown-body {\n  padding: 14px 0 4px;\n  color: #25354f;\n  line-height: 1.68;\n  font-size: 13.5px;" in css
    assert ".markdown-body h1 {\n  font-size: 19px;" in css
    assert ".markdown-body blockquote {" in css
    assert ".annotation-toolbar {" in css
    assert "position: fixed;" in css
    assert ".annotation-toolbar.visible {" in css
    assert ".annotation-swatch.bg-red {" in css


def test_desktop_report_viewer_renders_markdown_and_annotations() -> None:
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")

    assert 'data-annotation-command="backColor"' in html
    assert 'data-annotation-command="foreColor"' in html
    assert 'data-annotation-command="bold"' in html
    assert 'data-annotation-command="italic"' in html
    assert 'id="clearReportAnnotationsBtn"' in html
    assert "function renderMarkdown(markdown)" in script
    assert "renderInlineMarkdown" in script
    assert "blockquote" in script
    assert "<strong>$1</strong>" in script
    assert "paperflow.report.annotations." in script
    assert "applyReportAnnotation" in script
    assert "function updateReportAnnotationToolbar" in script
    assert "function selectedReportAnnotationRange" in script
    assert 'document.addEventListener("selectionchange", updateReportAnnotationToolbar)' in script
    assert 'toolbar.classList.add("visible")' in script
    assert "wrapper.dataset.paperflowAnnotation = command" in script
    assert "wrapper.style.backgroundColor = value" in script
    assert 'wrapper.style.fontWeight = "700"' in script
    assert 'wrapper.style.fontStyle = "italic"' in script
    assert "range.extractContents()" in script


def test_report_record_derives_abs_url_and_patches_missing_institution(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"
    report_path.write_text(
        "\n".join(
            [
                "---",
                'arxiv_id: "2606.17029v1"',
                'title: "DEEPRUBRIC"',
                'institution: "Shandong University; Zhongguancun Academy; Fudan University"',
                "---",
                "# DEEPRUBRIC",
                "",
                "## 基本信息",
                "",
                "- 机构：未提供",
            ]
        ),
        encoding="utf-8",
    )

    report = agents._report_record(report_path)  # noqa: SLF001 - report reader fallback contract

    assert report["abs_url"] == "https://arxiv.org/abs/2606.17029v1"
    assert report["institution"] == "Shandong University; Zhongguancun Academy; Fudan University"
    assert "- 机构：Shandong University; Zhongguancun Academy; Fudan University" in report["markdown"]


def test_report_snippet_skips_legacy_recommendation_time_quote(tmp_path: Path) -> None:
    report_path = tmp_path / "legacy.md"
    report_path.write_text(
        "\n".join(
            [
                "---",
                'title: "Legacy"',
                'report_version: "v1"',
                "---",
                "# Legacy",
                "",
                "> ★★☆☆☆ 按需阅读 · 约 20 分钟 · 模型 provider/model",
                "",
                "## 一句话总结",
                "",
                "这篇论文的正文摘要应该显示在侧边栏。",
            ]
        ),
        encoding="utf-8",
    )

    report = agents._report_record(report_path)  # noqa: SLF001 - report reader fallback contract

    assert "约 20 分钟" not in report["snippet"]
    assert report["snippet"] == "这篇论文的正文摘要应该显示在侧边栏。"


def test_desktop_direct_read_generation_shows_status_feedback() -> None:
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert 'id="directArxivStatus"' in html
    assert 'id="directPdfStatus"' in html
    assert 'class="direct-read-status"' in html
    assert "function setDirectReadStatus" in script
    assert "function setDirectReadBusy" in script
    assert "generatingTitle: (source) => `正在生成${source}精读报告`" in script
    assert "generatingTitle: (source) => `Generating ${source} reading report`" in script
    assert "后端正在拉取论文信息、调用模型并写入本地报告库" in script
    assert "The backend is fetching paper metadata, calling the model, and writing the local report." in script
    assert "报告已生成" in script
    assert "Report generated" in script
    assert "报告生成失败" in script
    assert "Report generation failed" in script
    assert "请先填写 arXiv ID" in script
    assert "Enter an arXiv ID" in script
    assert "请先填写 PDF 路径" in script
    assert "Enter a PDF path" in script
    assert "showFeedbackToast(warning ? \"warning\" : \"success\", ui().reports.generatedToast, reportTitle)" in script
    assert "payload.response_language = responseLanguage();" in script
    assert "await openReport(doc.report_id)" in script
    assert ".direct-read-status {" in css
    assert ".direct-read-status.success" in css
    assert ".direct-read-status.warning" in css
    assert ".direct-read-status.error" in css
    assert ".primary.loading" in css


def test_desktop_user_picker_hydrates_settings_profile_form() -> None:
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert 'id="profileSyncStatus"' in html
    assert 'id="profileInfoGrid"' in html
    assert 'id="profileTagGrid"' not in html
    assert ".profile-tag-grid" not in css
    assert ".setting-card-head small" in css
    assert ".profile-info-grid" in css
    assert ".profile-info-item.wide" in css
    assert "function renderProfileForm(data = {})" in script
    assert "function renderProfileInfoGrid(profile, raw, userInfo, details)" in script
    assert "function profileAffiliation(raw, userInfo)" in script
    assert "async function loadCurrentProfile()" in script
    assert "/api/profile?user_id=${encodeURIComponent(userId)}" in script
    assert "renderProfileForm(data);" in script
    assert "await loadCurrentProfile();" in script
    assert "$(\"profileUserId\").value = userId;" in script
    assert "profileFields" in script
    assert 'affiliation: "个人机构"' in script
    assert 'affiliation: "Affiliation"' in script
    assert 'profileInfoItem(labels.affiliation, profileAffiliation(raw, userInfo), "wide")' in script
    assert 'profileEditItem(labels.directions, "profileDirectionsInput"' in script
    assert 'profileEditItem(labels.keywords, "profileKeywordsInput"' in script
    assert 'profileEditItem(labels.authors, "profileAuthorsInput"' in script
    assert 'profileEditItem(labels.institutions, "profileInstitutionsInput"' in script
    assert 'profileEditItem(labels.topics, "profileTopicsInput"' in script
    assert 'profileAffiliationInput' not in script
    assert "用分号或换行分隔；可写 方向:0.8" in script
    assert "用分号或换行分隔；可写 主题:0.8" in script
    assert 'profileInfoItem("机构", listText(mustRead.institutions, 8), "wide")' not in script
    assert 'core_directions_text: $("profileDirectionsInput")?.value || ""' in script
    assert 'topic_weights_text: $("profileTopicsInput")?.value || ""' in script
    assert 'must_read_keywords: splitListValue($("profileKeywordsInput")?.value || "")' in script
    assert ".profile-info-item.editable" in css
    assert ".profile-info-item.editable small" in css
    assert 'id="naturalLanguage"' not in html
    assert "研究方向描述" not in html
    assert "profileEditableDescription" not in script
    assert 'natural_language: ""' in script
    assert 'renderSettingTags("profileTagGrid"' not in script
    assert "userInfo.has_profile ? labels.loaded : labels.missing" in script
    assert "profileLoaded: (userId) => `已加载 ${userId} 的画像信息。`" in script
    assert "profileLoaded: (userId) => `Loaded profile information for ${userId}.`" in script
    assert "showSettingsMessage(ui().settings.profileLoaded(userId));" in script


def test_desktop_save_profile_applies_manual_editable_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = {
        "user_id": "user_test",
        "version": "0.1",
        "core_directions": {"old": 0.2},
        "topic_weights": {"old topic": 0.1},
        "must_read": {"authors": ["Old"], "institutions": [], "keywords": []},
    }
    saved = {}

    monkeypatch.setattr(agents.coldstart_agent, "cold_start", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(agents.db_ops, "get_profile", lambda user_id: saved.get(user_id) or profile)

    def fake_update_profile(user_id, updated):
        saved[user_id] = updated
        return True

    monkeypatch.setattr(agents.db_ops, "update_profile", fake_update_profile)

    result = agents.create_or_update_profile(
        user_id="user_test",
        affiliation="OpenAI",
        core_directions_text="GUI Agent:0.8; Scientific Discovery=0.6",
        topic_weights_text="paper recommendation:0.7",
        must_read_keywords=["agent", "rag"],
        must_read_authors=["Alice"],
        must_read_institutions=["Stanford"],
    )

    updated = saved["user_test"]
    assert updated["affiliation"] == "OpenAI"
    assert updated["core_directions"] == {"GUI Agent": 0.8, "Scientific Discovery": 0.6}
    assert updated["topic_weights"] == {"paper recommendation": 0.7}
    assert updated["must_read"] == {
        "authors": ["Alice"],
        "institutions": ["Stanford"],
        "keywords": ["agent", "rag"],
    }
    assert result["profile"]["top_directions"][0] == ("GUI Agent", 0.8)


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


def test_desktop_reading_reports_forward_saved_report_style(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("PAPERFLOW_REPORT_STYLE=brief\n", encoding="utf-8")
    monkeypatch.setattr(agents, "ENV_PATH", env_path)
    monkeypatch.setattr(
        agents.db_ops,
        "get_push_papers",
        lambda push_id: {"papers": [{"id": 1, "title": "Styled Paper"}]},
    )
    captured: dict[str, object] = {}

    def fake_create_reading_report(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(agents.reading_agent, "create_reading_report", fake_create_reading_report)

    agents.create_reading_reports(
        user_id="user_style",
        push_id="push_style",
        paper_numbers=[1],
        write_feishu=False,
        response_language="en",
    )

    assert captured["request_metadata"]["report_style"] == "brief"
    assert captured["request_metadata"]["response_language"] == "en"


def test_desktop_direct_arxiv_read_generates_backend_report(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    report_path = tmp_path / "direct-arxiv.md"
    report_path.write_text("# Direct arXiv Report\n", encoding="utf-8")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        agents.db_ops,
        "get_paper_by_arxiv_id",
        lambda arxiv_id: {
            "id": 7,
            "arxiv_id": arxiv_id,
            "title": "Direct arXiv Paper",
            "authors": ["Alice"],
            "abstract": "A direct read paper.",
            "source": "arxiv",
        },
    )
    monkeypatch.setattr(agents, "_backfill_docs_to_wiki", lambda user_id, docs: 1)

    def fake_create_reading_report(**kwargs):
        captured.update(kwargs)
        return [
            {
                "title": "Direct arXiv Report",
                "report_path": str(report_path),
                "paper": kwargs["papers"][0],
            }
        ]

    monkeypatch.setattr(agents.reading_agent, "create_reading_report", fake_create_reading_report)

    result = agents.read_arxiv("user_direct", "https://arxiv.org/abs/2606.03963", write_feishu=False)

    assert result["count"] == 1
    assert result["wiki_backfilled"] == 1
    assert result["created_docs"][0]["title"] == "Direct arXiv Report"
    assert result["created_docs"][0]["report_id"]
    assert captured["user_id"] == "user_direct"
    assert captured["request_metadata"]["report_source_type"] == "desktop_arxiv"
    assert captured["request_metadata"]["report_source_key"] == "2606.03963"


def test_reading_report_template_changes_with_saved_style() -> None:
    report = agents.reading_agent.generate_reading_report(
        {"title": "Styled Paper", "abstract": "A structured abstract."},
        {"core_directions": {}},
        report_payload={
            "report_style": "deep",
            "one_sentence_summary": "A concise summary.",
            "abstract": "A structured abstract.",
            "recommendation_label": "maybe_interested",
        },
    )

    assert "Deep-Dive Checklist" in report


def test_reading_report_template_supports_english_response_language() -> None:
    report = agents.reading_agent.generate_reading_report(
        {
            "title": "English Paper",
            "abstract": "A structured abstract.",
            "authors": ["Alice"],
            "source": "arxiv",
            "system_label": "high_relevant",
            "system_score": 0.7,
        },
        {"core_directions": {}},
        report_payload={
            "response_language": "en",
            "one_sentence_summary": "A concise English summary.",
            "abstract": "A structured abstract.",
            "recommendation_label": "推荐阅读",
            "estimated_reading_minutes": 7,
        },
    )

    assert "## One-Sentence Summary" in report
    assert "## Paper Details" in report
    assert "- Authors: Alice" in report
    assert "- Recommendation: **Recommended**" in report
    assert "about 7 min" not in report
    assert "Estimated reading time" not in report
    assert "Q5: What empirical phenomena do the experiments reveal?" in report
    assert "Q7: Summarize the main content of the paper." in report
    assert "## 基本信息" not in report
    assert "预计阅读时间" not in report


def test_reading_report_template_omits_resource_and_evidence_locator_blocks() -> None:
    report = agents.reading_agent.generate_reading_report(
        {
            "title": "Clean Report Paper",
            "abstract": "A structured abstract.",
            "authors": ["Alice"],
            "pdf_url": "https://arxiv.org/pdf/2606.16995v1",
            "paper_url": "https://arxiv.org/abs/2606.16995v1",
            "score": 0.9,
        },
        {"core_directions": {}},
        report_payload={
            "one_sentence_summary": "一条简洁总结。",
            "abstract": "A structured abstract.",
            "institution": "OpenAI",
            "recommendation_label": "强烈推荐",
            "analysis_source": "pdf",
            "experimental_observations": "实验现象包括性能随证据质量提升而改善。",
            "analysis_note": "参考了 PDF 检索证据。",
            "report_evidence_anchors": {"method": ["p.1 method evidence"]},
            "field_evidence_map": {"core_method": ["p.2 method anchor"], "key_results": ["p.3 result anchor"]},
        },
    )

    assert "PDF: https://arxiv.org/pdf/2606.16995v1" not in report
    assert "原文: https://arxiv.org/abs/2606.16995v1" not in report
    assert "证据 PDF 全文 + 元数据" not in report
    assert "PDF 证据定位" not in report
    assert "方法证据锚点" not in report
    assert "结果证据锚点" not in report
    assert "代码与资源" not in report
    assert "预计阅读时间" not in report
    assert "约 8 分钟" not in report
    assert "Q5: 发现了什么实验现象？" in report
    assert "Q7: 总结一下论文的主要内容" in report
    assert "实验现象包括性能随证据质量提升而改善" in report
    assert "- 机构：OpenAI" in report
    assert "★★★★★（5/5）" in report


def test_recommendation_calibration_uses_plain_ranking_score() -> None:
    assert agents.reading_agent.calibrate_recommendation_label(
        {"score": 0.91},
        "强烈推荐",
        "pdf",
    ) == "强烈推荐"
    assert agents.reading_agent.calibrate_recommendation_label(
        {"score": 0.5},
        "强烈推荐",
        "pdf",
    ) == "值得快速浏览"


def test_reading_report_english_heuristic_fallbacks_do_not_emit_chinese(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agents.reading_agent, "_retrieve_report_evidence", lambda *_args, **_kwargs: {})

    paper = {
        "title": "Sparse English Paper",
        "authors": ["Alice"],
        "source": "arxiv",
        "score": 0.72,
        "abstract": "",
    }
    profile = {
        "core_directions": {"multimodal-reasoning": 0.8},
        "methodology_preferences": {
            "preference_data_driven_over_theory": True,
            "preference_systematic_work_over_incremental": True,
        },
    }

    payload = agents.reading_agent.build_heuristic_report_payload(
        paper,
        profile,
        pdf_error="PDF timed out",
        response_language="en",
    )
    report = agents.reading_agent.generate_reading_report(
        paper,
        profile,
        report_payload=payload,
        response_language="en",
    )

    assert payload["response_language"] == "en"
    assert payload["research_background"].startswith("Start with the original abstract")
    assert "PDF fetching timed out" in payload["analysis_note"]
    assert "Relationship to the user profile" in report
    assert "## Paper Details" in report
    assert not any("\u4e00" <= char <= "\u9fff" for char in report)


def test_reading_report_creation_passes_response_language_to_heuristics(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    paper = {"id": 1, "title": "English Creation Paper", "abstract": "", "authors": ["Alice"]}

    monkeypatch.setattr(agents.reading_agent, "get_profile", lambda _user_id: {"core_directions": {}})
    monkeypatch.setattr(agents.reading_agent, "ensure_profile_schema", lambda profile: profile)
    monkeypatch.setattr(agents.reading_agent, "get_existing_reading_reports_for_papers", lambda _user_id, _paper_ids: {})
    monkeypatch.setattr(agents.reading_agent, "_enrich_paper_for_reading_report_compat", lambda item, user_id=None: (item, None, None))
    monkeypatch.setattr(agents.reading_agent, "_synthesize_report_with_llm", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(agents.reading_agent, "_save_reading_report_markdown", lambda **_kwargs: str(tmp_path / "report.md"))
    monkeypatch.setattr(agents.reading_agent, "ingest_reading_report_to_wiki", lambda **_kwargs: {})
    monkeypatch.setattr(agents.reading_agent, "log_behavior", lambda **_kwargs: None)
    monkeypatch.setattr(agents.reading_agent, "_annotate_tracking_links", lambda _docs, _user_id: None)

    def fake_build_payload(*_args, **kwargs):
        captured["response_language"] = kwargs.get("response_language")
        return {
            "response_language": kwargs.get("response_language"),
            "abstract": "Abstract.",
            "one_sentence_summary": "Summary.",
            "recommendation_label": "推荐阅读",
            "analysis_source": "abstract",
            "estimated_reading_minutes": 5,
        }

    monkeypatch.setattr(agents.reading_agent, "build_heuristic_report_payload", fake_build_payload)

    docs = agents.reading_agent.create_reading_report(
        user_id="user_en",
        paper_ids=[1],
        papers=[paper],
        send_to_feishu=False,
        request_metadata={"response_language": "en"},
    )

    assert captured["response_language"] == "en"
    assert docs[0]["title"].startswith("[Reading]")
    assert docs[0]["report_payload"]["response_language"] == "en"


def test_reading_report_creation_generates_missing_reports_concurrently(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active = 0
    max_active = 0
    lock = threading.Lock()
    papers = [
        {"id": 1, "title": "Concurrent Paper One", "abstract": "A", "authors": ["Alice"]},
        {"id": 2, "title": "Concurrent Paper Two", "abstract": "B", "authors": ["Bob"]},
    ]

    monkeypatch.setenv("PAPERFLOW_READING_REPORT_CONCURRENCY", "2")
    monkeypatch.setattr(agents.reading_agent, "get_profile", lambda _user_id: {"core_directions": {}})
    monkeypatch.setattr(agents.reading_agent, "ensure_profile_schema", lambda profile: profile)
    monkeypatch.setattr(agents.reading_agent, "get_existing_reading_reports_for_papers", lambda _user_id, _paper_ids: {})
    monkeypatch.setattr(agents.reading_agent, "_enrich_paper_for_reading_report_compat", lambda item, user_id=None: (item, None, None))
    monkeypatch.setattr(agents.reading_agent, "build_heuristic_report_payload", lambda *_args, **_kwargs: {"analysis_source": "abstract", "recommendation_label": "推荐阅读"})
    monkeypatch.setattr(agents.reading_agent, "generate_reading_report", lambda paper, *_args, **_kwargs: f"# {paper['title']}")
    monkeypatch.setattr(agents.reading_agent, "_save_reading_report_markdown", lambda **kwargs: str(tmp_path / f"{kwargs['paper']['id']}.md"))
    monkeypatch.setattr(agents.reading_agent, "ingest_reading_report_to_wiki", lambda **_kwargs: {})
    monkeypatch.setattr(agents.reading_agent, "log_behavior", lambda **_kwargs: None)
    monkeypatch.setattr(agents.reading_agent, "_annotate_tracking_links", lambda _docs, _user_id: None)

    def fake_synthesize(*_args, **_kwargs):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.1)
        with lock:
            active -= 1
        return {}

    monkeypatch.setattr(agents.reading_agent, "_synthesize_report_with_llm", fake_synthesize)

    docs = agents.reading_agent.create_reading_report(
        user_id="user_concurrent",
        paper_ids=[1, 2],
        papers=papers,
        send_to_feishu=False,
    )

    assert len(docs) == 2
    assert [doc["paper"]["id"] for doc in docs] == [1, 2]
    assert max_active == 2


def test_daily_note_classification_repairs_missing_object_commas() -> None:
    first = "<!-- paperflow:aaaaaaaaaaaaaaaa -->"
    second = "<!-- paperflow:bbbbbbbbbbbbbbbb -->"
    response = f"""
    ```json
    {{
      "assignments": [
        {{"marker": "{first}", "category": "AI Research"}}
        {{"marker": "{second}", "category": "Machine Learning"}},
      ]
    }}
    ```
    """

    result = reading_agent._parse_daily_note_classification_response(  # noqa: SLF001 - parser resilience contract
        response,
        {first, second},
    )

    assert result == {first: "AI Research", second: "Machine Learning"}


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


def test_desktop_paper_card_actions_are_mutually_exclusive_before_submit() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert 'data-action="read"' in script
    assert '"加载中"' in script
    assert '"精读报告"' in script
    assert '"已选精读"' in script
    assert "readSinglePaper" in script
    assert "setPaperDisposition(number, \"read\")" in script
    assert "setPaperDisposition(number, \"skip\")" in script
    assert "setPaperDisposition(number, \"later\")" in script
    assert "同一篇论文只能选择精读、不感兴趣、稍后看中的一种" in script
    assert "待提交：" in script
    assert "card.dataset.disposition = disposition" in script
    assert "delete card.dataset.disposition" in script
    assert '"已不感兴趣"' in script
    assert '"已加入稍后看"' in script
    assert "selected_numbers: selectedNumbers" in script
    assert "请先选择精读论文" in script
    assert "selected_numbers: [number]" not in script
    assert 'button.dataset.action === "select"' not in script
    assert '.paper-card[data-disposition="skip"]' in css
    assert '.paper-card[data-disposition="later"]' in css
    assert '.paper-actions button[data-action="read"].active' in css
    assert '.paper-actions button[data-action="skip"].active' in css
    assert '.paper-actions button[data-action="later"].active' in css


def test_desktop_skip_and_later_feedback_submit_to_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_events: list[tuple[int, str, str]] = []

    monkeypatch.setattr(
        agents.db_ops,
        "get_push_papers",
        lambda push_id: {
            "papers": [
                {"id": "p1", "title": "Read Paper", "category": "agent"},
                {"id": "p2", "title": "Skip Paper", "category": "agent"},
                {"id": "p3", "title": "Later Paper", "category": "memory"},
            ]
        },
    )
    monkeypatch.setattr(agents.feedback_agent, "get_existing_selected_numbers", lambda user_id, push_id, papers: set())
    monkeypatch.setattr(agents.db_ops, "get_profile", lambda user_id: {"core_directions": {}})
    monkeypatch.setattr(agents.db_ops, "get_recent_selected_papers", lambda *args, **kwargs: [])
    monkeypatch.setattr(agents.feedback_agent, "estimate_feedback_strength_multiplier", lambda push_id, current_timestamp: (1.0, 0.0))
    monkeypatch.setattr(agents.feedback_agent, "update_profile_based_on_selection", lambda **kwargs: {"core_directions": {"agent": 1}})
    monkeypatch.setattr(agents.feedback_agent, "ingest_profile_drift_to_wiki", lambda **kwargs: None)

    def fake_log_feedback_event(**kwargs):
        captured_events.append((kwargs["paper_number"], kwargs["action"], kwargs["action_type"]))
        return len(captured_events)

    monkeypatch.setattr(agents, "_log_feedback_event", fake_log_feedback_event)

    result = agents.submit_gui_feedback(
        user_id="user_test",
        push_id="push_test",
        selected_numbers=[1],
        skipped_numbers=[2],
        later_numbers=[3],
    )

    assert result["selected_numbers"] == [1]
    assert result["skipped_numbers"] == [2]
    assert result["later_numbers"] == [3]
    assert (1, "selected", "gui_selected") in captured_events
    assert (2, "skipped", "gui_skipped") in captured_events
    assert (3, "later", "gui_later") in captured_events


def test_desktop_wiki_frontend_derives_architecture_from_backend_graph() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert "buildWikiMap" in script
    assert "conceptEntriesFromGraph" in script
    assert "candidateLabelsForNode" in script
    assert "architecture:core" in script
    assert "知识库架构" in script
    assert "真实图谱" in script
    assert "related_papers" in script
    assert 'setWikiMapFocus(pickWikiFocusNodeId() || "architecture:core")' in script
    assert "wikiStatsText" in script
    assert "wikiDailyGraphParams" in script
    assert 'id="wikiDailyScope"' in html
    assert 'id="wikiDailyMonth"' in html
    assert "wikiMapCatalog" not in script
    assert "concept:structured-memory" not in script
    assert "concept:agent" not in script
    assert "&limit=120" in script
    assert "const query = rawQuery ||" not in script
    assert 'DEMO_MODE ? demoWikiNodes : []' in script
    assert 'class="wiki-entry-body"' in html
    assert "Wiki 架构图" in html
    assert "grid-template-columns: minmax(760px, 1fr) 292px" in css
    assert "repeating-linear-gradient(115deg" in css
    assert ".wiki-graph.real .graph-node.small .node-label" in css
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


def test_desktop_buttons_have_unified_visual_feedback() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert "buttonFeedbackTimers: new WeakMap()" in script
    assert "lastActionButton: null" in script
    assert "function flashButtonFeedback" in script
    assert "function setActionButtonBusy" in script
    assert "function bindButtonFeedback" in script
    assert "document.addEventListener(\"click\"" in script
    assert "state.lastActionButton = button" in script
    assert "setActionButtonBusy(actionButton, true)" in script
    assert "flashButtonFeedback(actionButton, \"success\")" in script
    assert "flashButtonFeedback(actionButton, \"error\")" in script
    assert "bindButtonFeedback();" in script
    assert "已全选论文来源" in script
    assert "已清空论文来源" in script
    assert "已复制报告路径" in script
    assert "已打开链接" in script
    assert "已移除" in script
    assert "button.feedback-click::after" in css
    assert "button.feedback-success::after" in css
    assert "button.feedback-error::after" in css
    assert "button.is-busy" in css
    assert "@keyframes button-feedback-flash" in css
    assert "@keyframes button-busy-spin" in css


def test_desktop_paper_date_and_metrics_sync_with_backend() -> None:
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert '<strong id="candidateStat">-</strong>' in html
    assert '<strong id="filteredStat">-</strong>' in html
    assert "当前批次候选" in html
    assert "推荐数" in html
    assert "今日候选" not in html
    assert 'id="cacheSizeStat"' in html
    assert "2.8GB" not in html
    assert "cache_display" in script
    assert "storage_stats" in script
    assert 'new Date("2026-06-10")' not in script
    assert "function todayDateValue()" in script
    assert "function syncDateControls()" in script
    assert '$("paperDate").value = todayDateValue()' in script
    assert "selectedDateFetchDays()" in script
    assert "runButton.disabled = false" in script
    assert 'target_date: $("paperDate").value' in script
    assert "dailyLimit: (limit) => `每日上限 ${limit}`" in script
    assert "dailyLimit: (limit) => `Daily limit ${limit}`" in script
    assert "旧缓存参数不一致时会自动刷新" in script
    assert 'id="saveAdvancedSettingsBtn" class="primary" type="button">保存设置</button>' in html
    assert 'runAction(saveSettings, "保存设置")' in script
    assert "/api/daily/status?task_id=" in script
    assert "/api/daily/status?user_id=" in script
    assert "pollDailyTask(taskId, data.push, userId, pollToken)" in script
    assert "检查当天缓存" in script
    assert "已加载当天缓存" in script
    assert "本次没有重新爬取" in script
    assert 'if (data.cached || data.task?.status === "completed")' in script
    assert "fromCache: Boolean(data.cached || data.task.cached)" in script
    assert "while (pollToken === state.dailyPollToken)" in script
    assert "for (let attempt = 0; attempt < 80" not in script
    assert "function setDailyTaskState(" in script
    assert "async function resumeDailyTask()" in script
    assert 'if (name === "papers") {' in script
    assert "await resumeDailyTask()" in script
    assert "state.dailyPollToken += 1" in script
    assert "metadata.total_fetched ?? metadata.fetched_count ?? papers.length ?? 0" in script
    assert "metadata.paper_count ?? metadata.filtered_count ?? metadata.ranked_count ?? papers.length ?? 0" in script
    assert "function pushMetaText(" in script
    assert "最近缓存批次" in script
    assert "单源上限" in script
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


def test_desktop_reports_use_only_configured_report_dir_when_explicit(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    configured = tmp_path / "reports"
    configured.mkdir()
    (configured / "wiki-node.md").write_text(
        "---\nnode_id: paper:1\nnode_type: paper\n---\n# Wiki Node\n",
        encoding="utf-8",
    )
    (configured / "reading-report.md").write_text(
        "---\n"
        "user_id: \"cheng tan\"\n"
        "title: \"Reading Report\"\n"
        "report_version: \"test-v1\"\n"
        "saved_at: \"2026-06-14T10:00:00\"\n"
        "---\n"
        "# Reading Report\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(agents, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("PAPERFLOW_READING_REPORTS_DIR", str(configured))

    assert agents._reading_report_dirs() == [configured.resolve()]  # noqa: SLF001 - report source contract
    payload = agents.list_reports(user_id="cheng tan", days=30)

    assert payload["source_dirs"] == [str(configured)]
    assert [report["title"] for report in payload["reports"]] == ["Reading Report"]


def test_desktop_chat_sources_do_not_fallback_to_demo_in_real_mode() -> None:
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")

    assert "Efficient Test-Time Scaling</span>" not in html
    assert "Multi-Modal RAG</span>" not in html
    assert "Wiki: 结构化记忆</span>" not in html
    assert "function renderChatSources(sources = DEMO_MODE ? demoSources : [])" in script
    assert "data.sources || demoSources" not in script
    assert "暂无参考文献" in script
    assert 'mention_required: "需要选择论文"' in script
    assert 'data.routing_reason !== "mention_required" ? "" : routingLabel(data.routing_reason)' in script
    assert 'replace(/\\*\\*([^*\\n]+?)\\*\\*/g, "<strong>$1</strong>")' in script


def test_desktop_wiki_chat_supports_clickable_citations_streaming_and_mentions() -> None:
    html = (PROJECT_ROOT / "deployments/desktop/static/index.html").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "deployments/desktop/static/desktop.js").read_text(encoding="utf-8")
    css = (PROJECT_ROOT / "deployments/desktop/static/desktop.css").read_text(encoding="utf-8")

    assert 'id="mentionSuggestions"' in html
    assert 'id="chatMentionChips"' in html
    assert 'id="chatHistoryList"' in html
    assert 'id="newChatBtn"' in html
    assert 'id="clearChatHistoryBtn"' in html
    assert "quick-prompts" not in html
    assert "总结 RAG 趋势" not in html
    assert "对比两篇方法" not in html
    assert "找相关概念" not in html
    assert "/api/wiki/ask/stream" in script
    assert "quick-prompts" not in script
    assert "/api/chat/sessions" in script
    assert "/api/chat/sessions/clear" in script
    assert "/api/chat/session" in script
    assert "function clearChatHistory()" in script
    assert "此操作不会删除 Wiki 或精读报告" in script
    assert "clearChatHistoryBtn" in script
    assert "loadChatSessions({ openLatest: true })" in script
    assert "session_id: state.chatSessionId || \"\"" in script
    assert "state.chatSessionId = data.session_id" in script
    assert "isUnknownApiRoute" in script
    assert "renderChatHistoryUnavailable" in script
    assert "后端还没加载聊天历史接口" in script
    assert 'document.body.classList.toggle("chat-view", name === "chat")' in script
    assert "streamWikiAsk(payload, answerTarget, message)" in script
    assert "/api/wiki/mentions" in script
    assert "renderAnswerWithCitations" in script
    assert "let doneReceived = false" in script
    assert "doneReceived = true" in script
    assert "if (!doneReceived)" in script
    assert "流式连接中断，正在切换到完整回答" in script
    assert "流式回答中断，已自动切换到完整回答" in script
    assert "流式输出中断" in script
    assert "已自动切换到完整回答" in script
    assert "class=\"citation-ref\"" in script
    assert "data-citation-index" in script
    assert "focusCitationSource" in script
    assert "renderCitationRow" not in script
    assert "本地 Wiki 引用" not in script
    assert "参考文献 ·" in script
    assert "renderMentionSuggestions" in script
    assert "insertMention" in script
    assert "`@[${title}](${nodeId})`" in script
    assert "mentions: activeMentionsForQuestion(question)" in script
    assert "retrieval_required" in script
    assert ".citation-ref" in css
    assert ".mention-suggestions" in css
    assert ".quick-prompts" not in css
    assert ".chat-history-pane" in css
    assert ".chat-session-button.active" in css
    assert "body.chat-view #chat" in css
    assert "body.chat-view .chat-layout" in css
    assert "body.chat-view .source-list" in css
    assert "scrollbar-gutter: stable" in css
    assert ".answer-meta .wiki" in css
    assert ".answer-text strong" in css


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


def test_desktop_daily_push_task_reuses_cached_target_date(monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = PROJECT_ROOT / ".missing-test-env"
    monkeypatch.setattr(agents, "ENV_PATH", env_path)
    monkeypatch.setenv("PAPERFLOW_DAILY_LIMIT", "30")
    monkeypatch.setenv("PAPERFLOW_RELEVANCE_THRESHOLD", "60")
    monkeypatch.setenv("PAPERFLOW_ENABLE_ARXIV", "true")
    monkeypatch.setenv("PAPERFLOW_ENABLE_OPENREVIEW", "true")
    monkeypatch.setenv("PAPERFLOW_ENABLE_SEMANTIC_SCHOLAR", "false")
    monkeypatch.setenv("PAPERFLOW_ENABLE_CUSTOM_RSS", "false")
    monkeypatch.setenv("PAPERFLOW_DEFAULT_ARXIV_CATEGORIES", "cs.CL,cs.AI,cs.IR,cs.LG")
    monkeypatch.setenv("PAPERFLOW_DEFAULT_CONFERENCES", "ICLR,NeurIPS,ACL,SIGIR")
    monkeypatch.setenv("PAPERFLOW_DEFAULT_JOURNALS", "")
    monkeypatch.setenv("PAPERFLOW_CUSTOM_RSS_URLS", "https://arxiv.org/rss/cs.CL")
    cached_push = {
        "push_id": "push_cached_today",
        "push_time": "2026-06-14 08:00:00",
        "papers": [{"id": 1, "title": "Cached Paper"}],
        "metadata": {
            "paper_count": 1,
            "total_fetched": 8,
            "daily_limit": 30,
            "limit_per_source": 30,
            "fetch_days": 1,
            "target_date": "2026-06-14",
            "relevance_threshold": 60,
            "arxiv_categories": ["cs.CL", "cs.AI", "cs.IR", "cs.LG"],
            "conferences": ["ICLR", "NeurIPS", "ACL", "SIGIR"],
            "journals": [],
            "enable_semantic_scholar": False,
            "enable_custom_rss": False,
            "custom_rss_urls": [],
        },
    }

    monkeypatch.setattr(agents.db_ops, "get_push_for_date", lambda user_id, target_date: cached_push)
    monkeypatch.setattr(
        agents,
        "run_daily_push",
        lambda *args, **kwargs: pytest.fail("cached daily push should not recrawl"),
    )

    started = agents.start_daily_push_task(
        "user_task_cached",
        days=1,
        target_date="2026-06-14",
    )

    assert started["cached"] is True
    assert started["task"]["status"] == "completed"
    assert started["task"]["cached"] is True
    assert started["task"]["push"]["push_id"] == "push_cached_today"
    assert started["task"]["push"]["metadata"]["cached_for_date"] == "2026-06-14"


def test_desktop_daily_push_task_ignores_legacy_cache_without_target_date(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "PAPERFLOW_DAILY_LIMIT=30",
                "PAPERFLOW_RELEVANCE_THRESHOLD=60",
                "PAPERFLOW_ENABLE_ARXIV=true",
                "PAPERFLOW_ENABLE_OPENREVIEW=true",
                "PAPERFLOW_ENABLE_SEMANTIC_SCHOLAR=false",
                "PAPERFLOW_ENABLE_CUSTOM_RSS=false",
                "PAPERFLOW_DEFAULT_ARXIV_CATEGORIES=cs.CL,cs.AI,cs.IR,cs.LG",
                "PAPERFLOW_DEFAULT_CONFERENCES=ICLR,NeurIPS,ACL,SIGIR",
                "PAPERFLOW_DEFAULT_JOURNALS=",
                "PAPERFLOW_CUSTOM_RSS_URLS=",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(agents, "ENV_PATH", env_path)
    cached_push = {
        "push_id": "push_legacy_without_target_date",
        "push_time": "2026-06-14 08:00:00",
        "papers": [{"id": 1, "title": "Legacy Cached Paper"}],
        "metadata": {
            "paper_count": 1,
            "total_fetched": 8,
            "daily_limit": 30,
            "limit_per_source": 30,
            "fetch_days": 1,
            "cached_for_date": "2026-06-14",
            "relevance_threshold": 60,
            "arxiv_categories": ["cs.CL", "cs.AI", "cs.IR", "cs.LG"],
            "conferences": ["ICLR", "NeurIPS", "ACL", "SIGIR"],
            "journals": [],
            "enable_semantic_scholar": False,
            "enable_custom_rss": False,
            "custom_rss_urls": [],
        },
    }
    started_event = threading.Event()
    release_event = threading.Event()
    captured: dict[str, object] = {}

    monkeypatch.setattr(agents.db_ops, "get_push_for_date", lambda user_id, target_date: cached_push)

    def fake_run_daily_push(user_id, **kwargs):
        captured["user_id"] = user_id
        captured.update(kwargs)
        started_event.set()
        release_event.wait(timeout=2)
        return {
            "result": {"push_id": "push_new_target_date"},
            "push": {"push_id": "push_new_target_date", "papers": [], "metadata": {}},
        }

    monkeypatch.setattr(agents, "run_daily_push", fake_run_daily_push)

    started = agents.start_daily_push_task(
        "user_task_legacy_cache",
        days=1,
        target_date="2026-06-14",
    )

    try:
        assert started.get("cached") is not True
        assert started["task"]["status"] == "queued"
        assert started_event.wait(timeout=2)
        assert captured["target_date"] == "2026-06-14"
    finally:
        release_event.set()


def test_desktop_daily_push_task_ignores_cached_target_date_when_settings_change(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "PAPERFLOW_DAILY_LIMIT=12",
                "PAPERFLOW_RELEVANCE_THRESHOLD=80",
                "PAPERFLOW_ENABLE_ARXIV=true",
                "PAPERFLOW_ENABLE_OPENREVIEW=false",
                "PAPERFLOW_ENABLE_SEMANTIC_SCHOLAR=false",
                "PAPERFLOW_ENABLE_CUSTOM_RSS=false",
                "PAPERFLOW_DEFAULT_ARXIV_CATEGORIES=cs.CL",
                "PAPERFLOW_DEFAULT_CONFERENCES=",
                "PAPERFLOW_DEFAULT_JOURNALS=",
                "PAPERFLOW_CUSTOM_RSS_URLS=",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(agents, "ENV_PATH", env_path)
    cached_push = {
        "push_id": "push_old_settings",
        "push_time": "2026-06-14 08:00:00",
        "papers": [{"id": 1, "title": "Old Cached Paper"}],
        "metadata": {
            "paper_count": 1,
            "total_fetched": 8,
            "daily_limit": 30,
            "limit_per_source": 30,
            "fetch_days": 1,
            "relevance_threshold": 60,
            "arxiv_categories": ["cs.CL"],
            "conferences": [],
            "journals": [],
            "enable_semantic_scholar": False,
            "enable_custom_rss": False,
            "custom_rss_urls": [],
        },
    }
    started_event = threading.Event()
    release_event = threading.Event()
    captured: dict[str, object] = {}

    monkeypatch.setattr(agents.db_ops, "get_push_for_date", lambda user_id, target_date: cached_push)

    def fake_run_daily_push(user_id, **kwargs):
        captured["user_id"] = user_id
        captured.update(kwargs)
        started_event.set()
        release_event.wait(timeout=2)
        return {
            "result": {"push_id": "push_new_settings"},
            "push": {"push_id": "push_new_settings", "papers": [], "metadata": {}},
        }

    monkeypatch.setattr(agents, "run_daily_push", fake_run_daily_push)

    started = agents.start_daily_push_task(
        "user_task_cache_mismatch",
        days=1,
        target_date="2026-06-14",
    )

    try:
        assert started.get("cached") is not True
        assert started["task"]["status"] == "queued"
        assert started_event.wait(timeout=2)
        assert captured["limit_per_source"] == 12
    finally:
        release_event.set()


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


def test_desktop_daily_push_task_forwards_gui_filters_and_recovers_by_user(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    started_event = threading.Event()
    release_event = threading.Event()

    def fake_run_daily_push(user_id, **kwargs):
        captured["user_id"] = user_id
        captured.update(kwargs)
        started_event.set()
        release_event.wait(timeout=2)
        return {
            "result": {"push_id": "push_task_filters"},
            "push": {"push_id": "push_task_filters", "papers": [], "metadata": {}},
        }

    monkeypatch.setattr(agents, "run_daily_push", fake_run_daily_push)

    started = agents.start_daily_push_task(
        "user_task_filters",
        days=3,
        limit_per_source=77,
        arxiv_categories=["cs.LG", "cs.CV"],
        conferences=["ICLR"],
        journals=["Nature"],
        target_date="2026-06-12",
    )

    try:
        assert started_event.wait(timeout=2)
        by_user = agents.get_daily_push_task(user_id="user_task_filters")["task"]

        assert by_user["task_id"] == started["task"]["task_id"]
        assert by_user["days"] == 3
        assert by_user["limit_per_source"] == 77
        assert by_user["arxiv_categories"] == ["cs.LG", "cs.CV"]
        assert by_user["conferences"] == ["ICLR"]
        assert by_user["journals"] == ["Nature"]
        assert by_user["target_date"] == "2026-06-12"
        assert captured["user_id"] == "user_task_filters"
        assert captured["days"] == 3
        assert captured["limit_per_source"] == 77
        assert captured["arxiv_categories"] == ["cs.LG", "cs.CV"]
        assert captured["conferences"] == ["ICLR"]
        assert captured["journals"] == ["Nature"]
        assert captured["target_date"] == "2026-06-12"
        assert callable(captured["progress_callback"])
    finally:
        release_event.set()

    task = None
    for _ in range(50):
        task = agents.get_daily_push_task(task_id=started["task"]["task_id"])["task"]
        if task and task["status"] == "completed":
            break
        time.sleep(0.02)
    assert task is not None
    assert task["status"] == "completed"


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


def test_reading_report_writes_obsidian_deep_reading_and_daily_note(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daily_root = tmp_path / "Daily Note"
    monkeypatch.setenv("PAPERFLOW_READING_REPORTS_DIR", str(daily_root))
    monkeypatch.setenv("PAPERFLOW_PDF_DIR", str(daily_root))

    paper = {
        "id": 1,
        "title": "Generative AI in K-12 Classrooms: A Midyear Implementation Report",
        "arxiv_id": "2605.16277",
        "publish_date": "2026-05-20",
        "pdf_url": "https://arxiv.org/pdf/2605.16277",
        "abs_url": "https://arxiv.org/abs/2605.16277",
        "institution": "PaperFlow University",
        "subjects": ["cs.AI"],
        "abstract": "This paper studies generative AI in classrooms with teachers and students.",
    }
    payload = {
        "one_sentence_summary": "生成式人工智能在K-12教育场景中的实际应用模式与早期学业信号。",
        "keywords": ["education", "classroom"],
        "generation_provider": "heuristic",
        "generation_model": "test",
        "recommendation_label": "high_match",
    }

    report_path = Path(
        reading_agent._save_reading_report_markdown(  # noqa: SLF001 - storage contract
            user_id="cheng tan",
            paper=paper,
            report_content=(
                "# Generative AI in K-12 Classrooms\n\n"
                "Q6: 总结一下论文的主要内容\n\n"
                "这篇论文系统总结了生成式 AI 在 K-12 课堂中的使用方式、教师采用模式和早期学业信号。\n\n"
                "## 基本信息\n\n测试报告。"
            ),
            report_payload=payload,
        )
    )

    expected_dir = daily_root / "Daily Note 2026" / "Deep Reading - May 2026"
    daily_note = daily_root / "Daily Note 2026" / "Daily Note - May 2026.md"
    toc = daily_root / "Daily Note 2026" / "Table of Content - 2026.md"
    pdf_dir = reading_agent._resolve_configured_dir(  # noqa: SLF001 - storage contract
        "PAPERFLOW_PDF_DIR",
        "data/exports",
        paper,
        user_id="cheng tan",
        category="pdf",
    )

    assert report_path.parent == expected_dir
    assert report_path.name.startswith("Generative AI in K-12 Classrooms")
    assert report_path.suffix == ".md"
    report_text = report_path.read_text(encoding="utf-8")
    assert "[[Daily Note - May 2026]]" not in report_text
    assert "- PDF：" not in report_text
    assert 'abs_url: "https://arxiv.org/abs/2605.16277"' in report_text
    assert 'institution: "PaperFlow University"' in report_text
    assert pdf_dir == (daily_root / "Daily Note 2026" / "arXiv - May 2026").resolve()
    daily_text = daily_note.read_text(encoding="utf-8")
    assert "# AI for Education" in daily_text
    assert "[[Deep Reading - May 2026/Generative AI in K-12 Classrooms" in daily_text
    assert "这篇论文系统总结了生成式 AI 在 K-12 课堂中的使用方式" in daily_text
    assert "生成式人工智能在K-12教育场景中的实际应用模式与早期学业信号" not in daily_text
    assert "https://arxiv.org/pdf/2605.16277" in daily_text
    assert "[[Daily Note - May 2026]]" in toc.read_text(encoding="utf-8")


def test_daily_note_topic_summary_methods_use_user_profile() -> None:
    content = """
# Agent Skills, Harness & Tooling

<!-- paperflow:1234567890abcdef -->
## Reliable Tool Use for Research Agents

- **这篇论文研究 tool orchestration 和 multi-agent harness 如何提升科研代理的可靠性。**
""".strip()
    profile = {
        "core_directions": {"tool orchestration": 0.9, "reward modeling": 0.8},
        "topic_weights": {"multi-agent harness": 0.7},
        "must_read": {"keywords": ["research agents", "diffusion"]},
    }

    refreshed = reading_agent._refresh_daily_note_topic_summaries(  # noqa: SLF001 - summary contract
        content,
        user_profile=profile,
    )

    assert "- 方法：tool orchestration, multi-agent harness, research agents" in refreshed
    assert "reward modeling" not in refreshed
    assert "diffusion" not in refreshed


def test_obsidian_daily_note_category_uses_word_boundaries() -> None:
    category = reading_agent._daily_note_category(  # noqa: SLF001 - category contract
        {"title": "Dense Supervision, Sparse Updates: On the Sparsity and Geometry of On-Policy Distillation"},
        {},
    )

    assert category == "Machine Learning"
