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


def _create_pdf(tmp_path: Path, name: str, text: str) -> str:
    pdf_path = tmp_path / name
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(48, 48, 560, 780), text, fontsize=12)
    doc.save(pdf_path)
    doc.close()
    return str(pdf_path)


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
    assert updated_profile["core_directions"]["bio-molecular"] >= 0.65
    assert updated_profile["core_directions"]["language"] >= 0.65


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
