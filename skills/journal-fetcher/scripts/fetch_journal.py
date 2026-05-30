#!/usr/bin/env python3
"""
Journal Fetcher - 期刊论文抓取

支持期刊：
- Nature / Nature 子刊
- Science / Science 系列
- Cell
- PNAS
- The Lancet

数据源：使用各期刊的 RSS Feed 和公开 API
"""

import sys
import os
import json
import logging
import feedparser
import requests
import re
from html import unescape
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urljoin, urlparse, unquote, quote
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except ImportError:
    Retry = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SUPPRESS_HTTP_RETRY_WARNINGS = os.environ.get("PAPERFLOW_SUPPRESS_HTTP_RETRY_WARNINGS", "1").strip().lower() not in {"0", "false", "off", "no"}
if SUPPRESS_HTTP_RETRY_WARNINGS:
    logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

JOURNAL_SOURCES = {
    "nature": {
        "name": "Nature",
        "kind": "rss",
        "rss_url": "https://www.nature.com/nature.rss",
    },
    "nature-biotech": {
        "name": "Nature Biotechnology",
        "kind": "rss",
        "rss_url": "https://www.nature.com/nbt.rss",
    },
    "nature-methods": {
        "name": "Nature Methods",
        "kind": "rss",
        "rss_url": "https://www.nature.com/nmeth.rss",
    },
    "nature-machine-intelligence": {
        "name": "Nature Machine Intelligence",
        "kind": "rss",
        "rss_url": "https://www.nature.com/natmachintell.rss",
    },
    "nature-computational-science": {
        "name": "Nature Computational Science",
        "kind": "rss",
        "rss_url": "https://www.nature.com/natcomputsci.rss",
    },
    "nature-communications": {
        "name": "Nature Communications",
        "kind": "rss",
        "rss_url": "https://www.nature.com/ncomms.rss",
    },
    "science": {
        "name": "Science",
        "kind": "rss",
        "rss_url": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science",
    },
    "science-advances": {
        "name": "Science Advances",
        "kind": "rss",
        "rss_url": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv",
    },
    "cell": {
        "name": "Cell",
        "kind": "rss",
        "rss_url": "https://www.cell.com/cell/rss",
    },
    "pnas": {
        "name": "PNAS",
        "kind": "rss",
        "rss_url": "https://www.pnas.org/action/showFeed?type=header&feed=rss&jc=pnas",
    },
    "ijcv": {
        "name": "IJCV",
        "kind": "rss",
        "rss_url": "https://link.springer.com/search.rss?facet-journal-id=11263&facet-content-type=Article",
    },
    "tpami": {
        "name": "TPAMI",
        "kind": "ieee_api",
        "publication_title": "IEEE Transactions on Pattern Analysis and Machine Intelligence",
    },
}

JOURNAL_ALIASES = {
    "nature": "nature",
    "naturebiotechnology": "nature-biotech",
    "naturebiotech": "nature-biotech",
    "naturemethods": "nature-methods",
    "naturemachineintelligence": "nature-machine-intelligence",
    "naturecomputationalscience": "nature-computational-science",
    "naturecommunications": "nature-communications",
    "science": "science",
    "scienceadvances": "science-advances",
    "cell": "cell",
    "pnas": "pnas",
    "ijcv": "ijcv",
    "tpami": "tpami",
}

JOURNAL_REQUEST_TIMEOUT = float(os.environ.get("JOURNAL_REQUEST_TIMEOUT", "20"))
JOURNAL_DETAIL_FETCH_ENABLED = os.environ.get("JOURNAL_DETAIL_FETCH_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}
HTTP_RETRY_TOTAL = int(os.environ.get("PAPERFLOW_HTTP_RETRIES", "2"))
HTTP_RETRY_BACKOFF = float(os.environ.get("PAPERFLOW_HTTP_BACKOFF", "0.8"))
DEFAULT_REQUEST_HEADERS = {
    "User-Agent": os.environ.get(
        "PAPERFLOW_HTTP_USER_AGENT",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/135.0.0.0 Safari/537.36"
        ),
    ),
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

NON_RESEARCH_TITLE_PATTERNS = (
    "author correction",
    "publisher correction",
    "correction:",
    "daily briefing",
    "in other journals",
    "editorial",
    "world view",
    "research highlight",
    "career column",
    "book review",
    "podcast",
    "video abstract",
    "news feature",
    "news & views",
    "news and views",
)

NON_RESEARCH_LINK_PATTERNS = (
    "/news/",
    "/careers/",
    "/podcast/",
    "/videos/",
    "/multimedia/",
    "/opinion/",
    "/comments/",
    "/news-features/",
)

NON_RESEARCH_ARTICLE_TYPE_PATTERNS = (
    "news",
    "editorial",
    "opinion",
    "commentary",
    "correction",
    "briefing",
    "career",
    "world-view",
)

SECTION_TITLE_SKIP_PATTERNS = (
    "references",
    "acknowledg",
    "supplement",
    "author information",
    "about this article",
    "rights and permissions",
    "ethics declarations",
    "additional information",
    "peer review",
)

FEED_METADATA_PREFIX_RE = re.compile(
    r"^(?:"
    r"nature(?: communications| biotechnology| methods| machine intelligence| computational science)?"
    r"|science(?: advances)?"
    r"|cell"
    r"|pnas"
    r")\s*,\s*published online:\s*[^;]{1,160}(?:;\s*doi:\s*10\.\S+)?\s*",
    flags=re.I,
)


def normalize_journal_name(name: str) -> Optional[str]:
    """Normalize human-readable journal names into supported keys."""
    condensed = re.sub(r"[^a-z0-9]+", "", str(name or "").strip().lower())
    if not condensed:
        return None
    return JOURNAL_ALIASES.get(condensed)


def get_supported_journals() -> List[str]:
    """Return supported journal keys in stable order."""
    return list(JOURNAL_SOURCES.keys())


def _build_request_headers(*, referer: Optional[str] = None) -> Dict[str, str]:
    headers = dict(DEFAULT_REQUEST_HEADERS)
    headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    headers["Upgrade-Insecure-Requests"] = "1"
    if referer:
        headers["Referer"] = referer
    return headers


def _create_http_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = True

    if Retry is not None and HTTP_RETRY_TOTAL > 0:
        retry = Retry(
            total=HTTP_RETRY_TOTAL,
            connect=HTTP_RETRY_TOTAL,
            read=HTTP_RETRY_TOTAL,
            status=HTTP_RETRY_TOTAL,
            backoff_factor=HTTP_RETRY_BACKOFF,
            allowed_methods=frozenset({"GET", "HEAD"}),
            status_forcelist=(408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 524),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

    return session


def _http_get(url: str, *, timeout: float, referer: Optional[str] = None) -> requests.Response:
    session = _create_http_session()
    try:
        response = session.get(
            url,
            timeout=timeout,
            headers=_build_request_headers(referer=referer),
            allow_redirects=True,
        )
        response.raise_for_status()
        return response
    finally:
        session.close()


def _clean_html_text(fragment: Any) -> str:
    text = unescape(str(fragment or ""))
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _looks_like_feed_metadata_abstract(text: Any) -> bool:
    normalized = _clean_html_text(text).lower()
    return bool(normalized and "published online:" in normalized)


def _clean_abstract_text(fragment: Any) -> str:
    normalized = _clean_html_text(fragment)
    normalized = FEED_METADATA_PREFIX_RE.sub("", normalized).strip(" \n\t;,:-")
    return normalized


def _extract_meta_contents(html: str, names: List[str]) -> List[str]:
    values: List[str] = []
    if not html:
        return values

    for name in names:
        patterns = [
            rf"""<meta[^>]+(?:name|property)=["']{re.escape(name)}["'][^>]+content=["']([^"']+)["']""",
            rf"""<meta[^>]+content=["']([^"']+)["'][^>]+(?:name|property)=["']{re.escape(name)}["']""",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, html, flags=re.I):
                cleaned = _clean_html_text(match.group(1))
                if cleaned:
                    values.append(cleaned)
    return values


def _extract_first_meta_content(html: str, names: List[str]) -> str:
    values = _extract_meta_contents(html, names)
    return values[0] if values else ""


def _split_author_text(text: str) -> List[str]:
    cleaned = _clean_html_text(text)
    if not cleaned:
        return []
    parts = re.split(r"\s*;\s*|\s*\|\s*|\s*,\s*(?=[A-Z][a-z])", cleaned)
    authors = [part.strip() for part in parts if part.strip()]
    return authors[:20]


def _extract_pdf_url_from_html(html: str, page_url: str) -> str:
    preferred_patterns = (
        r"""<a[^>]+data-test=["']download-pdf["'][^>]+href=["']([^"']+\.pdf(?:\?[^"']*)?)["']""",
        r"""<a[^>]+href=["']([^"']+_reference\.pdf(?:\?[^"']*)?)["'][^>]*data-test=["']download-pdf["']""",
        r"""<a[^>]+href=["']([^"']+_reference\.pdf(?:\?[^"']*)?)["']""",
    )
    for pattern in preferred_patterns:
        match = re.search(pattern, html, flags=re.I)
        if match:
            return urljoin(page_url, match.group(1))

    direct_meta = _extract_first_meta_content(html, ["citation_pdf_url"])
    if direct_meta:
        return urljoin(page_url, direct_meta)

    patterns = (
        r"""<a[^>]+href=["']([^"']+\.pdf(?:\?[^"']*)?)["']""",
        r"""<a[^>]+href=["']([^"']*downloadPdf[^"']*)["']""",
        r"""<a[^>]+href=["']([^"']*/pdf(?:/|[?"'][^"']*)[^"']*)["']""",
    )
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.I)
        if match:
            return urljoin(page_url, match.group(1))
    return ""


def _extract_json_ld_payloads(html: str) -> List[Any]:
    payloads: List[Any] = []
    if not html:
        return payloads

    for match in re.finditer(
        r"""<script[^>]+type=["']application/ld\+json["'][^>]*>(.*?)</script>""",
        html,
        flags=re.I | re.S,
    ):
        raw = unescape(match.group(1) or "").strip()
        if not raw:
            continue
        raw = re.sub(r"^\s*<!--|-->\s*$", "", raw, flags=re.S).strip()
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        if isinstance(parsed, list):
            payloads.extend(parsed)
        else:
            payloads.append(parsed)
    return payloads


def _extract_json_ld_values(node: Any, key: str) -> List[str]:
    values: List[str] = []

    if isinstance(node, dict):
        for current_key, current_value in node.items():
            if current_key == key:
                if isinstance(current_value, str):
                    cleaned = _clean_html_text(current_value)
                    if cleaned:
                        values.append(cleaned)
                elif isinstance(current_value, list):
                    for item in current_value:
                        if isinstance(item, str):
                            cleaned = _clean_html_text(item)
                            if cleaned:
                                values.append(cleaned)
            values.extend(_extract_json_ld_values(current_value, key))
    elif isinstance(node, list):
        for item in node:
            values.extend(_extract_json_ld_values(item, key))

    return values


def _extract_json_ld_first_text(html: str, keys: List[str]) -> str:
    payloads = _extract_json_ld_payloads(html)
    if not payloads:
        return ""

    for key in keys:
        for payload in payloads:
            for value in _extract_json_ld_values(payload, key):
                if value:
                    return value
    return ""


def _extract_paragraphs_from_fragment(
    html_fragment: str,
    *,
    min_length: int = 80,
    max_paragraphs: int = 3,
) -> List[str]:
    paragraphs: List[str] = []
    for match in re.findall(r"<p\b[^>]*>(.*?)</p>", html_fragment or "", flags=re.I | re.S):
        paragraph = _clean_html_text(match)
        lowered = paragraph.lower()
        if len(paragraph) < min_length:
            continue
        if any(
            lowered.startswith(prefix)
            for prefix in (
                "rights and permissions",
                "access provided by",
                "download pdf",
                "about this article",
                "share this article",
                "this article is part of",
                "editor's summary",
                "references",
            )
        ):
            continue
        if paragraph not in paragraphs:
            paragraphs.append(paragraph)
        if len(paragraphs) >= max_paragraphs:
            break
    return paragraphs


def _extract_body_summary_from_html(html: str) -> str:
    if not html:
        return ""

    fragments: List[str] = []
    container_patterns = (
        r"<main\b[^>]*>(.*?)</main>",
        r"<article\b[^>]*>(.*?)</article>",
        r"""<section[^>]+class=["'][^"']*(?:article|content|body)[^"']*["'][^>]*>(.*?)</section>""",
        r"""<div[^>]+class=["'][^"']*(?:article|content|body|main)[^"']*["'][^>]*>(.*?)</div>""",
    )
    for pattern in container_patterns:
        matches = re.findall(pattern, html, flags=re.I | re.S)
        fragments.extend(matches)

    search_spaces = fragments + [html]
    paragraphs: List[str] = []
    for fragment in search_spaces:
        paragraphs.extend(_extract_paragraphs_from_fragment(fragment))
        if paragraphs:
            break

    if not paragraphs:
        return ""

    summary = " ".join(paragraphs[:3])
    summary = re.sub(r"\s+", " ", summary).strip()
    return summary


def _extract_main_html_fragment(html: str) -> str:
    if not html:
        return ""

    container_patterns = (
        r"<main\b[^>]*>(.*?)</main>",
        r"<article\b[^>]*>(.*?)</article>",
        r"""<div[^>]+class=["'][^"']*(?:article|content|body|main)[^"']*["'][^>]*>(.*?)</div>""",
    )

    fragments: List[str] = []
    for pattern in container_patterns:
        fragments.extend(re.findall(pattern, html, flags=re.I | re.S))

    if not fragments:
        return html
    return max(fragments, key=len)


def _normalize_section_key(raw_title: Any) -> str:
    title = _clean_html_text(raw_title).strip(":- ")
    lowered = title.lower()
    if not title or len(title) > 120:
        return ""
    if any(token in lowered for token in SECTION_TITLE_SKIP_PATTERNS):
        return ""

    mapping = (
        (("abstract",), "abstract"),
        (("introduction",), "introduction"),
        (("background", "related work", "prior work"), "background"),
        (("method", "methods", "approach", "framework", "model", "methodology", "materials and methods"), "method"),
        (("results", "findings"), "results"),
        (("experiment", "evaluation", "benchmark"), "experiments"),
        (("discussion",), "discussion"),
        (("limitation", "limitations"), "limitations"),
        (("conclusion", "conclusions"), "conclusion"),
    )

    for tokens, normalized in mapping:
        if any(token in lowered for token in tokens):
            return normalized

    slug = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    if not slug:
        return ""
    return slug[:48]


def _extract_source_page_sections_and_full_text(
    html: str,
    *,
    abstract: str = "",
) -> Tuple[Dict[str, str], str]:
    root = _extract_main_html_fragment(html)
    sections: Dict[str, str] = {}

    def store(section_key: str, value: str) -> None:
        cleaned_value = re.sub(r"\s+", " ", _clean_html_text(value)).strip()
        if len(cleaned_value) < 60:
            return
        if section_key == "abstract":
            sections[section_key] = cleaned_value[:6000]
            return
        previous = sections.get(section_key, "")
        if len(cleaned_value) > len(previous):
            sections[section_key] = cleaned_value[:6000]

    cleaned_abstract = _clean_html_text(abstract)
    if cleaned_abstract:
        store("abstract", cleaned_abstract)

    for attrs, body in re.findall(r"<section\b([^>]*)>(.*?)</section>", root, flags=re.I | re.S):
        raw_title = ""
        data_title_match = re.search(r"""data-title=["']([^"']+)["']""", attrs, flags=re.I)
        if data_title_match:
            raw_title = data_title_match.group(1)
        if not raw_title:
            heading_match = re.search(r"<h[1-4][^>]*>(.*?)</h[1-4]>", body, flags=re.I | re.S)
            if heading_match:
                raw_title = heading_match.group(1)

        section_key = _normalize_section_key(raw_title)
        if not section_key:
            continue

        paragraphs = _extract_paragraphs_from_fragment(body, min_length=40, max_paragraphs=12)
        if paragraphs:
            store(section_key, " ".join(paragraphs))

    heading_matches = list(re.finditer(r"<h([2-4])[^>]*>(.*?)</h\1>", root, flags=re.I | re.S))
    for index, match in enumerate(heading_matches):
        section_key = _normalize_section_key(match.group(2))
        if not section_key:
            continue
        block_end = heading_matches[index + 1].start() if index + 1 < len(heading_matches) else len(root)
        block_html = root[match.end():block_end]
        paragraphs = _extract_paragraphs_from_fragment(block_html, min_length=40, max_paragraphs=12)
        if paragraphs:
            store(section_key, " ".join(paragraphs))

    if len(sections) <= 1:
        paragraphs = _extract_paragraphs_from_fragment(root, min_length=60, max_paragraphs=10)
        filtered = [
            paragraph
            for paragraph in paragraphs
            if paragraph and paragraph not in sections.values()
        ]
        if filtered:
            store("introduction", " ".join(filtered[:4]))

    full_text_parts: List[str] = []
    for key in ("abstract", "introduction", "background", "method", "results", "experiments", "discussion", "conclusion"):
        value = sections.get(key)
        if value and value not in full_text_parts:
            full_text_parts.append(value)

    for key, value in sections.items():
        if value and value not in full_text_parts:
            full_text_parts.append(value)

    if not full_text_parts:
        fallback_paragraphs = _extract_paragraphs_from_fragment(root, min_length=60, max_paragraphs=12)
        full_text_parts.extend(fallback_paragraphs)

    full_text = " ".join(full_text_parts).strip()[:12000]
    return sections, full_text


def _extract_nature_abstract_from_html(html: str) -> str:
    if not html:
        return ""

    section_patterns = (
        r"""<section[^>]+data-title=["']Abstract["'][^>]*>(.*?)</section>""",
        r"""<div[^>]+id=["'][^"']*Abs[^"']*-content["'][^>]*>(.*?)</div>""",
    )
    for pattern in section_patterns:
        for fragment in re.findall(pattern, html, flags=re.I | re.S):
            paragraphs = _extract_paragraphs_from_fragment(fragment, min_length=40)
            if paragraphs:
                return re.sub(r"\s+", " ", " ".join(paragraphs)).strip()
    return ""


def _extract_nature_article_type_from_html(html: str) -> str:
    article_type = _extract_first_meta_content(
        html,
        ["citation_article_type", "dc.type", "og:type"],
    )
    if article_type:
        return article_type

    json_ld_article_type = _extract_json_ld_first_text(html, ["articleSection", "@type"])
    return json_ld_article_type


def _extract_doi_from_url_or_identifier(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    doi_match = re.search(r"(10\.\d{4,9}/\S+)", text, flags=re.I)
    if doi_match and not text.startswith(("http://", "https://")):
        return doi_match.group(1).rstrip(")>.,; ")

    if not text.startswith(("http://", "https://")):
        return ""

    parsed = urlparse(text)
    host = (parsed.netloc or "").lower()
    path = unquote(parsed.path or "").strip()

    if "doi.org" in host:
        return path.lstrip("/").rstrip(")>.,; ")

    doi_path_match = re.search(r"/doi/(?:abs|full|pdf|epdf|reader)?/?(.+)$", path, flags=re.I)
    if doi_path_match:
        return doi_path_match.group(1).strip("/").rstrip(")>.,; ")

    return doi_match.group(1).rstrip(")>.,; ") if doi_match else ""


def _reconstruct_openalex_abstract(inverted_index: Dict[str, Any]) -> str:
    if not isinstance(inverted_index, dict):
        return ""

    positioned_words: List[Tuple[int, str]] = []
    for word, positions in inverted_index.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            try:
                positioned_words.append((int(position), str(word)))
            except (TypeError, ValueError):
                continue

    if not positioned_words:
        return ""

    positioned_words.sort(key=lambda item: item[0])
    tokens = [word for _, word in positioned_words]
    text = " ".join(tokens)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    return text.strip()


def _fetch_crossref_metadata(doi: str) -> Dict[str, Any]:
    if not doi:
        return {}

    try:
        response = requests.get(
            f"https://api.crossref.org/works/{quote(doi, safe='')}",
            timeout=JOURNAL_REQUEST_TIMEOUT,
            headers={"User-Agent": DEFAULT_REQUEST_HEADERS["User-Agent"]},
        )
        response.raise_for_status()
        message = response.json().get("message") or {}
    except Exception:
        return {}

    title_list = message.get("title") or []
    authors = []
    for author in message.get("author") or []:
        given = str(author.get("given") or "").strip()
        family = str(author.get("family") or "").strip()
        full_name = " ".join(part for part in (given, family) if part).strip()
        if full_name:
            authors.append(full_name)

    pdf_url = ""
    for link in message.get("link") or []:
        candidate = str((link or {}).get("URL") or "").strip()
        if candidate.endswith(".pdf") or "/doi/pdf/" in candidate:
            pdf_url = candidate
            break

    published = (
        message.get("published-print")
        or message.get("published-online")
        or message.get("published")
        or message.get("issued")
        or {}
    )
    date_parts = ((published or {}).get("date-parts") or [[]])[0]
    publish_date = ""
    if isinstance(date_parts, list) and date_parts:
        publish_date = "-".join(str(part) for part in date_parts[:3])

    return {
        "title": _clean_html_text(title_list[0]) if title_list else "",
        "abstract": _clean_html_text(message.get("abstract")),
        "authors": authors,
        "doi": str(message.get("DOI") or doi).strip(),
        "pdf_url": pdf_url,
        "venue": _clean_html_text((message.get("container-title") or [""])[0]),
        "publish_date": publish_date,
    }


def _fetch_openalex_metadata(doi: str) -> Dict[str, Any]:
    if not doi:
        return {}

    try:
        response = requests.get(
            f"https://api.openalex.org/works?filter=doi:{quote(doi, safe='')}",
            timeout=JOURNAL_REQUEST_TIMEOUT,
            headers={"User-Agent": DEFAULT_REQUEST_HEADERS["User-Agent"]},
        )
        response.raise_for_status()
        results = (response.json() or {}).get("results") or []
        if not results:
            return {}
        work = results[0]
    except Exception:
        return {}

    authors = []
    for authorship in work.get("authorships") or []:
        author_name = _clean_html_text(((authorship or {}).get("author") or {}).get("display_name"))
        if author_name:
            authors.append(author_name)

    primary_location = work.get("primary_location") or {}
    best_oa_location = work.get("best_oa_location") or {}
    primary_source = primary_location.get("source") or {}

    return {
        "title": _clean_html_text(work.get("display_name") or work.get("title")),
        "abstract": _reconstruct_openalex_abstract(work.get("abstract_inverted_index") or {}),
        "authors": authors,
        "doi": _extract_doi_from_url_or_identifier(work.get("doi")) or doi,
        "pdf_url": (
            str(best_oa_location.get("pdf_url") or "").strip()
            or str(primary_location.get("pdf_url") or "").strip()
        ),
        "landing_page_url": (
            str(best_oa_location.get("landing_page_url") or "").strip()
            or str(primary_location.get("landing_page_url") or "").strip()
        ),
        "venue": _clean_html_text(
            primary_source.get("display_name")
            or work.get("primary_location", {}).get("raw_source_name")
        ),
        "publish_date": str(work.get("publication_date") or "").strip(),
    }


def _fetch_open_access_source_detail(url: Any) -> Dict[str, Any]:
    candidate = str(url or "").strip()
    if not candidate.startswith(("http://", "https://")):
        return {}

    if candidate.lower().endswith(".pdf"):
        return {"pdf_url": candidate}

    try:
        response = _http_get(candidate, timeout=JOURNAL_REQUEST_TIMEOUT)
    except Exception:
        return {
            "metadata": {
                "source_page": {
                    "source_kind": "source_page",
                    "source_url": candidate,
                    "abstract": "",
                    "sections": {},
                    "full_text": "",
                }
            }
        }

    final_url = str(response.url or candidate)
    content_type = str(response.headers.get("Content-Type") or "").lower()
    if "application/pdf" in content_type or final_url.lower().endswith(".pdf"):
        return {"pdf_url": final_url}

    parsed = _parse_article_detail_html(response.text or "", final_url)
    metadata = dict(parsed.get("metadata") or {})
    source_page = dict(metadata.get("source_page") or {})
    source_page_abstract = _clean_html_text(source_page.get("abstract"))
    parsed_abstract = _clean_html_text(parsed.get("abstract"))
    if source_page_abstract and (not parsed_abstract or len(source_page_abstract) > len(parsed_abstract) + 40):
        parsed["abstract"] = source_page_abstract
    metadata.setdefault(
        "source_page",
        {
            "source_kind": "source_page",
            "source_url": final_url,
            "abstract": "",
            "sections": {},
            "full_text": "",
        },
    )
    parsed["metadata"] = metadata
    return parsed


def _fetch_scholarly_metadata_fallback(url_or_doi: Any) -> Dict[str, Any]:
    doi = _extract_doi_from_url_or_identifier(url_or_doi)
    if not doi:
        return {}

    openalex_detail = _fetch_openalex_metadata(doi)
    crossref_detail = _fetch_crossref_metadata(doi)
    merged = {}

    for candidate in (crossref_detail, openalex_detail):
        if candidate.get("title") and not merged.get("title"):
            merged["title"] = candidate["title"]
        if candidate.get("authors") and not merged.get("authors"):
            merged["authors"] = list(candidate["authors"])
        if candidate.get("doi") and not merged.get("doi"):
            merged["doi"] = candidate["doi"]
        if candidate.get("pdf_url") and not merged.get("pdf_url"):
            merged["pdf_url"] = candidate["pdf_url"]
        if candidate.get("venue") and not merged.get("venue"):
            merged["venue"] = candidate["venue"]
        if candidate.get("publish_date") and not merged.get("publish_date"):
            merged["publish_date"] = candidate["publish_date"]

    merged["abstract"] = (
        openalex_detail.get("abstract")
        or crossref_detail.get("abstract")
        or merged.get("abstract")
        or ""
    )

    oa_source_url = str(openalex_detail.get("landing_page_url") or "").strip()
    if oa_source_url:
        oa_source_detail = _fetch_open_access_source_detail(oa_source_url)
        if oa_source_detail:
            merged = _merge_detail_into_paper(merged, oa_source_detail)
        else:
            existing_metadata = dict(merged.get("metadata") or {})
            existing_metadata.setdefault(
                "source_page",
                {
                    "source_kind": "source_page",
                    "source_url": oa_source_url,
                    "abstract": "",
                    "sections": {},
                    "full_text": "",
                },
            )
            merged["metadata"] = existing_metadata

    if merged:
        merged["doi"] = merged.get("doi") or doi
    return merged


def _looks_like_non_research_detail_page(detail: Dict[str, Any], page_url: str) -> bool:
    if not isinstance(detail, dict):
        return False

    host = (urlparse(str(page_url or "")).netloc or "").lower()
    path = (urlparse(str(page_url or "")).path or "").lower()
    title = _clean_html_text(detail.get("title")).lower()
    abstract = _clean_html_text(detail.get("abstract")).lower()
    article_type = _clean_html_text(detail.get("article_type")).lower()
    combined = " ".join(part for part in (title, abstract, article_type) if part)

    if any(pattern in combined for pattern in NON_RESEARCH_TITLE_PATTERNS):
        return True
    if any(pattern in article_type for pattern in NON_RESEARCH_ARTICLE_TYPE_PATTERNS):
        return True
    if "nature.com" in host and re.search(r"/articles/d\d{5}-", path):
        return True
    return False


def _parse_article_detail_html(html: str, page_url: str) -> Dict[str, Any]:
    host = (urlparse(str(page_url or "")).netloc or "").lower()

    title = _extract_first_meta_content(
        html,
        ["citation_title", "dc.title", "og:title", "twitter:title"],
    )
    if not title:
        title = _extract_json_ld_first_text(html, ["headline", "name"])
    if not title:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
        title = _clean_html_text(title_match.group(1)) if title_match else ""

    abstract = _extract_first_meta_content(
        html,
        ["citation_abstract", "dc.description", "description", "og:description", "twitter:description"],
    )
    if "nature.com" in host and (not abstract or len(_clean_html_text(abstract)) < 120):
        abstract = _extract_nature_abstract_from_html(html) or abstract
    if not abstract or len(_clean_html_text(abstract)) < 120:
        abstract = _extract_json_ld_first_text(html, ["description", "abstract"]) or abstract
    body_summary = _extract_body_summary_from_html(html)
    if body_summary and (not abstract or len(_clean_html_text(abstract)) < 120):
        abstract = body_summary
    sections, full_text = _extract_source_page_sections_and_full_text(html, abstract=abstract)
    section_abstract = _clean_html_text(sections.get("abstract"))
    if section_abstract:
        abstract = section_abstract
    authors = _extract_meta_contents(html, ["citation_author", "dc.creator", "author"])
    doi = _extract_first_meta_content(html, ["citation_doi", "dc.identifier"])
    article_type = (
        _extract_nature_article_type_from_html(html)
        if "nature.com" in host
        else _extract_first_meta_content(html, ["citation_article_type", "dc.type", "og:type"])
    )
    if not article_type:
        article_type = _extract_json_ld_first_text(html, ["articleSection", "@type"])
    if not doi:
        doi_match = re.search(r"https?://doi\.org/([^\s\"'<>]+)", html, flags=re.I)
        if doi_match:
            doi = doi_match.group(1).strip()

    metadata: Dict[str, Any] = {}
    if abstract or sections or full_text:
        metadata["source_page"] = {
            "source_kind": "source_page",
            "source_url": page_url,
            "abstract": _clean_html_text(abstract),
            "sections": sections,
            "full_text": full_text,
        }

    return {
        "title": title,
        "abstract": abstract,
        "authors": _split_author_text("; ".join(authors)),
        "doi": doi,
        "pdf_url": _extract_pdf_url_from_html(html, page_url),
        "article_type": article_type,
        "metadata": metadata,
    }


def _supports_article_detail_fetch(url: str) -> bool:
    host = (urlparse(str(url or "")).netloc or "").lower()
    return any(
        token in host
        for token in (
            "nature.com",
            "science.org",
            "cell.com",
            "pnas.org",
            "springer.com",
            "link.springer.com",
            "doi.org",
            "dl.acm.org",
            "acm.org",
            "openreview.net",
            "openaccess.thecvf.com",
            "ecva.net",
        )
    )


def _looks_like_research_article(entry: Any, journal_key: str) -> bool:
    title = _clean_html_text(entry.get("title", "")).lower()
    if not title:
        return False
    if any(pattern in title for pattern in NON_RESEARCH_TITLE_PATTERNS):
        return False

    link = str(entry.get("link", "")).lower()
    if any(token in link for token in NON_RESEARCH_LINK_PATTERNS):
        return False
    if "nature.com" in link and re.search(r"/articles/d\d{5}-", link):
        return False

    tags = []
    for tag in getattr(entry, "tags", []) or []:
        if isinstance(tag, dict):
            term = str(tag.get("term") or "").strip().lower()
            if term:
                tags.append(term)
    if any(term in {"news", "editorial", "career-feature", "opinion"} for term in tags):
        return False

    return True


def _fetch_article_detail(url: str) -> Dict[str, Any]:
    if not JOURNAL_DETAIL_FETCH_ENABLED:
        return {}

    doi = _extract_doi_from_url_or_identifier(url)
    if not _supports_article_detail_fetch(url):
        return _fetch_scholarly_metadata_fallback(url) if doi else {}

    try:
        response = _http_get(
            url,
            timeout=JOURNAL_REQUEST_TIMEOUT,
        )
    except Exception as exc:
        fallback = _fetch_scholarly_metadata_fallback(url)
        if fallback:
            return fallback
        print(f"  Detail fetch failed with no fallback for {url[:120]}: {type(exc).__name__}")
        return {}

    detail = _parse_article_detail_html(response.text or "", str(response.url or url))
    if doi:
        fallback = _fetch_scholarly_metadata_fallback(doi)
        if fallback:
            detail = _merge_detail_into_paper(detail, fallback)
    if _looks_like_non_research_detail_page(detail, str(response.url or url)):
        return {"_skip": True}
    return detail


def _merge_detail_into_paper(paper: Dict[str, Any], detail: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(paper)
    if not isinstance(detail, dict):
        return merged

    detail_title = _clean_html_text(detail.get("title"))
    if detail_title and (not merged.get("title") or merged.get("title") == "Unknown"):
        merged["title"] = detail_title

    current_abstract_raw = merged.get("abstract")
    current_abstract = _clean_abstract_text(current_abstract_raw)
    detail_abstract = _clean_abstract_text(detail.get("abstract"))
    if detail_abstract and (
        not current_abstract
        or merged.get("source") == "rss"
        or _looks_like_feed_metadata_abstract(current_abstract_raw)
        or len(detail_abstract) > len(current_abstract) + 40
    ):
        merged["abstract"] = detail_abstract
    elif current_abstract:
        merged["abstract"] = current_abstract

    current_authors = list(merged.get("authors") or [])
    detail_authors = list(detail.get("authors") or [])
    if detail_authors and (not current_authors or len(detail_authors) > len(current_authors)):
        merged["authors"] = detail_authors

    if detail.get("venue") and not merged.get("venue"):
        merged["venue"] = detail["venue"]
    if detail.get("publish_date") and not merged.get("publish_date"):
        merged["publish_date"] = detail["publish_date"]
    if detail.get("doi") and not merged.get("doi"):
        merged["doi"] = detail["doi"]
    if detail.get("pdf_url"):
        merged["pdf_url"] = detail["pdf_url"]

    existing_metadata = dict(merged.get("metadata") or {})
    detail_metadata = dict(detail.get("metadata") or {})
    if detail_metadata:
        merged["metadata"] = {**existing_metadata, **detail_metadata}

    return merged


def fetch_ieee_journal_papers(
    journal_key: str,
    limit: int = 20,
    days: int = 7
) -> List[Dict[str, Any]]:
    """Fetch journal papers from IEEE Xplore when an API key is configured."""
    api_key = os.environ.get("IEEE_API_KEY", "").strip()
    source = JOURNAL_SOURCES[journal_key]
    if not api_key:
        print(f"Skipping {source['name']}: IEEE_API_KEY not configured")
        return []

    cutoff_date = datetime.now() - timedelta(days=days)
    params = {
        "apikey": api_key,
        "format": "json",
        "max_records": limit,
        "sort_order": "desc",
        "sort_field": "article_number",
        "publication_title": source["publication_title"],
    }

    try:
        response = requests.get("https://api.ieee.org/xplore/v2/articles", params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"Error fetching {source['name']} from IEEE Xplore ({type(e).__name__})")
        return []

    papers = []
    for article in data.get("articles", []):
        raw_date = str(article.get("publication_date", "")).strip()
        published = None
        for fmt in ("%d %B %Y", "%Y-%m-%d", "%Y-%m", "%Y"):
            try:
                published = datetime.strptime(raw_date, fmt)
                break
            except ValueError:
                continue

        if published and published < cutoff_date:
            continue

        authors = []
        author_payload = article.get("authors", {})
        for author in author_payload.get("authors", []) if isinstance(author_payload, dict) else []:
            name = author.get("full_name") or author.get("name")
            if name:
                authors.append(name)

        papers.append({
            "title": article.get("title", "Unknown"),
            "abstract": article.get("abstract", ""),
            "authors": authors,
            "venue": source["name"],
            "journal": journal_key,
            "doi": article.get("doi", ""),
            "url": article.get("html_url") or article.get("pdf_url", ""),
            "publish_date": published.isoformat() if published else raw_date,
            "categories": [journal_key],
            "source": "ieee",
        })

    print(f"  Fetched {len(papers)} papers from {source['name']}")
    return papers


def extract_entry_datetime(entry) -> Optional[datetime]:
    """Extract the best available publication timestamp from an RSS entry."""
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            return datetime(*parsed[:6])
    return None


def fetch_journal_papers(
    journal: str = "nature",
    limit: int = 20,
    days: int = 7
) -> List[Dict[str, Any]]:
    """
    抓取指定期刊的论文

    Args:
        journal: 期刊名称 (nature, science, cell, pnas, etc.)
        limit: 返回数量限制
        days: 最近 N 天

    Returns:
        论文列表
    """
    journal_key = normalize_journal_name(journal) or str(journal or "").strip().lower()
    journal_info = JOURNAL_SOURCES.get(journal_key)
    if not journal_info:
        print(f"Unknown journal: {journal}")
        return []

    print(f"Fetching from {journal_info['name']}...")

    if journal_info.get("kind") == "ieee_api":
        return fetch_ieee_journal_papers(journal_key=journal_key, limit=limit, days=days)

    papers = []
    cutoff_date = datetime.now() - timedelta(days=days)

    try:
        # 解析 RSS Feed
        feed = feedparser.parse(journal_info["rss_url"])

        for entry in feed.entries:
            if len(papers) >= limit:
                break

            # 提取论文信息
            published = extract_entry_datetime(entry)

            if published and published < cutoff_date:
                continue
            if published is None:
                # RSS 没有可靠时间字段时不把旧条目伪装成“今天”
                continue
            if not _looks_like_research_article(entry, journal_key):
                continue

            paper = {
                "title": entry.get('title', 'Unknown'),
                "abstract": _clean_abstract_text(entry.get('summary', entry.get('description', ''))),
                "authors": extract_authors_from_rss(entry),
                "venue": journal_info["name"],
                "journal": journal_key,
                "doi": extract_doi(entry),
                "url": entry.get('link', ''),
                "publish_date": published.isoformat(),
                "categories": [journal_key],
                "source": "rss",
            }
            detail = _fetch_article_detail(paper["url"])
            if detail.get("_skip"):
                continue
            paper = _merge_detail_into_paper(paper, detail)
            papers.append(paper)

    except Exception as e:
        print(f"Error fetching {journal_info['name']}: {e}")

    print(f"  Fetched {len(papers)} papers from {journal_info['name']}")
    return papers


def extract_authors_from_rss(entry) -> List[str]:
    """从 RSS 条目中提取作者"""
    authors = []

    # 尝试不同格式
    if hasattr(entry, 'author'):
        author_str = entry.author
        if author_str:
            # 分割多个作者
            for author in author_str.split(','):
                author = author.strip()
                if author:
                    authors.append(author)

    if hasattr(entry, 'authors'):
        for author in entry.authors:
            if isinstance(author, dict) and 'name' in author:
                authors.append(author['name'])
            elif isinstance(author, str):
                authors.append(author)

    return authors[:10]  # 限制作者数量


def extract_doi(entry) -> Optional[str]:
    """从 RSS 条目中提取 DOI"""
    # 尝试从链接中提取
    link = entry.get('link', '')
    if 'doi.org' in link:
        parts = link.split('doi.org/')
        if len(parts) > 1:
            return parts[1]

    # 尝试从 DOI 字段提取
    if hasattr(entry, 'doi'):
        return entry.doi

    return None


def fetch_by_date(
    start_date: str,
    end_date: str,
    journals: List[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    按日期范围获取论文（兼容 arxiv-fetcher 接口）

    Args:
        start_date: 开始日期 (YYYYMMDD)
        end_date: 结束日期 (YYYYMMDD)
        journals: 期刊列表
        limit: 总数量限制

    Returns:
        论文列表
    """
    if journals is None:
        journals = ["nature", "science", "cell"]

    try:
        start_dt = datetime.strptime(start_date, "%Y%m%d")
        end_dt = datetime.strptime(end_date, "%Y%m%d")
    except ValueError:
        start_dt = None
        end_dt = None

    window_days = 30
    if start_dt and end_dt:
        if start_dt > end_dt:
            start_dt, end_dt = end_dt, start_dt
        window_days = max(1, (end_dt - start_dt).days + 1)

    all_papers = []
    limit_per_journal = max(limit // len(journals), 10)

    for journal in journals:
        papers = fetch_journal_papers(
            journal=journal,
            limit=limit_per_journal,
            days=window_days
        )
        all_papers.extend(papers)

    # 去重（基于 DOI 或 title）
    seen = set()
    unique_papers = []
    for paper in all_papers:
        key = paper.get('doi') or paper.get('title')
        if key and key not in seen:
            seen.add(key)
            unique_papers.append(paper)

    # 限制总数
    return unique_papers[:limit]


def get_recent_papers(
    days: int = 7,
    journals: List[str] = None,
    limit_per_journal: int = 20
) -> List[Dict[str, Any]]:
    """
    获取最近 N 天的论文

    Args:
        days: 最近 N 天
        journals: 期刊列表
        limit_per_journal: 每个期刊的数量限制

    Returns:
        论文列表
    """
    if journals is None:
        journals = ["nature", "science", "cell"]

    normalized_journals = []
    for journal in journals:
        normalized = normalize_journal_name(journal)
        if not normalized:
            print(f"Skipping unsupported journal source: {journal}")
            continue
        normalized_journals.append(normalized)

    all_papers = []

    for journal in normalized_journals:
        papers = fetch_journal_papers(
            journal=journal,
            limit=limit_per_journal,
            days=days
        )
        all_papers.extend(papers)

    # 去重
    seen = set()
    unique_papers = []
    for paper in all_papers:
        key = paper.get('doi') or paper.get('title')
        if key and key not in seen:
            seen.add(key)
            unique_papers.append(paper)

    return unique_papers


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Journal Fetcher")
    parser.add_argument("--journal", type=str, default="nature", help="Journal name")
    parser.add_argument("--limit", type=int, default=20, help="Max papers to fetch")
    parser.add_argument("--days", type=int, default=7, help="Recent N days")
    parser.add_argument("--output", type=str, help="Output JSON file path")

    args = parser.parse_args()

    print(f"Fetching papers from {args.journal}...")

    papers = fetch_journal_papers(
        journal=args.journal,
        limit=args.limit,
        days=args.days
    )

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(papers)} papers to {args.output}")
    else:
        print(f"\nFetched {len(papers)} papers:")
        for i, paper in enumerate(papers[:5]):
            print(f"\n{i+1}. {paper.get('title', 'Unknown')[:60]}")
            print(f"   DOI: {paper.get('doi', 'N/A')}")
            print(f"   URL: {paper.get('url', 'N/A')}")

        if len(papers) > 5:
            print(f"\n... and {len(papers) - 5} more")
