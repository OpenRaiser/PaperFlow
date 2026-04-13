#!/usr/bin/env python3
"""
OpenReview Fetcher - 会议论文抓取

支持会议：
- ICLR (International Conference on Learning Representations)
- NeurIPS (Neural Information Processing Systems)
- ICML (International Conference on Machine Learning)
- ACL (Association for Computational Linguistics)
- EMNLP (Empirical Methods in Natural Language Processing)

数据源：OpenReview API v2 / CVF / ECVA / DBLP
"""

import sys
import os
import json
import time
import re
import html
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import openreview
    from openreview.api import OpenReviewClient
    OPENREVIEW_AVAILABLE = True
except ImportError:
    OPENREVIEW_AVAILABLE = False
    OpenReviewClient = None  # Placeholder for type hints
    print("Warning: openreview-py not installed. Install with: pip install openreview-py")

# API v2 基础 URL
OPENREVIEW_BASE = "https://api2.openreview.net"
CVF_OPENACCESS_BASE = "https://openaccess.thecvf.com"
ECVA_BASE = "https://www.ecva.net"
DBLP_PUBL_SEARCH_API = "https://dblp.org/search/publ/api"

# 会议数据映射（Venue IDs）
CONFERENCE_MAP = {
    "iclr": {"venue_id": "ICLR.cc", "name": "ICLR", "source_type": "openreview"},
    "neurips": {"venue_id": "NeurIPS.cc", "name": "NeurIPS", "source_type": "openreview"},
    "icml": {"venue_id": "ICML.cc", "name": "ICML", "source_type": "openreview"},
    "acl": {"venue_id": "ACL.org", "name": "ACL", "source_type": "openreview"},
    "emnlp": {"venue_id": "EMNLP", "name": "EMNLP", "source_type": "openreview"},
    "cvpr": {
        "name": "CVPR",
        "source_type": "cvf",
        "cvf_code": "CVPR",
        "approx_publish_month": 2,
        "approx_publish_day": 28,
    },
    "iccv": {
        "name": "ICCV",
        "source_type": "cvf",
        "cvf_code": "ICCV",
        "approx_publish_month": 7,
        "approx_publish_day": 31,
    },
    "eccv": {
        "name": "ECCV",
        "source_type": "ecva",
        "approx_publish_month": 9,
        "approx_publish_day": 30,
    },
    "acmmm": {
        "name": "ACM MM",
        "source_type": "dblp_toc",
        "dblp_toc_template": "db/conf/mm/mm{year}.bht",
        "approx_publish_month": 10,
        "approx_publish_day": 27,
    },
}

CONFERENCE_ALIASES = {
    "iclr": "iclr",
    "icml": "icml",
    "neurips": "neurips",
    "nips": "neurips",
    "cvpr": "cvpr",
    "iccv": "iccv",
    "eccv": "eccv",
    "acl": "acl",
    "emnlp": "emnlp",
    "acmmm": "acmmm",
    "acmmultimedia": "acmmm",
}

SUBMISSION_INVITATION_SUFFIXES = (
    "Submission",
    "Blind_Submission",
)

_CLIENT_CACHE: Dict[str, Optional[OpenReviewClient]] = {}
_CLIENT_RETRY_AFTER: float = 0.0


def normalize_conference_name(name: str) -> Optional[str]:
    """Normalize free-form conference names into supported OpenReview keys."""
    condensed = re.sub(r"[^a-z0-9]+", "", str(name or "").strip().lower())
    if not condensed:
        return None
    return CONFERENCE_ALIASES.get(condensed)


def get_supported_conferences() -> List[str]:
    """Return supported conference keys in stable order."""
    return list(CONFERENCE_MAP.keys())


def allow_mock_papers() -> bool:
    """Only allow synthetic conference papers when explicitly enabled."""
    value = os.environ.get("SCITASTE_ALLOW_MOCK_PAPERS", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_client() -> Optional[OpenReviewClient]:
    """获取 OpenReview API v2 客户端"""
    global _CLIENT_RETRY_AFTER

    if not OPENREVIEW_AVAILABLE:
        return None

    if _CLIENT_RETRY_AFTER and time.time() < _CLIENT_RETRY_AFTER:
        return None

    username = os.environ.get("OPENREVIEW_USERNAME", "")
    password = os.environ.get("OPENREVIEW_PASSWORD", "")
    token = os.environ.get("OPENREVIEW_TOKEN", "")
    cache_key = f"{username}|{token}"

    if cache_key in _CLIENT_CACHE:
        return _CLIENT_CACHE[cache_key]

    if not username or not password:
        if token:
            # 使用 token 直接创建客户端
            client = OpenReviewClient(
                baseurl=OPENREVIEW_BASE,
                token=token
            )
            _CLIENT_CACHE[cache_key] = client
            return client
        else:
            print("Warning: OPENREVIEW_USERNAME or OPENREVIEW_PASSWORD not set.")
            print("Set credentials in .env file for full API access.")
            _CLIENT_CACHE[cache_key] = None
            return None

    try:
        client = OpenReviewClient(
            baseurl=OPENREVIEW_BASE,
            username=username,
            password=password
        )
        print("OpenReview API v2 client initialized")
        _CLIENT_CACHE[cache_key] = client
        return client
    except Exception as e:
        error_text = str(e)
        if "RateLimitError" in error_text or "Too many requests" in error_text:
            _CLIENT_RETRY_AFTER = time.time() + 30
        print(f"OpenReview client initialization error: {e}")
        _CLIENT_CACHE[cache_key] = None
        return None


def _build_submission_invitations(conference: str, year: int) -> List[str]:
    """Build likely submission invitation IDs for a conference/year pair."""
    normalized = normalize_conference_name(conference)
    if not normalized:
        return []
    venue_info = CONFERENCE_MAP[normalized]
    if venue_info.get("source_type") != "openreview":
        return []
    venue_root = f"{venue_info['venue_id']}/{year}/Conference"
    return [f"{venue_root}/-/{suffix}" for suffix in SUBMISSION_INVITATION_SUFFIXES]


def _clean_html_text(fragment: str) -> str:
    """Convert a short HTML fragment into plain readable text."""
    if not fragment:
        return ""
    text = re.sub(r"<[^>]+>", " ", fragment)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _split_authors(authors_text: str) -> List[str]:
    """Split author strings and drop lightweight presenter/corresponding markers."""
    authors = []
    for raw_name in str(authors_text or "").split(","):
        name = re.sub(r"\s*\*+$", "", raw_name).strip()
        if name:
            authors.append(name)
    return authors


def _http_get_text(url: str, timeout: int = 60, attempts: int = 3) -> requests.Response:
    """Fetch a text page with a couple of retries for flaky conference hosts."""
    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        except Exception as e:
            last_error = e
            if attempt >= attempts:
                break
            time.sleep(min(2, attempt))

    if last_error:
        raise last_error
    raise RuntimeError(f"Failed to fetch URL: {url}")


def _approx_conference_publish_date(conference: str, year: int) -> str:
    """Approximate a release date for proceedings sources without per-paper timestamps."""
    info = CONFERENCE_MAP[conference]
    month = int(info.get("approx_publish_month", 1))
    day = int(info.get("approx_publish_day", 1))
    try:
        return datetime(year, month, day).isoformat()
    except ValueError:
        return datetime(year, month, 1).isoformat()


def _fetch_cvf_detail(detail_url: str, title: str, venue_name: str, conference: str, year: int) -> Dict[str, Any]:
    """Fetch abstract/pdf/authors from an official CVF paper detail page."""
    try:
        response = _http_get_text(detail_url, timeout=60)
        detail_html = response.text
    except Exception as e:
        print(f"  Error fetching CVF detail page: {type(e).__name__}")
        return {
            "title": title,
            "abstract": "",
            "authors": [],
            "venue": venue_name,
            "publish_date": _approx_conference_publish_date(conference, year),
            "categories": [conference],
            "pdf_url": None,
            "cvf_url": detail_url,
        }

    authors_match = re.search(r'<div id="authors">(.*?)</div>', detail_html, re.I | re.S)
    authors_text = _clean_html_text(authors_match.group(1)) if authors_match else ""
    authors_text = authors_text.split("; Proceedings", 1)[0].strip()
    authors = _split_authors(authors_text)

    abstract_match = re.search(r'<div id="abstract">(.*?)</div>', detail_html, re.I | re.S)
    abstract = _clean_html_text(abstract_match.group(1)) if abstract_match else ""

    pdf_match = re.search(r'<a href="([^"]+\.pdf)">pdf</a>', detail_html, re.I)
    pdf_url = urljoin(CVF_OPENACCESS_BASE, pdf_match.group(1)) if pdf_match else None

    return {
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "venue": venue_name,
        "publish_date": _approx_conference_publish_date(conference, year),
        "categories": [conference],
        "pdf_url": pdf_url,
        "cvf_url": detail_url,
    }


def _search_cvf_papers(conference: str, year: int, limit: int) -> List[Dict[str, Any]]:
    """Fetch papers from the official CVF Open Access repository."""
    info = CONFERENCE_MAP[conference]
    index_url = f"{CVF_OPENACCESS_BASE}/{info['cvf_code']}{year}?day=all"

    try:
        response = requests.get(index_url, timeout=60)
        if response.status_code == 404:
            print(f"No CVF open access page found for {info['name']} {year}")
            return []
        response.raise_for_status()
        index_html = response.text
    except Exception as e:
        print(f"CVF open access error for {info['name']} {year}: {type(e).__name__}")
        return []

    blocks = re.findall(r'<dt class="ptitle">.*?</dd>', index_html, re.I | re.S)
    papers: List[Dict[str, Any]] = []

    for block in blocks[:limit]:
        title_match = re.search(r'<a href="([^"]+_paper\.html)">(.+?)</a>', block, re.I | re.S)
        if not title_match:
            continue

        detail_url = urljoin(CVF_OPENACCESS_BASE, title_match.group(1))
        title = _clean_html_text(title_match.group(2))
        papers.append(
            _fetch_cvf_detail(
                detail_url=detail_url,
                title=title,
                venue_name=info["name"],
                conference=conference,
                year=year,
            )
        )

    print(f"Fetched {len(papers)} papers from official CVF page for {info['name']} {year}")
    return papers


def _fetch_ecva_detail(
    detail_url: str,
    title: str,
    authors: List[str],
    venue_name: str,
    conference: str,
    year: int,
    pdf_url: Optional[str],
) -> Dict[str, Any]:
    """Fetch abstract and metadata from an official ECVA paper detail page."""
    try:
        response = _http_get_text(detail_url, timeout=60)
        detail_html = response.text
    except Exception as e:
        print(f"  Error fetching ECVA detail page: {type(e).__name__}")
        return {
            "title": title,
            "abstract": "",
            "authors": authors,
            "venue": venue_name,
            "publish_date": _approx_conference_publish_date(conference, year),
            "categories": [conference],
            "pdf_url": pdf_url,
            "ecva_url": detail_url,
        }

    authors_match = re.search(r'<div id="authors">(.*?)</div>', detail_html, re.I | re.S)
    authors_text = _clean_html_text(authors_match.group(1)) if authors_match else ""
    authors_text = authors_text.split(";", 1)[0].strip()
    parsed_authors = _split_authors(authors_text) or authors

    abstract_match = re.search(r'<div id="abstract">(.*?)</div>', detail_html, re.I | re.S)
    abstract = _clean_html_text(abstract_match.group(1)) if abstract_match else ""
    abstract = abstract.strip().strip('"').strip()

    return {
        "title": title,
        "abstract": abstract,
        "authors": parsed_authors,
        "venue": venue_name,
        "publish_date": _approx_conference_publish_date(conference, year),
        "categories": [conference],
        "pdf_url": pdf_url,
        "ecva_url": detail_url,
    }


def _search_ecva_papers(conference: str, year: int, limit: int) -> List[Dict[str, Any]]:
    """Fetch ECCV papers from the official ECVA papers page."""
    info = CONFERENCE_MAP[conference]
    index_url = f"{ECVA_BASE}/papers.php"

    try:
        response = _http_get_text(index_url, timeout=60)
        index_html = response.text
    except Exception as e:
        print(f"ECVA papers index error for {info['name']} {year}: {type(e).__name__}")
        return []

    marker = f"ECCV {year} Papers"
    start_idx = index_html.find(marker)
    if start_idx == -1:
        print(f"No ECVA papers section found for {info['name']} {year}")
        return []

    section_html = index_html[start_idx:]
    next_section_idx = section_html.find('<button class="accordion"', len(marker))
    if next_section_idx != -1:
        section_html = section_html[:next_section_idx]

    entry_pattern = re.compile(
        r'<dt class="ptitle">\s*<br>\s*<a href=([^\s>]+)>(.*?)</a>\s*</dt>\s*'
        r'<dd>(.*?)</dd>\s*<dd>(.*?)</dd>',
        re.I | re.S,
    )
    papers: List[Dict[str, Any]] = []

    for detail_rel, title_html, authors_html, links_html in entry_pattern.findall(section_html):
        title = _clean_html_text(title_html)
        authors = _split_authors(_clean_html_text(authors_html))
        pdf_matches = re.findall(r"href=['\"]([^'\"]+\.pdf)['\"]", links_html, re.I)
        pdf_url = None
        for candidate in pdf_matches:
            if "-supp" not in candidate.lower():
                pdf_url = urljoin(ECVA_BASE, candidate)
                break
        if not pdf_url and pdf_matches:
            pdf_url = urljoin(ECVA_BASE, pdf_matches[0])

        papers.append(
            _fetch_ecva_detail(
                detail_url=urljoin(ECVA_BASE, detail_rel),
                title=title,
                authors=authors,
                venue_name=info["name"],
                conference=conference,
                year=year,
                pdf_url=pdf_url,
            )
        )
        if len(papers) >= limit:
            break

    print(f"Fetched {len(papers)} papers from official ECVA page for {info['name']} {year}")
    return papers


def _normalize_dblp_author(author_entry: Any) -> str:
    """Strip DBLP disambiguation suffixes such as '0001' from author labels."""
    if isinstance(author_entry, dict):
        value = author_entry.get("text", "")
    else:
        value = str(author_entry or "")
    value = re.sub(r"\s+\d{4}$", "", value).strip()
    return value


def _extract_dblp_authors(raw_authors: Any) -> List[str]:
    """Normalize DBLP author payloads into a simple name list."""
    if isinstance(raw_authors, dict):
        raw_authors = raw_authors.get("author", [])
    if isinstance(raw_authors, list):
        return [name for name in (_normalize_dblp_author(item) for item in raw_authors) if name]
    normalized = _normalize_dblp_author(raw_authors)
    return [normalized] if normalized else []


def _parse_page_count(pages: Any) -> Optional[int]:
    """Parse a DBLP page range like '123-130' into a page count."""
    match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", str(pages or ""))
    if not match:
        return None
    start_page = int(match.group(1))
    end_page = int(match.group(2))
    if end_page < start_page:
        return None
    return (end_page - start_page) + 1


def _looks_like_acmmm_regular_paper(paper_info: Dict[str, Any]) -> bool:
    """Heuristically suppress workshop/demo/tutorial metadata entries in ACM MM proceedings."""
    title = _clean_html_text(paper_info.get("title", ""))
    lowered = title.lower()

    if not title:
        return False

    non_paper_markers = (
        " workshop ",
        "workshop on ",
        " international workshop ",
        " tutorial",
        " doctoral symposium",
        " grand challenge",
        " competition",
        " demo track",
        " demonstration",
        " panel",
        " keynote",
        " opening remarks",
        " closing remarks",
        " welcome message",
        " message from ",
        " organizer",
    )
    padded = f" {lowered} "
    if any(marker in padded for marker in non_paper_markers):
        return False

    if re.match(r"^[a-z0-9&+./ \-]+'?\d{2}\s*:", lowered) and "workshop" in lowered:
        return False

    page_count = _parse_page_count(paper_info.get("pages"))
    if page_count is not None and page_count <= 2 and len(_extract_dblp_authors(paper_info.get("authors"))) <= 2:
        return False

    return True


def _search_dblp_toc_papers(conference: str, year: int, limit: int) -> List[Dict[str, Any]]:
    """Fetch proceedings entries from DBLP's public TOC API."""
    info = CONFERENCE_MAP[conference]
    toc_key = info["dblp_toc_template"].format(year=year)
    fetch_limit = min(max(limit * 5, 50), 200)
    url = f"{DBLP_PUBL_SEARCH_API}?q=toc:{toc_key}:&h={fetch_limit}&format=json"

    try:
        response = _http_get_text(url, timeout=60)
        payload = response.json()
    except Exception as e:
        print(f"DBLP proceedings error for {info['name']} {year}: {type(e).__name__}")
        return []

    hits = payload.get("result", {}).get("hits", {}).get("hit", [])
    if isinstance(hits, dict):
        hits = [hits]

    papers: List[Dict[str, Any]] = []
    for hit in hits:
        paper_info = hit.get("info", {})
        if conference == "acmmm" and not _looks_like_acmmm_regular_paper(paper_info):
            continue
        title = _clean_html_text(paper_info.get("title", ""))
        record_url = paper_info.get("url") or ""
        papers.append(
            {
                "title": title,
                "abstract": "",
                "authors": _extract_dblp_authors(paper_info.get("authors")),
                "venue": paper_info.get("venue") or info["name"],
                "publish_date": _approx_conference_publish_date(conference, year),
                "categories": [conference],
                "pdf_url": paper_info.get("ee") if str(paper_info.get("ee", "")).lower().endswith(".pdf") else None,
                "doi_url": paper_info.get("ee"),
                "dblp_url": record_url if str(record_url).startswith("http") else "",
            }
        )
        if len(papers) >= limit:
            break

    print(f"Fetched {len(papers)} papers from DBLP proceedings TOC for {info['name']} {year}")
    return papers


def _extract_note_value(value: Any, default: Any = "") -> Any:
    """Normalize OpenReview content fields that may be raw values or {'value': ...} objects."""
    if isinstance(value, dict):
        if "value" in value:
            return value.get("value", default)
        return default
    return value if value is not None else default


def _parse_date(value: str) -> Optional[date]:
    """Parse YYYYMMDD / YYYY-MM-DD strings into date objects."""
    normalized = (value or "").strip()
    if not normalized:
        return None

    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    return None


def _infer_years_from_range(start_date: str, end_date: str) -> List[int]:
    """Infer candidate conference years from a date range."""
    parsed_start = _parse_date(start_date)
    parsed_end = _parse_date(end_date)

    if not parsed_start and not parsed_end:
        return [datetime.now().year]

    if not parsed_start:
        parsed_start = parsed_end
    if not parsed_end:
        parsed_end = parsed_start

    if parsed_start > parsed_end:
        parsed_start, parsed_end = parsed_end, parsed_start

    return list(range(parsed_end.year, parsed_start.year - 1, -1))


def _paper_in_date_range(paper: Dict[str, Any], start_date: Optional[date], end_date: Optional[date]) -> bool:
    """Check whether a paper publish_date falls within the requested date range."""
    publish_date = paper.get("publish_date")
    if not publish_date:
        return True

    try:
        paper_date = datetime.fromisoformat(str(publish_date).replace("Z", "+00:00")).date()
    except ValueError:
        return True

    if start_date and paper_date < start_date:
        return False
    if end_date and paper_date > end_date:
        return False
    return True


def search_papers(
    query: str = "",
    conference: str = "iclr",
    year: int = 2024,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    搜索会议论文（使用 OpenReview API v2）

    Args:
        query: 搜索关键词
        conference: 会议名称
        year: 年份
        limit: 最大论文数

    Returns:
        论文列表
    """
    normalized_conference = normalize_conference_name(conference)

    if not normalized_conference:
        print(f"Conference source not supported by OpenReview fetcher: {conference}")
        return []

    conference_info = CONFERENCE_MAP[normalized_conference]
    if conference_info.get("source_type") == "cvf":
        return _search_cvf_papers(normalized_conference, year, limit)
    if conference_info.get("source_type") == "ecva":
        return _search_ecva_papers(normalized_conference, year, limit)
    if conference_info.get("source_type") == "dblp_toc":
        return _search_dblp_toc_papers(normalized_conference, year, limit)

    papers = []
    client = get_client()

    if not client:
        if allow_mock_papers():
            print("Using mock data (OpenReview unavailable and SCITASTE_ALLOW_MOCK_PAPERS enabled)")
            return _get_mock_papers(normalized_conference, year, limit)
        print("OpenReview unavailable or not configured; skipping conference fetch.")
        return []

    venue_info = conference_info
    invitations = _build_submission_invitations(normalized_conference, year)

    try:
        notes = []
        used_invitation = None
        for invitation in invitations:
            notes = client.get_notes(
                invitation=invitation,
                limit=limit
            )
            if notes:
                used_invitation = invitation
                break

        if not notes:
            print(f"No OpenReview notes found for {conference.upper()} {year} using invitations: {invitations}")
            return []

        for note in notes:
            try:
                title = _extract_note_value(note.content.get("title"), "Unknown Title")
                abstract = _extract_note_value(note.content.get("abstract"), "")
                authors = _extract_note_value(note.content.get("authors"), [])
                paper = {
                    "title": title,
                    "abstract": abstract,
                    "authors": authors if isinstance(authors, list) else [str(authors)],
                    "venue": venue_info["name"],
                    "openreview_id": note.id,
                    "openreview_url": f"https://openreview.net/forum?id={note.id}",
                    "publish_date": datetime.fromtimestamp(note.cdate / 1000).isoformat() if note.cdate else datetime.now().isoformat(),
                    "categories": [normalized_conference],
                    "pdf_url": f"https://openreview.net/pdf?id={note.id}" if note.id else None,
                }
                papers.append(paper)
            except Exception as e:
                print(f"  Error processing note: {e}")
                continue

        print(f"Fetched {len(papers)} papers from {used_invitation}")

    except Exception as e:
        print(f"OpenReview API error: {e}")
        if allow_mock_papers():
            print("Falling back to mock data")
            papers = _get_mock_papers(normalized_conference, year, limit)
        else:
            print("Mock papers disabled; returning no conference papers.")
            papers = []

    return papers


def _get_mock_papers(conference: str, year: int, limit: int) -> List[Dict[str, Any]]:
    """获取模拟数据（当 API 不可用时）"""
    papers = []

    for i in range(min(limit, 10)):
        paper = {
            "title": f"[{conference.upper()} {year}] Sample Paper {i+1}",
            "abstract": f"This is a sample abstract for paper {i+1} from {conference.upper()} {year}.",
            "authors": [f"Author {i+1}", f"Author {i+2}"],
            "venue": conference.upper(),
            "openreview_id": f"{conference}_{year}_{i+1}",
            "openreview_url": f"https://openreview.net/forum?id={conference}_{year}_{i+1}",
            "publish_date": datetime.now().isoformat(),
            "categories": [conference.lower()],
            "pdf_url": None,
        }
        papers.append(paper)

    return papers


def get_conference_papers(
    conference: str = "iclr",
    year: int = 2024,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """获取特定会议的论文"""
    return search_papers(
        conference=conference,
        year=year,
        limit=limit
    )


def get_recent_papers(
    days: int = 7,
    conferences: List[str] = None,
    limit_per_conference: int = 50,
    years: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """获取最近 N 天的论文"""
    if conferences is None:
        conferences = ["iclr", "neurips", "icml"]
    if years is None:
        years = [datetime.now().year]

    all_papers = []

    for conf in conferences:
        conference_papers = []
        for year in years:
            remaining = limit_per_conference - len(conference_papers)
            if remaining <= 0:
                break

            print(f"Fetching {conf.upper()} papers for {year}...")
            papers = get_conference_papers(
                conference=conf,
                year=year,
                limit=remaining
            )
            conference_papers.extend(papers)
            print(f"  Fetched {len(papers)} papers from {conf.upper()} {year}")

        all_papers.extend(conference_papers[:limit_per_conference])

    # 去重
    seen_titles = set()
    unique_papers = []
    for paper in all_papers:
        title = paper.get("title", "")
        if title and title not in seen_titles:
            seen_titles.add(title)
            unique_papers.append(paper)

    return unique_papers


def fetch_by_date(
    start_date: str,
    end_date: str,
    conferences: List[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """按日期范围获取论文（兼容 arxiv-fetcher 接口）"""
    if conferences is None:
        conferences = ["iclr", "neurips", "icml"]

    parsed_start = _parse_date(start_date)
    parsed_end = _parse_date(end_date)
    inferred_years = _infer_years_from_range(start_date, end_date)
    per_conference_limit = max(1, limit // max(len(conferences), 1))

    papers = get_recent_papers(
        days=30,
        conferences=conferences,
        limit_per_conference=per_conference_limit,
        years=inferred_years,
    )

    filtered = [
        paper for paper in papers
        if _paper_in_date_range(paper, parsed_start, parsed_end)
    ]

    return filtered[:limit]


if __name__ == "__main__":
    import argparse

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="OpenReview Fetcher")
    parser.add_argument("--conference", type=str, default="iclr", help="Conference name")
    parser.add_argument("--year", type=int, default=2024, help="Conference year")
    parser.add_argument("--limit", type=int, default=50, help="Max papers to fetch")
    parser.add_argument("--output", type=str, help="Output JSON file path")

    args = parser.parse_args()

    print(f"Fetching papers from {args.conference.upper()} {args.year}...")
    print(f"OpenReview client library available: {OPENREVIEW_AVAILABLE}")

    papers = get_conference_papers(
        conference=args.conference,
        year=args.year,
        limit=args.limit
    )

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(papers)} papers to {args.output}")
    else:
        print(f"\nFetched {len(papers)} papers:")
        for i, paper in enumerate(papers[:5]):
            source_url = (
                paper.get("openreview_url")
                or paper.get("cvf_url")
                or paper.get("ecva_url")
                or paper.get("dblp_url")
                or paper.get("doi_url")
                or paper.get("pdf_url")
            )
            print(f"\n{i+1}. {paper.get('title', 'Unknown')[:60]}")
            print(f"   URL: {source_url}")

        if len(papers) > 5:
            print(f"\n... and {len(papers) - 5} more")
