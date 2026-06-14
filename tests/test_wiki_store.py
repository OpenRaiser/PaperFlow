from __future__ import annotations

import importlib
import json
from pathlib import Path


db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
wiki_db = importlib.import_module("skills.wiki-store.scripts.wiki_db")
wiki_ingest = importlib.import_module("agents.wiki-agent.ingest.from_reading_report")
feedback_ingest = importlib.import_module("agents.wiki-agent.ingest.from_feedback")
daily_ingest = importlib.import_module("agents.wiki-agent.ingest.from_daily_push")
drift_ingest = importlib.import_module("agents.wiki-agent.ingest.from_profile_drift")
topic_ingest = importlib.import_module("agents.wiki-agent.ingest.from_topic_clustering")
answer_module = importlib.import_module("agents.wiki-agent.retrieve.answer")
backfill_ingest = importlib.import_module("agents.wiki-agent.ingest.backfill")
monthly_export = importlib.import_module("agents.wiki-agent.export.monthly_report")


def _use_tmp_wiki(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(db_ops, "DB_PATH", tmp_path / "paperflow.db")
    monkeypatch.setenv("PAPERFLOW_WIKI_DIR", str(tmp_path / "wiki"))
    monkeypatch.setenv("PAPERFLOW_ROLES_PATH", str(tmp_path / "roles.json"))
    monkeypatch.setenv("PAPERFLOW_LLM_PROVIDER", "mock")
    monkeypatch.setenv("PAPERFLOW_EMBED_PROVIDER", "hash")
    db_ops.init_db()
    wiki_db.init_wiki_schema()


def test_wiki_store_upserts_lists_searches_and_writes_mirror(monkeypatch, tmp_path):
    _use_tmp_wiki(monkeypatch, tmp_path)

    node = wiki_db.upsert_node(
        user_id="user_alice",
        node_id="paper:2604.00001",
        node_type="paper",
        title="Diffusion Planning for Agents",
        body="A diffusion planning method for scientific agents.",
        metadata={"arxiv_id": "2604.00001"},
        keywords="diffusion planning agents",
        source_type="reading_report",
        source_ref="report.md",
    )

    assert node["node_id"] == "paper:2604.00001"
    assert (tmp_path / "wiki" / node["file_path"]).exists()

    listed = wiki_db.list_nodes("user_alice")
    assert [item["node_id"] for item in listed] == ["paper:2604.00001"]

    found = wiki_db.search_nodes("user_alice", "diffusion")
    assert found and found[0]["title"] == "Diffusion Planning for Agents"

    stats = wiki_db.stats("user_alice")
    assert stats["nodes"] == 1
    assert stats["nodes_by_type"] == {"paper": 1}
    assert stats["wiki_dir"] == str(tmp_path / "wiki")


def test_wiki_mirror_uses_user_defined_role_name(monkeypatch, tmp_path):
    _use_tmp_wiki(monkeypatch, tmp_path)
    (tmp_path / "roles.json").write_text(
        json.dumps({"roles": {"gui agent lab": {"user_id": "user_alice"}}}),
        encoding="utf-8",
    )

    node = wiki_db.upsert_node(
        user_id="user_alice",
        node_id="paper:2604.00002",
        node_type="paper",
        title="Role Scoped Wiki Mirror",
        body="Wiki Markdown mirrors should use the user-facing role name.",
    )

    assert node["file_path"].startswith("gui-agent-lab/papers/")
    assert (tmp_path / "wiki" / node["file_path"]).exists()


def test_reading_report_ingest_creates_paper_sections_edges_and_citations(monkeypatch, tmp_path):
    _use_tmp_wiki(monkeypatch, tmp_path)

    result = wiki_ingest.ingest_reading_report(
        user_id="user_alice",
        paper={
            "id": 7,
            "arxiv_id": "2604.00007",
            "title": "Graph RAG for Literature Review",
            "authors": ["Ada"],
            "abstract": "Graph retrieval improves literature review agents.",
            "categories": ["cs.CL"],
            "pdf_path": str(tmp_path / "papers" / "2604.00007.pdf"),
        },
        report_md="# Graph RAG for Literature Review\n",
        payload={
            "one_sentence_summary": "A graph RAG system for literature review.",
            "core_method": "Builds a graph over papers and retrieves section evidence.",
            "key_results": "Improves citation-grounded answers.",
            "main_contributions": ["Section-level citation nodes"],
            "relevance_points": ["Useful for PaperFlow wiki search"],
            "keywords": ["graph", "rag", "literature"],
            "generation_provider": "mock",
            "generation_model": "mock-model",
        },
        report_path=str(tmp_path / "reports" / "2604.00007 - reading-report.md"),
        doc_url="https://example.feishu.cn/docx/wiki",
        doc_token="doc_wiki",
    )

    assert result["paper_node"] == "paper:2604.00007"
    assert result["section_count"] >= 5

    stats = wiki_db.stats("user_alice")
    assert stats["nodes_by_type"]["paper"] == 1
    assert stats["nodes_by_type"]["section"] >= 5
    assert stats["edges"] >= 5
    assert stats["citations"] >= 5

    found = wiki_db.search_nodes("user_alice", "citation")
    assert any(item["node_type"] == "section" for item in found)
    paper_node = wiki_db.get_node("user_alice", "paper:2604.00007")
    assert paper_node["metadata"]["pdf_path"].endswith("2604.00007.pdf")
    assert paper_node["metadata"]["report_path"].endswith("reading-report.md")
    assert "## Summary" in paper_node["body"]
    assert "## Why It Matters" in paper_node["body"]
    assert "Useful for PaperFlow wiki search" in paper_node["body"]
    section_nodes = wiki_db.search_nodes("user_alice", "Solution approach", node_type="section")
    assert any("Graph RAG for Literature Review / Q3 Solution approach" == node["title"] for node in section_nodes)


def test_feedback_ingest_creates_preference_edges(monkeypatch, tmp_path):
    _use_tmp_wiki(monkeypatch, tmp_path)

    selected = feedback_ingest.ingest_feedback_event(
        user_id="user_alice",
        push_id="push_001",
        paper={
            "id": 9,
            "arxiv_id": "2604.00009",
            "title": "Agentic Paper Recommendation",
            "abstract": "A recommender for agentic paper reading.",
            "topics": ["agents", "recommendation"],
            "category": "high_relevant",
        },
        action="selected",
        action_type="selected",
        category="high_relevant",
        metadata={"paper_number": 1},
        behavior_log_id=101,
    )
    skipped = feedback_ingest.ingest_feedback_event(
        user_id="user_alice",
        push_id="push_001",
        paper={
            "id": 10,
            "arxiv_id": "2604.00010",
            "title": "Unrelated Hardware Survey",
            "abstract": "A survey of unrelated hardware systems.",
            "topics": ["hardware"],
            "category": "maybe_interested",
        },
        action="skipped",
        action_type="skipped",
        category="maybe_interested",
        metadata={"paper_number": 2},
        behavior_log_id=102,
    )

    assert selected["relation"] == "interested_in"
    assert skipped["relation"] == "skipped"

    stats = wiki_db.stats("user_alice")
    assert stats["nodes_by_type"] == {"paper": 2}
    assert stats["edges"] == 2
    assert stats["citations"] == 2

    found = wiki_db.search_nodes("user_alice", "agentic")
    assert [node["node_id"] for node in found] == ["paper:2604.00009"]


def test_daily_push_drift_topics_embeddings_and_ask(monkeypatch, tmp_path):
    _use_tmp_wiki(monkeypatch, tmp_path)

    daily_ingest.ingest_pushed_paper(
        user_id="user_alice",
        push_id="push_20260601",
        paper={
            "id": 11,
            "arxiv_id": "2606.00011",
            "title": "Graph RAG Memory for Scientific Agents",
            "abstract": "Graph RAG memory helps scientific agents cite prior readings.",
            "keywords": ["graph-rag", "agents"],
        },
        category="high_relevant",
        metadata={"rank": 1, "score": 0.91, "keywords": ["graph-rag", "agents"]},
        behavior_log_id=201,
    )
    pushed_paper = wiki_db.get_node("user_alice", "paper:2606.00011")
    push_trajectory = wiki_db.get_node("user_alice", "trajectory:user_alice:push_20260601")
    assert "## Candidate Summary" in pushed_paper["body"]
    assert "## Recommendation Context" in pushed_paper["body"]
    assert "Candidate paper from daily push" not in pushed_paper["body"]
    assert "## Daily Push Snapshot" in push_trajectory["body"]
    drift_result = drift_ingest.ingest_drift(
        user_id="user_alice",
        before={"topic_weights": {"graph-rag": 0.2}},
        after={
            "topic_weights": {"graph-rag": 0.5},
            "drift_state": {"status": "shifting", "long_term_vector": [0.1] * 64},
        },
        evidence_papers=[{"arxiv_id": "2606.00011"}],
        source_ref="push_20260601",
    )
    topic_result = topic_ingest.flush_topics("user_alice", min_count=1)
    embed_result = wiki_db.embed_nodes_for_user("user_alice", force=True)
    answer = answer_module.answer_question("user_alice", "graph rag agents", limit=4)

    assert drift_result["delta_count"] == 1
    topic_node = wiki_db.get_node("user_alice", "topic:graph-rag")
    trajectory_node = wiki_db.get_node("user_alice", drift_result["trajectory_node"])
    assert "## Topic Signal" in topic_node["body"]
    assert "Topic node for" not in topic_node["body"]
    assert "## Interest Drift Summary" in trajectory_node["body"]
    assert "long_term_vector" not in trajectory_node["metadata"].get("drift_state", {})
    assert topic_result["topics"] >= 1
    assert embed_result["embedded"] >= 3
    assert answer["citations"]
    assert "mock" in answer["token_usage"]["provider"]


def test_search_and_ask_degrade_when_model_backends_fail(monkeypatch, tmp_path):
    _use_tmp_wiki(monkeypatch, tmp_path)

    wiki_db.upsert_node(
        user_id="user_alice",
        node_id="paper:2606.00013",
        node_type="paper",
        title="Robust Local Wiki Search",
        body="Keyword search should still work when model backends are unavailable.",
        keywords="robust local search",
    )

    def broken_vector_search(*_args, **_kwargs):
        raise RuntimeError("embedding backend unavailable")

    class BrokenLLM:
        name = "broken"
        model = "broken-model"

        def generate(self, *_args, **_kwargs):
            raise RuntimeError("llm backend unavailable")

    monkeypatch.setattr(wiki_db, "vector_search_nodes", broken_vector_search)
    monkeypatch.setattr(answer_module, "build_llm_provider", lambda: BrokenLLM())

    found = wiki_db.search_nodes("user_alice", "robust local")
    answer = answer_module.answer_question("user_alice", "robust local", limit=2)

    assert found
    assert found[0]["node_id"] == "paper:2606.00013"
    assert "local wiki snippets" in answer["text"]
    assert answer["token_usage"]["llm_error"] == "llm backend unavailable"


def test_backfill_replays_push_and_feedback_logs(monkeypatch, tmp_path):
    _use_tmp_wiki(monkeypatch, tmp_path)

    paper_id = db_ops.save_paper(
        arxiv_id="2606.00012",
        doi="",
        title="Backfilled Agent Memory",
        authors=["Alice"],
        abstract="Backfilled memory for agents.",
        categories=["cs.AI"],
    )
    db_ops.log_behavior(
        user_id="user_alice",
        push_id="push_backfill",
        paper_id=paper_id,
        action="pushed",
        action_type="push",
        category="high_relevant",
        metadata={"rank": 1, "score": 0.9, "keywords": ["memory"]},
    )
    db_ops.log_behavior(
        user_id="user_alice",
        push_id="push_backfill",
        paper_id=paper_id,
        action="selected",
        action_type="selected",
        category="high_relevant",
        metadata={"paper_number": 1},
    )

    result = backfill_ingest.backfill_user("user_alice")
    stats = wiki_db.stats("user_alice")

    assert result["pushed"] == 1
    assert result["feedback"] == 1
    assert stats["nodes_by_type"]["paper"] == 1
    assert stats["edges"] >= 2


def test_backfill_handles_wiki_only_database(monkeypatch, tmp_path):
    monkeypatch.setattr(db_ops, "DB_PATH", tmp_path / "paperflow.db")
    monkeypatch.setenv("PAPERFLOW_WIKI_DIR", str(tmp_path / "wiki"))
    wiki_db.init_wiki_schema()

    assert backfill_ingest.backfill_all() == {}
    result = backfill_ingest.backfill_user("user_alice")
    assert result["pushed"] == 0
    assert result["feedback"] == 0
    assert result["missing_tables"] == ["behavior_logs", "papers"]


def test_monthly_export_writes_obsidian_report_and_topic_index(monkeypatch, tmp_path):
    _use_tmp_wiki(monkeypatch, tmp_path)
    output_dir = tmp_path / "Obsidian Vault" / "Daily Note 2026"
    topic_dir = output_dir / "topic index"

    wiki_db.upsert_node(
        user_id="user_alice",
        node_id="paper:2605.00001",
        node_type="paper",
        title="Graph RAG Agents for Literature Review",
        body="A graph RAG agent helps readers organize monthly literature review notes.",
        metadata={
            "arxiv_id": "2605.00001",
            "publish_date": "2026-05-14",
            "url": "https://arxiv.org/abs/2605.00001",
            "pdf_path": str(output_dir / "arXiv - May 2026" / "2605.00001.pdf"),
            "report_path": str(output_dir / "arXiv - May 2026" / "2605.00001 - reading-report.md"),
        },
        keywords="graph-rag agents literature",
    )
    wiki_db.upsert_node(
        user_id="user_alice",
        node_id="paper:2606.00002",
        node_type="paper",
        title="June Paper Outside Export",
        body="This paper belongs to June.",
        metadata={"arxiv_id": "2606.00002", "publish_date": "2026-06-01"},
        keywords="agents",
    )

    result = monthly_export.export_monthly_report(
        "user_alice",
        month="2026-05",
        output_dir=str(output_dir),
        topic_index_dir=str(topic_dir),
    )

    report_path = Path(result["report_path"])
    topic_index_path = Path(result["topic_index_path"])
    assert result["paper_count"] == 1
    assert report_path == (
        output_dir
        / "user_alice"
        / "monthly_reports"
        / "PaperFlow Monthly Report - user_alice - 2026-05.md"
    )
    assert topic_index_path == topic_dir / "user_alice" / "Topic Index - user_alice - 2026-05.md"
    assert report_path.exists()
    assert topic_index_path.exists()
    report_text = report_path.read_text(encoding="utf-8")
    topic_text = topic_index_path.read_text(encoding="utf-8")
    assert "Graph RAG Agents for Literature Review" in report_text
    assert "June Paper Outside Export" not in report_text
    assert "graph-rag" in report_text
    assert "精读" in report_text
    assert "## graph-rag" in topic_text


def test_monthly_export_uses_configured_env_dirs(monkeypatch, tmp_path):
    _use_tmp_wiki(monkeypatch, tmp_path)
    report_dir = tmp_path / "daily-note"
    topic_dir = tmp_path / "topic-index"
    monkeypatch.setenv("PAPERFLOW_MONTHLY_REPORT_DIR", str(report_dir))
    monkeypatch.setenv("PAPERFLOW_TOPIC_INDEX_DIR", str(topic_dir))

    wiki_db.upsert_node(
        user_id="user_alice",
        node_id="paper:2605.00003",
        node_type="paper",
        title="Configured Export Directory",
        body="A paper saved through configured monthly export directories.",
        metadata={"publish_date": "2026-05-20"},
        keywords="configuration",
    )

    result = monthly_export.export_monthly_report("user_alice", month="2026-05")

    assert Path(result["report_path"]).parent == report_dir / "user_alice" / "monthly_reports"
    assert Path(result["topic_index_path"]).parent == topic_dir / "user_alice"


def test_monthly_export_fallback_topic_dir_does_not_duplicate_role(monkeypatch, tmp_path):
    _use_tmp_wiki(monkeypatch, tmp_path)

    wiki_db.upsert_node(
        user_id="user_alice",
        node_id="paper:2605.00004",
        node_type="paper",
        title="Fallback Topic Directory",
        body="Fallback Topic Index output should not duplicate the role folder.",
        metadata={"publish_date": "2026-05-20"},
        keywords="configuration",
    )

    result = monthly_export.export_monthly_report("user_alice", month="2026-05")

    assert Path(result["report_path"]).parent == tmp_path / "exports" / "user_alice" / "monthly_reports"
    assert Path(result["topic_index_path"]).parent == tmp_path / "exports" / "user_alice" / "topic_index"


def test_monthly_export_separates_configured_dirs_by_role_name(monkeypatch, tmp_path):
    _use_tmp_wiki(monkeypatch, tmp_path)
    (tmp_path / "roles.json").write_text(
        json.dumps(
            {
                "roles": {
                    "gui agent lab": {"user_id": "user_alice"},
                    "science lab": {"user_id": "user_bob"},
                }
            }
        ),
        encoding="utf-8",
    )
    report_dir = tmp_path / "daily-note"
    monkeypatch.setenv("PAPERFLOW_MONTHLY_REPORT_DIR", str(report_dir))
    monkeypatch.setenv("PAPERFLOW_TOPIC_INDEX_DIR", str(report_dir / "topic-index"))

    for user_id, title in (
        ("user_alice", "GUI Paper"),
        ("user_bob", "Science Paper"),
    ):
        wiki_db.upsert_node(
            user_id=user_id,
            node_id=f"paper:{title}",
            node_type="paper",
            title=title,
            body="A role-scoped export test paper.",
            metadata={"publish_date": "2026-05-20"},
            keywords="configuration",
        )

    alice = monthly_export.export_monthly_report("user_alice", month="2026-05")
    bob = monthly_export.export_monthly_report("user_bob", month="2026-05")

    assert Path(alice["report_path"]).parent == report_dir / "gui-agent-lab" / "monthly_reports"
    assert Path(bob["report_path"]).parent == report_dir / "science-lab" / "monthly_reports"
    assert Path(alice["report_path"]).name == "PaperFlow Monthly Report - gui-agent-lab - 2026-05.md"
    assert Path(bob["report_path"]).name == "PaperFlow Monthly Report - science-lab - 2026-05.md"
