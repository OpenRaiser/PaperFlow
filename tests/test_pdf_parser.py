"""
Regression tests for PDF parsing and cold-start integration.
"""

import importlib
import sys
from pathlib import Path

import fitz


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pdf_parser = importlib.import_module("skills.pdf-parser.scripts.parse_pdf")
coldstart_agent = importlib.import_module("agents.coldstart-agent.main")


def _create_pdf(tmp_path: Path, text: str) -> str:
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(48, 48, 560, 780), text, fontsize=12)
    doc.save(pdf_path)
    doc.close()
    return str(pdf_path)


def test_extract_metadata_ignores_numbered_heading_as_authors():
    text = pdf_parser.clean_extracted_text(
        "Research Infra\u200b\n1. Personalized Paper Reading\n核心架构：一个不断学习你的系统"
    )

    metadata = pdf_parser.extract_metadata(text)

    assert metadata["title"] == "Research Infra"
    assert metadata["authors"] == []


def test_parse_pdf_extracts_methodology_and_full_text(tmp_path, monkeypatch):
    monkeypatch.setattr(pdf_parser, "_get_embedding_service", lambda: None)

    pdf_path = _create_pdf(
        tmp_path,
        "\n".join(
            [
                "A Data-Driven Framework for Protein Language Models",
                "Alice Smith, Bob Jones",
                "",
                "Abstract",
                "We present a data-driven framework for protein language model experiments in computational biology. Code available on GitHub.",
                "",
                "Introduction",
                "Protein language models are increasingly useful in computational biology.",
                "",
                "Method",
                "Our framework uses a benchmark dataset and a platform for systematic experiments.",
                "",
                "Results",
                "Experiments show improved performance.",
                "",
                "Conclusion",
                "The method is broadly useful.",
            ]
        ),
    )

    result = pdf_parser.parse_pdf(pdf_path)

    assert result["title"] == "A Data-Driven Framework for Protein Language Models"
    assert result["authors"] == ["Alice Smith", "Bob Jones"]
    assert "protein language model" in result["abstract"].lower()
    assert result["methodology_preferences"]["preference_data_driven_over_theory"] is True
    assert result["methodology_preferences"]["preference_systematic_work_over_incremental"] is True
    assert result["methodology_preferences"]["preference_open_source_code"] is True
    assert result["methodology_preferences"]["preference_bio_science_application"] is True
    assert "protein language model" in result["inferred_topics"]
    assert "framework uses a benchmark dataset" in result["full_text"].lower()


def test_extract_text_from_pdf_uses_ocr_when_primary_text_is_too_short(tmp_path, monkeypatch):
    pdf_path = _create_pdf(tmp_path, "scan placeholder")

    monkeypatch.setattr(pdf_parser, "HAS_PYMUPDF", True)
    monkeypatch.setattr(pdf_parser, "_extract_text_from_pdf_with_pymupdf", lambda path: "")
    monkeypatch.setattr(pdf_parser, "_should_try_ocr", lambda text, path: True)
    monkeypatch.setattr(
        pdf_parser,
        "_extract_text_from_pdf_with_ocr",
        lambda path: "OCR recovered abstract text with method details and results.",
    )

    text = pdf_parser.extract_text_from_pdf(pdf_path)

    assert text == "OCR recovered abstract text with method details and results."


def test_extract_text_from_pdf_keeps_primary_text_when_ocr_is_not_better(tmp_path, monkeypatch):
    pdf_path = _create_pdf(tmp_path, "text layer placeholder")

    monkeypatch.setattr(pdf_parser, "HAS_PYMUPDF", True)
    monkeypatch.setattr(
        pdf_parser,
        "_extract_text_from_pdf_with_pymupdf",
        lambda path: "Primary extracted text with enough content to keep.",
    )
    monkeypatch.setattr(pdf_parser, "_should_try_ocr", lambda text, path: True)
    monkeypatch.setattr(pdf_parser, "_extract_text_from_pdf_with_ocr", lambda path: "short ocr")

    text = pdf_parser.extract_text_from_pdf(pdf_path)

    assert text == "Primary extracted text with enough content to keep."


def test_infer_research_directions_can_use_embedding_service(monkeypatch):
    class FakeEmbeddingService:
        def embed_text(self, text):
            if "interface automation" in text.lower():
                return [1.0, 0.0]
            return [0.0, 1.0]

        def embed_batch(self, texts):
            embeddings = []
            for text in texts:
                if "interface automation" in text.lower() or "computer use" in text.lower():
                    embeddings.append([1.0, 0.0])
                else:
                    embeddings.append([0.0, 1.0])
            return embeddings

        def cosine_similarity(self, vector1, vector2):
            return sum(a * b for a, b in zip(vector1, vector2))

    monkeypatch.setattr(pdf_parser, "_get_embedding_service", lambda: FakeEmbeddingService())
    monkeypatch.setattr(pdf_parser, "SEMANTIC_DIRECTION_MIN_SIMILARITY", 0.30)

    directions = pdf_parser.infer_research_directions(
        "This paper studies interface automation for computer use with screen understanding."
    )

    assert any(direction["name"] == "GUI Agent" for direction in directions)


def test_score_direction_confidence_caps_single_pdf_weight():
    assert pdf_parser.score_direction_confidence(match_count=6, keyword_count=6) == 0.7
    assert pdf_parser.score_direction_confidence(match_count=2, keyword_count=6) < 0.7


def test_merge_pdf_result_into_profile_uses_parser_output():
    profile = {
        "user_id": "user_rolea",
        "core_directions": {},
        "topic_weights": {},
        "methodology_preferences": {},
    }
    result = {
        "research_directions": [{"name": "GUI Agent", "confidence": 0.8}],
        "methodology_preferences": {
            "preference_data_driven_over_theory": True,
            "preference_systematic_work_over_incremental": True,
        },
        "inferred_topics": ["protein language model"],
        "full_text": "dataset benchmark github protein",
    }

    coldstart_agent.merge_pdf_result_into_profile(profile, result)

    assert profile["core_directions"]["gui-agent"] == 0.55
    assert profile["topic_weights"]["gui-agent"] == 0.55
    assert profile["topic_weights"]["protein-language-model"] == 0.3
    assert profile["methodology_preferences"]["preference_data_driven_over_theory"] is True
    assert profile["methodology_preferences"]["preference_systematic_work_over_incremental"] is True
    assert profile["methodology_preferences"]["preference_open_source_code"] is True
    assert profile["methodology_preferences"]["preference_bio_science_application"] is True
