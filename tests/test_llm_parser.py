"""
Tests for LLM parser fallback safety.
"""

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

llm_parser = importlib.import_module("agents.master-coordinator.scripts.llm_parser")


def test_get_openai_client_skips_placeholder_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "your_openai_api_key_here")
    monkeypatch.setattr(llm_parser, "LLM_FALLBACK_DISABLED", False)

    client = llm_parser._get_openai_client()

    assert client is None


def test_parse_intent_with_llm_disables_after_auth_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-invalid")
    monkeypatch.setattr(llm_parser, "LLM_FALLBACK_DISABLED", False)

    class FakeCompletions:
        def create(self, **kwargs):
            raise RuntimeError("401 Unauthorized")

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    fake_client = FakeClient()
    monkeypatch.setattr(llm_parser, "_get_openai_client", lambda: fake_client)

    result = llm_parser.parse_intent_with_llm("降低 GUI Agent 权重")

    assert result is None
    assert llm_parser.LLM_FALLBACK_DISABLED is True


def test_parse_intent_with_llm_uses_local_provider(monkeypatch):
    monkeypatch.setenv("LLM_PARSER_PROVIDER", "local")

    captured = {}

    def fake_local(system_prompt, user_text, max_new_tokens=512):
        captured["system_prompt"] = system_prompt
        captured["user_text"] = user_text
        captured["max_new_tokens"] = max_new_tokens
        return {
            "action": "adjust_interest",
            "direction": "decrease",
            "topics": ["GUI Agent"],
            "confidence": 0.93,
            "reasoning": "matched explicit negation",
        }

    monkeypatch.setattr(llm_parser, "_generate_json_with_local_llm", fake_local)
    monkeypatch.setattr(llm_parser, "_generate_json_with_openai", lambda *args, **kwargs: None)

    result = llm_parser.parse_intent_with_llm("我对 GUI Agent 不感兴趣", known_topics=["GUI Agent", "智能体"])

    assert result["direction"] == "decrease"
    assert result["topics"] == ["GUI Agent"]
    assert captured["user_text"] == "我对 GUI Agent 不感兴趣"
    assert "当前用户画像里已经存在的方向/主题有" in captured["system_prompt"]


def test_parse_intent_with_llm_auto_falls_back_to_openai(monkeypatch):
    monkeypatch.setenv("LLM_PARSER_PROVIDER", "auto")

    monkeypatch.setattr(llm_parser, "_generate_json_with_local_llm", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        llm_parser,
        "_generate_json_with_openai",
        lambda *args, **kwargs: {
            "action": "adjust_interest",
            "direction": "increase",
            "topics": ["protein language model"],
            "confidence": 0.88,
            "reasoning": "fallback openai",
        },
    )

    result = llm_parser.parse_intent_with_llm("我最近对 protein language model 更感兴趣了")

    assert result["direction"] == "increase"
    assert result["topics"] == ["protein language model"]


def test_embedding_checkpoint_is_rejected_for_local_generation(tmp_path):
    model_dir = tmp_path / "Qwen3-Embedding-8B"
    model_dir.mkdir()
    (model_dir / "modules.json").write_text(
        '[{"type":"sentence_transformers.models.Transformer"},'
        '{"type":"sentence_transformers.models.Pooling"},'
        '{"type":"sentence_transformers.models.Normalize"}]',
        encoding="utf-8",
    )

    assert llm_parser._is_embedding_style_checkpoint(model_dir) is True


def test_incomplete_local_llm_directory_is_ignored(tmp_path):
    model_dir = tmp_path / "Qwen3-4B-Instruct-2507"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")

    assert llm_parser._has_minimum_local_llm_files(model_dir) is False


def test_synthesize_reading_report_with_llm_uses_local_provider(monkeypatch):
    monkeypatch.setenv("LLM_PARSER_PROVIDER", "local")

    captured = {}

    def fake_local(system_prompt, user_text, max_new_tokens=512):
        captured["system_prompt"] = system_prompt
        captured["user_text"] = user_text
        captured["max_new_tokens"] = max_new_tokens
        return {
            "one_sentence_summary": "这篇论文提出了一个更稳健的论文筛选流程。",
            "research_background": "论文关注科研助手在高噪声候选集上的筛选效率问题。",
            "core_method": "方法采用两阶段排序与证据过滤。",
            "key_results": "结果显示排序质量和阅读效率都有提升。",
            "main_contributions": ["提出两阶段流程", "给出更贴近使用场景的评测"],
            "limitations": ["跨领域泛化仍需进一步验证"],
            "relevance_points": ["和用户关注的智能体方向高度相关"],
            "reading_focus": ["重点看 Method 和 Results"],
            "recommendation_label": "推荐阅读",
        }

    monkeypatch.setattr(llm_parser, "_generate_json_with_local_llm", fake_local)
    monkeypatch.setattr(llm_parser, "_generate_json_with_openai", lambda *args, **kwargs: None)

    result = llm_parser.synthesize_reading_report_with_llm(
        paper={
            "title": "Scientific Planner",
            "abstract": "We propose a scientific planner.",
            "authors": ["Alice"],
        },
        user_profile={"core_directions": {"agent": 0.8}},
        parsed_pdf={"sections": {"method": "We propose a two-stage planner."}},
        heuristic_payload={"one_sentence_summary": "heuristic draft"},
    )

    assert result["recommendation_label"] == "推荐阅读"
    assert result["main_contributions"][0] == "提出两阶段流程"
    assert "Scientific Planner" in captured["user_text"]
    assert "科研论文精读助手" in captured["system_prompt"]
