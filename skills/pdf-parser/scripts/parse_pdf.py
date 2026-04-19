#!/usr/bin/env python3
"""
PDF Parser: Extract structured information from research papers.
"""

import importlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# PyMuPDF
try:
    import fitz
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

# pdfplumber
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    from rapidocr_onnxruntime import RapidOCR
    HAS_RAPIDOCR = True
except ImportError:
    HAS_RAPIDOCR = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pytesseract
    HAS_PYTESSERACT = True
except ImportError:
    HAS_PYTESSERACT = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# Common section heading patterns, including numbered headings like
# "1 Introduction" and "II. Method".
SECTION_HEADING_PREFIX = r"(?:\d+(?:\.\d+)*[.)]?|[IVXivx]+[.)]?|[一二三四五六七八九十]+[、.)]?)?"


def _section_heading_pattern(*titles: str) -> str:
    joined_titles = "|".join(re.escape(title) for title in titles)
    return (
        rf"(?:^|\n)\s*{SECTION_HEADING_PREFIX}\s*"
        rf"(?:{joined_titles})\s*[:：]?\s*(?:$|\n)"
    )


SECTION_PATTERNS = {
    "abstract": _section_heading_pattern("abstract", "summary", "摘要"),
    "introduction": _section_heading_pattern("introduction", "background", "related work"),
    "method": _section_heading_pattern("method", "methodology", "approach", "our method", "model"),
    "results": _section_heading_pattern("results", "experiments", "evaluation", "experiments and results"),
    "discussion": _section_heading_pattern("discussion", "analysis"),
    "conclusion": _section_heading_pattern("conclusion", "summary", "future work"),
    "references": _section_heading_pattern("references", "bibliography"),
}

SECTION_TITLES = {
    "abstract",
    "summary",
    "introduction",
    "background",
    "related work",
    "method",
    "methodology",
    "approach",
    "results",
    "experiments",
    "evaluation",
    "discussion",
    "analysis",
    "conclusion",
    "future work",
    "references",
    "bibliography",
    "摘要",
}

ABSTRACT_HEADINGS = {"abstract", "summary", "摘要"}
KEYWORD_HEADINGS = {"keywords", "keyword", "关键词"}

# 研究领域关键词
RESEARCH_AREA_KEYWORDS = {
    "GUI Agent": ["gui", "interface", "agent", "automation", "ui", "interaction"],
    "Protein Folding": ["protein", "folding", "structure", "alphafold"],
    "Machine Learning": ["machine learning", "deep learning", "neural network"],
    "NLP": ["natural language", "language model", "nlp", "text"],
    "Computer Vision": ["computer vision", "image", "visual", "cv"],
    "Bioinformatics": ["bioinformatics", "genomics", "computational biology"],
}

TOPIC_PATTERNS = [
    "gui agent",
    "protein language model",
    "protein folding",
    "computational biology",
    "bioinformatics",
    "multimodal reasoning",
    "machine learning",
    "deep learning",
    "language model",
    "computer vision",
]

SEMANTIC_DIRECTION_PROTOTYPES = {
    "GUI Agent": "GUI agent for interface automation, screen understanding, computer use, UI interaction, action planning",
    "Protein Folding": "Protein folding, structure prediction, AlphaFold, biomolecular structure modeling, protein design",
    "Machine Learning": "Machine learning methods, predictive modeling, representation learning, classification and regression",
    "NLP": "Natural language processing, language models, text generation, transformers, language understanding",
    "Computer Vision": "Computer vision, image understanding, visual recognition, video analysis, visual grounding",
    "Bioinformatics": "Bioinformatics, computational biology, genomics, biological sequence modeling, molecular analysis",
}
SEMANTIC_DIRECTION_MIN_SIMILARITY = float(os.environ.get("PDF_PARSER_MIN_EMBED_SIMILARITY", "0.30"))
PDF_PARSER_ENABLE_OCR = os.environ.get("PDF_PARSER_ENABLE_OCR", "1").strip().lower() not in {"0", "false", "off", "no"}
PDF_PARSER_OCR_MIN_TEXT_CHARS = int(os.environ.get("PDF_PARSER_OCR_MIN_TEXT_CHARS", "200"))
PDF_PARSER_OCR_DPI = int(os.environ.get("PDF_PARSER_OCR_DPI", "220"))
PDF_PARSER_OCR_MAX_PAGES = int(os.environ.get("PDF_PARSER_OCR_MAX_PAGES", "12"))
PDF_PARSER_OCR_LANG = os.environ.get("PDF_PARSER_OCR_LANG", "eng")

_EMBEDDING_SERVICE = None
_OCR_ENGINE = None


def clean_extracted_text(text: str) -> str:
    """Normalize PDF text so downstream regexes behave predictably."""
    if not text:
        return ""

    text = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\ufeff", "")
    )

    cleaned_lines: List[str] = []
    previous_blank = False
    for raw_line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line:
            if not previous_blank:
                cleaned_lines.append("")
            previous_blank = True
            continue
        cleaned_lines.append(line)
        previous_blank = False

    return "\n".join(cleaned_lines).strip()


def _normalize_heading_line(line: str) -> str:
    normalized = re.sub(
        r"^\s*(?:(?:\d+(?:\.\d+)*[.)]?)|(?:[IVXivx]+[.)]?)|(?:[一二三四五六七八九十]+[、.)]?))?\s*",
        "",
        (line or "").strip(),
    )
    return normalized.strip().lower().rstrip(":：")


def _get_rapidocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE or None

    if not HAS_RAPIDOCR:
        _OCR_ENGINE = False
        return None

    try:
        _OCR_ENGINE = RapidOCR()
    except Exception:
        _OCR_ENGINE = False
    return _OCR_ENGINE or None


def _extract_text_from_pdf_with_pymupdf(pdf_path: str) -> str:
    if not HAS_PYMUPDF:
        return ""

    doc = fitz.open(pdf_path)
    try:
        text = ""
        for page in doc:
            text += page.get_text("text", sort=True) + "\n"
        return clean_extracted_text(text)
    finally:
        doc.close()


def _extract_text_from_pdf_with_pdfplumber(pdf_path: str) -> str:
    if not HAS_PDFPLUMBER:
        return ""

    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return clean_extracted_text(text)


def _should_try_ocr(text: str, pdf_path: str) -> bool:
    if not PDF_PARSER_ENABLE_OCR or not HAS_PYMUPDF:
        return False

    normalized = clean_extracted_text(text)
    if len(normalized) < PDF_PARSER_OCR_MIN_TEXT_CHARS:
        return True

    try:
        doc = fitz.open(pdf_path)
        try:
            page_count = max(1, len(doc))
        finally:
            doc.close()
    except Exception:
        page_count = 1

    avg_chars_per_page = len(normalized) / max(page_count, 1)
    if avg_chars_per_page < max(40, PDF_PARSER_OCR_MIN_TEXT_CHARS // 2):
        return True

    return False


def _render_page_to_numpy(page: Any):
    if not HAS_NUMPY:
        return None

    scale = max(1.0, float(PDF_PARSER_OCR_DPI) / 72.0)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    channels = max(1, int(pix.n))
    try:
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, channels)
    except Exception:
        return None
    return image


def _ocr_page_with_rapidocr(page: Any) -> str:
    engine = _get_rapidocr_engine()
    if engine is None:
        return ""

    image = _render_page_to_numpy(page)
    if image is None:
        return ""

    try:
        result, _elapsed = engine(image)
    except Exception:
        return ""

    texts: List[str] = []
    for item in result or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        candidate = item[1]
        if isinstance(candidate, (list, tuple)) and candidate:
            candidate = candidate[0]
        text = str(candidate or "").strip()
        if text:
            texts.append(text)
    return "\n".join(texts).strip()


def _ocr_page_with_pytesseract(page: Any) -> str:
    if not (HAS_PIL and HAS_PYTESSERACT):
        return ""

    scale = max(1.0, float(PDF_PARSER_OCR_DPI) / 72.0)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    mode = "RGB" if pix.n < 4 else "RGBA"
    try:
        image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
        return str(pytesseract.image_to_string(image, lang=PDF_PARSER_OCR_LANG) or "").strip()
    except Exception:
        return ""


def _ocr_page_with_pymupdf_ocr(page: Any) -> str:
    textpage_ocr = getattr(page, "get_textpage_ocr", None)
    if not callable(textpage_ocr):
        return ""

    try:
        textpage = textpage_ocr(dpi=PDF_PARSER_OCR_DPI, language=PDF_PARSER_OCR_LANG)
        return str(page.get_text("text", textpage=textpage) or "").strip()
    except Exception:
        return ""


def _extract_text_from_pdf_with_ocr(pdf_path: str) -> str:
    if not HAS_PYMUPDF or not PDF_PARSER_ENABLE_OCR:
        return ""

    doc = fitz.open(pdf_path)
    try:
        page_texts: List[str] = []
        max_pages = max(1, int(PDF_PARSER_OCR_MAX_PAGES))
        for page_index, page in enumerate(doc):
            if page_index >= max_pages:
                break
            text = (
                _ocr_page_with_rapidocr(page)
                or _ocr_page_with_pytesseract(page)
                or _ocr_page_with_pymupdf_ocr(page)
            )
            cleaned = clean_extracted_text(text)
            if cleaned:
                page_texts.append(cleaned)
        return clean_extracted_text("\n\n".join(page_texts))
    finally:
        doc.close()


def _get_embedding_service():
    global _EMBEDDING_SERVICE
    if _EMBEDDING_SERVICE is not None:
        return _EMBEDDING_SERVICE

    try:
        embedding_module = importlib.import_module("skills.embedding.scripts.embed")
        _EMBEDDING_SERVICE = embedding_module.get_embedding_service()
    except Exception:
        _EMBEDDING_SERVICE = False

    return _EMBEDDING_SERVICE or None


def score_semantic_direction_confidence(similarity: float) -> float:
    """Convert embedding similarity into a conservative cold-start confidence."""
    margin = max(0.0, float(similarity) - SEMANTIC_DIRECTION_MIN_SIMILARITY)
    return round(min(0.68, 0.48 + margin * 0.9), 4)


def is_section_heading(line: str) -> bool:
    """Return True when a line looks like a section title rather than content."""
    return _normalize_heading_line(line) in SECTION_TITLES


def split_author_names(line: str) -> List[str]:
    """Extract plausible author names from a byline."""
    normalized = (line or "").strip()
    if not normalized:
        return []
    if re.match(r"^\d+[\.\)]", normalized):
        return []
    if "http" in normalized.lower():
        return []
    if is_section_heading(normalized):
        return []

    parts = re.split(r",|;|\band\b", normalized, flags=re.IGNORECASE)
    authors: List[str] = []
    for part in parts:
        candidate = re.sub(r"[\d*†‡]+", "", part).strip(" -|")
        if not candidate:
            continue
        if "@" in candidate:
            continue
        words = [word for word in candidate.split() if word]
        if not 1 <= len(words) <= 5:
            continue
        if not all(re.match(r"^[A-Z][A-Za-z.'\-]*$", word) for word in words):
            continue
        authors.append(candidate)
    return authors


def extract_title_and_authors(lines: List[str]) -> Dict[str, Any]:
    """Infer title and author byline from the first page text."""
    metadata: Dict[str, Any] = {"title": "", "authors": []}
    if not lines:
        return metadata

    title_lines: List[str] = []
    title_end_idx = -1
    for index, raw_line in enumerate(lines[:25]):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("http"):
            continue
        if is_section_heading(line):
            continue
        if len(line) < 6:
            continue
        title_lines.append(line)
        title_end_idx = index
        for follow_idx in range(index + 1, min(index + 4, len(lines))):
            follow_line = lines[follow_idx].strip()
            if not follow_line:
                break
            if is_section_heading(follow_line) or split_author_names(follow_line):
                break
            if follow_line.startswith("http") or re.match(r"^\d+[\.\)]", follow_line):
                break
            if len(" ".join(title_lines + [follow_line])) > 180:
                break
            title_lines.append(follow_line)
            title_end_idx = follow_idx
        break

    if title_lines:
        metadata["title"] = " ".join(title_lines)

    for line in lines[title_end_idx + 1:title_end_idx + 6]:
        authors = split_author_names(line)
        if authors:
            metadata["authors"] = authors
            break
        if line.strip() and (is_section_heading(line) or re.match(r"^\d+[\.\)]", line.strip())):
            break

    return metadata


def extract_abstract(text: str) -> str:
    """Extract the abstract/summary block when present."""
    normalized_text = clean_extracted_text(text)
    if normalized_text:
        lines = normalized_text.split("\n")
        start_index = None
        for index, line in enumerate(lines):
            if _normalize_heading_line(line) in ABSTRACT_HEADINGS:
                start_index = index + 1
                break

        if start_index is not None:
            body_lines: List[str] = []
            previous_blank = False
            for line in lines[start_index:]:
                stripped = line.strip()
                if not stripped:
                    if body_lines and not previous_blank:
                        body_lines.append("")
                    previous_blank = True
                    continue

                previous_blank = False
                normalized_heading = _normalize_heading_line(stripped)
                if body_lines and (
                    normalized_heading in SECTION_TITLES
                    or normalized_heading in KEYWORD_HEADINGS
                    or stripped.lower().startswith("keywords:")
                    or stripped.startswith("关键词")
                ):
                    break
                body_lines.append(stripped)

            abstract = "\n".join(body_lines).strip()
            if abstract:
                return abstract

    patterns = [
        r"(?:^|\n)\s*(?:abstract|summary|摘要)\s*[:：]?\s*\n+(?P<body>.+?)(?=\n\s*(?:keywords?|introduction|background|related work|1\.|i\.|一、)\b|\Z)",
        r"(?:^|\n)\s*(?:abstract|summary|摘要)\s*[:：]?\s*(?P<body>.+?)(?=\n\s*\n|\n\s*(?:introduction|background|1\.|i\.)\b|\Z)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group("body").strip()
    return ""


def extract_text_from_pdf(pdf_path: str) -> str:
    """从 PDF 提取文本"""
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    primary_text = ""
    if HAS_PYMUPDF:
        primary_text = _extract_text_from_pdf_with_pymupdf(pdf_path)
    elif HAS_PDFPLUMBER:
        primary_text = _extract_text_from_pdf_with_pdfplumber(pdf_path)
    else:
        raise ImportError("No PDF library available. Install pymupdf or pdfplumber.")

    if _should_try_ocr(primary_text, pdf_path):
        ocr_text = _extract_text_from_pdf_with_ocr(pdf_path)
        if (not primary_text and ocr_text) or len(ocr_text) > len(primary_text) + 80:
            return ocr_text

    return primary_text


def extract_metadata(text: str) -> Dict:
    """提取元数据（标题、作者等）"""
    lines = text.split("\n")
    metadata = extract_title_and_authors(lines)
    metadata["abstract"] = extract_abstract(text)
    return metadata


def extract_sections(text: str) -> Dict[str, str]:
    """提取章节内容"""
    sections = {}

    for section_name, pattern in SECTION_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start = match.end()
            next_section = None
            for other_name, other_pattern in SECTION_PATTERNS.items():
                if other_name != section_name:
                    other_match = re.search(other_pattern, text[start:], re.IGNORECASE)
                    if other_match:
                        if next_section is None or other_match.start() < next_section:
                            next_section = other_match.start()

            if next_section:
                sections[section_name] = text[start:start + next_section].strip()
            else:
                sections[section_name] = text[start:].strip()

    return sections


def score_direction_confidence(match_count: int, keyword_count: int) -> float:
    """Convert keyword coverage into a conservative single-PDF confidence score."""
    if match_count < 2 or keyword_count <= 0:
        return 0.0

    coverage = match_count / keyword_count
    return round(min(0.70, 0.45 + coverage * 0.25), 4)


def infer_research_directions(text: str) -> List[Dict]:
    """推断研究方向"""
    text_lower = text.lower()
    direction_map: Dict[str, Dict[str, Any]] = {}

    for area, keywords in RESEARCH_AREA_KEYWORDS.items():
        match_count = sum(1 for kw in keywords if kw in text_lower)
        if match_count >= 2:
            confidence = score_direction_confidence(match_count, len(keywords))
            if confidence > 0:
                direction_map[area] = {"name": area, "confidence": confidence}

    embedding_service = _get_embedding_service()
    semantic_text = text[:4000].strip()
    if embedding_service and semantic_text:
        try:
            text_embedding = embedding_service.embed_text(semantic_text)
            prototype_names = list(SEMANTIC_DIRECTION_PROTOTYPES.keys())
            prototype_embeddings = embedding_service.embed_batch(
                [SEMANTIC_DIRECTION_PROTOTYPES[name] for name in prototype_names]
            )

            for area, prototype_embedding in zip(prototype_names, prototype_embeddings):
                similarity = embedding_service.cosine_similarity(text_embedding, prototype_embedding)
                if similarity < SEMANTIC_DIRECTION_MIN_SIMILARITY:
                    continue

                confidence = score_semantic_direction_confidence(similarity)
                current = direction_map.get(area)
                if current is None or confidence > float(current.get("confidence", 0.0)):
                    direction_map[area] = {"name": area, "confidence": confidence}
        except Exception as exc:
            print(f"Semantic PDF direction inference failed: {exc}")

    directions = list(direction_map.values())
    directions.sort(key=lambda x: x["confidence"], reverse=True)
    return directions[:5]


def infer_methodology_preferences(text: str, sections: Dict[str, str]) -> Dict[str, bool]:
    """Infer cold-start methodology preferences from the extracted text."""
    method_text = (sections.get("method", "") + "\n" + sections.get("results", "")).lower()
    full_text = text.lower()
    return {
        "preference_data_driven_over_theory": any(
            keyword in method_text or keyword in full_text
            for keyword in ("dataset", "data-driven", "empirical", "experiment", "benchmark")
        ),
        "preference_systematic_work_over_incremental": any(
            keyword in method_text or keyword in full_text
            for keyword in ("framework", "system", "pipeline", "benchmark", "infrastructure", "platform")
        ),
        "preference_open_source_code": any(
            keyword in full_text
            for keyword in ("github", "open source", "code available", "code release")
        ),
        "preference_bio_science_application": any(
            keyword in full_text
            for keyword in ("bio", "protein", "molecular", "genomics", "computational biology", "scientific")
        ),
    }


def infer_topics(text: str, directions: List[Dict[str, Any]]) -> List[str]:
    """Extract a small set of explicit topic phrases for profile bootstrapping."""
    text_lower = text.lower()
    topics = []
    for pattern in TOPIC_PATTERNS:
        if pattern in text_lower and pattern not in topics:
            topics.append(pattern)
    for direction in directions:
        normalized = direction["name"].lower()
        if normalized not in topics:
            topics.append(normalized)
    return topics[:8]


def parse_pdf(pdf_path: str) -> Dict:
    """解析 PDF"""
    text = extract_text_from_pdf(pdf_path)
    metadata = extract_metadata(text)
    sections = extract_sections(text)
    directions = infer_research_directions(text)
    methodology_preferences = infer_methodology_preferences(text, sections)
    inferred_topics = infer_topics(text, directions)

    return {
        **metadata,
        "sections": sections,
        "inferred_directions": directions,
        "methodology_preferences": methodology_preferences,
        "inferred_topics": inferred_topics,
        "full_text": text
    }


def parse_paper_for_coldstart(pdf_path: str) -> Dict:
    """为冷启动解析论文"""
    result = parse_pdf(pdf_path)

    return {
        "research_directions": result["inferred_directions"],
        "methodology_preferences": result["methodology_preferences"],
        "inferred_topics": result.get("inferred_topics", []),
        "title": result["title"],
        "authors": result["authors"],
        "abstract": result["abstract"],
        "full_text": result["full_text"],
    }


def emit_json(data: Dict[str, Any]) -> None:
    """Print JSON without crashing on Windows terminals with GBK encoding."""
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(payload)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(payload.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        result = parse_paper_for_coldstart(pdf_path)
        emit_json(result)
    else:
        print("Usage: python parse_pdf.py <pdf_path>")
