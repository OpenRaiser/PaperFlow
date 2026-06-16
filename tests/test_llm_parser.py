"""
Tests for LLM parser fallback safety.
"""

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

llm_parser = importlib.import_module("agents.master-coordinator.scripts.llm_parser")
profile_updater = importlib.import_module("skills.profile-updater.scripts.update_profile")
direction_lexicon = importlib.import_module("config.direction_lexicon")


def test_get_openai_client_skips_placeholder_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "your_openai_api_key_here")
    monkeypatch.setattr(llm_parser, "LLM_FALLBACK_DISABLED", False)

    client = llm_parser._get_openai_client()

    assert client is None


def test_get_openai_client_uses_dashscope_env_as_compat_fallback(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_TIMEOUT", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test-dashscope-key")
    monkeypatch.setenv("DASHSCOPE_BASE_URL", "https://compat.example.com/v1")
    monkeypatch.setenv("DASHSCOPE_API_TIMEOUT", "33")
    monkeypatch.setattr(llm_parser, "LLM_FALLBACK_DISABLED", False)
    monkeypatch.setattr(llm_parser, "OpenAI", FakeClient)

    client = llm_parser._get_openai_client()

    assert isinstance(client, FakeClient)
    assert captured["api_key"] == "sk-test-dashscope-key"
    assert captured["base_url"] == "https://compat.example.com/v1"
    assert captured["timeout"] == 33.0


def test_dashscope_parser_provider_aliases_to_openai(monkeypatch):
    monkeypatch.setenv("LLM_PARSER_PROVIDER", "dashscope")

    assert llm_parser._get_llm_parser_provider() == "openai"


def test_openai_parser_model_prefers_canonical_paperflow_env(monkeypatch):
    monkeypatch.setenv("PAPERFLOW_LLM_MODEL", "canonical-model")
    monkeypatch.setenv("LLM_PARSER_OPENAI_MODEL", "legacy-parser-model")
    monkeypatch.setenv("DASHSCOPE_LLM_MODEL", "legacy-dashscope-model")

    assert llm_parser._get_openai_parser_model() == "canonical-model"


def test_openai_parser_model_accepts_legacy_parser_alias(monkeypatch):
    monkeypatch.delenv("PAPERFLOW_LLM_MODEL", raising=False)
    monkeypatch.setenv("LLM_PARSER_OPENAI_MODEL", "legacy-parser-model")

    assert llm_parser._get_openai_parser_model() == "legacy-parser-model"


def test_fallback_generation_model_prefers_backup_model_env(monkeypatch):
    monkeypatch.setenv("PAPERFLOW_LLM_MODEL", "primary-model")
    monkeypatch.setenv("PAPERFLOW_FALLBACK_LLM_MODEL", "backup-model")

    assert llm_parser._get_fallback_generation_model() == "backup-model"


def test_profile_updater_handles_mismatched_interest_vector_dimensions():
    updated = profile_updater.update_interest_vector(
        current_vector=[1.0, 0.0],
        selected_vectors=[[1.0, 0.0, 0.0]],
        alpha=0.5,
    )

    assert len(updated) == 3


def test_get_hf_llm_client_skips_placeholder_token(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "your_hf_token_here")
    monkeypatch.setenv("HF_API_KEY", "")
    monkeypatch.setattr(llm_parser, "HF_LLM_DISABLED", False)
    monkeypatch.setattr(llm_parser, "get_token", lambda: "")

    client = llm_parser._get_hf_llm_client()

    assert client is None


def test_get_hf_llm_client_skips_auto_router_for_non_hf_key(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "sk-test-provider-key")
    monkeypatch.setenv("HF_LLM_PROVIDER", "")
    monkeypatch.setenv("HF_INFERENCE_PROVIDER", "auto")
    monkeypatch.setattr(llm_parser, "HF_LLM_DISABLED", False)

    client = llm_parser._get_hf_llm_client()

    assert client is None


def test_parse_intent_with_llm_disables_after_auth_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-invalid")
    monkeypatch.setenv("LLM_PARSER_PROVIDER", "openai")
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

    result = llm_parser.parse_intent_with_llm("lower GUI Agent weight")

    assert result is None
    assert llm_parser.LLM_FALLBACK_DISABLED is True


def test_parse_intent_with_llm_uses_local_provider(monkeypatch):
    monkeypatch.setenv("LLM_PARSER_PROVIDER", "local")

    captured = {}

    def fake_local(system_prompt, user_text, max_new_tokens=512, **kwargs):
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

    result = llm_parser.parse_intent_with_llm(
        "我对 GUI Agent 不感兴趣",
        known_topics=["GUI Agent", "智能体"],
    )

    assert result["direction"] == "decrease"
    assert result["topics"] == ["GUI Agent"]
    assert captured["user_text"] == "我对 GUI Agent 不感兴趣"
    assert "当前用户画像里已经存在的方向" in captured["system_prompt"]


def test_parse_intent_with_llm_auto_falls_back_to_openai(monkeypatch):
    monkeypatch.setenv("LLM_PARSER_PROVIDER", "auto")

    monkeypatch.setattr(llm_parser, "_generate_json_with_local_llm", lambda *args, **kwargs: None)
    monkeypatch.setattr(llm_parser, "_generate_json_with_hf_api", lambda *args, **kwargs: None)
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


def test_parse_intent_with_llm_uses_hf_api_provider(monkeypatch):
    monkeypatch.setenv("LLM_PARSER_PROVIDER", "hf_api")

    captured = {}

    def fake_hf(system_prompt, user_text, max_tokens=500, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["user_text"] = user_text
        captured["max_tokens"] = max_tokens
        return {
            "action": "adjust_interest",
            "direction": "decrease",
            "topics": ["cold-start"],
            "confidence": 0.91,
            "reasoning": "matched explicit negative preference",
        }

    monkeypatch.setattr(llm_parser, "_generate_json_with_hf_api", fake_hf)
    monkeypatch.setattr(llm_parser, "_generate_json_with_openai", lambda *args, **kwargs: None)

    result = llm_parser.parse_intent_with_llm("我对 cold-start 不感兴趣")

    assert result["direction"] == "decrease"
    assert result["topics"] == ["cold-start"]
    assert captured["user_text"] == "我对 cold-start 不感兴趣"


def test_generate_json_with_hf_api_falls_back_to_text_generation(monkeypatch):
    monkeypatch.setattr(llm_parser, "HF_LLM_DISABLED", False)
    monkeypatch.setattr(llm_parser, "_get_hf_llm_model", lambda: "Qwen/Qwen3-8B")

    class FakeMessage:
        def __init__(self, content):
            self.content = content

    class FakeChoice:
        def __init__(self, content):
            self.message = FakeMessage(content)

    class FakeChatResponse:
        def __init__(self, content):
            self.choices = [FakeChoice(content)]

    class FakeClient:
        def chat_completion(self, **kwargs):
            raise RuntimeError("chat endpoint unavailable")

        def text_generation(self, prompt, **kwargs):
            return (
                "<think>reasoning</think>\n```json\n"
                '{"action":"adjust_interest","direction":"decrease","topics":["GUI Agent"],"confidence":0.9}'
                "\n```"
            )

    monkeypatch.setattr(llm_parser, "_get_hf_llm_client", lambda: FakeClient())

    result = llm_parser._generate_json_with_hf_api("system", "user", max_tokens=64)

    assert result["direction"] == "decrease"
    assert result["topics"] == ["GUI Agent"]


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

    def fake_local(system_prompt, user_text, max_new_tokens=512, **kwargs):
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
            "institution": "OpenAI",
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
    assert result["generation_provider"] == "local"
    assert result["institution"] == "OpenAI"
    assert "Scientific Planner" in captured["user_text"]
    assert "institution" in captured["system_prompt"]
    assert "科研论文精读助手" in captured["system_prompt"]


def test_synthesize_reading_report_with_llm_uses_hf_api_provider(monkeypatch):
    monkeypatch.setenv("LLM_PARSER_PROVIDER", "hf_api")

    def fake_hf(system_prompt, user_text, max_tokens=500, **kwargs):
        return {
            "one_sentence_summary": "这篇论文给出了一套更稳定的论文兴趣建模流程。",
            "research_background": "论文关注个性化科研推荐中的用户兴趣漂移问题。",
            "core_method": "方法结合了结构化画像与反馈闭环。",
            "key_results": "结果显示推荐命中率和可解释性同时提升。",
            "main_contributions": ["统一冷启动与持续学习链路", "把反馈信号转成更稳定的画像更新"],
            "limitations": ["跨学科场景仍需更多验证"],
            "relevance_points": ["适合当前的学术推荐系统场景"],
            "reading_focus": ["优先阅读方法设计和反馈实验"],
            "recommendation_label": "推荐阅读",
        }

    monkeypatch.setattr(llm_parser, "_generate_json_with_hf_api", fake_hf)
    monkeypatch.setattr(llm_parser, "_generate_json_with_openai", lambda *args, **kwargs: None)

    result = llm_parser.synthesize_reading_report_with_llm(
        paper={
            "title": "Profile Drift Modeling",
            "abstract": "We model user profile drift in paper recommendation.",
            "authors": ["Alice"],
        },
        user_profile={"core_directions": {"agent": 0.8}},
        parsed_pdf={"sections": {"method": "We combine profile priors with online feedback."}},
        heuristic_payload={"one_sentence_summary": "heuristic draft"},
    )

    assert result["recommendation_label"] == "推荐阅读"
    assert result["reading_focus"][0] == "优先阅读方法设计和反馈实验"
    assert result["generation_provider"].startswith("huggingface:")
    assert result["generation_model"]


def test_synthesize_reading_report_with_llm_uses_reading_timeout_override(monkeypatch):
    monkeypatch.setenv("READING_REPORT_LLM_TIMEOUT", "180")

    captured = {}

    def fake_generate(system_prompt, user_text, max_tokens=500, timeout_override=None, **kwargs):
        captured["timeout_override"] = timeout_override
        captured["max_tokens"] = max_tokens
        return {
            "one_sentence_summary": "summary",
            "research_background": "background",
            "core_method": "method",
            "key_results": "results",
            "main_contributions": ["c1"],
            "limitations": ["l1"],
            "relevance_points": ["r1"],
            "reading_focus": ["f1"],
            "recommendation_label": "推荐阅读",
        }

    monkeypatch.setattr(llm_parser, "_generate_json_with_configured_llm", fake_generate)

    result = llm_parser.synthesize_reading_report_with_llm(
        paper={"title": "Paper", "abstract": "Abstract", "authors": ["Alice"]},
        user_profile={"core_directions": {"agent": 0.8}},
        parsed_pdf=None,
        heuristic_payload={},
    )

    assert result["recommendation_label"] == "推荐阅读"
    assert captured["timeout_override"] == 180.0
    assert captured["max_tokens"] >= 4096
    assert result["generation_provider"]
    assert result["generation_model"]


def test_synthesize_reading_report_with_llm_includes_retrieved_evidence_in_prompt(monkeypatch):
    captured = {}

    def fake_generate(system_prompt, user_text, max_tokens=500, timeout_override=None, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["user_text"] = user_text
        return {
            "one_sentence_summary": "summary",
            "research_background": "background",
            "core_method": "method",
            "key_results": "results",
            "main_contributions": ["c1"],
            "limitations": ["l1"],
            "relevance_points": ["r1"],
            "reading_focus": ["f1"],
            "recommendation_label": "推荐阅读",
            "analysis_note": "生成式补充已参考 PDF 检索证据。",
        }

    monkeypatch.setattr(llm_parser, "_generate_json_with_configured_llm", fake_generate)

    result = llm_parser.synthesize_reading_report_with_llm(
        paper={"title": "Paper", "abstract": "Abstract", "authors": ["Alice"]},
        user_profile={"core_directions": {"agent": 0.8}},
        parsed_pdf={"sections": {"method": "We propose a planner."}},
        heuristic_payload={
            "one_sentence_summary": "heuristic draft",
            "retrieved_evidence": {
                "descriptor": "openai:test:1024",
                "chunk_count": 8,
                "matches": {
                    "method": [
                        {
                            "section": "method",
                            "score": 0.91,
                            "text": "We propose a two-stage planner with an evidence retriever.",
                        }
                    ],
                    "results": [
                        {
                            "section": "results",
                            "score": 0.88,
                            "text": "The method improves ranking quality by 12%.",
                        }
                    ],
                },
            },
        },
    )

    assert result["analysis_note"] == "生成式补充已参考 PDF 检索证据。"
    assert "retrieved_evidence" in captured["user_text"]
    assert "two-stage planner with an evidence retriever" in captured["user_text"]
    assert "improves ranking quality by 12%" in captured["user_text"]
    assert "优先参考这些 PDF 语义检索命中的证据片段" in captured["system_prompt"]


def test_synthesize_reading_report_with_llm_includes_field_evidence_map_in_prompt(monkeypatch):
    captured = {}

    def fake_generate(system_prompt, user_text, max_tokens=500, timeout_override=None, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["user_text"] = user_text
        return {
            "one_sentence_summary": "summary",
            "research_background": "background",
            "core_method": "method",
            "key_results": "results",
            "main_contributions": ["c1"],
            "limitations": ["l1"],
            "relevance_points": ["r1"],
            "reading_focus": ["f1"],
            "recommendation_label": "推荐阅读",
            "analysis_note": "已按字段证据约束生成。",
        }

    monkeypatch.setattr(llm_parser, "_generate_json_with_configured_llm", fake_generate)

    result = llm_parser.synthesize_reading_report_with_llm(
        paper={"title": "Paper", "abstract": "Abstract", "authors": ["Alice"]},
        user_profile={"core_directions": {"agent": 0.8}},
        parsed_pdf={"sections": {"method": "We propose a planner."}},
        heuristic_payload={
            "field_evidence_map": {
                "research_background": ["Introduction | score=0.901 | The main challenge is dataset shift."],
                "core_method": ["Method | score=0.933 | We propose a two-stage planner."],
                "key_results": ["Results | score=0.887 | The method improves ranking quality by 12%."],
            }
        },
    )

    assert result["analysis_note"] == "已按字段证据约束生成。"
    assert "field_evidence_map" in captured["user_text"]
    assert "The method improves ranking quality by 12%" in captured["user_text"]
    assert "不要把 results 证据写到 research_background" in captured["system_prompt"]


def test_summarize_retrieved_evidence_for_prompt_limits_and_formats_matches():
    summary = llm_parser._summarize_retrieved_evidence_for_prompt(
        {
            "retrieved_evidence": {
                "descriptor": "fake:test:4",
                "chunk_count": 5,
                "matches": {
                    "method": [
                        {
                            "section": "method",
                            "score": 0.91234,
                            "text": "We propose a two-stage planner with an evidence retriever and a gating network.",
                        },
                        {
                            "section": "approach",
                            "score": 0.83456,
                            "text": "The gating network ranks candidate papers.",
                        },
                        {
                            "section": "extra",
                            "score": 0.81234,
                            "text": "This third item should be truncated by count limit.",
                        },
                    ]
                },
            }
        }
    )

    assert summary["descriptor"] == "fake:test:4"
    assert summary["chunk_count"] == 5
    assert len(summary["matches"]["method"]) == 2
    assert summary["matches"]["method"][0].startswith("[method score=0.912]")
    assert "two-stage planner" in summary["matches"]["method"][0]


def test_summarize_field_evidence_map_for_prompt_limits_items():
    summary = llm_parser._summarize_field_evidence_map_for_prompt(
        {
            "field_evidence_map": {
                "core_method": [
                    "Method | score=0.912 | We propose a two-stage planner.",
                    "Approach | score=0.851 | A gating network ranks candidate papers.",
                    "Extra | score=0.801 | This third item should be trimmed.",
                ]
            }
        }
    )

    assert len(summary["core_method"]) == 2
    assert "two-stage planner" in summary["core_method"][0]


def test_local_llm_cuda_oom_falls_back_to_cpu(monkeypatch):
    monkeypatch.setattr(llm_parser, "LOCAL_LLM_DEVICE_OVERRIDE", None)

    class FakeTensor:
        def __init__(self, values):
            self.values = list(values)
            self.shape = (1, len(self.values))

        def to(self, device):
            return self

        def __getitem__(self, item):
            if isinstance(item, slice):
                return self.values[item]
            return self.values[item]

    class FakeTokenizer:
        pad_token_id = 0
        eos_token_id = 1

        def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
            return "prompt"

        def __call__(self, prompt_text, return_tensors="pt"):
            return {"input_ids": FakeTensor([1, 2, 3])}

        def decode(self, generated_ids, skip_special_tokens=True):
            return '{"action":"adjust_interest","direction":"decrease","topics":["GUI Agent"],"confidence":0.9}'

    class FakeOutputs:
        def __getitem__(self, index):
            return list(range(6))

    class FakeModel:
        def __init__(self, device):
            self.device = device

        def generate(self, **kwargs):
            if self.device == "cuda":
                raise RuntimeError("CUDA out of memory. Tried to allocate 38.00 MiB.")
            return FakeOutputs()

    backends = {
        "cuda": {
            "tokenizer": FakeTokenizer(),
            "model": FakeModel("cuda"),
            "device": "cuda",
            "cache_key": "fake::cuda",
        },
        "cpu": {
            "tokenizer": FakeTokenizer(),
            "model": FakeModel("cpu"),
            "device": "cpu",
            "cache_key": "fake::cpu",
        },
    }

    monkeypatch.setattr(llm_parser, "_clear_cuda_cache", lambda: None)
    monkeypatch.setattr(llm_parser, "_evict_local_llm_backend", lambda cache_key: None)
    monkeypatch.setattr(llm_parser, "_should_fallback_local_llm_to_cpu_on_oom", lambda: True)
    monkeypatch.setattr(
        llm_parser,
        "_get_local_llm_backend",
        lambda force_device=None: backends["cpu"]
        if force_device == "cpu" or llm_parser.LOCAL_LLM_DEVICE_OVERRIDE == "cpu"
        else backends["cuda"],
    )

    class FakeTorch:
        @staticmethod
        def inference_mode():
            class _Context:
                def __enter__(self):
                    return None

                def __exit__(self, exc_type, exc, tb):
                    return False

            return _Context()

    monkeypatch.setattr(llm_parser, "torch", FakeTorch)

    result = llm_parser._generate_json_with_local_llm("system", "user", max_new_tokens=32)

    assert result["direction"] == "decrease"
    assert llm_parser.LOCAL_LLM_DEVICE_OVERRIDE == "cpu"


def test_parse_research_directions_returns_fast_candidates_without_llm(monkeypatch):
    monkeypatch.setenv("LLM_PARSER_PROVIDER", "openai")

    def fail_openai(*args, **kwargs):
        raise AssertionError("explicit direction descriptions should not require slow LLM parsing")

    monkeypatch.setattr(llm_parser, "_generate_json_with_openai", fail_openai)

    result = llm_parser.parse_research_directions(
        "I am interested in protein language model and GUI agent",
        auto_learn=False,
    )

    names = [item["name"] for item in result]
    assert "protein-language-model" in names
    assert "gui-agent" in names


def test_normalize_research_directions_falls_back_to_pending_after_openai_timeout(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PARSER_PROVIDER", "openai")
    monkeypatch.setenv("LLM_PARSER_DIRECTION_TIMEOUT", "9")
    monkeypatch.setattr(direction_lexicon, "PENDING_PATH", tmp_path / "direction_pending.json")

    captured = {}

    def fake_openai(system_prompt, user_text, max_tokens=500, timeout_override=None, **kwargs):
        captured["timeout_override"] = timeout_override
        return None

    monkeypatch.setattr(llm_parser, "_generate_json_with_openai", fake_openai)
    monkeypatch.setattr(llm_parser, "_looks_like_explicit_direction_description", lambda text: False)

    result = llm_parser.normalize_research_directions(
        "scientific planning for protein design",
        auto_persist_known_aliases=False,
        user_id="user_test",
    )

    assert captured["timeout_override"] == 9.0
    assert result["canonical_directions"] == []
    assert result["pending_candidates"][0]["candidate_key"] == "scientific-planning-for-protein-design"
