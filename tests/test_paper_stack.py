"""
Regression tests for paper-source configuration and embedding integration.
"""

import importlib
import math
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

embedding_module = importlib.import_module("skills.embedding.scripts.embed")
openreview_fetcher = importlib.import_module("skills.openreview-fetcher.scripts.fetch_openreview")
daily_push_agent = importlib.import_module("agents.daily-push-agent.main")
db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")


def test_hash_embedding_respects_configured_dimensions(tmp_path):
    service = embedding_module.EmbeddingService(
        provider="hash",
        model="hash",
        dimensions=16,
        cache_dir=tmp_path,
    )

    embedding = service.embed_text("protein language model")

    assert len(embedding) == 16
    assert math.isclose(sum(value * value for value in embedding), 1.0, rel_tol=1e-6)
    assert service.descriptor == "hash:hash:16"


def test_placeholder_openai_key_falls_back_to_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-your-api-key-here")

    service = embedding_module.EmbeddingService(
        provider="openai",
        dimensions=24,
        cache_dir=tmp_path,
    )

    embedding = service.embed_text("gui agent paper")

    assert service.provider == "hash"
    assert service.model == "hash"
    assert len(embedding) == 24


def test_cosine_similarity_handles_dimension_mismatch():
    score = embedding_module.cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0])

    assert math.isclose(score, 1.0, rel_tol=1e-6)


def test_dashscope_embedding_provider_aliases_to_openai_client(tmp_path, monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test-dashscope-key")
    monkeypatch.setenv("DASHSCOPE_BASE_URL", "https://compat.example.com/v1")
    monkeypatch.setenv("DASHSCOPE_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B")
    monkeypatch.setattr(embedding_module, "OpenAI", FakeClient)
    monkeypatch.setattr(embedding_module, "OPENAI_AVAILABLE", True)

    service = embedding_module.EmbeddingService(
        provider="dashscope",
        dimensions=24,
        cache_dir=tmp_path,
    )

    assert service.provider == "openai"
    assert service.model == "Qwen/Qwen3-Embedding-8B"
    assert captured["api_key"] == "sk-test-dashscope-key"
    assert captured["base_url"] == "https://compat.example.com/v1"


def test_batch_embedding_error_switches_descriptor_to_hash(tmp_path, monkeypatch):
    class FakeEmbeddings:
        def create(self, **kwargs):
            raise RuntimeError("401 Unauthorized")

    class FakeClient:
        def __init__(self):
            self.embeddings = FakeEmbeddings()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-key")
    monkeypatch.setattr(embedding_module, "OpenAI", lambda **kwargs: FakeClient())
    monkeypatch.setattr(embedding_module, "OPENAI_AVAILABLE", True)

    service = embedding_module.EmbeddingService(
        provider="openai",
        model="Qwen/Qwen3-Embedding-8B",
        dimensions=8,
        cache_dir=tmp_path,
    )

    vectors = service.embed_batch(["a", "b"])

    assert service.provider == "hash"
    assert service.model == "hash"
    assert len(vectors) == 2
    assert all(len(vector) == 8 for vector in vectors)


def test_openreview_normalize_conference_name_rejects_unsupported_source():
    assert openreview_fetcher.normalize_conference_name("NeurIPS") == "neurips"
    assert openreview_fetcher.normalize_conference_name("CVPR") == "cvpr"
    assert openreview_fetcher.normalize_conference_name("ECCV") == "eccv"
    assert openreview_fetcher.normalize_conference_name("ACM MM") == "acmmm"
    assert openreview_fetcher.normalize_conference_name("KDD") is None


def test_openreview_search_papers_skips_unsupported_conference():
    papers = openreview_fetcher.search_papers(conference="KDD", year=2026, limit=5)

    assert papers == []


def test_daily_push_default_conferences_expand_to_supported_enabled_sources():
    conferences = daily_push_agent.load_default_conferences()

    assert conferences == ["iclr", "icml", "neurips", "cvpr", "iccv", "eccv", "acl", "emnlp", "acmmm"]


def test_daily_push_repairs_missing_profile_via_runtime_bootstrap(monkeypatch):
    state = {"bootstrapped": False}
    real_import = importlib.import_module

    def fake_get_profile(user_id):
        if not state["bootstrapped"]:
            return None
        return {
            "version": "0.1",
            "core_directions": {"gui-agent": 0.7},
            "topic_weights": {"gui-agent": 0.7},
            "must_read": {"authors": [], "institutions": [], "keywords": []},
        }

    class FakeRuntimeBootstrap:
        @staticmethod
        def ensure_role_profiles(root_dir):
            state["bootstrapped"] = True
            return {"created": ["user_rolea"], "updated": []}

    def fake_import(name):
        if name == "scripts.runtime_bootstrap":
            return FakeRuntimeBootstrap()
        return real_import(name)

    monkeypatch.setattr(daily_push_agent, "get_profile", fake_get_profile)
    monkeypatch.setattr(daily_push_agent.importlib, "import_module", fake_import)
    monkeypatch.setattr(daily_push_agent, "load_scoring_weights", lambda: {})
    monkeypatch.setattr(daily_push_agent, "fetch_and_process_papers", lambda **kwargs: [])

    result = daily_push_agent.daily_push(user_id="user_rolea", send_to_feishu=False)

    assert state["bootstrapped"] is True
    assert result is None


def test_openreview_search_papers_fetches_official_cvf_page(monkeypatch):
    class FakeResponse:
        def __init__(self, text, status_code=200):
            self.text = text
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

    index_html = """
    <dt class="ptitle"><br><a href="/content/CVPR2025/html/Example_Paper_CVPR_2025_paper.html">Example CVPR Paper</a></dt>
    <dd></dd>
    """
    detail_html = """
    <div id="papertitle">Example CVPR Paper</div>
    <div id="authors"><br><b><i>Alice Smith, Bob Lee</i></b>; Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition (CVPR), 2025</div>
    <div id="abstract">A strong vision paper.</div>
    <a href="/content/CVPR2025/papers/Example_Paper_CVPR_2025_paper.pdf">pdf</a>
    """

    def fake_get(url, timeout=60):
        if url.endswith("/CVPR2025?day=all"):
            return FakeResponse(index_html)
        if url.endswith("Example_Paper_CVPR_2025_paper.html"):
            return FakeResponse(detail_html)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(openreview_fetcher.requests, "get", fake_get)

    papers = openreview_fetcher.search_papers(conference="CVPR", year=2025, limit=3)

    assert len(papers) == 1
    assert papers[0]["title"] == "Example CVPR Paper"
    assert papers[0]["authors"] == ["Alice Smith", "Bob Lee"]
    assert papers[0]["abstract"] == "A strong vision paper."
    assert papers[0]["venue"] == "CVPR"
    assert papers[0]["categories"] == ["cvpr"]
    assert papers[0]["publish_date"].startswith("2025-02-28")
    assert papers[0]["pdf_url"].endswith("Example_Paper_CVPR_2025_paper.pdf")


def test_openreview_search_papers_fetches_official_ecva_page(monkeypatch):
    class FakeResponse:
        def __init__(self, text, status_code=200):
            self.text = text
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

    index_html = """
    <button class="accordion">ECCV 2024 Papers</button>
    <div class="accordion-content">
      <div id="content">
        <dl>
          <dt class="ptitle"><br> <a href=papers/eccv_2024/papers_ECCV/html/4_ECCV_2024_paper.php>Example ECCV Paper</a> </dt>
          <dd>Alice Smith*, Bob Lee</dd>
          <dd>[<a href='papers/eccv_2024/papers_ECCV/papers/00004.pdf'>pdf</a>]</dd>
        </dl>
      </div>
    </div>
    <button class="accordion">ECCV 2022 Papers</button>
    """
    detail_html = """
    <div id="authors"><br /><b><i>Alice Smith*, Bob Lee</i></b> ; </div>
    <font size="5"><br /><b>Abstract</b></font>
    <div id="abstract">"A strong ECCV paper."</div>
    """

    def fake_get(url, timeout=60):
        if url.endswith("/papers.php"):
            return FakeResponse(index_html)
        if url.endswith("/papers/eccv_2024/papers_ECCV/html/4_ECCV_2024_paper.php"):
            return FakeResponse(detail_html)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(openreview_fetcher.requests, "get", fake_get)

    papers = openreview_fetcher.search_papers(conference="ECCV", year=2024, limit=3)

    assert len(papers) == 1
    assert papers[0]["title"] == "Example ECCV Paper"
    assert papers[0]["authors"] == ["Alice Smith", "Bob Lee"]
    assert papers[0]["abstract"] == "A strong ECCV paper."
    assert papers[0]["venue"] == "ECCV"
    assert papers[0]["categories"] == ["eccv"]
    assert papers[0]["publish_date"].startswith("2024-09-30")
    assert papers[0]["pdf_url"].endswith("00004.pdf")


def test_openreview_search_papers_fetches_dblp_toc_source(monkeypatch):
    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code
            self.text = ""

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

        def json(self):
            return self._payload

    payload = {
        "result": {
            "hits": {
                "hit": [
                    {
                        "info": {
                            "title": "Example ACM MM Paper.",
                            "authors": {
                                "author": [
                                    {"text": "Alice Smith 0001"},
                                    {"text": "Bob Lee"},
                                ]
                            },
                            "venue": "ACM Multimedia",
                            "ee": "https://doi.org/10.1145/example",
                            "url": "https://dblp.org/rec/conf/mm/example",
                        }
                    }
                ]
            }
        }
    }

    def fake_get(url, timeout=60):
        if url.startswith(openreview_fetcher.DBLP_PUBL_SEARCH_API):
            return FakeResponse(payload)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(openreview_fetcher.requests, "get", fake_get)

    papers = openreview_fetcher.search_papers(conference="ACM MM", year=2025, limit=3)

    assert len(papers) == 1
    assert papers[0]["title"] == "Example ACM MM Paper."
    assert papers[0]["authors"] == ["Alice Smith", "Bob Lee"]
    assert papers[0]["abstract"] == ""
    assert papers[0]["venue"] == "ACM Multimedia"
    assert papers[0]["categories"] == ["acmmm"]
    assert papers[0]["publish_date"].startswith("2025-10-27")
    assert papers[0]["pdf_url"] is None
    assert papers[0]["doi_url"] == "https://doi.org/10.1145/example"


def test_openreview_search_papers_filters_acmmm_workshop_entries(monkeypatch):
    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code
            self.text = ""

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"http {self.status_code}")

        def json(self):
            return self._payload

    payload = {
        "result": {
            "hits": {
                "hit": [
                    {
                        "info": {
                            "title": "CogMAEC'25: The 1st Workshop on Cognition-oriented Multimodal Affective and Empathetic Computing.",
                            "authors": {"author": [{"text": "Alice Smith"}]},
                            "venue": "ACM Multimedia",
                            "pages": "14323-14325",
                            "ee": "https://doi.org/10.1145/workshop",
                            "url": "https://dblp.org/rec/conf/mm/workshop",
                        }
                    },
                    {
                        "info": {
                            "title": "Rule Meets Learning: Confidence-Aware Multi-View Fusion for Self-Supervised 3D Hand Pose Estimation.",
                            "authors": {"author": [{"text": "Bob Lee"}, {"text": "Carol Kim"}]},
                            "venue": "ACM Multimedia",
                            "pages": "1646-1655",
                            "ee": "https://doi.org/10.1145/maintrack",
                            "url": "https://dblp.org/rec/conf/mm/maintrack",
                        }
                    },
                ]
            }
        }
    }

    def fake_get(url, timeout=60):
        if url.startswith(openreview_fetcher.DBLP_PUBL_SEARCH_API):
            return FakeResponse(payload)
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(openreview_fetcher.requests, "get", fake_get)

    papers = openreview_fetcher.search_papers(conference="ACM MM", year=2025, limit=5)

    assert len(papers) == 1
    assert papers[0]["title"].startswith("Rule Meets Learning")


def test_daily_push_acmmm_source_bucket_and_quality():
    paper = {
        "source": "openreview",
        "venue": "ACM Multimedia",
        "categories": ["acmmm"],
    }

    assert daily_push_agent.infer_conference_key(paper) == "acmmm"
    assert daily_push_agent.get_source_bucket(paper) == "acmmm"
    assert daily_push_agent.estimate_quality_score(paper) == 0.8


def test_daily_push_default_journals_include_broad_supported_catalog():
    journals = daily_push_agent.load_default_journals()

    for expected in [
        "nature",
        "nature-biotech",
        "nature-methods",
        "nature-machine-intelligence",
        "nature-computational-science",
        "nature-communications",
        "science",
        "science-advances",
        "cell",
        "pnas",
        "ijcv",
        "tpami",
    ]:
        assert expected in journals


def test_hf_api_embedding_uses_inference_client(tmp_path, monkeypatch):
    captured = {}

    class FakeInferenceClient:
        def __init__(self, model=None, provider=None, api_key=None, timeout=None, **kwargs):
            captured["model"] = model
            captured["provider"] = provider
            captured["api_key"] = api_key
            captured["timeout"] = timeout

        def feature_extraction(self, text, model=None):
            captured["text"] = text
            captured["feature_model"] = model
            return [0.1, 0.2, 0.3]

    monkeypatch.setenv("HF_TOKEN", "hf_test_token")
    monkeypatch.setenv("HF_INFERENCE_PROVIDER", "auto")
    monkeypatch.setenv("HF_API_TIMEOUT", "42")
    monkeypatch.setattr(embedding_module, "HUGGINGFACE_HUB_AVAILABLE", True)
    monkeypatch.setattr(embedding_module, "InferenceClient", FakeInferenceClient)

    service = embedding_module.EmbeddingService(
        provider="hf_api",
        model="Qwen/Qwen3-Embedding-8B",
        dimensions=3,
        cache_dir=tmp_path,
    )
    embedding = service.embed_text("protein language model")

    assert service.provider == "hf_api"
    assert service.model == "Qwen/Qwen3-Embedding-8B"
    assert embedding == [0.1, 0.2, 0.3]
    assert captured == {
        "model": "Qwen/Qwen3-Embedding-8B",
        "provider": "auto",
        "api_key": "hf_test_token",
        "timeout": 42.0,
        "text": "protein language model",
        "feature_model": "Qwen/Qwen3-Embedding-8B",
    }


def test_nscale_api_embedding_uses_native_endpoint(tmp_path, monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {
                        "embedding": [0.1, 0.2, 0.3],
                        "index": 0,
                    }
                ]
            }

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("NSCALE_API_KEY", "sk-nscale-test-key")
    monkeypatch.setenv("NSCALE_BASE_URL", "https://api.test.nscale.com")
    monkeypatch.setenv("NSCALE_API_TIMEOUT", "12")
    monkeypatch.setattr(embedding_module.requests, "post", fake_post)

    service = embedding_module.EmbeddingService(
        provider="nscale_api",
        model="Qwen3-Embedding-8B",
        dimensions=3,
        cache_dir=tmp_path,
    )
    embedding = service.embed_text("protein language model")

    assert service.provider == "nscale_api"
    assert embedding == [0.1, 0.2, 0.3]
    assert captured["url"] == "https://api.test.nscale.com/v1/embeddings"
    assert captured["headers"]["Authorization"] == "Bearer sk-nscale-test-key"
    assert captured["json"]["model"] == "Qwen3-Embedding-8B"
    assert captured["json"]["input"] == "protein language model"
    assert captured["timeout"] == 12.0


def test_missing_hf_token_falls_back_to_hash(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_API_KEY", raising=False)
    monkeypatch.setattr(embedding_module, "HUGGINGFACE_HUB_AVAILABLE", True)
    monkeypatch.setattr(embedding_module, "get_token", lambda: None)

    service = embedding_module.EmbeddingService(
        provider="hf_api",
        model="Qwen/Qwen3-Embedding-8B",
        dimensions=16,
        cache_dir=tmp_path,
    )

    embedding = service.embed_text("gui agent paper")

    assert service.provider == "hash"
    assert service.model == "hash"
    assert len(embedding) == 16


def test_hf_api_uses_logged_in_hf_token_when_env_missing(tmp_path, monkeypatch):
    captured = {}

    class FakeInferenceClient:
        def __init__(self, model=None, provider=None, api_key=None, timeout=None, **kwargs):
            captured["api_key"] = api_key
            captured["model"] = model
            captured["provider"] = provider

        def feature_extraction(self, text, model=None):
            return [1.0, 0.0]

    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_API_KEY", raising=False)
    monkeypatch.setattr(embedding_module, "HUGGINGFACE_HUB_AVAILABLE", True)
    monkeypatch.setattr(embedding_module, "get_token", lambda: "hf_logged_in_token")
    monkeypatch.setattr(embedding_module, "InferenceClient", FakeInferenceClient)

    service = embedding_module.EmbeddingService(
        provider="hf_api",
        model="Qwen/Qwen3-Embedding-8B",
        dimensions=2,
        cache_dir=tmp_path,
    )

    embedding = service.embed_text("science agent")

    assert service.provider == "hf_api"
    assert embedding == [1.0, 0.0]
    assert captured == {
        "api_key": "hf_logged_in_token",
        "model": "Qwen/Qwen3-Embedding-8B",
        "provider": "auto",
    }


def test_hf_api_ignores_placeholder_env_token_and_uses_logged_in_token(tmp_path, monkeypatch):
    captured = {}

    class FakeInferenceClient:
        def __init__(self, model=None, provider=None, api_key=None, timeout=None, **kwargs):
            captured["api_key"] = api_key
            captured["model"] = model
            captured["provider"] = provider

        def feature_extraction(self, text, model=None):
            return [1.0, 0.0]

    monkeypatch.setenv("HF_TOKEN", "hf_xxxxxxxxxxxxxxxxxxxx")
    monkeypatch.delenv("HF_API_KEY", raising=False)
    monkeypatch.setattr(embedding_module, "HUGGINGFACE_HUB_AVAILABLE", True)
    monkeypatch.setattr(embedding_module, "get_token", lambda: "hf_logged_in_token")
    monkeypatch.setattr(embedding_module, "InferenceClient", FakeInferenceClient)

    service = embedding_module.EmbeddingService(
        provider="hf_api",
        model="Qwen/Qwen3-Embedding-8B",
        dimensions=2,
        cache_dir=tmp_path,
    )

    embedding = service.embed_text("science agent")

    assert service.provider == "hf_api"
    assert embedding == [1.0, 0.0]
    assert captured == {
        "api_key": "hf_logged_in_token",
        "model": "Qwen/Qwen3-Embedding-8B",
        "provider": "auto",
    }


def test_non_hf_key_with_auto_embedding_provider_falls_back_to_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "sk-test-provider-key")
    monkeypatch.setenv("HF_EMBEDDING_PROVIDER", "")
    monkeypatch.setenv("HF_INFERENCE_PROVIDER", "auto")
    monkeypatch.setattr(embedding_module, "HUGGINGFACE_HUB_AVAILABLE", True)

    service = embedding_module.EmbeddingService(
        provider="hf_api",
        model="Qwen/Qwen3-Embedding-8B",
        dimensions=8,
        cache_dir=tmp_path,
    )

    embedding = service.embed_text("science agent")

    assert service.provider == "hash"
    assert service.model == "hash"
    assert len(embedding) == 8


def test_qwen_local_embedding_enables_trust_remote_code(tmp_path, monkeypatch):
    captured = {}

    class FakeSentenceTransformer:
        def __init__(self, model_name, **kwargs):
            captured["model_name"] = model_name
            captured["kwargs"] = kwargs

        def encode(self, text, normalize_embeddings=True):
            return [1.0, 0.0, 0.0]

    monkeypatch.setattr(embedding_module, "SENTENCE_TRANSFORMERS_AVAILABLE", True)
    monkeypatch.setattr(embedding_module, "SentenceTransformer", FakeSentenceTransformer)

    service = embedding_module.EmbeddingService(
        provider="local",
        model="Qwen/Qwen3-Embedding-8B",
        dimensions=3,
        cache_dir=tmp_path,
    )

    assert service.provider == "local"
    assert service.model == "Qwen/Qwen3-Embedding-8B"
    assert captured["model_name"] == "Qwen/Qwen3-Embedding-8B"
    assert captured["kwargs"]["trust_remote_code"] is True


def test_local_embedding_model_path_overrides_model_id(tmp_path, monkeypatch):
    captured = {}
    local_model_dir = tmp_path / "Qwen3-Embedding-8B"
    local_model_dir.mkdir()

    class FakeSentenceTransformer:
        def __init__(self, model_name, **kwargs):
            captured["model_name"] = model_name
            captured["kwargs"] = kwargs

        def encode(self, text, normalize_embeddings=True):
            return [1.0, 0.0]

    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL_PATH", str(local_model_dir))
    monkeypatch.setenv("LOCAL_EMBEDDING_TRUST_REMOTE_CODE", "true")
    monkeypatch.setattr(embedding_module, "SENTENCE_TRANSFORMERS_AVAILABLE", True)
    monkeypatch.setattr(embedding_module, "SentenceTransformer", FakeSentenceTransformer)

    service = embedding_module.EmbeddingService(
        provider="local",
        model="sentence-transformers/all-MiniLM-L6-v2",
        dimensions=2,
        cache_dir=tmp_path,
    )

    assert service.model == "Qwen3-Embedding-8B"
    assert captured["model_name"] == str(local_model_dir)
    assert captured["kwargs"]["trust_remote_code"] is True


def test_openreview_without_credentials_returns_empty_when_mock_disabled(monkeypatch):
    monkeypatch.delenv("SCITASTE_ALLOW_MOCK_PAPERS", raising=False)
    monkeypatch.setattr(openreview_fetcher, "get_client", lambda: None)

    papers = openreview_fetcher.search_papers(conference="iclr", year=2026, limit=3)

    assert papers == []


def test_openreview_search_uses_submission_invitation_and_limit(monkeypatch):
    class FakeNote:
        def __init__(self):
            self.id = "note_123"
            self.cdate = 1710000000000
            self.content = {
                "title": {"value": "OpenReview Test Paper"},
                "abstract": {"value": "Test abstract"},
                "authors": {"value": ["Alice", "Bob"]},
            }

    class FakeClient:
        def __init__(self):
            self.calls = []

        def get_notes(self, **kwargs):
            self.calls.append(kwargs)
            return [FakeNote()]

    client = FakeClient()
    monkeypatch.setattr(openreview_fetcher, "get_client", lambda: client)

    papers = openreview_fetcher.search_papers(conference="iclr", year=2026, limit=3)

    assert len(papers) == 1
    assert papers[0]["title"] == "OpenReview Test Paper"
    assert client.calls == [{"invitation": "ICLR.cc/2026/Conference/-/Submission", "limit": 3}]


def test_openreview_get_client_caches_authenticated_client(monkeypatch):
    monkeypatch.setattr(openreview_fetcher, "OPENREVIEW_AVAILABLE", True)
    monkeypatch.setattr(openreview_fetcher, "_CLIENT_CACHE", {})
    monkeypatch.setattr(openreview_fetcher, "_CLIENT_RETRY_AFTER", 0.0)
    monkeypatch.setenv("OPENREVIEW_USERNAME", "user@example.com")
    monkeypatch.setenv("OPENREVIEW_PASSWORD", "secret")
    monkeypatch.delenv("OPENREVIEW_TOKEN", raising=False)

    calls = {"count": 0}

    class FakeClient:
        pass

    def fake_client_factory(**kwargs):
        calls["count"] += 1
        return FakeClient()

    monkeypatch.setattr(openreview_fetcher, "OpenReviewClient", fake_client_factory)

    client1 = openreview_fetcher.get_client()
    client2 = openreview_fetcher.get_client()

    assert client1 is client2
    assert calls["count"] == 1


def test_openreview_fetch_by_date_uses_inferred_year_and_filters_range(monkeypatch):
    calls = []

    def fake_get_recent_papers(days, conferences, limit_per_conference, years=None):
        calls.append(
            {
                "days": days,
                "conferences": conferences,
                "limit_per_conference": limit_per_conference,
                "years": years,
            }
        )
        return [
            {"title": "2026 Paper", "publish_date": "2026-04-10T12:00:00", "venue": "ICLR"},
            {"title": "2024 Paper", "publish_date": "2024-04-10T12:00:00", "venue": "ICLR"},
        ]

    monkeypatch.setattr(openreview_fetcher, "get_recent_papers", fake_get_recent_papers)

    papers = openreview_fetcher.fetch_by_date(
        start_date="20260401",
        end_date="20260412",
        conferences=["iclr"],
        limit=6,
    )

    assert calls == [
        {
            "days": 30,
            "conferences": ["iclr"],
            "limit_per_conference": 6,
            "years": [2026],
        }
    ]
    assert [paper["title"] for paper in papers] == ["2026 Paper"]


def test_prepare_paper_features_uses_embedding_service(monkeypatch):
    class FakeService:
        descriptor = "hash:hash:4"

    monkeypatch.setattr(daily_push_agent, "get_embedding_service", lambda: FakeService())
    monkeypatch.setattr(
        daily_push_agent,
        "embed_batch",
        lambda texts: [[0.1, 0.2, 0.3, 0.4] for _ in texts],
    )

    papers = [
        {
            "title": "GUI Agent for Protein Design",
            "abstract": "A benchmark for agentic protein workflows.",
            "categories": ["cs.AI"],
            "source": "arxiv",
        }
    ]

    prepared = daily_push_agent.prepare_paper_features(papers)

    assert prepared[0]["embedding"] == [0.1, 0.2, 0.3, 0.4]
    assert prepared[0]["embedding_model"] == "hash:hash:4"
    assert prepared[0]["quality_score"] > 0.5
    assert "agent" in prepared[0]["keywords"]


def test_extract_topics_from_title_recognizes_bio_science_signals():
    topics = daily_push_agent.extract_topics_from_title(
        "Single-cell multi-omic analysis of protein structure in scientific discovery"
    )

    assert "bio-molecular" in topics
    assert "bioinformatics" in topics
    assert "protein-folding" in topics
    assert "science-discovery" in topics


def test_categorize_papers_filters_quality_only_items():
    profile = {
        "interest_vector": [1.0, 0.0, 0.0, 0.0],
        "topic_weights": {
            "bio-molecular": 0.95,
            "protein-folding": 0.8,
        },
        "author_heat": {},
        "institution_heat": {},
        "must_read": {"authors": [], "institutions": [], "keywords": []},
    }
    weights = {
        "threshold_high_relevant": 0.40,
        "threshold_maybe_interested": 0.25,
        "threshold_edge_relevant": 0.15,
        "min_relevance_signal": 0.08,
        "rank_high_fraction": 0.10,
        "rank_maybe_fraction": 0.40,
    }

    irrelevant = daily_push_agent.PaperWithScore(
        paper={
            "title": "General Nature News",
            "keywords": ["nature"],
            "authors": [],
            "embedding": [0.0, 1.0, 0.0, 0.0],
            "institution": "",
        },
        score=0.22,
        category="edge_relevant",
        relevance_signal=0.0,
    )
    relevant = daily_push_agent.PaperWithScore(
        paper={
            "title": "Protein structure modeling",
            "keywords": ["bio-molecular", "protein-folding"],
            "authors": [],
            "embedding": [1.0, 0.0, 0.0, 0.0],
            "institution": "",
        },
        score=0.31,
        category="maybe_interested",
        relevance_signal=0.95,
    )

    categorized = daily_push_agent.categorize_papers_by_rank([relevant, irrelevant], profile, weights)

    assert len(categorized) == 1
    assert categorized[0].paper["title"] == "Protein structure modeling"
    assert categorized[0].category in {"high_relevant", "maybe_interested"}


def test_get_must_read_matches_reports_match_reasons():
    matches = daily_push_agent.get_must_read_matches(
        {
            "authors": ["Cheng Tan", "Alice Smith"],
            "institution": "Tsinghua University",
            "keywords": ["protein-folding", "bio-molecular"],
        },
        {
            "must_read": {
                "authors": ["cheng tan"],
                "institutions": ["tsinghua"],
                "keywords": ["protein-folding"],
            }
        },
    )

    assert matches == {
        "authors": ["cheng tan"],
        "institutions": ["tsinghua"],
        "keywords": ["protein-folding"],
    }


def test_format_push_card_shows_must_read_configuration_when_no_hit():
    scored_papers = [
        daily_push_agent.PaperWithScore(
            paper={
                "title": "Protein structure modeling",
                "authors": ["Alice Smith"],
                "categories": ["cs.AI"],
            },
            score=0.35,
            category="high_relevant",
            relevance_signal=0.9,
        )
    ]

    card = daily_push_agent.format_push_card(
        scored_papers,
        profile={
            "must_read": {
                "authors": ["cheng tan"],
                "institutions": [],
                "keywords": [],
            }
        },
        date="04-12",
        total_fetched=10,
    )

    assert "🔒 必读清单命中（0 篇）" in card
    assert "当前配置：作者 cheng tan | 机构 （空） | 关键词 （空）" in card
    assert "本次推送未命中当前必读清单。" in card


def test_format_push_card_shows_must_read_hit_reason():
    scored_papers = [
        daily_push_agent.PaperWithScore(
            paper={
                "title": "A Must Read Paper",
                "authors": ["Cheng Tan"],
                "categories": ["cs.AI"],
                "institution": "Tsinghua University",
                "keywords": ["protein-folding"],
            },
            score=0.95,
            category="must_read",
            relevance_signal=0.95,
        )
    ]

    card = daily_push_agent.format_push_card(
        scored_papers,
        profile={
            "must_read": {
                "authors": ["cheng tan"],
                "institutions": ["tsinghua"],
                "keywords": ["protein-folding"],
            }
        },
        date="04-12",
        total_fetched=1,
    )

    assert "🔒 必读清单命中（1 篇）" in card
    assert "命中：作者：cheng tan；机构：tsinghua；关键词：protein-folding" in card


def test_fetch_and_process_papers_passes_days_to_journal_fetcher(monkeypatch):
    journal_calls = []

    monkeypatch.setattr(daily_push_agent, "arxiv_fetch_by_date", lambda **kwargs: [])
    monkeypatch.setattr(daily_push_agent, "openreview_fetch_by_date", lambda **kwargs: [])

    def fake_journal_fetch_recent(*, journals, days, limit_per_journal):
        journal_calls.append(
            {
                "journals": journals,
                "days": days,
                "limit_per_journal": limit_per_journal,
            }
        )
        return []

    monkeypatch.setattr(daily_push_agent, "journal_fetch_recent", fake_journal_fetch_recent)
    monkeypatch.setattr(daily_push_agent, "prepare_paper_features", lambda papers: papers)

    papers = daily_push_agent.fetch_and_process_papers(
        days=3,
        arxiv_categories=["cs.AI"],
        conferences=["iclr"],
        journals=["nature", "science"],
        limit_per_source=5,
    )

    assert papers == []
    assert journal_calls == [
        {
            "journals": ["nature", "science"],
            "days": 3,
            "limit_per_journal": 5,
        },
        {
            "journals": ["nature", "science"],
            "days": 7,
            "limit_per_journal": 5,
        },
    ]


def test_fetch_and_process_papers_widens_sparse_sources_for_recent_push(monkeypatch):
    arxiv_calls = []
    journal_calls = []

    def fake_arxiv_fetch_by_date(*, start_date, end_date, categories, limit):
        arxiv_calls.append({"start_date": start_date, "end_date": end_date, "categories": categories, "limit": limit})
        if len(arxiv_calls) == 1:
            return []
        return [{"title": "Fallback arXiv paper"}]

    def fake_journal_fetch_recent(*, journals, days, limit_per_journal):
        journal_calls.append(days)
        if days == 1:
            return []
        return [{"title": "Fallback Nature paper"}]

    monkeypatch.setattr(daily_push_agent, "arxiv_fetch_by_date", fake_arxiv_fetch_by_date)
    monkeypatch.setattr(daily_push_agent, "openreview_fetch_by_date", lambda **kwargs: [])
    monkeypatch.setattr(daily_push_agent, "journal_fetch_recent", fake_journal_fetch_recent)
    monkeypatch.setattr(daily_push_agent, "prepare_paper_features", lambda papers: papers)

    papers = daily_push_agent.fetch_and_process_papers(
        days=1,
        arxiv_categories=["cs.AI"],
        conferences=["iclr"],
        journals=["nature"],
        limit_per_source=5,
    )

    assert [paper["title"] for paper in papers] == ["Fallback arXiv paper", "Fallback Nature paper"]
    assert len(arxiv_calls) == 2
    assert journal_calls == [1, 7]


def test_fetch_and_process_papers_widens_openreview_when_pool_is_sparse(monkeypatch):
    openreview_calls = []

    def fake_openreview_fetch_by_date(*, start_date, end_date, conferences, limit):
        openreview_calls.append(
            {
                "start_date": start_date,
                "end_date": end_date,
                "conferences": conferences,
                "limit": limit,
            }
        )
        if len(openreview_calls) == 1:
            return []
        return [{"title": "Fallback ICLR paper"}]

    monkeypatch.setattr(daily_push_agent, "arxiv_fetch_by_date", lambda **kwargs: [])
    monkeypatch.setattr(daily_push_agent, "openreview_fetch_by_date", fake_openreview_fetch_by_date)
    monkeypatch.setattr(daily_push_agent, "journal_fetch_recent", lambda **kwargs: [])
    monkeypatch.setattr(daily_push_agent, "prepare_paper_features", lambda papers: papers)

    papers = daily_push_agent.fetch_and_process_papers(
        days=1,
        arxiv_categories=["cs.AI"],
        conferences=["iclr"],
        journals=["nature"],
        limit_per_source=5,
    )

    assert [paper["title"] for paper in papers] == ["Fallback ICLR paper"]
    assert len(openreview_calls) == 2


def test_apply_source_diversity_quota_caps_dominant_source():
    weights = {
        "source_diversity_min_total": 4,
        "source_diversity_min_per_bucket": 2,
        "source_diversity_max_share": 0.6,
    }

    papers = [
        daily_push_agent.PaperWithScore(
            paper={"title": f"Nature {idx}", "source": "journal", "journal": "nature"},
            score=0.9 - idx * 0.01,
            category="high_relevant",
            relevance_signal=0.5,
        )
        for idx in range(8)
    ] + [
        daily_push_agent.PaperWithScore(
            paper={"title": f"arXiv {idx}", "source": "arxiv"},
            score=0.7 - idx * 0.01,
            category="maybe_interested",
            relevance_signal=0.4,
        )
        for idx in range(2)
    ]

    balanced = daily_push_agent.apply_source_diversity_quota(papers, weights)
    bucket_counts = {}
    for paper in balanced:
        bucket = daily_push_agent.get_source_bucket(paper.paper)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

    assert len(balanced) == 8
    assert bucket_counts == {"nature": 6, "arxiv": 2}


def test_apply_source_diversity_quota_keeps_single_source_results():
    weights = {
        "source_diversity_min_total": 4,
        "source_diversity_min_per_bucket": 2,
        "source_diversity_max_share": 0.6,
    }
    papers = [
        daily_push_agent.PaperWithScore(
            paper={"title": f"arXiv {idx}", "source": "arxiv"},
            score=0.8 - idx * 0.01,
            category="maybe_interested",
            relevance_signal=0.4,
        )
        for idx in range(4)
    ]

    balanced = daily_push_agent.apply_source_diversity_quota(papers, weights)

    assert [paper.paper["title"] for paper in balanced] == [paper.paper["title"] for paper in papers]


def test_save_paper_persists_embedding_payload(test_db_path):
    db_ops.DB_PATH = test_db_path

    paper_id = db_ops.save_paper(
        arxiv_id="2404.12345",
        title="A Data-Driven Framework",
        authors=["Alice Smith"],
        abstract="Framework paper",
        embedding=[0.1, 0.2, 0.3],
        embedding_model="hash:hash:3",
    )
    stored = db_ops.get_paper_by_arxiv_id("2404.12345")

    assert paper_id is not None
    assert stored["embedding"] is not None
    assert stored["embedding_model"] == "hash:hash:3"
