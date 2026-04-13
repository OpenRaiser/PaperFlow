#!/usr/bin/env python3
"""
Reading Agent - 精读报告代理

职责：为用户选中的论文生成精读报告，创建飞书文档。
报告包含：
- 标题、作者、机构
- 核心问题（解决了什么）
- 方法（怎么做）
- 贡献（创新点）
- 实验（效果如何）
- 个人思考（值得读吗）
"""

import sys
import os
import json
import re
import tempfile
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from urllib.parse import urljoin

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 使用 importlib 导入带连字符的模块
import importlib

# 飞书报告器
feishu_reporter = importlib.import_module("skills.feishu-reporter.scripts.feishu_reporter")
create_doc = feishu_reporter.create_doc
send_text = feishu_reporter.send_text
get_drive_meta = getattr(feishu_reporter, "get_drive_meta", None)

# 数据库操作
db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
get_profile = db_ops.get_profile
log_behavior = db_ops.log_behavior


PDF_DOWNLOAD_TIMEOUT = float(os.environ.get("READING_REPORT_PDF_TIMEOUT", "60"))
ARXIV_DETAIL_TIMEOUT = float(os.environ.get("READING_REPORT_ARXIV_TIMEOUT", "12"))
MAX_ABSTRACT_CHARS = int(os.environ.get("READING_REPORT_ABSTRACT_CHARS", "1200"))
MAX_SECTION_CHARS = int(os.environ.get("READING_REPORT_SECTION_CHARS", "1800"))
DEFAULT_REQUEST_HEADERS = {"User-Agent": "SciTaste/0.1 ReadingAgent"}

CONTRIBUTION_CUES = (
    "we propose",
    "we present",
    "we introduce",
    "we develop",
    "we build",
    "we study",
    "this paper",
    "our approach",
    "our framework",
    "our method",
)
RESULT_CUES = (
    "outperform",
    "improve",
    "achieve",
    "demonstrate",
    "show that",
    "results show",
    "state-of-the-art",
    "sota",
    "gain",
    "better than",
)
LIMITATION_CUES = (
    "limitation",
    "limitations",
    "future work",
    "however",
    "remain",
    "remaining",
    "challenge",
    "beyond the scope",
)

DIRECTION_LABELS = {
    "gui-agent": "GUI Agent",
    "multimodal-reasoning": "多模态推理",
    "vision": "视觉",
    "language": "语言",
    "machine-learning": "机器学习",
    "deep-learning": "深度学习",
    "reinforcement-learning": "强化学习",
    "reasoning": "推理",
    "agent": "智能体",
    "optimization": "优化",
    "retrieval": "检索",
    "generation": "生成",
    "data-native": "数据原生",
    "bio-molecular": "生物分子",
    "science-discovery": "科学发现",
}


def extract_doc_url(doc_info: Dict[str, Any]) -> Optional[str]:
    """Best-effort extract the document URL from different Feishu response shapes."""
    if not isinstance(doc_info, dict):
        return None

    def _valid_url(candidate: Any) -> Optional[str]:
        text = str(candidate or "").strip()
        if text.startswith("http://") or text.startswith("https://"):
            return text
        return None

    for candidate in (doc_info.get("url"), doc_info.get("doc_url"), doc_info.get("link")):
        valid = _valid_url(candidate)
        if valid:
            return valid

    data = doc_info.get("data")
    if isinstance(data, dict):
        for candidate in (data.get("url"), data.get("doc_url"), data.get("link")):
            valid = _valid_url(candidate)
            if valid:
                return valid

        document = data.get("document")
        if isinstance(document, dict):
            for candidate in (document.get("url"), document.get("doc_url"), document.get("link")):
                valid = _valid_url(candidate)
                if valid:
                    return valid

    return None


def extract_doc_token(doc_info: Dict[str, Any]) -> Optional[str]:
    """Best-effort extract the document token from different Feishu response shapes."""
    if not isinstance(doc_info, dict):
        return None

    for candidate in (doc_info.get("obj_token"), doc_info.get("document_id"), doc_info.get("token")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    data = doc_info.get("data")
    if isinstance(data, dict):
        for candidate in (data.get("obj_token"), data.get("document_id"), data.get("token")):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()

        document = data.get("document")
        if isinstance(document, dict):
            for candidate in (
                document.get("obj_token"),
                document.get("document_id"),
                document.get("token"),
            ):
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()

    return None


def _load_arxiv_fetcher():
    return importlib.import_module("skills.arxiv-fetcher.scripts.fetch_arxiv")


def _load_pdf_parser():
    return importlib.import_module("skills.pdf-parser.scripts.parse_pdf")


def _load_llm_parser():
    try:
        return importlib.import_module("agents.master-coordinator.scripts.llm_parser")
    except Exception:
        return importlib.import_module("agents.master_coordinator.main").llm_parser


def _parse_jsonish_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not value:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return [text]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [str(parsed).strip()] if parsed else []
    return [str(value).strip()]


def _clean_text(text: Any) -> str:
    normalized = str(text or "")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    return normalized.strip()


def _truncate_text(text: Any, max_chars: int) -> str:
    normalized = _clean_text(text)
    if len(normalized) <= max_chars:
        return normalized
    clipped = normalized[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:") or normalized[: max_chars - 1]
    return f"{clipped}…"


def _split_sentences(text: Any) -> List[str]:
    normalized = _clean_text(text)
    if not normalized:
        return []

    parts = re.split(r"(?<=[。！？!?\.])\s+|(?<=;)\s+", normalized)
    sentences: List[str] = []
    for part in parts:
        sentence = re.sub(r"\s+", " ", part).strip()
        if len(sentence) >= 12:
            sentences.append(sentence)
    return sentences


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _unique_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(normalized)
    return ordered


def _append_analysis_note(base: Any, extra: Any) -> str:
    base_text = _clean_text(base)
    extra_text = _clean_text(extra)
    if not base_text:
        return extra_text
    if not extra_text:
        return base_text
    if extra_text in base_text:
        return base_text
    if base_text in extra_text:
        return extra_text
    return f"{base_text} {extra_text}"


def _describe_pdf_fallback(pdf_error: Optional[str]) -> str:
    lowered = _clean_text(pdf_error).lower()
    if not lowered:
        return "未能拿到 PDF 全文，本次报告改为按模板基于摘要和元数据生成；方法与实验细节建议回原文核对。"
    if "403" in lowered or "forbidden" in lowered:
        reason = "源站拒绝了 PDF 访问"
    elif "timed out" in lowered or "timeout" in lowered:
        reason = "PDF 抓取超时"
    elif "ssl" in lowered or "eof" in lowered or "connection" in lowered:
        reason = "PDF 抓取时网络连接不稳定"
    elif "content-type" in lowered or "did not return a pdf" in lowered:
        reason = "源站没有直接返回 PDF 文件"
    else:
        reason = "PDF 抓取或解析失败"
    return f"{reason}，本次报告改为按模板基于摘要和元数据生成；方法与实验细节建议回原文核对。"


def _recommendation_score(label: str) -> int:
    normalized = _clean_text(label)
    mapping = {
        "强烈推荐": 5,
        "推荐阅读": 4,
        "值得快速浏览": 3,
        "按需阅读": 2,
    }
    return mapping.get(normalized, 3)


def _format_markdown_link(label: str, url: str) -> str:
    clean_url = _clean_text(url)
    if clean_url.startswith("http://") or clean_url.startswith("https://"):
        return clean_url
    return clean_url or "暂无"


def _get_first_url(paper: Dict[str, Any], *keys: str) -> str:
    metadata = paper.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    for key in keys:
        for container in (paper, metadata):
            candidate = _clean_text(container.get(key))
            if candidate.startswith("http://") or candidate.startswith("https://"):
                return candidate
    return ""


def _get_direct_pdf_url(paper: Dict[str, Any]) -> str:
    candidates = [
        paper.get("pdf_url"),
        paper.get("url"),
        paper.get("paper_url"),
        paper.get("doi_url"),
        paper.get("openreview_url"),
        (paper.get("metadata") or {}).get("pdf_url"),
        (paper.get("metadata") or {}).get("url"),
        (paper.get("metadata") or {}).get("link"),
        (paper.get("metadata") or {}).get("paper_url"),
        (paper.get("metadata") or {}).get("doi_url"),
        (paper.get("metadata") or {}).get("openreview_url"),
    ]

    for candidate in candidates:
        text = _clean_text(candidate)
        if _looks_like_pdf_url(text):
            return text

    arxiv_id = _clean_text(paper.get("arxiv_id"))
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    return ""


def _build_resource_items(paper: Dict[str, Any]) -> List[Tuple[str, str]]:
    code_url = _get_first_url(paper, "code_url", "github_url", "repo_url", "repository_url")
    dataset_url = _get_first_url(paper, "dataset_url", "data_url")
    project_url = _get_first_url(paper, "project_url", "paper_url", "openreview_url", "url")
    pdf_url = _get_direct_pdf_url(paper)

    items: List[Tuple[str, str]] = []
    items.append(("代码", _format_markdown_link("代码链接", code_url) if code_url else "暂未发现公开链接"))
    items.append(("数据", _format_markdown_link("数据链接", dataset_url) if dataset_url else "暂未发现公开链接"))
    items.append(("项目主页", _format_markdown_link("项目主页", project_url) if project_url else "暂未发现公开链接"))
    items.append(("原文 PDF", _format_markdown_link("PDF", pdf_url) if pdf_url else "暂未发现公开链接"))

    arxiv_id = _clean_text(paper.get("arxiv_id"))
    if arxiv_id:
        items.append(("arXiv", _format_markdown_link(arxiv_id, f"https://arxiv.org/abs/{arxiv_id}")))

    doi = _clean_text(paper.get("doi"))
    if doi:
        items.append(("DOI", _format_markdown_link(doi, f"https://doi.org/{doi}")))

    return items


def _build_recommendation_reason(payload: Dict[str, Any]) -> str:
    reasons: List[str] = []
    relevance_points = payload.get("relevance_points") or []
    reading_focus = payload.get("reading_focus") or []
    analysis_source = _clean_text(payload.get("analysis_source"))

    if relevance_points:
        reasons.append(_clean_text(relevance_points[0]))
    if analysis_source == "pdf":
        reasons.append("这次已拿到 PDF 全文结构，方法和结果信息相对更完整。")
    elif _clean_text(payload.get("analysis_note")):
        reasons.append(_clean_text(payload.get("analysis_note")))
    if reading_focus:
        reasons.append(f"建议优先看：{_clean_text(reading_focus[0])}")

    if not reasons:
        reasons.append("当前推荐主要基于题目、摘要、元数据和你的画像匹配结果。")
    return reasons[0]


def _looks_like_placeholder_title(title: str) -> bool:
    normalized = _clean_text(title).lower()
    if not normalized:
        return True
    return bool(re.fullmatch(r"(paper|test paper)\s*\d*", normalized))


def _format_direction_label(direction: str) -> str:
    normalized = str(direction or "").strip()
    if not normalized:
        return "当前方向"
    lowered = normalized.lower()
    if lowered in DIRECTION_LABELS:
        return DIRECTION_LABELS[lowered]
    if any("\u4e00" <= ch <= "\u9fff" for ch in normalized):
        return normalized
    return (
        normalized.replace("-", " ").replace("_", " ").title().replace("Gui", "GUI").replace("Ai", "AI")
    )


def _format_authors(authors: Any) -> str:
    names = _parse_jsonish_list(authors)
    return ", ".join(names) if names else "未知"


def _normalize_paper(paper: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(paper or {})
    normalized["authors"] = _parse_jsonish_list(normalized.get("authors"))

    metadata = normalized.get("metadata")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    normalized["metadata"] = metadata

    for field in (
        "title",
        "abstract",
        "institution",
        "venue",
        "publish_date",
        "arxiv_id",
        "doi",
        "pdf_url",
        "url",
        "paper_url",
        "doi_url",
        "openreview_url",
        "journal",
        "source",
        "category",
    ):
        if field in normalized:
            normalized[field] = _clean_text(normalized.get(field))

    score = normalized.get("score")
    try:
        normalized["score"] = float(score)
    except (TypeError, ValueError):
        normalized["score"] = 0.0

    return normalized
def format_created_docs_summary(created_docs: List[Dict[str, Any]]) -> str:
    """Format the reading-report completion message with direct document links."""
    lines = [
        "=" * 60,
        f"Reading reports created ({len(created_docs)})",
        "=" * 60,
        "",
    ]

    for index, doc in enumerate(created_docs, start=1):
        title = doc.get("paper", {}).get("title") or doc.get("title", "Unknown")
        lines.append(f"{index:02d}. {title[:60]}")
        if doc.get("url"):
            lines.append(f"    {doc['url']}")
        elif doc.get("doc_token"):
            lines.append(f"    doc_token: {doc['doc_token']}")
        lines.append("")

    lines.append("Open the links above to start reading.")
    return "\n".join(lines)


def _merge_paper_details(base: Dict[str, Any], detail: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    detail = _normalize_paper(detail)

    for key in ("arxiv_id", "doi", "pdf_url", "publish_date", "venue", "institution"):
        if not _clean_text(merged.get(key)):
            merged[key] = detail.get(key, merged.get(key))

    if _looks_like_placeholder_title(str(merged.get("title", ""))) and detail.get("title"):
        merged["title"] = detail["title"]

    if not merged.get("authors"):
        merged["authors"] = detail.get("authors", [])

    if not _clean_text(merged.get("abstract")) and detail.get("abstract"):
        merged["abstract"] = detail["abstract"]

    existing_metadata = dict(merged.get("metadata") or {})
    detail_metadata = dict(detail.get("metadata") or {})
    merged["metadata"] = {**detail_metadata, **existing_metadata}

    return merged


def _looks_like_pdf_url(candidate: Any) -> bool:
    text = _clean_text(candidate).lower()
    if not (text.startswith("http://") or text.startswith("https://")):
        return False
    return (
        ".pdf" in text
        or "/pdf?" in text
        or "/pdf/" in text
        or "arxiv.org/pdf/" in text
        or "openreview.net/pdf" in text
    )


def _collect_source_page_urls(paper: Dict[str, Any]) -> List[str]:
    metadata = paper.get("metadata") or {}
    candidates = [
        paper.get("paper_url"),
        paper.get("url"),
        paper.get("doi_url"),
        paper.get("openreview_url"),
        metadata.get("paper_url"),
        metadata.get("url"),
        metadata.get("link"),
        metadata.get("doi_url"),
        metadata.get("openreview_url"),
    ]

    urls: List[str] = []
    for candidate in candidates:
        text = _clean_text(candidate)
        if not text.startswith("http://") and not text.startswith("https://"):
            continue
        if _looks_like_pdf_url(text):
            continue
        if text not in urls:
            urls.append(text)
    return urls


def _resolve_pdf_url_from_source_page(source_url: str) -> str:
    response = requests.get(
        source_url,
        timeout=PDF_DOWNLOAD_TIMEOUT,
        headers=DEFAULT_REQUEST_HEADERS,
        allow_redirects=True,
    )
    response.raise_for_status()

    final_url = _clean_text(response.url) or _clean_text(source_url)
    content_type = str(response.headers.get("Content-Type") or "").lower()
    if _looks_like_pdf_url(final_url) or "application/pdf" in content_type:
        return final_url

    html = response.text or ""
    patterns = (
        r"""<meta[^>]+(?:name|property)=["']citation_pdf_url["'][^>]+content=["']([^"']+)["']""",
        r"""<meta[^>]+content=["']([^"']+)["'][^>]+(?:name|property)=["']citation_pdf_url["']""",
        r"""<a[^>]+href=["']([^"']+\.pdf(?:\?[^"']*)?)["']""",
        r"""<a[^>]+href=["']([^"']*downloadPdf[^"']*)["']""",
    )

    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if not match:
            continue
        candidate = urljoin(final_url, match.group(1).strip())
        if candidate:
            return candidate

    return ""


def _extract_pdf_url(paper: Dict[str, Any]) -> str:
    candidates = [
        paper.get("pdf_url"),
        paper.get("url"),
        paper.get("paper_url"),
        paper.get("doi_url"),
        paper.get("openreview_url"),
        (paper.get("metadata") or {}).get("pdf_url"),
        (paper.get("metadata") or {}).get("url"),
        (paper.get("metadata") or {}).get("link"),
        (paper.get("metadata") or {}).get("paper_url"),
        (paper.get("metadata") or {}).get("doi_url"),
        (paper.get("metadata") or {}).get("openreview_url"),
    ]

    for candidate in candidates:
        text = _clean_text(candidate)
        if _looks_like_pdf_url(text):
            return text

    for source_url in _collect_source_page_urls(paper):
        try:
            resolved = _resolve_pdf_url_from_source_page(source_url)
        except Exception as exc:
            print(f"  Failed to resolve PDF from source page {source_url[:120]}: {exc}")
            continue
        if _clean_text(resolved):
            return resolved

    arxiv_id = _clean_text(paper.get("arxiv_id"))
    if arxiv_id:
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    return ""


def _get_pdf_enrichment_mode() -> str:
    """Return PDF enrichment mode: smart, always, or off."""
    mode = os.environ.get("READING_REPORT_PDF_MODE", "always").strip().lower()
    return mode or "smart"


def _paper_has_sufficient_metadata_for_report(paper: Dict[str, Any]) -> bool:
    """Whether the existing paper payload is already enough for a solid abstract-based report."""
    return bool(
        _clean_text(paper.get("abstract"))
        and _parse_jsonish_list(paper.get("authors"))
        and not _looks_like_placeholder_title(_clean_text(paper.get("title")))
    )


def _is_arxiv_pdf_url(pdf_url: str) -> bool:
    return "arxiv.org/" in _clean_text(pdf_url).lower()


def _should_attempt_pdf_enrichment(
    paper: Dict[str, Any],
    pdf_url: str,
    *,
    detail_fetch_failed: bool = False,
) -> Tuple[bool, str]:
    """Decide whether to download/parse the PDF for this report."""
    if not _clean_text(pdf_url):
        return False, "no_pdf_url"

    mode = _get_pdf_enrichment_mode()
    if mode in {"off", "false", "0", "disabled", "none"}:
        return False, "pdf_mode_disabled"

    if mode in {"always", "on", "true", "1", "force"}:
        return True, "forced"

    if not _paper_has_sufficient_metadata_for_report(paper):
        return True, "metadata_incomplete"

    if detail_fetch_failed and _is_arxiv_pdf_url(pdf_url):
        return False, "arxiv_detail_failed"

    return False, "metadata_already_sufficient"


def _extract_source_links(paper: Dict[str, Any]) -> List[Tuple[str, str]]:
    links: List[Tuple[str, str]] = []

    arxiv_id = _clean_text(paper.get("arxiv_id"))
    if arxiv_id:
        links.append(("arXiv", f"https://arxiv.org/abs/{arxiv_id}"))

    pdf_url = _extract_pdf_url(paper)
    if pdf_url:
        links.append(("PDF", pdf_url))

    doi = _clean_text(paper.get("doi"))
    if doi:
        links.append(("DOI", f"https://doi.org/{doi}"))

    paper_url = _clean_text(
        paper.get("paper_url")
        or paper.get("url")
        or (paper.get("metadata") or {}).get("paper_url")
        or (paper.get("metadata") or {}).get("url")
        or (paper.get("metadata") or {}).get("link")
    )
    if paper_url and all(paper_url != url for _, url in links):
        links.append(("原始链接", paper_url))

    return links


def _download_pdf(pdf_url: str, title: str) -> str:
    response = requests.get(
        pdf_url,
        timeout=PDF_DOWNLOAD_TIMEOUT,
        headers=DEFAULT_REQUEST_HEADERS,
    )
    response.raise_for_status()
    content_type = str(response.headers.get("Content-Type") or "").lower()
    if "application/pdf" not in content_type and not response.content.startswith(b"%PDF"):
        raise ValueError(
            f"Resolved URL did not return a PDF (content-type={content_type or 'unknown'})"
        )

    safe_prefix = re.sub(r"[^A-Za-z0-9]+", "_", title or "paper").strip("_")[:40] or "paper"
    with tempfile.NamedTemporaryFile(prefix=f"{safe_prefix}_", suffix=".pdf", delete=False) as temp_file:
        temp_file.write(response.content)
        return temp_file.name


def _parse_pdf_for_report(pdf_path: str) -> Dict[str, Any]:
    pdf_parser = _load_pdf_parser()
    text = pdf_parser.extract_text_from_pdf(pdf_path)
    metadata = pdf_parser.extract_metadata(text)
    sections = pdf_parser.extract_sections(text)
    return {
        **metadata,
        "sections": sections,
        "full_text": text,
    }


def enrich_paper_for_reading_report(paper: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[str]]:
    enriched = _normalize_paper(paper)
    pdf_error: Optional[str] = None
    parsed_pdf: Optional[Dict[str, Any]] = None
    detail_fetch_failed = False

    arxiv_id = _clean_text(enriched.get("arxiv_id"))
    if arxiv_id:
        try:
            fetcher = _load_arxiv_fetcher()
            try:
                detail = fetcher.get_paper_detail(arxiv_id, timeout=ARXIV_DETAIL_TIMEOUT)
            except TypeError:
                detail = fetcher.get_paper_detail(arxiv_id)
        except Exception as exc:
            detail = None
            detail_fetch_failed = True
            print(f"Failed to fetch arXiv detail for {arxiv_id}: {exc}")
        if detail:
            enriched = _merge_paper_details(enriched, detail)

    pdf_url = _extract_pdf_url(enriched)
    if pdf_url:
        enriched["pdf_url"] = pdf_url

    temp_pdf_path: Optional[str] = None
    should_parse_pdf, skip_reason = _should_attempt_pdf_enrichment(
        enriched,
        pdf_url,
        detail_fetch_failed=detail_fetch_failed,
    )
    if pdf_url and not should_parse_pdf:
        print(f"  Skipping PDF enrichment ({skip_reason})")

    if pdf_url and should_parse_pdf:
        try:
            print(f"  Downloading PDF for enrichment: {pdf_url[:120]}")
            temp_pdf_path = _download_pdf(pdf_url, enriched.get("title", "paper"))
            parsed_pdf = _parse_pdf_for_report(temp_pdf_path)
            print("  PDF enrichment parsed successfully")
        except Exception as exc:
            pdf_error = str(exc)
            print(f"PDF enrichment failed for {enriched.get('title', 'Unknown')}: {exc}")
        finally:
            if temp_pdf_path:
                try:
                    Path(temp_pdf_path).unlink(missing_ok=True)
                except OSError:
                    pass

    if parsed_pdf:
        if _looks_like_placeholder_title(enriched.get("title", "")) and _clean_text(parsed_pdf.get("title")):
            enriched["title"] = _clean_text(parsed_pdf.get("title"))
        if not _clean_text(enriched.get("abstract")) and _clean_text(parsed_pdf.get("abstract")):
            enriched["abstract"] = _clean_text(parsed_pdf.get("abstract"))
        if not enriched.get("authors"):
            enriched["authors"] = _parse_jsonish_list(parsed_pdf.get("authors"))

    return enriched, parsed_pdf, pdf_error


def _pick_sentences(text: str, *, limit: int, cues: Tuple[str, ...] = ()) -> List[str]:
    sentences = _split_sentences(text)
    if not sentences:
        return []

    ranked: List[str] = []
    if cues:
        lowered_sentences = [(sentence, sentence.lower()) for sentence in sentences]
        for sentence, lowered in lowered_sentences:
            if any(cue in lowered for cue in cues):
                ranked.append(sentence)

    if len(ranked) < limit:
        ranked.extend(sentences)

    unique_ranked = _unique_preserve_order(ranked)
    return [_truncate_text(sentence, 180) for sentence in unique_ranked[:limit]]


def _estimate_reading_minutes(parsed_pdf: Optional[Dict[str, Any]], abstract: str) -> int:
    word_count = 0
    if parsed_pdf:
        word_count = len(_clean_text(parsed_pdf.get("full_text")).split())
    if word_count <= 0:
        word_count = len(_clean_text(abstract).split()) * 4
    return max(5, min(20, round(max(word_count, 600) / 220)))


def _recommendation_label(paper: Dict[str, Any]) -> str:
    category = _clean_text(paper.get("category")).lower()
    score = float(paper.get("score") or 0.0)

    if category == "must_read" or score >= 0.85:
        return "强烈推荐"
    if category == "high_relevant" or score >= 0.70:
        return "推荐阅读"
    if category == "maybe_interested" or score >= 0.50:
        return "值得快速浏览"
    return "按需阅读"


def _build_relevance_points(
    paper: Dict[str, Any],
    user_profile: Dict[str, Any],
    combined_text: str,
    parsed_pdf: Optional[Dict[str, Any]],
) -> List[str]:
    text_lower = combined_text.lower()
    points: List[str] = []

    core_directions = user_profile.get("core_directions", {}) or {}
    sorted_directions = sorted(core_directions.items(), key=lambda item: float(item[1]), reverse=True)

    matched: List[str] = []
    for direction, weight in sorted_directions[:3]:
        tokens = str(direction).lower().replace("-", " ").replace("_", " ").split()
        if str(direction).lower() in text_lower or any(token in text_lower for token in tokens if len(token) >= 4):
            matched.append(f"{_format_direction_label(direction)}（权重 {float(weight):.2f}）")

    if matched:
        points.append(f"这篇论文和你当前画像里的方向有直接重合：{', '.join(matched)}。")
    elif sorted_directions:
        points.append(f"它不一定和你当前最核心的 {_format_direction_label(sorted_directions[0][0])} 完全同题，但方法设计和评测组织值得借鉴。")
    else:
        points.append("你当前画像还在持续学习阶段，这篇论文适合作为新的兴趣锚点来判断后续是否继续追踪。")

    preferences = user_profile.get("methodology_preferences", {}) or {}
    if preferences.get("preference_data_driven_over_theory"):
        points.append("从方法论上看，它偏向数据驱动或实验验证路径，和你当前偏好比较一致。")
    if preferences.get("preference_systematic_work_over_incremental"):
        points.append("如果你更看重系统性工作，可以重点看它如何组织任务设定、实验协议和整体框架。")
    if preferences.get("preference_bio_science_application"):
        points.append("若你当前关注生物或科学应用，建议额外留意论文中的任务场景、数据来源和落地边界。")
    if parsed_pdf and parsed_pdf.get("sections", {}).get("results"):
        points.append("建议把精力放在 Results/Experiments 部分，判断提升是否真正来自核心方法而不是实验技巧。")

    score = float(paper.get("score") or 0.0)
    if score > 0:
        points.append(f"当前推荐分约为 {score:.2f}，系统判断它与画像存在一定相关性。")

    return _unique_preserve_order(points)[:4]
def _legacy_generate_reading_report(paper: Dict, user_profile: Dict) -> str:
    """
    生成精读报告

    Args:
        paper: 论文字典
        user_profile: 用户画像

    Returns:
        Markdown 格式的报告内容
    """
    title = paper.get("title", "Unknown Title")
    authors = paper.get("authors", [])
    arxiv_id = paper.get("arxiv_id", "")
    abstract = paper.get("abstract", "")

    # 构建报告
    lines = []

    # 标题
    lines.append(f"# {title}")
    lines.append("")

    # 元信息
    lines.append("## 📋 元信息")
    lines.append("")
    lines.append(f"- **arXiv ID**: `{arxiv_id}`")
    lines.append(f"- **作者**: {', '.join(authors) if isinstance(authors, list) else authors}")
    lines.append(f"- **机构**: {paper.get('institution', 'Unknown')}")
    lines.append(f"- **推送日期**: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")

    # 摘要
    lines.append("## 📝 摘要")
    lines.append("")
    if abstract:
        # 简单分段
        abstract_lines = abstract.strip().split('\n')
        for line in abstract_lines:
            lines.append(f"> {line.strip()}")
    else:
        lines.append("> 摘要暂未获取")
    lines.append("")

    # 核心问题
    lines.append("## 🎯 核心问题")
    lines.append("")
    lines.append("**这篇论文试图解决什么问题？**")
    lines.append("")
    lines.append("<!-- 待填充：论文的核心问题是什么？现有方法的局限性？ -->")
    lines.append("")

    # 方法
    lines.append("## 🔧 方法")
    lines.append("")
    lines.append("**作者提出了什么方法？**")
    lines.append("")
    lines.append("<!-- 待填充：核心技术、模型架构、关键创新 -->")
    lines.append("")

    # 贡献
    lines.append("## ✨ 主要贡献")
    lines.append("")
    lines.append("<!-- 待填充：1. 2. 3. 列出主要贡献 -->")
    lines.append("")

    # 实验
    lines.append("## 📊 实验")
    lines.append("")
    lines.append("**实验设置和主要结果**")
    lines.append("")
    lines.append("<!-- 待填充：数据集、baseline、主要指标对比 -->")
    lines.append("")

    # 与用户画像的关联
    lines.append("## 🔗 与你的研究方向关联")
    lines.append("")
    core_directions = user_profile.get("core_directions", {})
    if core_directions:
        lines.append("匹配的研究方向：")
        for direction, weight in sorted(core_directions.items(), key=lambda x: -x[1])[:3]:
            lines.append(f"- {direction} (权重：{weight:.2f})")
    else:
        lines.append("（冷启动阶段，继续探索中...）")
    lines.append("")

    # 阅读建议
    lines.append("## 💡 阅读建议")
    lines.append("")
    lines.append("**值得读吗？**")
    lines.append("")
    score = paper.get("score", 0.5)
    if score >= 0.75:
        lines.append("✅ **强烈推荐** - 高度匹配你的研究方向")
    elif score >= 0.5:
        lines.append("🟡 **建议浏览** - 可能对你有启发")
    else:
        lines.append("⚪ **可选读** - 边缘相关，有时间再看")
    lines.append("")

    # 笔记区
    lines.append("## 📓 我的笔记")
    lines.append("")
    lines.append("<!-- 在这里记录你的思考和收获 -->")
    lines.append("")
    lines.append("- 这篇文章的核心 insight 是什么？")
    lines.append("- 对我的研究有什么启发？")
    lines.append("- 可以复现或扩展吗？")
    lines.append("")

    # 分隔线
    lines.append("---")
    lines.append("")
    lines.append(f"*报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return "\n".join(lines)


def format_short_summary(paper: Dict) -> str:
    """
    生成简短摘要（用于飞书消息）

    Args:
        paper: 论文字典

    Returns:
        简短摘要文本
    """
    title = paper.get("title", "Unknown")[:60]
    arxiv_id = paper.get("arxiv_id", "")

    lines = []
    lines.append("=" * 60)
    lines.append(f"📄 精读报告已生成")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"**{title}**")
    lines.append("")
    lines.append(f"arXiv: `{arxiv_id}`")
    lines.append("")
    lines.append("报告包含：")
    lines.append("  • 核心问题")
    lines.append("  • 方法")
    lines.append("  • 贡献")
    lines.append("  • 实验")
    lines.append("  • 阅读建议")
    lines.append("")
    lines.append("点击文档链接查看完整报告 👇")

    return "\n".join(lines)


def _infer_section_from_abstract(abstract: str, section_type: str) -> str:
    """
    从摘要中推断特定部分的内容

    Args:
        abstract: 论文摘要
        section_type: 要推断的部分类型 (background, method, results)

    Returns:
        推断出的部分内容
    """
    if not abstract:
        return ""

    sentences = _split_sentences(abstract)
    if not sentences:
        return ""

    # 根据部分类型选择不同的线索词
    section_cues = {
        "background": ("we address", "we tackle", "challenge", "problem", "limitation", "however", "despite", "existing", "prior work"),
        "method": ("we propose", "we present", "we introduce", "we develop", "our approach", "our method", "framework", "model", "architecture"),
        "results": ("outperform", "improve", "achieve", "demonstrate", "results show", "experimental", "evaluation", "gain", "better than", "superior"),
    }

    cues = section_cues.get(section_type, ())

    # 优先选择包含线索词的句子
    matched = []
    for sentence in sentences:
        lowered = sentence.lower()
        if any(cue in lowered for cue in cues):
            matched.append(sentence)

    if matched:
        return " ".join(matched[:2])

    # 如果没有匹配的，根据位置返回
    if section_type == "background":
        return " ".join(sentences[:2]) if len(sentences) >= 2 else sentences[0] if sentences else ""
    elif section_type == "results":
        return " ".join(sentences[-2:]) if len(sentences) >= 2 else sentences[-1] if sentences else ""
    else:  # method
        mid = len(sentences) // 2
        return " ".join(sentences[mid:mid+2]) if len(sentences) > 2 else sentences[mid] if sentences else ""


def build_heuristic_report_payload(
    paper: Dict[str, Any],
    user_profile: Dict[str, Any],
    parsed_pdf: Optional[Dict[str, Any]] = None,
    pdf_error: Optional[str] = None,
) -> Dict[str, Any]:
    sections = dict((parsed_pdf or {}).get("sections") or {})
    abstract = _truncate_text(
        _first_non_empty((parsed_pdf or {}).get("abstract"), paper.get("abstract")),
        MAX_ABSTRACT_CHARS,
    )
    introduction = _truncate_text(sections.get("introduction"), MAX_SECTION_CHARS)
    method = _truncate_text(sections.get("method"), MAX_SECTION_CHARS)
    results = _truncate_text(sections.get("results"), MAX_SECTION_CHARS)
    discussion = _truncate_text(sections.get("discussion"), MAX_SECTION_CHARS)
    conclusion = _truncate_text(sections.get("conclusion"), MAX_SECTION_CHARS)

    # 使用 PDF 解析的章节内容，或者从摘要推断
    bg_from_pdf = " ".join(_pick_sentences(introduction, limit=2)) if introduction else ""
    bg_from_abstract = _infer_section_from_abstract(abstract, "background")
    research_background = _first_non_empty(bg_from_pdf, bg_from_abstract)
    if not research_background:
        research_background = "建议先查看原文摘要和引言部分以了解研究背景。"

    method_from_pdf = " ".join(_pick_sentences(method, limit=2, cues=CONTRIBUTION_CUES)) if method else ""
    method_from_abstract = _infer_section_from_abstract(abstract, "method")
    core_method = _first_non_empty(method_from_pdf, method_from_abstract)
    if not core_method:
        core_method = "方法细节建议重点查看原文的 Method / Approach 部分。"

    results_from_pdf = " ".join(_pick_sentences(results, limit=2, cues=RESULT_CUES)) if results else ""
    results_from_abstract = _infer_section_from_abstract(abstract, "results")
    key_results = _first_non_empty(results_from_pdf, results_from_abstract)
    if not key_results:
        key_results = "实验结果和建议重点核对原文表格和主要指标。"

    summary_candidates = _pick_sentences(abstract, limit=1, cues=CONTRIBUTION_CUES + RESULT_CUES)
    if not summary_candidates:
        summary_candidates = _pick_sentences(introduction or abstract, limit=1)
    one_sentence_summary = summary_candidates[0] if summary_candidates else "本文的核心信息仍建议结合原文进一步核对。"

    main_contributions = _unique_preserve_order(
        _pick_sentences(abstract, limit=3, cues=CONTRIBUTION_CUES)
        + _pick_sentences(method, limit=2, cues=CONTRIBUTION_CUES)
        + _pick_sentences(results, limit=1, cues=RESULT_CUES)
    )[:3]
    if not main_contributions:
        main_contributions = [
            "论文给出了明确的问题定义和任务设定，适合作为领域入口文献来读。",
            "文中提供了可直接关注的方法主线，建议结合原文图表理解其模块关系。",
            "实验部分值得重点核对，以确认结论是否和方法创新真正对应。",
        ]

    limitations = _unique_preserve_order(
        _pick_sentences(conclusion, limit=2, cues=LIMITATION_CUES)
        + _pick_sentences(discussion, limit=2, cues=LIMITATION_CUES)
    )
    if not limitations:
        limitations = ["文中未明显展开局限性，阅读时建议重点核对数据覆盖范围、评测设置和泛化边界。"]
        if pdf_error:
            limitations.append("本次未成功抓取 PDF，方法与实验细节部分仍应以原文为准。")

    reading_focus = []
    if introduction:
        reading_focus.append("先看 Introduction，确认论文到底在补哪一块空白。")
    if method:
        reading_focus.append("再看 Method / Approach，把核心模块、训练目标和输入输出关系理清。")
    if results:
        reading_focus.append("重点看 Experiments / Results，确认提升来自哪里，以及 baseline 是否公平。")
    if conclusion or discussion:
        reading_focus.append("最后看 Conclusion / Discussion，判断作者自己如何定义边界与下一步。")
    if not reading_focus:
        reading_focus.append("当前建议先读摘要，再回到原文按图表和章节标题定位方法与实验细节。")

    combined_text = "\n".join(
        item for item in [paper.get("title"), abstract, introduction, method, results, conclusion, discussion] if item
    )

    analysis_note = (
        "本报告已结合 PDF 全文结构做自动提炼。"
        if parsed_pdf
        else "本报告当前基于摘要和元数据自动生成，方法与实验细节建议回到原文核对。"
    )
    if pdf_error:
        analysis_note = _append_analysis_note(analysis_note, _describe_pdf_fallback(pdf_error))

    return {
        "abstract": abstract,
        "one_sentence_summary": one_sentence_summary,
        "research_background": research_background,
        "core_method": core_method,
        "key_results": key_results,
        "main_contributions": main_contributions,
        "limitations": limitations[:3],
        "relevance_points": _build_relevance_points(paper, user_profile, combined_text, parsed_pdf),
        "reading_focus": _unique_preserve_order(reading_focus)[:4],
        "estimated_reading_minutes": _estimate_reading_minutes(parsed_pdf, abstract),
        "analysis_source": "pdf" if parsed_pdf else "abstract",
        "analysis_note": analysis_note,
        "recommendation_label": _recommendation_label(paper),
    }


def _normalize_string_list(value: Any, limit: int = 4) -> List[str]:
    if isinstance(value, str):
        candidates = re.split(r"\n+|[;；]+", value)
    elif isinstance(value, list):
        candidates = [str(item) for item in value]
    else:
        return []

    items: List[str] = []
    for candidate in candidates:
        cleaned = re.sub(r"^\s*[-*•\d\.\)\(]+\s*", "", str(candidate)).strip()
        if len(cleaned) >= 4:
            items.append(_truncate_text(cleaned, 180))
    return _unique_preserve_order(items)[:limit]


def _synthesize_report_with_llm(
    paper: Dict[str, Any],
    user_profile: Dict[str, Any],
    parsed_pdf: Optional[Dict[str, Any]],
    heuristic_payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    fallback_note = "生成式精读补充本次未返回，当前内容仍按精读模板基于已拿到的摘要、元数据和可用 PDF 片段生成。"

    try:
        llm_parser = _load_llm_parser()
    except Exception as exc:
        print(f"Unable to load llm parser for reading report: {exc}")
        return {"analysis_note": fallback_note}

    helper = getattr(llm_parser, "synthesize_reading_report_with_llm", None)
    if not callable(helper):
        return {"analysis_note": fallback_note}

    try:
        result = helper(
            paper=paper,
            user_profile=user_profile,
            parsed_pdf=parsed_pdf,
            heuristic_payload=heuristic_payload,
        )
        if isinstance(result, dict) and result:
            return result
        return {"analysis_note": fallback_note}
    except Exception as exc:
        print(f"LLM reading synthesis failed: {exc}")
        return {"analysis_note": fallback_note}


def _merge_report_payload(base: Dict[str, Any], llm_payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(llm_payload, dict):
        return base

    merged = dict(base)
    for key in ("one_sentence_summary", "research_background", "core_method", "key_results"):
        value = _clean_text(llm_payload.get(key))
        if value:
            merged[key] = value

    analysis_note = _clean_text(llm_payload.get("analysis_note"))
    if analysis_note:
        merged["analysis_note"] = _append_analysis_note(merged.get("analysis_note"), analysis_note)

    for key in ("main_contributions", "limitations", "relevance_points", "reading_focus"):
        values = _normalize_string_list(llm_payload.get(key))
        if values:
            merged[key] = values

    recommendation_label = _clean_text(llm_payload.get("recommendation_label"))
    if recommendation_label:
        merged["recommendation_label"] = recommendation_label

    return merged


def _resolve_doc_url_from_meta(doc_token: Optional[str]) -> Optional[str]:
    if not doc_token or not callable(get_drive_meta):
        return None

    try:
        meta = get_drive_meta(doc_token)
    except Exception as exc:
        print(f"Unable to fetch drive meta for doc {doc_token}: {exc}")
        return None

    if not isinstance(meta, dict):
        return None

    candidates = [meta.get("url"), meta.get("doc_url")]
    data = meta.get("data")
    if isinstance(data, dict):
        candidates.extend([data.get("url"), data.get("doc_url")])
        metas = data.get("metas")
        if isinstance(metas, list):
            for item in metas:
                if isinstance(item, dict):
                    candidates.extend([item.get("url"), item.get("doc_url")])

    for candidate in candidates:
        text = str(candidate or "").strip()
        if text.startswith("http://") or text.startswith("https://"):
            return text
    return None


def generate_reading_report(
    paper: Dict[str, Any],
    user_profile: Dict[str, Any],
    report_payload: Optional[Dict[str, Any]] = None,
) -> str:
    payload = report_payload or build_heuristic_report_payload(paper, user_profile)
    title = _clean_text(paper.get("title")) or "Untitled Paper"
    abstract = payload.get("abstract") or _clean_text(paper.get("abstract")) or "暂无摘要。"
    arxiv_id = _clean_text(paper.get("arxiv_id"))
    doi = _clean_text(paper.get("doi"))
    recommendation_label = payload.get("recommendation_label") or _recommendation_label(paper)
    recommendation_score = _recommendation_score(recommendation_label)
    recommendation_stars = "★" * recommendation_score + "☆" * (5 - recommendation_score)
    analysis_source_label = "PDF 全文 + 元数据" if payload.get("analysis_source") == "pdf" else "摘要 + 元数据"
    analysis_note = _clean_text(payload.get("analysis_note"))
    resource_items = _build_resource_items(paper)
    recommendation_reason = _build_recommendation_reason(payload)

    lines = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## 基本信息")
    lines.append("")
    lines.append(f"- 作者：{_format_authors(paper.get('authors'))}")
    lines.append(f"- 机构：{_clean_text(paper.get('institution')) or '未提供'}")
    lines.append(f"- 来源：{_clean_text(paper.get('venue') or paper.get('journal') or paper.get('source')) or '未知'}")
    lines.append(f"- 日期：{_clean_text(paper.get('publish_date')) or '未知'}")
    lines.append(f"- 推荐级别：**{recommendation_label}**")
    lines.append(f"- 预计阅读时间：约 {int(payload.get('estimated_reading_minutes') or 8)} 分钟")
    lines.append(f"- 解析来源：{analysis_source_label}")
    if arxiv_id:
        lines.append(f"- arXiv ID：`{arxiv_id}`")
    if doi:
        lines.append(f"- DOI：`{doi}`")
    lines.append("")

    lines.append("## 一句话总结")
    lines.append("")
    lines.append(payload.get("one_sentence_summary") or "当前没有足够信息生成一句话总结。")
    lines.append("")

    lines.append("## 摘要速览")
    lines.append("")
    for paragraph in _clean_text(abstract).split("\n"):
        if paragraph.strip():
            lines.append(f"> {paragraph.strip()}")
    lines.append("")

    lines.append("## 研究背景")
    lines.append("")
    lines.append(payload.get("research_background") or "建议先回到原文摘要和引言确认研究问题。")
    lines.append("")

    lines.append("## 核心方法")
    lines.append("")
    lines.append(payload.get("core_method") or "当前未成功提炼方法细节，请重点阅读 Method / Approach 部分。")
    lines.append("")

    lines.append("## 主要结果")
    lines.append("")
    lines.append(payload.get("key_results") or "当前没有提炼出明确结果，请重点核对实验表格和主要指标。")
    lines.append("")

    lines.append("## 创新点")
    lines.append("")
    for index, item in enumerate(payload.get("main_contributions") or [], start=1):
        lines.append(f"{index}. {item}")
    lines.append("")

    lines.append("## 局限性")
    lines.append("")
    for item in payload.get("limitations") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## 与我的研究的关系")
    lines.append("")
    for item in payload.get("relevance_points") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## 建议怎么读")
    lines.append("")
    if analysis_note:
        lines.append(f"- {analysis_note}")
    for item in payload.get("reading_focus") or []:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## 代码与资源")
    lines.append("")
    for label, value in resource_items:
        lines.append(f"- {label}：{value}")
    if analysis_note:
        lines.append(f"- 解析说明：{analysis_note}")
    lines.append("")

    lines.append("## 推荐指数")
    lines.append("")
    lines.append(f"{recommendation_stars}（{recommendation_score}/5）")
    lines.append(f"- 推荐理由：{recommendation_reason}")
    lines.append("")

    lines.append("## 我的笔记")
    lines.append("")
    lines.append("- 我最想复现或借鉴的点：")
    lines.append("- 这篇论文和我当前方向的连接：")
    lines.append("- 下一步要不要继续追作者 / 代码 / 后续工作：")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    return "\n".join(lines)


def resolve_selected_papers(paper_refs: List[int], papers: List[Dict]) -> List[Dict]:
    """Resolve paper references from either 1-based positions or actual paper IDs."""
    resolved: List[Dict] = []
    seen_keys: set[str] = set()

    papers_by_id = {}
    for paper in papers:
        paper_id = paper.get("id")
        if paper_id is not None:
            papers_by_id[int(paper_id)] = paper

    for paper_ref in paper_refs:
        paper: Optional[Dict[str, Any]] = None

        idx = int(paper_ref) - 1
        if 0 <= idx < len(papers):
            paper = papers[idx]

        if paper is None:
            paper = papers_by_id.get(int(paper_ref))

        if paper is None:
            continue

        unique_key = str(paper.get("id") or paper.get("arxiv_id") or paper.get("title") or paper_ref)
        if unique_key in seen_keys:
            continue
        seen_keys.add(unique_key)
        resolved.append(paper)

    return resolved


def _legacy_create_reading_report(
    user_id: str,
    paper_ids: List[int],
    papers: List[Dict],
    folder_id: Optional[str] = None,
    send_to_feishu: bool = True,
    feishu_user_id: Optional[str] = None,
    chat_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    创建精读报告

    Args:
        user_id: 用户 ID
        paper_ids: 选中的论文编号列表
        papers: 论文列表
        folder_id: 飞书文件夹 ID（可选）
        send_to_feishu: 是否发送飞书通知
        feishu_user_id: 飞书用户 ID
        chat_id: 聊天 ID（优先使用，发送到原对话框）

    Returns:
        创建的文档信息列表
    """
    print(f"Creating reading reports for user: {user_id}")
    print(f"Selected papers: {paper_ids}")

    # 优先使用 chat_id，否则使用 feishu_user_id
    target_id = chat_id or feishu_user_id
    use_chat_id = chat_id is not None

    # 获取用户画像
    profile = get_profile(user_id)
    if not profile:
        print(f"Warning: No profile found for user {user_id}, using default")
        profile = {"core_directions": {}}

    # 获取选中的论文
    selected_papers = resolve_selected_papers(paper_ids, papers)

    if not selected_papers:
        print("No valid papers selected")
        if send_to_feishu and target_id:
            send_text(
                target_id,
                "这次没有找到可生成精读的论文，请先推送后回复编号，或重新发送“精读”。",
                use_chat_id=use_chat_id,
            )
        return []

    # 为每篇论文创建报告
    created_docs = []

    for i, paper in enumerate(selected_papers):
        print(f"\n[{i+1}/{len(selected_papers)}] Processing: {paper.get('title', 'Unknown')[:50]}...")

        # 生成报告内容
        report_content = generate_reading_report(paper, profile)

        # 生成文档标题
        doc_title = f"[精读] {paper.get('title', 'Unknown')[:40]}"

        try:
            # 创建飞书文档
            doc_info = create_doc(
                title=doc_title,
                content=report_content,
                folder_id=folder_id
            )

            print(f"  Created: {doc_info}")
            created_docs.append(
                {
                    "paper": paper,
                    "doc_info": doc_info,
                    "title": doc_title,
                    "url": extract_doc_url(doc_info),
                    "doc_token": extract_doc_token(doc_info),
                }
            )

            # 记录行为日志
            log_behavior(
                user_id=user_id,
                push_id="reading_report",
                paper_id=paper.get("id"),
                action="created_report",
                action_type="reading",
                category="reading_agent",
                metadata={"arxiv_id": paper.get("arxiv_id")}
            )

        except Exception as e:
            print(f"  Error creating document: {e}")

    # 发送飞书通知
    if send_to_feishu and created_docs:
        summary_lines = [
            "=" * 60,
            f"📚 精读报告已生成 ({len(created_docs)} 篇)",
            "=" * 60,
            ""
        ]

        for doc in created_docs[:5]:  # 最多显示 5 篇
            title = doc["title"].replace("[精读] ", "")[:40]
            summary_lines.append(f"• {title}")

        if len(created_docs) > 5:
            summary_lines.append(f"... 还有 {len(created_docs) - 5} 篇")

        summary_lines.append("")
        summary_lines.append("请在飞书文档中查看完整报告")

        summary_text = format_created_docs_summary(created_docs)

        try:
            if target_id:
                send_text(target_id, summary_text, use_chat_id=use_chat_id)
                print(f"\nNotification sent to Feishu target: {target_id}")
        except Exception as e:
            print(f"\nFailed to send to Feishu: {e}")
    elif send_to_feishu and target_id:
        try:
            send_text(
                target_id,
                "精读任务已执行，但这次没有成功生成文档链接。请稍后重试；如果还不行，我可以继续帮你排查。",
                use_chat_id=use_chat_id,
            )
        except Exception as e:
            print(f"\nFailed to send fallback notice to Feishu: {e}")

    return created_docs


def create_reading_report(
    user_id: str,
    paper_ids: List[int],
    papers: List[Dict],
    folder_id: Optional[str] = None,
    send_to_feishu: bool = True,
    feishu_user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    print(f"Creating reading reports for user: {user_id}")
    print(f"Selected papers: {paper_ids}")

    target_id = chat_id or feishu_user_id
    use_chat_id = chat_id is not None

    profile = get_profile(user_id)
    if not profile:
        print(f"Warning: No profile found for user {user_id}, using default")
        profile = {"core_directions": {}, "methodology_preferences": {}}

    selected_papers = resolve_selected_papers(paper_ids, papers)
    if not selected_papers:
        print("No valid papers selected")
        if send_to_feishu and target_id:
            send_text(
                target_id,
                "这次没有找到可生成精读的论文，请先推送后回复编号，或重新发送“精读”。",
                use_chat_id=use_chat_id,
            )
        return []

    created_docs: List[Dict[str, Any]] = []
    for index, raw_paper in enumerate(selected_papers, start=1):
        print(f"\n[{index}/{len(selected_papers)}] Processing: {str(raw_paper.get('title', 'Unknown'))[:60]}")

        try:
            enriched_paper, parsed_pdf, pdf_error = enrich_paper_for_reading_report(raw_paper)
            heuristic_payload = build_heuristic_report_payload(
                enriched_paper,
                profile,
                parsed_pdf=parsed_pdf,
                pdf_error=pdf_error,
            )
            llm_payload = _synthesize_report_with_llm(
                enriched_paper,
                profile,
                parsed_pdf=parsed_pdf,
                heuristic_payload=heuristic_payload,
            )
            report_payload = _merge_report_payload(heuristic_payload, llm_payload)
            report_content = generate_reading_report(
                enriched_paper,
                profile,
                report_payload=report_payload,
            )

            doc_title = f"[精读] {enriched_paper.get('title', 'Unknown')[:80]}"
            doc_info = create_doc(title=doc_title, content=report_content, folder_id=folder_id)
            doc_url = extract_doc_url(doc_info)
            doc_token = extract_doc_token(doc_info)
            if not doc_url and doc_token:
                doc_url = _resolve_doc_url_from_meta(doc_token)

            created_docs.append(
                {
                    "paper": enriched_paper,
                    "doc_info": doc_info,
                    "title": doc_title,
                    "url": doc_url,
                    "doc_token": doc_token,
                    "report_payload": report_payload,
                }
            )

            log_behavior(
                user_id=user_id,
                push_id="reading_report",
                paper_id=enriched_paper.get("id"),
                action="created_report",
                action_type="reading",
                category="reading_agent",
                metadata={
                    "arxiv_id": enriched_paper.get("arxiv_id"),
                    "doc_token": doc_token,
                    "doc_url": doc_url,
                    "analysis_source": report_payload.get("analysis_source"),
                },
            )
            print(f"  Created reading doc: {doc_url or doc_token or '[no link yet]'}")
        except Exception as exc:
            print(f"  Error creating reading report: {exc}")

    if send_to_feishu and created_docs and target_id:
        summary_text = format_created_docs_summary(created_docs)
        try:
            send_text(target_id, summary_text, use_chat_id=use_chat_id)
            print(f"\nNotification sent to Feishu target: {target_id}")
        except Exception as exc:
            print(f"\nFailed to send to Feishu: {exc}")
    elif send_to_feishu and target_id:
        try:
            send_text(
                target_id,
                "精读任务已执行，但这次没有成功生成文档链接。请稍后重试；如果还不行，我可以继续帮你排查。",
                use_chat_id=use_chat_id,
            )
        except Exception as exc:
            print(f"\nFailed to send fallback notice to Feishu: {exc}")

    return created_docs


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Reading Agent - 生成精读报告")
    parser.add_argument("--user-id", type=str, default="user_001", help="用户 ID")
    parser.add_argument("--paper-ids", nargs="+", type=int, required=True, help="选中的论文编号")
    parser.add_argument("--folder-id", type=str, help="飞书文件夹 ID")
    parser.add_argument("--no-feishu", action="store_true", help="不发送飞书通知")
    parser.add_argument("--feishu-user-id", type=str, help="飞书用户 ID")

    args = parser.parse_args()

    # 测试数据
    test_papers = [
        {"id": 1, "arxiv_id": "2401.001", "title": "Test Paper 1", "authors": ["Author A"], "abstract": "This is a test abstract."},
        {"id": 2, "arxiv_id": "2401.002", "title": "Test Paper 2", "authors": ["Author B"], "abstract": "Another test abstract."},
    ]

    create_reading_report(
        user_id=args.user_id,
        paper_ids=args.paper_ids,
        papers=test_papers,
        folder_id=args.folder_id,
        send_to_feishu=not args.no_feishu,
        feishu_user_id=args.feishu_user_id
    )
