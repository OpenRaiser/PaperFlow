"""
Tests for cold-start profile bootstrap and PDF-style profile rendering.
"""

import importlib
import json
import sys
from pathlib import Path

import fitz


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

coldstart_agent = importlib.import_module("agents.coldstart-agent.main")
master_coordinator = importlib.import_module("agents.master_coordinator.main")
reading_agent = importlib.import_module("agents.reading-agent.main")
db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
direction_lexicon = importlib.import_module("config.direction_lexicon")


def _create_pdf(tmp_path: Path, name: str, text: str) -> str:
    pdf_path = tmp_path / name
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(48, 48, 560, 780), text, fontsize=12)
    doc.save(pdf_path)
    doc.close()
    return str(pdf_path)


def _build_scholar_html(publications=None, *, stats=None, interests=None, homepage_url=None) -> str:
    publications = publications or [
        {
            "title": "GUI Agent Infrastructure for Scientific Discovery",
            "authors": "Ada Example, John Doe",
            "venue": "Nature Machine Intelligence",
            "citations": 128,
            "year": 2025,
        },
        {
            "title": "Protein Language Models for Molecular Design",
            "authors": "Ada Example, Jane Roe",
            "venue": "ICLR",
            "citations": 64,
            "year": 2024,
        },
    ]
    stats = stats or {"Citations": 1024, "h-index": 21}
    interests = interests or [
        "GUI Agent",
        "Protein Language Model",
        "Scientific Discovery",
    ]

    publication_rows = []
    for index, publication in enumerate(publications, start=1):
        publication_rows.append(
            f"""
          <tr class="gsc_a_tr">
            <td class="gsc_a_t">
              <a class="gsc_a_at" href="/citations?view_op=view_citation&citation_for_view=test:{index}">
                {publication['title']}
              </a>
              <div class="gs_gray">{publication['authors']}</div>
              <div class="gs_gray">{publication['venue']}</div>
            </td>
            <td class="gsc_a_c"><a class="gsc_a_ac" href="/citations?view_op=view_citation&citation_for_view=test:{index}">{publication['citations']}</a></td>
            <td class="gsc_a_y"><span class="gsc_a_h">{publication['year']}</span></td>
          </tr>
            """
        )

    stats_rows = []
    for label, value in stats.items():
        stats_rows.append(
            f"""
          <tr>
            <td class="gsc_rsb_sc1">{label}</td>
            <td class="gsc_rsb_std">{value}</td>
          </tr>
            """
        )

    homepage_html = (
        f'<a class="gsc_prf_ila" href="{homepage_url}">{homepage_url}</a>'
        if homepage_url
        else ""
    )

    return f"""
    <html>
      <body>
        <div id="gsc_prf_in">Dr. Ada Example</div>
        <div class="gsc_prf_il">Institute of Scientific Discovery</div>
        {homepage_html}
        <div id="gsc_prf_int">
          {''.join(f'<a href="/citations?view_op=search_authors&mauthors=label:test">{interest}</a>' for interest in interests)}
        </div>
        <table id="gsc_rsb_st">
          {''.join(stats_rows)}
        </table>
        <table id="gsc_a_t">
          {''.join(publication_rows)}
        </table>
      </body>
    </html>
    """


def _sample_scholar_html() -> str:
    return _build_scholar_html()


def _sample_homepage_html() -> str:
    return """
    <html>
      <head>
        <title>Ada Example</title>
        <meta name="description" content="Professor working on scientific reasoning and AI for science." />
      </head>
      <body>
        <h2>Research Interests</h2>
        <ul>
          <li>Scientific reasoning</li>
          <li>AI for science</li>
        </ul>
        <h2>Projects</h2>
        <ul>
          <li>Vision-language agents for scientific workflows</li>
        </ul>
      </body>
    </html>
    """


def test_parse_natural_language_rolea_description_sets_expected_preferences():
    parsed = coldstart_agent.parse_natural_language(
        "direction: data-native scientific discovery, bio-molecular data infrastructure, gui agent"
    )

    assert parsed["core_directions"]["gui-agent"] > 0
    assert parsed["core_directions"]["data-native"] > 0
    assert parsed["core_directions"]["bio-molecular"] > 0
    assert parsed["methodology_preferences"]["preference_data_driven_over_theory"] is True
    assert parsed["methodology_preferences"]["preference_systematic_work_over_incremental"] is True
    assert parsed["methodology_preferences"]["preference_bio_science_application"] is True


def test_parse_natural_language_prefers_exact_canonical_research_phrases():
    parsed = coldstart_agent.parse_natural_language("Research interests: scientific reasoning; AI for science")

    assert parsed["core_directions"]["scientific-reasoning"] >= 0.9
    assert parsed["core_directions"]["ai-for-science"] >= 0.9
    assert "science-discovery" not in parsed["core_directions"]
    assert "reasoning" not in parsed["core_directions"]


def test_parse_natural_language_keeps_methodology_neutral_without_evidence():
    parsed = coldstart_agent.parse_natural_language("scientific reasoning and AI for science")

    assert "preference_data_driven_over_theory" not in parsed["methodology_preferences"]
    assert "preference_systematic_work_over_incremental" not in parsed["methodology_preferences"]


def test_repair_profile_from_role_description_backfills_empty_profile(test_db_path, tmp_path):
    db_ops.DB_PATH = test_db_path

    profile = {
        "user_id": "user_rolea",
        "version": "0.1",
        "core_directions": {},
        "methodology_preferences": {},
        "must_read": {"authors": [], "institutions": [], "keywords": []},
        "topic_weights": {},
        "author_heat": {},
        "institution_heat": {},
        "interest_vector": [],
        "taste_profile": {},
        "reading_history": [],
    }
    db_ops.create_profile("user_rolea", profile)

    roles_path = tmp_path / "roles.json"
    roles_path.write_text(
        json.dumps(
            {
                "roles": {
                    "rolea": {
                        "user_id": "user_rolea",
                        "description": "direction: data-native scientific discovery, bio-molecular data infrastructure, gui agent",
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    original_role_meta_path = master_coordinator.ROLE_META_PATH
    try:
        master_coordinator.ROLE_META_PATH = str(roles_path)
        repaired = master_coordinator.repair_profile_from_role_description("user_rolea", profile)
    finally:
        master_coordinator.ROLE_META_PATH = original_role_meta_path

    assert repaired["core_directions"]["gui-agent"] > 0
    assert repaired["methodology_preferences"]["preference_data_driven_over_theory"] is True


def test_format_profile_message_uses_pdf_style_sections(sample_profile):
    message = master_coordinator.format_profile_message(sample_profile)

    assert "📋 你的学术画像" in message
    assert "━━━ 核心方向 ━━━" in message
    assert "━━━ 方法论偏好 ━━━" in message
    assert "━━━ 必读清单 ━━━" in message


def test_detect_intent_routes_profile_updates_correctly():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    weight_intent = coordinator.detect_intent("降低 GUI Agent 权重")
    interest_intent = coordinator.detect_intent("我最近对 protein language model 更感兴趣了")

    assert weight_intent["intent"] == "profile_update"
    assert weight_intent["slots"]["direction"] == "decrease"
    assert interest_intent["intent"] == "profile_update"
    assert interest_intent["slots"]["topic"] == "protein language model"


def test_detect_intent_prioritizes_explicit_cold_start_over_profile_update(monkeypatch):
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    def fail_parse(*args, **kwargs):
        raise AssertionError("explicit cold-start command should bypass profile-update parsing")

    monkeypatch.setitem(
        master_coordinator.MasterCoordinator.detect_intent.__globals__,
        "parse_profile_update_request",
        fail_parse,
    )

    intent = coordinator.detect_intent("冷启动")

    assert intent["intent"] == "cold_start"


def test_detect_intent_prioritizes_numeric_feedback_over_profile_update(monkeypatch):
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    def fail_parse(*args, **kwargs):
        raise AssertionError("numeric feedback should bypass profile-update parsing")

    monkeypatch.setitem(
        master_coordinator.MasterCoordinator.detect_intent.__globals__,
        "parse_profile_update_request",
        fail_parse,
    )

    intent = coordinator.detect_intent("1 2 3")

    assert intent["intent"] == "feedback"
    assert intent["slots"]["reply"] == "1 2 3"


def test_detect_intent_ignores_weekly_report_echo():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    weekly_report = (
        "============================================================\n"
        "📊 你的学术画像周度报告 | 2026-04-05 ~ 2026-04-12\n"
        "============================================================\n\n"
        "━━━ 本周阅读统计 ━━━\n"
        "推送论文总数：60\n"
        "你选择精读：6（选择率 10.0%）"
    )
    intent = coordinator.detect_intent(weekly_report)

    assert intent["intent"] == "ignore"


def test_detect_intent_ignores_reading_report_echo():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    reading_report_summary = (
        "============================================================\n"
        "Reading reports created (2)\n"
        "============================================================\n\n"
        "01. DNA damage drives antigen diversification\n"
        "    doc_token: EbKydK0DqoFHNrxJ2XichnognKf\n\n"
        "02. Female mice grow testes after this single DNA tweak\n"
        "    doc_token: V4Evdnt7joFuPWxAjdCchMnfn5c\n\n"
        "Open the links above to start reading."
    )
    intent = coordinator.detect_intent(reading_report_summary)

    assert intent["intent"] == "ignore"


def test_detect_intent_ignores_reading_doc_title_echo():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    intent = coordinator.detect_intent("[精读] 面向兴趣漂移驱动的序列推荐用户表示学习")

    assert intent["intent"] == "ignore"


def test_handle_profile_update_adjusts_existing_direction_weight(test_db_path, monkeypatch):
    db_ops.DB_PATH = test_db_path
    master_coordinator.db_ops.DB_PATH = test_db_path

    profile = master_coordinator.build_empty_profile("user_rolea")
    profile["core_directions"] = {"gui-agent": 0.7}
    profile["topic_weights"] = {"gui-agent": 0.7}
    db_ops.create_profile("user_rolea", profile)

    monkeypatch.setattr(master_coordinator, "send_message", lambda *args, **kwargs: {"success": True})

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_profile_update("降低 GUI Agent 权重")
    updated_profile = db_ops.get_profile("user_rolea")

    assert result["success"] is True
    assert updated_profile["core_directions"]["gui-agent"] == 0.55
    assert updated_profile["topic_weights"]["gui-agent"] == 0.55


def test_parse_profile_update_supports_explicit_target_weight_without_loading_llm(monkeypatch):
    def fail_llm(*args, **kwargs):
        raise AssertionError("explicit target-weight phrasing should not require LLM parsing")

    monkeypatch.setattr(master_coordinator, "_parse_profile_update_with_llm", fail_llm)

    slots = master_coordinator.parse_profile_update_request("多模态推理的权重提高到1")

    assert slots["action"] == "adjust_weight"
    assert slots["direction"] == "increase"
    assert slots["topic"] == "多模态推理"
    assert slots["weight_target"] == 1.0


def test_parse_profile_update_supports_target_weight_without_explicit_weight_keyword(monkeypatch):
    def fail_llm(*args, **kwargs):
        raise AssertionError("direct target-weight phrasing should not require LLM parsing")

    monkeypatch.setattr(master_coordinator, "_parse_profile_update_with_llm", fail_llm)

    set_slots = master_coordinator.parse_profile_update_request("将视觉设为1")
    lower_slots = master_coordinator.parse_profile_update_request("把 GUI Agent 降到0.2")

    assert set_slots["action"] == "adjust_weight"
    assert set_slots["direction"] == "increase"
    assert set_slots["topic"] == "视觉"
    assert set_slots["weight_target"] == 1.0

    assert lower_slots["action"] == "adjust_weight"
    assert lower_slots["direction"] == "decrease"
    assert lower_slots["topic"] == "GUI Agent"
    assert lower_slots["weight_target"] == 0.2


def test_handle_profile_update_sets_explicit_target_weight(test_db_path, monkeypatch):
    db_ops.DB_PATH = test_db_path
    master_coordinator.db_ops.DB_PATH = test_db_path

    profile = master_coordinator.build_empty_profile("user_rolea")
    profile["core_directions"] = {"multimodal-reasoning": 0.79}
    profile["topic_weights"] = {"multimodal-reasoning": 0.79}
    db_ops.create_profile("user_rolea", profile)

    monkeypatch.setattr(master_coordinator, "send_message", lambda *args, **kwargs: {"success": True})

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_profile_update("多模态推理的权重提高到1")
    updated_profile = db_ops.get_profile("user_rolea")

    assert result["success"] is True
    assert "多模态推理" in result["updated_topics"]
    assert updated_profile["core_directions"]["multimodal-reasoning"] == 1.0
    assert updated_profile["topic_weights"]["multimodal-reasoning"] == 1.0


def test_handle_profile_update_adds_interest_signal_from_free_text(test_db_path, monkeypatch):
    db_ops.DB_PATH = test_db_path
    master_coordinator.db_ops.DB_PATH = test_db_path

    profile = master_coordinator.build_empty_profile("user_rolea")
    db_ops.create_profile("user_rolea", profile)

    monkeypatch.setattr(master_coordinator, "send_message", lambda *args, **kwargs: {"success": True})

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_profile_update("我最近对 protein language model 更感兴趣了")
    updated_profile = db_ops.get_profile("user_rolea")

    assert result["success"] is True
    assert "蛋白语言模型" in result["updated_topics"]
    assert updated_profile["core_directions"]["protein-language-model"] >= 0.55
    assert updated_profile["topic_weights"]["protein-language-model"] >= 0.55


def test_handle_profile_update_deduplicates_pending_direction_prompt(test_db_path, monkeypatch):
    db_ops.DB_PATH = test_db_path
    master_coordinator.db_ops.DB_PATH = test_db_path

    profile = master_coordinator.build_empty_profile("user_rolea")
    profile["core_directions"] = {"bio-molecular": 0.68, "language": 0.60}
    profile["topic_weights"] = {"bio-molecular": 0.68, "language": 0.60}
    db_ops.create_profile("user_rolea", profile)

    captured = {}
    pending_prompt = '发现候选新方向：智能制造，回复“确认方向：智能制造”后纳入统一方向库。'

    monkeypatch.setitem(
        master_coordinator.MasterCoordinator.handle_profile_update.__globals__,
        "parse_profile_update_request",
        lambda *args, **kwargs: {
            "action": "adjust_interest",
            "direction": "increase",
            "topic": "智能制造",
            "topics": ["智能制造"],
        },
    )
    monkeypatch.setitem(
        master_coordinator.MasterCoordinator.handle_profile_update.__globals__,
        "normalize_profile_update_topics",
        lambda *args, **kwargs: {
            "canonical_directions": [],
            "temporary_matches": [],
            "pending_candidates": [
                {
                    "candidate_key": "smart-manufacturing",
                    "name": "smart-manufacturing",
                    "name_cn": "智能制造",
                }
            ],
            "explanations": [pending_prompt],
        },
    )
    def fake_send_message(text, *args, **kwargs):
        captured["text"] = text
        return {"success": True}

    monkeypatch.setitem(
        master_coordinator.MasterCoordinator.handle_profile_update.__globals__,
        "send_message",
        fake_send_message,
    )

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_profile_update("添加方向：智能制造")

    assert result["success"] is True
    assert captured["text"].count(pending_prompt) == 1


def test_detect_intent_prefers_llm_for_profile_update(monkeypatch):
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    coordinator.profile = {
        "core_directions": {"gui-agent": 0.8},
        "topic_weights": {"gui-agent": 0.8},
    }

    def fake_llm_parse(text, profile=None):
        assert profile is coordinator.profile
        return {
            "action": "adjust_interest",
            "direction": "decrease",
            "topic": "GUI Agent",
            "topics": ["GUI Agent"],
            "from_llm": True,
        }

    monkeypatch.setitem(
        master_coordinator.MasterCoordinator.detect_intent.__globals__,
        "parse_profile_update_request",
        fake_llm_parse,
    )

    intent = coordinator.detect_intent("我对GUI Agent不感兴趣")

    assert intent["intent"] == "profile_update"
    assert intent["slots"]["direction"] == "decrease"
    assert intent["slots"]["topic"] == "GUI Agent"


def test_parse_profile_update_handles_negative_interest_without_loading_llm(monkeypatch):
    def fail_llm(*args, **kwargs):
        raise AssertionError("simple negative-interest phrasing should not require LLM parsing")

    monkeypatch.setattr(master_coordinator, "_parse_profile_update_with_llm", fail_llm)

    slots = master_coordinator.parse_profile_update_request("我对Cold Start不感兴趣")

    assert slots["action"] == "adjust_interest"
    assert slots["direction"] == "decrease"
    assert slots["topic"] == "Cold Start"


def test_detect_intent_handles_topic_removal_phrase_without_loading_llm(monkeypatch):
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    def fail_llm(*args, **kwargs):
        raise AssertionError("simple topic-removal phrasing should not require LLM parsing")

    monkeypatch.setattr(master_coordinator, "_parse_profile_update_with_llm", fail_llm)

    intent = coordinator.detect_intent("我不需要Cold Start方向")

    assert intent["intent"] == "profile_update"
    assert intent["slots"]["action"] == "remove_topic"
    assert intent["slots"]["direction"] == "remove"
    assert intent["slots"]["topic"] == "Cold Start"


def test_parse_profile_update_keeps_soft_negative_interest_as_weight_decrease(monkeypatch):
    def fail_llm(*args, **kwargs):
        raise AssertionError("simple soft-negative phrasing should not require LLM parsing")

    monkeypatch.setattr(master_coordinator, "_parse_profile_update_with_llm", fail_llm)

    slots = master_coordinator.parse_profile_update_request("我对GUI Agent不太感兴趣")

    assert slots["action"] == "adjust_interest"
    assert slots["direction"] == "decrease"
    assert slots["topic"] == "GUI Agent"


def test_handle_profile_update_removes_topic_from_profile(test_db_path, monkeypatch):
    db_ops.DB_PATH = test_db_path
    master_coordinator.db_ops.DB_PATH = test_db_path

    profile = master_coordinator.build_empty_profile("user_rolea")
    profile["core_directions"] = {"cold-start": 0.65, "gui-agent": 0.80}
    profile["topic_weights"] = {"cold-start": 0.65, "gui-agent": 0.80}
    db_ops.create_profile("user_rolea", profile)

    monkeypatch.setattr(master_coordinator, "send_message", lambda *args, **kwargs: {"success": True})

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_profile_update("我不需要Cold Start方向")
    updated_profile = db_ops.get_profile("user_rolea")

    assert result["success"] is True
    assert "cold-start" not in updated_profile["core_directions"]
    assert "cold-start" not in updated_profile["topic_weights"]
    assert updated_profile["core_directions"]["gui-agent"] == 0.80
    assert updated_profile["topic_weights"]["gui-agent"] == 0.80


def test_handle_profile_update_strong_negative_interest_only_decreases_existing_topic(test_db_path, monkeypatch):
    db_ops.DB_PATH = test_db_path
    master_coordinator.db_ops.DB_PATH = test_db_path

    profile = master_coordinator.build_empty_profile("user_rolea")
    profile["core_directions"] = {"cold-start": 0.65, "gui-agent": 0.80}
    profile["topic_weights"] = {"cold-start": 0.65, "gui-agent": 0.80}
    db_ops.create_profile("user_rolea", profile)

    monkeypatch.setattr(master_coordinator, "send_message", lambda *args, **kwargs: {"success": True})

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_profile_update("我对cold-start不感兴趣")
    updated_profile = db_ops.get_profile("user_rolea")

    assert result["success"] is True
    assert updated_profile["core_directions"]["cold-start"] == 0.5
    assert updated_profile["topic_weights"]["cold-start"] == 0.5
    assert updated_profile["core_directions"]["gui-agent"] == 0.80


def test_handle_profile_update_negative_unknown_topic_does_not_create_new_direction(test_db_path, monkeypatch):
    db_ops.DB_PATH = test_db_path
    master_coordinator.db_ops.DB_PATH = test_db_path

    profile = master_coordinator.build_empty_profile("user_rolea")
    profile["core_directions"] = {"gui-agent": 0.80}
    profile["topic_weights"] = {"gui-agent": 0.80}
    db_ops.create_profile("user_rolea", profile)

    monkeypatch.setattr(master_coordinator, "send_message", lambda *args, **kwargs: {"success": True})

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_profile_update("我对cold-start不感兴趣")
    updated_profile = db_ops.get_profile("user_rolea")

    assert result["success"] is True
    assert "cold-start" not in updated_profile["core_directions"]
    assert "cold-start" not in updated_profile["topic_weights"]
    assert updated_profile["core_directions"]["gui-agent"] == 0.80


def test_handle_profile_update_decreases_language_family_topics_together(test_db_path, monkeypatch):
    db_ops.DB_PATH = test_db_path
    master_coordinator.db_ops.DB_PATH = test_db_path

    profile = master_coordinator.build_empty_profile("user_rolec")
    profile["core_directions"] = {"language": 0.45, "nlp": 0.35, "vision": 0.70}
    profile["topic_weights"] = {"language": 0.45, "nlp": 0.35, "vision": 0.70}
    db_ops.create_profile("user_rolec", profile)

    monkeypatch.setattr(master_coordinator, "send_message", lambda *args, **kwargs: {"success": True})

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolec")
    result = coordinator.handle_profile_update("我对语言不感兴趣")
    updated_profile = db_ops.get_profile("user_rolec")

    assert result["success"] is True
    assert updated_profile["core_directions"]["language"] == 0.30
    assert updated_profile["topic_weights"]["language"] == 0.30
    assert updated_profile["core_directions"]["nlp"] == 0.20
    assert updated_profile["topic_weights"]["nlp"] == 0.20
    assert updated_profile["core_directions"]["vision"] == 0.70
    assert len(updated_profile["interest_vector"]) == 1024


def test_handle_profile_update_uses_llm_topic_without_broadening_scope(test_db_path, monkeypatch):
    db_ops.DB_PATH = test_db_path
    master_coordinator.db_ops.DB_PATH = test_db_path

    profile = master_coordinator.build_empty_profile("user_rolea")
    profile["core_directions"] = {"gui-agent": 0.8, "agent": 0.7}
    profile["topic_weights"] = {"gui-agent": 0.8, "agent": 0.7}
    db_ops.create_profile("user_rolea", profile)

    monkeypatch.setitem(
        master_coordinator.MasterCoordinator.handle_profile_update.__globals__,
        "send_message",
        lambda *args, **kwargs: {"success": True},
    )

    def fake_llm_parse(text, profile=None):
        return {
            "action": "adjust_interest",
            "direction": "decrease",
            "topic": "GUI Agent",
            "topics": ["GUI Agent"],
            "from_llm": True,
        }

    monkeypatch.setitem(
        master_coordinator.MasterCoordinator.handle_profile_update.__globals__,
        "parse_profile_update_request",
        fake_llm_parse,
    )

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_profile_update("我对GUI Agent不感兴趣")
    updated_profile = db_ops.get_profile("user_rolea")

    assert result["success"] is True
    assert updated_profile["core_directions"]["gui-agent"] == 0.65
    assert updated_profile["topic_weights"]["gui-agent"] == 0.65
    assert updated_profile["core_directions"]["agent"] == 0.70
    assert updated_profile["topic_weights"]["agent"] == 0.70


def test_cold_start_uses_baseline_pdf_and_incremental_pdf_merge(test_db_path, monkeypatch, tmp_path):
    db_ops.DB_PATH = test_db_path
    coldstart_agent.db_ops.DB_PATH = test_db_path
    pdf_parser = importlib.import_module("skills.pdf-parser.scripts.parse_pdf")
    monkeypatch.setattr(pdf_parser, "_get_embedding_service", lambda: None)

    baseline_pdf = _create_pdf(
        tmp_path,
        "Research Infra.pdf",
        "\n".join(
            [
                "Research Infra",
                "",
                "Abstract",
                "We study GUI agent infrastructure for interface automation and computer use in scientific workflows.",
                "",
                "Introduction",
                "A GUI agent platform can coordinate screen agent and action agent systems.",
                "",
                "Method",
                "Our framework and benchmark infrastructure are data-driven and systematic.",
            ]
        ),
    )
    uploaded_pdf = _create_pdf(
        tmp_path,
        "protein.pdf",
        "\n".join(
            [
                "Protein Folding Benchmark",
                "",
                "Abstract",
                "We present a protein folding benchmark using structure prediction and AlphaFold style modeling.",
                "",
                "Method",
                "The benchmark includes a dataset for machine learning experiments.",
            ]
        ),
    )

    monkeypatch.setenv("SCITASTE_BASELINE_PDF", baseline_pdf)

    profile = coldstart_agent.cold_start(
        user_id="user_rolea",
        pdf_paths=[uploaded_pdf],
        send_to_feishu=False,
    )
    stored_profile = db_ops.get_profile("user_rolea")

    assert profile["core_directions"]["gui-agent"] >= 0.55
    assert stored_profile["core_directions"]["gui-agent"] >= 0.55
    assert stored_profile["core_directions"]["protein-folding"] <= 0.55
    assert max(stored_profile["core_directions"].values()) <= 0.70


def test_parse_google_scholar_profile_html_extracts_metadata():
    parsed = coldstart_agent._parse_google_scholar_profile_html(_sample_scholar_html())

    assert parsed["name"] == "Dr. Ada Example"
    assert parsed["affiliation"] == "Institute of Scientific Discovery"
    assert parsed["interests"] == ["GUI Agent", "Protein Language Model", "Scientific Discovery"]
    assert parsed["publications"][0]["title"] == "GUI Agent Infrastructure for Scientific Discovery"
    assert parsed["publications"][0]["citations"] == 128
    assert parsed["publications"][1]["year"] == 2024
    assert parsed["stats"]["citations"] == 1024
    assert parsed["top_coauthors"][0]["name"] == "John Doe"
    assert parsed["top_cited_publications"][0]["title"] == "GUI Agent Infrastructure for Scientific Discovery"
    assert parsed["collaboration_network"][0]["name"] == "John Doe"
    assert parsed["collaboration_network"][0]["citation_sum"] == 128


def test_cold_start_merges_google_scholar_signals_into_profile(test_db_path, monkeypatch):
    db_ops.DB_PATH = test_db_path
    coldstart_agent.db_ops.DB_PATH = test_db_path

    class _FakeResponse:
        def __init__(self, text: str):
            self.text = text

        def raise_for_status(self):
            return None

    captured = {}

    class _FakeSession:
        def get(self, url, headers=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["timeout"] = timeout
            return _FakeResponse(_sample_scholar_html())

    monkeypatch.setattr(coldstart_agent.requests, "Session", lambda: _FakeSession())

    profile = coldstart_agent.cold_start(
        user_id="user_role_scholar",
        scholar_url="https://scholar.google.com/citations?user=test123&hl=en",
        send_to_feishu=False,
    )
    stored_profile = db_ops.get_profile("user_role_scholar")

    assert "pagesize=" in captured["url"]
    assert profile["core_directions"]["gui-agent"] >= 0.55
    assert profile["core_directions"]["protein-language-model"] >= 0.55
    assert profile["core_directions"]["science-discovery"] >= 0.55
    assert profile["author_heat"]["John Doe"] >= 0.2
    assert profile["institution_heat"]["Institute of Scientific Discovery"] == 0.6
    assert len(profile["interest_vector"]) == 1024
    assert stored_profile["core_directions"]["gui-agent"] == profile["core_directions"]["gui-agent"]


def test_cold_start_sends_plain_profile_card_without_scholar_preface(test_db_path, monkeypatch):
    db_ops.DB_PATH = test_db_path
    coldstart_agent.db_ops.DB_PATH = test_db_path

    class _FakeResponse:
        def __init__(self, text: str):
            self.text = text

        def raise_for_status(self):
            return None

    class _FakeSession:
        def get(self, url, headers=None, timeout=None):
            return _FakeResponse(_sample_scholar_html())

    sent = {}

    monkeypatch.setattr(coldstart_agent.requests, "Session", lambda: _FakeSession())
    monkeypatch.setattr(
        coldstart_agent.feishu_reporter,
        "send_text",
        lambda target_id, text: sent.update({"target_id": target_id, "text": text}) or {"success": True},
    )

    profile = coldstart_agent.cold_start(
        user_id="user_role_scholar",
        scholar_url="https://scholar.google.com/citations?user=test123&hl=en",
        send_to_feishu=True,
        feishu_user_id="ou_test_user",
        reset_existing=True,
    )

    assert sent["target_id"] == "ou_test_user"
    assert sent["text"] == coldstart_agent.format_profile_card(profile, "user_role_scholar")
    assert "Google Scholar" not in sent["text"]


def test_cold_start_writes_scholar_seed_data_back_to_role_meta(test_db_path, monkeypatch, tmp_path):
    db_ops.DB_PATH = test_db_path
    coldstart_agent.db_ops.DB_PATH = test_db_path

    roles_path = tmp_path / "roles.json"
    roles_path.write_text(
        json.dumps(
            {
                "roles": {
                    "rolea": {
                        "user_id": "user_rolea",
                        "description": "",
                        "scholar_url": "https://old.example.com/scholar",
                        "homepage_url": "https://old.example.com",
                        "scholar_seed": {"interests": ["old"]},
                        "homepage_seed": {"research_interests": ["old"]},
                    }
                },
                "current_role": "rolea",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class _FakeResponse:
        def __init__(self, text: str):
            self.text = text

        def raise_for_status(self):
            return None

    class _FakeSession:
        def get(self, url, headers=None, timeout=None):
            return _FakeResponse(
                _build_scholar_html(
                    interests=["Scientific Reasoning", "AI for Science"],
                    homepage_url="https://ada.example.com",
                )
            )

    monkeypatch.setattr(coldstart_agent.requests, "Session", lambda: _FakeSession())
    monkeypatch.setattr(coldstart_agent.requests, "get", lambda *args, **kwargs: _FakeResponse(_sample_homepage_html()))

    original_role_meta_path = coldstart_agent.ROLE_META_PATH
    try:
        coldstart_agent.ROLE_META_PATH = roles_path
        coldstart_agent.cold_start(
            user_id="user_rolea",
            scholar_url="https://scholar.google.com/citations?user=test123&hl=en",
            send_to_feishu=False,
            reset_existing=True,
        )
    finally:
        coldstart_agent.ROLE_META_PATH = original_role_meta_path

    updated_roles = json.loads(roles_path.read_text(encoding="utf-8"))
    role_meta = updated_roles["roles"]["rolea"]

    assert role_meta["description"] == role_meta["bootstrap_summary"]
    assert any(entry["canonical_name"] == "scientific-reasoning" for entry in role_meta["seed_directions"])
    assert role_meta["bootstrap_summary"].startswith("direction: ")
    assert role_meta["seed_directions"][0]["name"]
    assert role_meta["seed_directions"][0]["name_cn"]
    assert "scholar_url" not in role_meta
    assert "homepage_url" not in role_meta
    assert "scholar_seed" not in role_meta
    assert "homepage_seed" not in role_meta


def test_parse_google_scholar_profile_paginates_and_aggregates_network_signals(monkeypatch):
    page_one = _build_scholar_html(
        publications=[
            {
                "title": f"GUI Agent Infrastructure Study {index}",
                "authors": "Ada Example, John Doe" if index < 12 else "Ada Example, John Doe, Alex Smith",
                "venue": "Nature Machine Intelligence" if index % 2 == 0 else "Science",
                "citations": 200 - index,
                "year": 2025 - (index % 3),
            }
            for index in range(20)
        ]
    )
    page_two = _build_scholar_html(
        publications=[
            {
                "title": f"Protein Language Model Discovery {index}",
                "authors": "Ada Example, Jane Roe" if index < 10 else "Ada Example, John Doe, Jane Roe",
                "venue": "ICLR" if index % 2 == 0 else "NeurIPS",
                "citations": 100 - index,
                "year": 2024 - (index % 4),
            }
            for index in range(20)
        ]
    )

    class _FakeResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    class _FakeSession:
        def __init__(self):
            self.calls = []

        def get(self, url, headers=None, timeout=None):
            self.calls.append(url)
            if "cstart=0" in url:
                return _FakeResponse(page_one)
            return _FakeResponse(page_two)

    fake_session = _FakeSession()
    monkeypatch.setattr(coldstart_agent.requests, "Session", lambda: fake_session)
    monkeypatch.setenv("SCITASTE_SCHOLAR_PAGE_SIZE", "20")
    monkeypatch.setenv("SCITASTE_SCHOLAR_PUBLICATION_LIMIT", "25")
    monkeypatch.setenv("SCITASTE_SCHOLAR_MAX_PAGES", "2")

    result = coldstart_agent.parse_google_scholar_profile("https://scholar.google.com/citations?user=test123&hl=en")

    assert len(result["scholar_profile"]["publications"]) == 25
    assert len(fake_session.calls) >= 2
    assert result["scholar_profile"]["top_coauthors"][0]["name"] == "John Doe"
    assert result["scholar_profile"]["top_cited_publications"]
    assert result["scholar_profile"]["collaboration_network"]
    assert result["parsed_profile"]["author_heat"]["John Doe"] >= 0.35
    assert result["parsed_profile"]["institution_heat"]["Institute of Scientific Discovery"] == 0.6


def test_parse_google_scholar_profile_uses_fallback_after_blocked_attempt(monkeypatch):
    blocked_html = "<html><body>Our systems have detected unusual traffic from your computer network.</body></html>"

    class _FakeResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    class _FakeSession:
        def __init__(self):
            self.calls = 0

        def get(self, url, headers=None, timeout=None):
            self.calls += 1
            if self.calls == 1:
                return _FakeResponse(blocked_html)
            return _FakeResponse(_sample_scholar_html())

    fake_session = _FakeSession()
    monkeypatch.setattr(coldstart_agent.requests, "Session", lambda: fake_session)

    result = coldstart_agent.parse_google_scholar_profile("https://scholar.google.com/citations?user=test123&hl=en")

    assert result["scholar_profile"]["publications"]
    assert any("fallback" in note.lower() for note in result["direction_explanations"])


def test_parse_google_scholar_profile_extracts_homepage_url(monkeypatch):
    class _FakeResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    class _FakeSession:
        def get(self, url, headers=None, timeout=None):
            return _FakeResponse(
                _build_scholar_html(
                    interests=["Scientific Reasoning", "AI for Science"],
                    homepage_url="https://ada.example.com",
                )
            )

    monkeypatch.setattr(coldstart_agent.requests, "Session", lambda: _FakeSession())

    result = coldstart_agent.parse_google_scholar_profile("https://scholar.google.com/citations?user=test123&hl=en")

    assert result["scholar_profile"]["homepage_url"] == "https://ada.example.com"
    assert "scientific-reasoning" in result["parsed_profile"]["core_directions"]
    assert "ai-for-science" in result["parsed_profile"]["core_directions"]
    assert any("高引代表作" in note for note in result["direction_explanations"])


def test_parse_research_homepage_prioritizes_explicit_research_interests(monkeypatch):
    class _FakeResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    monkeypatch.setattr(coldstart_agent.requests, "get", lambda *args, **kwargs: _FakeResponse(_sample_homepage_html()))

    result = coldstart_agent.parse_research_homepage("https://ada.example.com")

    core = result["parsed_profile"]["core_directions"]
    assert "scientific-reasoning" in core
    assert "ai-for-science" in core
    assert "vision" not in core


def test_detect_intent_ignores_must_read_list_echo():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    must_read_list = (
        "============================================================\n"
        "📋 必读清单\n"
        "============================================================\n\n"
        "━━━ 👥 作者 (1) ━━━\n"
        "  • tansong\n\n"
        "━━━ 🏛️ 机构 (0) ━━━\n"
        "  （空，待添加）\n\n"
        "━━━ 🔑 关键词 (0) ━━━\n"
        "  （空，待添加）\n\n"
        "============================================================\n"
        "添加方式：\n"
        '  "加个必读作者：Mohammed AlQuraishi"\n'
        '  "添加必读机构：MIT"\n'
        '  "添加必读关键词：GUI Agent"\n\n'
        "移除方式：\n"
        '  "移除必读作者：张三"\n'
        "============================================================"
    )

    intent = coordinator.detect_intent(must_read_list)

    assert intent["intent"] == "ignore"


def test_format_direction_label_prettifies_dynamic_labels():
    assert master_coordinator.format_direction_label("nlp") == "自然语言处理"
    assert master_coordinator.format_direction_label("comparison") == "Comparison"
    assert master_coordinator.format_direction_label("ai-detection") == "AI Detection"


def test_derive_topic_key_canonicalizes_ai_detection_aliases():
    assert master_coordinator.derive_topic_key("Ai 检测") == "ai-detection"
    assert master_coordinator.derive_topic_key("AI检测") == "ai-detection"
    assert master_coordinator.derive_topic_key("AIGC 检测") == "ai-detection"


def test_find_profile_topic_key_matches_ai_detection_alias():
    profile = {
        "core_directions": {"ai-detection": 0.65},
        "topic_weights": {"ai-detection": 0.65},
    }

    assert master_coordinator.find_profile_topic_key(profile, "Ai 检测") == "ai-detection"
    assert master_coordinator.find_profile_topic_key(profile, "AI检测") == "ai-detection"


def test_handle_profile_update_canonicalizes_ai_detection_alias(test_db_path, monkeypatch):
    db_ops.DB_PATH = test_db_path
    master_coordinator.db_ops.DB_PATH = test_db_path

    profile = master_coordinator.build_empty_profile("user_rolea")
    db_ops.create_profile("user_rolea", profile)

    monkeypatch.setattr(master_coordinator, "send_message", lambda *args, **kwargs: {"success": True})
    coldstart_agent = importlib.import_module("agents.coldstart-agent.main")
    monkeypatch.setattr(coldstart_agent, "parse_natural_language", lambda text, use_llm=True: {"core_directions": {}})

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_profile_update("Ai 检测的权重提高到1")
    updated_profile = db_ops.get_profile("user_rolea")

    assert result["success"] is True
    assert "AI Detection" in result["updated_topics"]
    assert updated_profile["core_directions"]["ai-detection"] == 1.0
    assert updated_profile["topic_weights"]["ai-detection"] == 1.0
    assert "ai 检测" not in updated_profile["core_directions"]
    assert "ai 检测" not in updated_profile["topic_weights"]


def test_detect_intent_routes_must_read_removal_before_profile_update(monkeypatch):
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    def fail_llm(*args, **kwargs):
        raise AssertionError("must-read removal should not fall into profile-update parsing")

    monkeypatch.setattr(master_coordinator, "_parse_profile_update_with_llm", fail_llm)

    intent = coordinator.detect_intent("移除必读作者：张三")

    assert intent["intent"] == "must_read"
    assert intent["slots"]["command"] == "移除必读作者：张三"


def test_detect_intent_routes_plain_institution_and_keyword_additions_to_must_read():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    institution_intent = coordinator.detect_intent("加个机构：MIT")
    keyword_intent = coordinator.detect_intent("添加关键词：GUI Agent")

    assert institution_intent["intent"] == "must_read"
    assert institution_intent["slots"]["command"] == "加个机构：MIT"
    assert keyword_intent["intent"] == "must_read"
    assert keyword_intent["slots"]["command"] == "添加关键词：GUI Agent"


def test_detect_intent_routes_plain_institution_removal_to_must_read():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    intent = coordinator.detect_intent("去掉机构上海ai lab")

    assert intent["intent"] == "must_read"
    assert intent["slots"]["command"] == "去掉机构上海ai lab"


def test_detect_intent_routes_academic_profile_to_show_profile():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    intent = coordinator.detect_intent("学术画像")

    assert intent["intent"] == "show_profile"


def test_detect_intent_routes_confirm_direction_command():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    intent = coordinator.detect_intent("确认方向：AIGC 检测")

    assert intent["intent"] == "confirm_direction"
    assert intent["slots"]["topic"] == "AIGC 检测"


def test_handle_confirm_direction_promotes_pending_candidate(test_db_path, monkeypatch, tmp_path):
    db_ops.DB_PATH = test_db_path
    master_coordinator.db_ops.DB_PATH = test_db_path

    monkeypatch.setattr(direction_lexicon, "LEXICON_PATH", tmp_path / "direction_lexicon.json")
    monkeypatch.setattr(direction_lexicon, "PENDING_PATH", tmp_path / "direction_pending.json")
    monkeypatch.setattr(master_coordinator, "send_message", lambda *args, **kwargs: {"success": True})

    direction_lexicon.upsert_pending_direction_candidate(
        "agentic ui automation",
        proposed_name="agentic-ui-automation",
        proposed_name_cn="界面智能体自动化",
        confidence=0.42,
        user_id="user_rolea",
        reason="novel_direction_candidate",
    )

    profile = master_coordinator.build_empty_profile("user_rolea")
    db_ops.create_profile("user_rolea", profile)

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_confirm_direction("界面智能体自动化")
    updated_profile = db_ops.get_profile("user_rolea")
    confirmed_entry = direction_lexicon.get_direction_entry("agentic-ui-automation")

    assert result["success"] is True
    assert result["confirmed_direction"] == "agentic-ui-automation"
    assert "界面智能体自动化" in result["updated_topics"]
    assert updated_profile["core_directions"]["agentic-ui-automation"] == 0.8
    assert updated_profile["topic_weights"]["agentic-ui-automation"] == 0.8
    assert confirmed_entry is not None
    assert "agentic ui automation" in confirmed_entry["aliases"]


def test_detect_intent_does_not_treat_general_research_text_as_cold_start_when_profile_exists(monkeypatch):
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    coordinator.profile = {
        "core_directions": {"gui-agent": 0.8},
        "topic_weights": {"gui-agent": 0.8},
    }

    monkeypatch.setitem(
        master_coordinator.MasterCoordinator.detect_intent.__globals__,
        "parse_profile_update_request",
        lambda *args, **kwargs: None,
    )

    intent = coordinator.detect_intent("我研究多模态智能体")

    assert intent["intent"] == "unknown"


def test_detect_intent_routes_bootstrap_description_to_cold_start_when_profile_missing(monkeypatch):
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    coordinator.profile = {"core_directions": {}, "topic_weights": {}}

    monkeypatch.setitem(
        master_coordinator.MasterCoordinator.detect_intent.__globals__,
        "parse_profile_update_request",
        lambda *args, **kwargs: None,
    )

    intent = coordinator.detect_intent("我研究多模态智能体")

    assert intent["intent"] == "cold_start"


def test_parse_natural_language_ignores_plain_cold_start_command():
    parsed = coldstart_agent.parse_natural_language("冷启动")

    assert parsed["core_directions"] == {}
    assert parsed["topic_weights"] == {}


def test_handle_cold_start_uses_role_description_for_explicit_command(monkeypatch, tmp_path):
    roles_path = tmp_path / "roles.json"
    roles_path.write_text(
        json.dumps(
            {
                "roles": {
                    "rolea": {
                        "user_id": "user_rolea",
                        "description": "direction: gui agent, bio-molecular data infrastructure",
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    captured = {}

    class FakeColdStartModule:
        @staticmethod
        def cold_start(**kwargs):
            captured.update(kwargs)
            return {"success": True}

    real_import = importlib.import_module

    def fake_import(name):
        if name == "agents.coldstart-agent.main":
            return FakeColdStartModule()
        return real_import(name)

    monkeypatch.setattr(master_coordinator, "ROLE_META_PATH", str(roles_path))
    monkeypatch.setattr(master_coordinator.importlib, "import_module", fake_import)

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_cold_start("冷启动")

    assert result["success"] is True
    assert captured["natural_language"] == "direction: gui agent, bio-molecular data infrastructure"


def test_detect_intent_routes_google_scholar_url_to_cold_start():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    intent = coordinator.detect_intent("https://scholar.google.com/citations?user=test123&hl=en")

    assert intent["intent"] == "cold_start"
    assert intent["slots"]["scholar_url"] == "https://scholar.google.com/citations?user=test123&hl=en"


def test_detect_intent_routes_homepage_url_to_cold_start():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    intent = coordinator.detect_intent("https://ada.example.com")

    assert intent["intent"] == "cold_start"
    assert intent["slots"]["homepage_url"] == "https://ada.example.com"


def test_detect_intent_routes_pdf_url_to_reading_report():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    intent = coordinator.detect_intent("https://arxiv.org/pdf/2401.00001.pdf")

    assert intent["intent"] == "reading_report"
    assert intent["slots"]["pdf_url"] == "https://arxiv.org/pdf/2401.00001.pdf"


def test_handle_reading_report_accepts_direct_pdf_url(monkeypatch):
    captured = {}

    class FakeReadingAgent:
        @staticmethod
        def create_reading_report(**kwargs):
            captured.update(kwargs)
            return [{"url": "https://example.feishu.cn/docx/pdf-link"}]

    real_import = importlib.import_module

    def fake_import(name):
        if name == "agents.reading-agent.main":
            return FakeReadingAgent()
        return real_import(name)

    monkeypatch.setattr(master_coordinator.importlib, "import_module", fake_import)

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_reading_report(
        pdf_url="https://arxiv.org/pdf/2401.00001.pdf",
        title_hint="Paper",
    )

    assert result["success"] is True
    assert captured["paper_ids"] == []
    assert captured["papers"][0]["pdf_url"] == "https://arxiv.org/pdf/2401.00001.pdf"
    assert captured["request_metadata"]["report_source_type"] == "text_pdf_url"
    assert captured["request_metadata"]["report_source_key"] == "https://arxiv.org/pdf/2401.00001.pdf"


def test_detect_intent_routes_expand_push_request():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    intent = coordinator.detect_intent("再看看🟡里有没有遗漏的")

    assert intent["intent"] == "expand_push"
    assert intent["slots"]["category"] == "maybe_interested"


def test_detect_intent_routes_classification_correction_request():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    intent = coordinator.detect_intent("16应该是🔴不是🟡，这个方向我很关注")

    assert intent["intent"] == "classification_correction"
    assert intent["slots"]["paper_number"] == 16
    assert intent["slots"]["target_category"] == "high_relevant"


def test_detect_intent_routes_report_feedback_request():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    intent = coordinator.detect_intent("这篇报告没抓住重点")

    assert intent["intent"] == "report_feedback"
    assert intent["slots"]["sentiment"] == "negative"


def test_detect_intent_routes_reviewer_watch_request():
    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")

    intent = coordinator.detect_intent("ICLR 2026 的 top reviewer 有没有什么好用的清单，把 top reviewer 也加上")

    assert intent["intent"] == "reviewer_watch"
    assert intent["slots"]["conference"] == "iclr"
    assert intent["slots"]["year"] == 2026


def test_handle_expand_push_sends_filtered_bucket(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        master_coordinator,
        "get_latest_push",
        lambda user_id: {
            "push_id": "push_1",
            "papers": [
                {"rank": 1, "title": "Paper A", "authors": ["Alice"], "category": "high_relevant"},
                {"rank": 2, "title": "Paper B", "authors": ["Bob"], "category": "maybe_interested"},
                {"rank": 3, "title": "Paper C", "authors": ["Carol"], "category": "maybe_interested"},
            ],
        },
    )
    monkeypatch.setattr(
        master_coordinator,
        "send_message",
        lambda text, *args, **kwargs: captured.update({"text": text}) or {"success": True},
    )

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_expand_push(category="maybe_interested")

    assert result["success"] is True
    assert "Paper B" in captured["text"]
    assert "Paper C" in captured["text"]


def test_handle_classification_correction_applies_strong_signal(test_db_path, monkeypatch):
    db_ops.DB_PATH = test_db_path
    master_coordinator.db_ops.DB_PATH = test_db_path

    profile = master_coordinator.build_empty_profile("user_rolea")
    db_ops.create_profile("user_rolea", profile)

    monkeypatch.setattr(
        master_coordinator,
        "get_latest_push",
        lambda user_id: {
            "push_id": "push_1",
            "papers": [
                {
                    "id": 1,
                    "rank": 1,
                    "title": "GUI Agent Paper",
                    "authors": ["Alice"],
                    "category": "maybe_interested",
                    "topics": ["gui-agent"],
                }
            ],
        },
    )
    monkeypatch.setattr(master_coordinator, "send_message", lambda *args, **kwargs: {"success": True})

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_classification_correction(1, "high_relevant")
    updated_profile = db_ops.get_profile("user_rolea")

    assert result["success"] is True
    assert updated_profile["topic_weights"]["gui-agent"] > 0


def test_handle_report_feedback_updates_report_preferences(test_db_path, monkeypatch):
    db_ops.DB_PATH = test_db_path
    master_coordinator.db_ops.DB_PATH = test_db_path

    profile = master_coordinator.build_empty_profile("user_rolea")
    db_ops.create_profile("user_rolea", profile)

    monkeypatch.setattr(
        master_coordinator,
        "get_recent_created_report",
        lambda user_id, minutes=720: {
            "paper_id": 1,
            "doc_token": "doc_test",
            "doc_url": "https://example.feishu.cn/docx/doc_test",
            "paper_title": "Report Paper",
        },
    )
    monkeypatch.setattr(master_coordinator, "send_message", lambda *args, **kwargs: {"success": True})

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_report_feedback("negative")
    updated_profile = db_ops.get_profile("user_rolea")

    assert result["success"] is True
    assert updated_profile["report_preferences"]["prefer_more_evidence"] is True
    assert updated_profile["report_preferences"]["preferred_evidence_top_k"] >= 4


def test_handle_cold_start_passes_scholar_url_and_stripped_text(monkeypatch):
    captured = {}

    class FakeColdStartModule:
        @staticmethod
        def cold_start(**kwargs):
            captured.update(kwargs)
            return {"success": True}

    real_import = importlib.import_module

    def fake_import(name):
        if name == "agents.coldstart-agent.main":
            return FakeColdStartModule()
        return real_import(name)

    monkeypatch.setattr(master_coordinator.importlib, "import_module", fake_import)

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_cold_start(
        "冷启动 https://scholar.google.com/citations?user=test123&hl=en 我研究机器人工程与智能制造"
    )

    assert result["success"] is True
    assert captured["scholar_url"] == "https://scholar.google.com/citations?user=test123&hl=en"
    assert "机器人工程" in captured["natural_language"]
    assert "scholar.google.com" not in captured["natural_language"]
    assert captured["reset_existing"] is True


def test_handle_cold_start_passes_homepage_url_and_stripped_text(monkeypatch):
    captured = {}

    class FakeColdStartModule:
        @staticmethod
        def cold_start(**kwargs):
            captured.update(kwargs)
            return {"success": True}

    real_import = importlib.import_module

    def fake_import(name):
        if name == "agents.coldstart-agent.main":
            return FakeColdStartModule()
        return real_import(name)

    monkeypatch.setattr(master_coordinator.importlib, "import_module", fake_import)

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_cold_start("冷启动 https://ada.example.com 我研究 scientific reasoning")

    assert result["success"] is True
    assert captured["homepage_url"] == "https://ada.example.com"
    assert "ada.example.com" not in captured["natural_language"]
    assert "scientific reasoning" in captured["natural_language"]
    assert captured["reset_existing"] is True


def test_handle_cold_start_falls_back_to_role_bootstrap_summary(monkeypatch, tmp_path):
    roles_path = tmp_path / "roles.json"
    roles_path.write_text(
        json.dumps(
            {
                "roles": {
                    "rolea": {
                        "user_id": "user_rolea",
                        "description": "",
                        "bootstrap_summary": "direction: scientific reasoning, ai for science",
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    captured = {}

    class FakeColdStartModule:
        @staticmethod
        def cold_start(**kwargs):
            captured.update(kwargs)
            return {"success": True}

    real_import = importlib.import_module

    def fake_import(name):
        if name == "agents.coldstart-agent.main":
            return FakeColdStartModule()
        return real_import(name)

    monkeypatch.setattr(master_coordinator, "ROLE_META_PATH", str(roles_path))
    monkeypatch.setattr(master_coordinator.importlib, "import_module", fake_import)

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_cold_start("冷启动")

    assert result["success"] is True
    assert captured["natural_language"] == "direction: scientific reasoning, ai for science"


def test_cold_start_reset_existing_rebuilds_profile_from_scratch(test_db_path):
    db_ops.DB_PATH = test_db_path
    coldstart_agent.db_ops.DB_PATH = test_db_path

    original = coldstart_agent.build_empty_profile("user_roleb")
    original["core_directions"] = {"multimodal-reasoning": 0.67, "vision-language": 0.60}
    original["topic_weights"] = {"multimodal-reasoning": 0.67, "vision-language": 0.60}
    db_ops.create_profile("user_roleb", original)

    rebuilt = coldstart_agent.cold_start(
        user_id="user_roleb",
        natural_language=None,
        send_to_feishu=False,
        reset_existing=True,
    )

    assert rebuilt["core_directions"] == {}
    assert rebuilt["topic_weights"] == {}


def test_reading_agent_resolves_actual_paper_ids_without_silently_dropping_all(monkeypatch):
    papers = [
        {"id": 91, "title": "Paper A", "authors": ["A"], "abstract": "A"},
        {"id": 75, "title": "Paper B", "authors": ["B"], "abstract": "B"},
    ]

    monkeypatch.setattr(reading_agent, "get_profile", lambda user_id: {"core_directions": {}})
    monkeypatch.setattr(reading_agent, "create_doc", lambda title, content, folder_id=None: {"url": "https://doc.local/1"})
    monkeypatch.setattr(reading_agent, "log_behavior", lambda **kwargs: 1)
    monkeypatch.setattr(reading_agent, "send_text", lambda *args, **kwargs: {"success": True})

    docs = reading_agent.create_reading_report(
        user_id="user_rolec",
        paper_ids=[91],
        papers=papers,
        send_to_feishu=False,
    )

    assert len(docs) == 1
    assert docs[0]["paper"]["id"] == 91


def test_reading_agent_reports_when_no_valid_papers_found(monkeypatch):
    messages = []

    monkeypatch.setattr(reading_agent, "get_profile", lambda user_id: {"core_directions": {}})
    monkeypatch.setattr(
        reading_agent,
        "send_text",
        lambda target_id, text, use_chat_id=False: messages.append({"target_id": target_id, "text": text, "use_chat_id": use_chat_id}) or {"success": True},
    )

    docs = reading_agent.create_reading_report(
        user_id="user_rolec",
        paper_ids=[999],
        papers=[{"id": 91, "title": "Paper A"}],
        send_to_feishu=True,
        chat_id="oc_test_chat",
    )

    assert docs == []
    assert messages
    assert "没有找到可生成精读的论文" in messages[0]["text"]


def test_handle_reading_report_prefers_latest_selected_papers(monkeypatch):
    captured = {}

    class FakeReadingAgent:
        @staticmethod
        def create_reading_report(**kwargs):
            captured.update(kwargs)
            return [{"url": "https://example.feishu.cn/docx/selected"}]

    real_import = importlib.import_module

    def fake_import(name):
        if name == "agents.reading-agent.main":
            return FakeReadingAgent()
        return real_import(name)

    monkeypatch.setattr(
        master_coordinator,
        "get_latest_selected_papers",
        lambda user_id: {
            "push_id": "push_selected_1",
            "papers": [
                {"id": 91, "title": "Selected A", "authors": ["A"], "abstract": "A"},
                {"id": 75, "title": "Selected B", "authors": ["B"], "abstract": "B"},
            ],
        },
    )
    monkeypatch.setattr(master_coordinator, "get_latest_push", lambda user_id: None)
    monkeypatch.setattr(master_coordinator.importlib, "import_module", fake_import)

    coordinator = master_coordinator.MasterCoordinator(user_id="user_rolea")
    result = coordinator.handle_reading_report()

    assert result["success"] is True
    assert captured["paper_ids"] == [1, 2]
    assert [paper["id"] for paper in captured["papers"]] == [91, 75]
    assert captured["request_metadata"] == {"selection_push_id": "push_selected_1"}
