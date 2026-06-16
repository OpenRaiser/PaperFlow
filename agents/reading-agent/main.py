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
import hashlib
import shutil
import tempfile
import inspect
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Any, Tuple
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import requests
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

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 使用 importlib 导入带连字符的模块
import importlib

# 飞书报告器
feishu_reporter = importlib.import_module("deployments.feishu.feishu-reporter.scripts.feishu_reporter")
create_doc = feishu_reporter.create_doc
send_text = feishu_reporter.send_text
get_drive_meta = getattr(feishu_reporter, "get_drive_meta", None)
direction_lexicon = importlib.import_module("config.direction_lexicon")

# 数据库操作
db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
get_profile = db_ops.get_profile
update_profile = db_ops.update_profile
log_behavior = db_ops.log_behavior
get_latest_push = getattr(db_ops, "get_latest_push", lambda user_id: None)
get_push_papers = getattr(db_ops, "get_push_papers", lambda push_id: None)
get_existing_reading_reports_for_papers = getattr(
    db_ops,
    "get_existing_reading_reports_for_papers",
    lambda user_id, paper_ids: {},
)
get_recent_created_report_by_source = getattr(
    db_ops,
    "get_recent_created_report_by_source",
    lambda user_id, source_type, source_key, days=30: None,
)
profile_updater = importlib.import_module("skills.profile-updater.scripts.update_profile")
ensure_profile_schema = profile_updater.ensure_profile_schema
update_profile_with_reading_signal = profile_updater.update_profile_with_reading_signal
role_utils = importlib.import_module("paperflow.roles")
try:
    wiki_reading_ingest = importlib.import_module("agents.wiki-agent.ingest.from_reading_report")
except Exception:
    wiki_reading_ingest = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PDF_DOWNLOAD_TIMEOUT = float(os.environ.get("READING_REPORT_PDF_TIMEOUT", "60"))
ARXIV_DETAIL_TIMEOUT = float(os.environ.get("READING_REPORT_ARXIV_TIMEOUT", "12"))
MAX_ABSTRACT_CHARS = int(os.environ.get("READING_REPORT_ABSTRACT_CHARS", "1200"))
MAX_SECTION_CHARS = int(os.environ.get("READING_REPORT_SECTION_CHARS", "1800"))
READING_REPORT_CHUNK_CHARS = int(os.environ.get("READING_REPORT_CHUNK_CHARS", "1200"))
READING_REPORT_CHUNK_OVERLAP = int(os.environ.get("READING_REPORT_CHUNK_OVERLAP", "180"))
READING_REPORT_EVIDENCE_TOP_K = int(os.environ.get("READING_REPORT_EVIDENCE_TOP_K", "3"))
READING_REPORT_EVIDENCE_VERSION = (
    os.environ.get("READING_REPORT_EVIDENCE_VERSION", "2026-04-27-v4").strip()
    or "2026-04-27-v4"
)
READING_REPORT_EVIDENCE_CACHE_ENABLED = os.environ.get("READING_REPORT_EVIDENCE_CACHE_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}
READING_REPORT_OUTPUT_VERSION = os.environ.get("READING_REPORT_OUTPUT_VERSION", "2026-06-04-v5").strip() or "2026-06-04-v5"
READING_REPORT_PROFILE_RETRIEVAL_WEIGHT = float(os.environ.get("READING_REPORT_PROFILE_RETRIEVAL_WEIGHT", "0.25"))
HTTP_RETRY_TOTAL = int(os.environ.get("PAPERFLOW_HTTP_RETRIES", "2"))
HTTP_RETRY_BACKOFF = float(os.environ.get("PAPERFLOW_HTTP_BACKOFF", "0.8"))


def _normalize_response_language(value: Any = None) -> str:
    raw = str(value or "").strip().lower().replace("_", "-")
    return "en" if raw.startswith("en") or raw == "english" else "zh"


MONTH_LABELS = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sept",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}

DAILY_NOTE_CATEGORY_OPTIONS = [
    "On-Policy Distillation & Post-Training",
    "Multimodal Models & Visual Reasoning",
    "Reward Models & Reinforcement Learning",
    "Data, Benchmarking & Evaluation",
    "World Models, Generation & Audio",
    "Research Agents & Scientific Discovery",
    "Web, GUI & Computer-Use Agents",
    "Agent Skills, Harness & Tooling",
    "Memory, Personalization & Long-Horizon Agents",
    "AI for Science & Biology",
    "Foundation AI & AGI",
    "AI for Education",
    "Language Models",
    "Machine Learning",
    "AI Agents",
    "AI Research",
]

DAILY_NOTE_CLASSIFICATION_PROMPT = """You are PaperFlow's Daily Note curator.

Your task is to review a monthly Daily Note after a new deep-reading paper has
been inserted. Assign every paper to exactly one category from the allowed list.

Rules:
- Return JSON only.
- Use only category names from allowed_categories.
- Preserve every paper marker exactly.
- Do not invent papers or remove papers.
- Prefer specific research themes over broad buckets.
- If a paper crosses multiple areas, choose the category most useful for later retrieval.
- Use user_profile as the user's research context when two categories are both plausible.

Expected JSON:
{
  "assignments": [
    {"marker": "<!-- paperflow:... -->", "category": "Allowed Category"}
  ]
}
"""


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "off", "no", ""}


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int = 16) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw) if raw else int(default)
    except (TypeError, ValueError):
        value = int(default)
    return max(minimum, min(maximum, value))


def _reading_report_concurrency_limit(task_count: int) -> int:
    configured = _env_int(
        "PAPERFLOW_READING_REPORT_CONCURRENCY",
        _env_int("PAPERFLOW_MAX_CONCURRENCY", 3, minimum=1, maximum=8),
        minimum=1,
        maximum=8,
    )
    return max(1, min(int(task_count or 1), configured))


def _resolve_configured_dir(
    env_name: str,
    default_relative: str,
    paper: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    category: str = "",
) -> Path:
    configured = os.environ.get(env_name, "").strip()
    base_dir = Path(configured).expanduser() if configured else PROJECT_ROOT / default_relative
    if not base_dir.is_absolute():
        base_dir = PROJECT_ROOT / base_dir
    if user_id and not configured:
        base_dir = role_utils.apply_output_scope(
            base_dir,
            user_id,
            category=category,
            project_root=PROJECT_ROOT,
        )
    obsidian_dir = _obsidian_month_dir(base_dir, paper or {}, category)
    if obsidian_dir is not None:
        obsidian_dir.mkdir(parents=True, exist_ok=True)
        return obsidian_dir.resolve()
    if _env_flag("PAPERFLOW_STORAGE_MONTHLY_SUBDIR", default=True):
        base_dir = base_dir / _month_folder_name(paper or {})
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir.resolve()


def _parse_publish_month(paper: Dict[str, Any]) -> datetime:
    for key in ("publish_date", "published", "updated", "created_at", "fetched_at"):
        raw = _clean_text(paper.get(key))
        if not raw:
            continue
        for fmt, width in (("%Y-%m-%d", 10), ("%Y/%m/%d", 10), ("%Y-%m", 7), ("%Y/%m", 7)):
            try:
                return datetime.strptime(raw[:width], fmt)
            except ValueError:
                continue
        match = re.search(r"(20\d{2})[-/](\d{1,2})", raw)
        if match:
            year = int(match.group(1))
            month = max(1, min(12, int(match.group(2))))
            return datetime(year, month, 1)
    return datetime.now()


def _month_folder_name(paper: Dict[str, Any]) -> str:
    date = _parse_publish_month(paper)
    return f"arXiv - {MONTH_LABELS.get(date.month, date.strftime('%b'))} {date.year}"


def _daily_note_folder_name(paper: Dict[str, Any]) -> str:
    date = _parse_publish_month(paper)
    return f"Daily Note {date.year}"


def _daily_note_file_name(paper: Dict[str, Any]) -> str:
    date = _parse_publish_month(paper)
    return f"Daily Note - {MONTH_LABELS.get(date.month, date.strftime('%b'))} {date.year}.md"


def _deep_reading_folder_name(paper: Dict[str, Any]) -> str:
    date = _parse_publish_month(paper)
    return f"Deep Reading - {MONTH_LABELS.get(date.month, date.strftime('%b'))} {date.year}"


def _looks_like_obsidian_daily_root(path: Path) -> bool:
    name = path.name
    if name == "Daily Note":
        return True
    if re.fullmatch(r"Daily Note 20\d{2}", name):
        return True
    return any(path.glob("Daily Note 20[0-9][0-9]")) or any(path.glob("Daily Note - * 20[0-9][0-9].md"))


def _obsidian_year_dir(base_dir: Path, paper: Dict[str, Any]) -> Optional[Path]:
    if not _looks_like_obsidian_daily_root(base_dir):
        return None
    year_dir_name = _daily_note_folder_name(paper)
    if re.fullmatch(r"Daily Note 20\d{2}", base_dir.name):
        return base_dir
    return base_dir / year_dir_name


def _obsidian_month_dir(base_dir: Path, paper: Dict[str, Any], kind: str) -> Optional[Path]:
    year_dir = _obsidian_year_dir(base_dir, paper)
    if year_dir is None and kind in {"pdf", "reading_reports"} and _env_flag("PAPERFLOW_DAILY_NOTE_EXPORT", True):
        year_dir = base_dir / _daily_note_folder_name(paper)
    if year_dir is None:
        return None
    if kind == "pdf":
        return year_dir / _month_folder_name(paper)
    if kind == "reading_reports":
        return year_dir / _deep_reading_folder_name(paper)
    return None


def _safe_filename(value: Any, *, max_len: int = 120) -> str:
    text = _clean_text(value)
    text = re.sub(r"[\\/:*?\"<>|]+", "-", text)
    text = re.sub(r"\s+", " ", text).strip(" .-_")
    text = re.sub(r"[-_ ]{2,}", "-", text)
    return (text or "paper")[:max_len].strip(" .-_") or "paper"


def _paper_file_stem(paper: Dict[str, Any]) -> str:
    arxiv_id = _clean_text(paper.get("arxiv_id"))
    if arxiv_id:
        return _safe_filename(arxiv_id.replace("/", "-"))
    doi = _clean_text(paper.get("doi"))
    if doi:
        return "doi-" + _safe_filename(doi, max_len=110)
    title = _clean_text(paper.get("title"))
    if title:
        return _safe_filename(title)
    paper_id = _clean_text(paper.get("id"))
    return _safe_filename(paper_id or "paper")


def _paper_title_file_stem(paper: Dict[str, Any], *, max_len: int = 96) -> str:
    title = _clean_text(paper.get("title"))
    if title:
        return _safe_filename(title, max_len=max_len)
    return _paper_file_stem(paper)


def _wiki_ingest_enabled() -> bool:
    return os.environ.get("PAPERFLOW_WIKI_INGEST", "1").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


def ingest_reading_report_to_wiki(
    *,
    user_id: str,
    paper: Dict[str, Any],
    report_content: str,
    report_payload: Dict[str, Any],
    report_path: Optional[str] = None,
    doc_url: Optional[str] = None,
    doc_token: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Best-effort wiki ingestion hook for generated reading reports."""
    if not _wiki_ingest_enabled() or wiki_reading_ingest is None:
        return None
    try:
        return wiki_reading_ingest.ingest_reading_report(
            user_id=user_id,
            paper=paper,
            report_md=report_content,
            payload=report_payload,
            report_path=report_path,
            doc_url=doc_url,
            doc_token=doc_token,
        )
    except Exception as exc:
        print(f"  Wiki ingest skipped due to error: {exc}")
        return None
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

FEED_METADATA_PREFIX_RE = re.compile(
    r"^(?:"
    r"nature(?: communications| biotechnology| methods| machine intelligence| computational science)?"
    r"|science(?: advances)?"
    r"|cell"
    r"|pnas"
    r")\s*,\s*published online:\s*[^;]{1,160}(?:;\s*doi:\s*10\.\S+)?\s*",
    flags=re.I,
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


def _load_journal_fetcher():
    return importlib.import_module("skills.journal-fetcher.scripts.fetch_journal")


def _load_pdf_parser():
    return importlib.import_module("skills.pdf-parser.scripts.parse_pdf")


def _load_embedding_module():
    return importlib.import_module("skills.embedding.scripts.embed")


def _load_llm_parser():
    return importlib.import_module("agents.master-coordinator.scripts.llm_parser")


def _build_request_headers(*, referer: Optional[str] = None, accept_pdf: bool = False) -> Dict[str, str]:
    headers = dict(DEFAULT_REQUEST_HEADERS)
    if accept_pdf:
        headers["Accept"] = "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8"
    else:
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


def _http_get(
    url: str,
    *,
    timeout: float,
    referer: Optional[str] = None,
    accept_pdf: bool = False,
    allow_redirects: bool = True,
) -> requests.Response:
    session = _create_http_session()
    try:
        response = session.get(
            url,
            timeout=timeout,
            headers=_build_request_headers(referer=referer, accept_pdf=accept_pdf),
            allow_redirects=allow_redirects,
        )
        response.raise_for_status()
        return response
    finally:
        session.close()


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


def _strip_html_markup(text: Any) -> str:
    normalized = unescape(str(text or ""))
    normalized = re.sub(r"(?i)<br\s*/?>", "\n", normalized)
    normalized = re.sub(r"(?i)</p\s*>", "\n", normalized)
    normalized = re.sub(r"(?i)<p\b[^>]*>", "", normalized)
    normalized = re.sub(r"<[^>]+>", " ", normalized)
    normalized = normalized.replace("\xa0", " ")
    return _clean_text(normalized)


def _looks_like_feed_metadata_abstract(text: Any) -> bool:
    normalized = _strip_html_markup(text).lower()
    return bool(normalized and "published online:" in normalized)


def _clean_abstract_text(text: Any) -> str:
    normalized = _strip_html_markup(text)
    normalized = FEED_METADATA_PREFIX_RE.sub("", normalized).strip(" \n\t;,:-")
    return _clean_text(normalized)


def _clean_pdf_evidence_text(text: Any) -> str:
    """Remove common PDF extraction noise before retrieval/report synthesis."""
    normalized = _clean_text(text)
    if not normalized:
        return ""

    normalized = re.sub(r"(?<=\w)-\s+(?=\w)", "", normalized)
    normalized = re.sub(r"arXiv:\s*\d{4}\.\d{4,5}v?\d*(?:\s*\[[^\]]+\])?", " ", normalized, flags=re.I)

    clean_lines: List[str] = []
    for raw_line in normalized.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        lower = line.lower()
        if len(line) <= 2 and re.fullmatch(r"\d+", line):
            continue
        if lower.startswith(("fig.", "figure ", "table ", "algorithm ")):
            continue
        if "corresponding author" in lower or "this work was supported" in lower:
            continue
        if re.search(r"\b[\w.+-]+@[\w.-]+\.\w+\b", line):
            continue
        if re.search(r"\barxiv preprint arxiv:\d", lower):
            continue
        if re.search(r"\bin proceedings of\b|\bpages \d+\b|\bcvpr\b.*\bpages\b", lower):
            continue
        clean_lines.append(line)

    cleaned = _clean_text(" ".join(clean_lines))
    return re.sub(r"\s+", " ", cleaned).strip()


def _is_noisy_pdf_evidence_text(text: Any, *, min_chars: int = 40) -> bool:
    cleaned = _clean_text(text)
    if len(cleaned) < min_chars:
        return True
    alpha_count = len(re.findall(r"[A-Za-z]", cleaned))
    alpha_ratio = alpha_count / max(1, len(cleaned))
    if alpha_ratio < 0.45:
        return True

    lower = cleaned.lower()
    hard_noise_patterns = (
        "corresponding author",
        "this work was supported",
        "all rights reserved",
        "published as a conference paper",
        "arxiv preprint arxiv:",
        "references",
    )
    if any(pattern in lower for pattern in hard_noise_patterns):
        return True

    citation_like = len(re.findall(r"\[\d+\]|\bet al\.\b|\bpages?\s+\d+\b", lower))
    figure_like = len(re.findall(r"\bfig(?:ure)?\.?\s*\d+|\btable\s+\d+", lower))
    if citation_like + figure_like >= 4:
        return True

    symbol_count = len(re.findall(r"[=<>±∑√∞≈≠≤≥_{}^$\\]", cleaned))
    if symbol_count > 12 and symbol_count / max(1, len(cleaned)) > 0.03:
        return True

    return False


def _prefer_candidate_abstract(
    current_abstract: Any,
    candidate_abstract: Any,
    *,
    min_extra_chars: int = 40,
) -> bool:
    """Whether a candidate abstract is meaningfully better than the current one."""
    current_raw = current_abstract
    current_clean = _clean_abstract_text(current_raw)
    candidate_clean = _clean_abstract_text(candidate_abstract)

    if not candidate_clean:
        return False
    if not current_clean:
        return True
    if _looks_like_feed_metadata_abstract(current_raw):
        return True
    return len(candidate_clean) > len(current_clean) + min_extra_chars


def _truncate_text(text: Any, max_chars: int) -> str:
    normalized = _clean_text(text)
    if len(normalized) <= max_chars:
        return normalized
    clipped = normalized[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:") or normalized[: max_chars - 1]
    return f"{clipped}…"


def _split_sentences(text: Any) -> List[str]:
    normalized = _clean_pdf_evidence_text(text)
    if not normalized:
        return []

    parts = re.split(r"(?<=[。！？!?\.])\s+|(?<=;)\s+", normalized)
    sentences: List[str] = []
    for part in parts:
        sentence = re.sub(r"\s+", " ", part).strip()
        if len(sentence) >= 12 and not _is_noisy_pdf_evidence_text(sentence, min_chars=12):
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


def _preferred_evidence_top_k(user_profile: Dict[str, Any]) -> int:
    preferences = (user_profile or {}).get("report_preferences", {}) or {}
    try:
        preferred = int(preferences.get("preferred_evidence_top_k", READING_REPORT_EVIDENCE_TOP_K) or READING_REPORT_EVIDENCE_TOP_K)
    except (TypeError, ValueError):
        preferred = READING_REPORT_EVIDENCE_TOP_K
    return max(3, min(5, preferred))


def _describe_pdf_fallback(
    pdf_error: Optional[str],
    *,
    fallback_mode: str = "abstract",
    response_language: str = "zh",
) -> str:
    is_en = _normalize_response_language(response_language) == "en"
    lowered = _clean_text(pdf_error).lower()
    if not lowered:
        reason = "The PDF full text was unavailable" if is_en else "未能拿到 PDF 全文"
    elif "403" in lowered or "forbidden" in lowered:
        reason = "The source blocked PDF access" if is_en else "源站拒绝了 PDF 访问"
    elif "timed out" in lowered or "timeout" in lowered:
        reason = "PDF fetching timed out" if is_en else "PDF 抓取超时"
    elif "ssl" in lowered or "eof" in lowered or "connection" in lowered:
        reason = "The network connection was unstable while fetching the PDF" if is_en else "PDF 抓取时网络连接不稳定"
    elif "content-type" in lowered or "did not return a pdf" in lowered:
        reason = "The source did not return a PDF file directly" if is_en else "源站没有直接返回 PDF 文件"
    else:
        reason = "PDF fetching or parsing failed" if is_en else "PDF 抓取或解析失败"
    if is_en:
        if fallback_mode == "source_page":
            return (
                f"{reason}; this report fell back to the source page text and metadata. "
                "Verify method and experiment details in the original paper."
            )
        return (
            f"{reason}; this report fell back to the template, abstract, and metadata. "
            "Verify method and experiment details in the original paper."
        )
    if fallback_mode == "source_page":
        return f"{reason}，本次报告已回退为基于源站正文和元数据生成；方法与实验细节仍建议回原文核对。"
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


def _recommendation_display_label(label: str, response_language: str = "zh") -> str:
    normalized = _clean_text(label)
    if _normalize_response_language(response_language) != "en":
        return normalized
    return {
        "强烈推荐": "Strongly recommended",
        "推荐阅读": "Recommended",
        "值得快速浏览": "Worth a quick scan",
        "按需阅读": "Read if needed",
    }.get(normalized, normalized or "Recommended")


def _label_rank(label: str) -> int:
    mapping = {
        "按需阅读": 0,
        "值得快速浏览": 1,
        "推荐阅读": 2,
        "强烈推荐": 3,
    }
    return mapping.get(_clean_text(label), 1)


def _rank_label(rank: int) -> str:
    labels = ["按需阅读", "值得快速浏览", "推荐阅读", "强烈推荐"]
    return labels[max(0, min(int(rank), len(labels) - 1))]


def calibrate_recommendation_label(paper: Dict[str, Any], proposed_label: Any, analysis_source: Any = None) -> str:
    """Constrain reading-report recommendation labels to ranking/evaluation evidence."""
    system_label = _clean_text(paper.get("system_label") or paper.get("relevance_level"))
    oracle_label = _clean_text(paper.get("oracle_label"))
    analysis_source_text = _clean_text(analysis_source).lower()

    try:
        system_score = float(paper.get("system_score", paper.get("relevance_score", 0.0)) or 0.0)
    except (TypeError, ValueError):
        system_score = 0.0
    for score_key in ("score", "relevance", "ranking_score", "final_score"):
        try:
            candidate_score = float(paper.get(score_key, 0.0) or 0.0)
        except (TypeError, ValueError):
            candidate_score = 0.0
        system_score = max(system_score, candidate_score)
    try:
        oracle_score = float(paper.get("oracle_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        oracle_score = 0.0

    if system_label == "must_read" or oracle_label == "strong_relevant" or system_score >= 0.82 or oracle_score >= 0.72:
        max_rank = 3
        default_rank = 3
    elif system_label == "high_relevant" or oracle_label == "relevant" or system_score >= 0.62 or oracle_score >= 0.48:
        max_rank = 2
        default_rank = 2
    elif system_label == "maybe_interested" or oracle_label == "weak_relevant" or system_score >= 0.36 or oracle_score >= 0.25:
        max_rank = 1
        default_rank = 1
    else:
        max_rank = 0
        default_rank = 0

    is_hard_priority = system_label == "must_read" or oracle_label == "strong_relevant" or oracle_score >= 0.72
    if not is_hard_priority and analysis_source_text not in {"pdf", "source_page"} and max_rank > 2:
        max_rank = 2

    proposed_rank = _label_rank(str(proposed_label or ""))
    if not _clean_text(proposed_label):
        proposed_rank = default_rank

    return _rank_label(min(max(proposed_rank, default_rank), max_rank))


def build_recommendation_calibration_metadata(
    paper: Dict[str, Any],
    proposed_label: Any,
    final_label: Any,
    analysis_source: Any = None,
) -> Dict[str, Any]:
    return {
        "proposed_label": _clean_text(proposed_label),
        "final_label": _clean_text(final_label),
        "analysis_source": _clean_text(analysis_source),
        "system_label": _clean_text(paper.get("system_label") or paper.get("relevance_level")),
        "system_score": paper.get("system_score", paper.get("relevance_score")),
        "oracle_label": _clean_text(paper.get("oracle_label")),
        "oracle_score": paper.get("oracle_score"),
    }


def _format_plain_url(url: str) -> str:
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


def _build_resource_items(paper: Dict[str, Any], response_language: str = "zh") -> List[Tuple[str, str]]:
    language = _normalize_response_language(response_language)
    missing = "No public link found yet" if language == "en" else "暂未发现公开链接"
    labels = {
        "code": "Code" if language == "en" else "代码",
        "data": "Data" if language == "en" else "数据",
        "project": "Project page" if language == "en" else "项目主页",
        "pdf": "Paper PDF" if language == "en" else "原文 PDF",
    }
    code_url = _get_first_url(paper, "code_url", "github_url", "repo_url", "repository_url")
    dataset_url = _get_first_url(paper, "dataset_url", "data_url")
    project_url = _get_first_url(
        paper,
        "project_url",
        "paper_url",
        "openreview_url",
        "cvf_url",
        "ecva_url",
        "dblp_url",
        "doi_url",
        "url",
    )
    pdf_url = _get_direct_pdf_url(paper)

    items: List[Tuple[str, str]] = []
    items.append((labels["code"], _format_plain_url(code_url) if code_url else missing))
    items.append((labels["data"], _format_plain_url(dataset_url) if dataset_url else missing))
    items.append((labels["project"], _format_plain_url(project_url) if project_url else missing))
    items.append((labels["pdf"], _format_plain_url(pdf_url) if pdf_url else missing))

    arxiv_id = _clean_text(paper.get("arxiv_id"))
    if arxiv_id:
        items.append(("arXiv", _format_plain_url(f"https://arxiv.org/abs/{arxiv_id}")))

    doi = _clean_text(paper.get("doi"))
    if doi:
        items.append(("DOI", _format_plain_url(f"https://doi.org/{doi}")))

    return items


def _format_subjects(paper: Dict[str, Any]) -> str:
    for key in ("subjects", "categories", "category", "primary_category", "tags", "topics"):
        value = paper.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, dict):
            values = [str(item).strip() for item in value.values() if str(item).strip()]
        elif isinstance(value, (list, tuple, set)):
            values = [str(item).strip() for item in value if str(item).strip()]
        else:
            values = [str(value).strip()]
        if values:
            return ", ".join(_unique_preserve_order(values))
    return "未知"


def _collect_report_action_pairs(paper: Dict[str, Any], response_language: str = "zh") -> List[Tuple[str, str]]:
    language = _normalize_response_language(response_language)
    labels = {
        "paper": "Paper" if language == "en" else "原文",
        "code": "Code" if language == "en" else "代码",
        "project": "Project" if language == "en" else "项目",
    }
    candidates: List[Tuple[str, str]] = []
    pdf_url = _get_direct_pdf_url(paper)
    if pdf_url:
        candidates.append(("PDF", pdf_url))

    arxiv_id = _clean_text(paper.get("arxiv_id"))
    paper_url = _get_first_url(
        paper,
        "paper_url",
        "openreview_url",
        "cvf_url",
        "ecva_url",
        "dblp_url",
        "doi_url",
        "url",
    )
    if not paper_url and arxiv_id:
        paper_url = f"https://arxiv.org/abs/{arxiv_id}"
    if paper_url:
        candidates.append((labels["paper"], paper_url))

    code_url = _get_first_url(paper, "code_url", "github_url", "repo_url", "repository_url")
    if code_url:
        candidates.append((labels["code"], code_url))

    project_url = _get_first_url(paper, "project_url")
    if project_url:
        candidates.append((labels["project"], project_url))

    seen: set[str] = set()
    pairs: List[Tuple[str, str]] = []
    for label, url in candidates:
        clean_url = _clean_text(url)
        if not clean_url or clean_url in seen:
            continue
        seen.add(clean_url)
        pairs.append((label, clean_url))
    return pairs


def _build_report_action_links(paper: Dict[str, Any], response_language: str = "zh") -> str:
    """Bullet list of action URLs (Feishu-safe, one URL per line)."""
    return "\n".join(f"- {label}: {url}" for label, url in _collect_report_action_pairs(paper, response_language))


def _append_qa_block(lines: List[str], label: str, question: str, body: Any) -> None:
    """Append a single-layer Q/A block in papers.cool style."""
    lines.append(f"### {label} {question}")
    lines.append("")
    if isinstance(body, (list, tuple)):
        any_item = False
        for item in body:
            text = _clean_text(item)
            if text:
                lines.append(f"- {text}")
                any_item = True
        if not any_item:
            lines.append("当前信息不足，建议回到原文核对。")
    else:
        text = _clean_text(body)
        lines.append(text or "当前信息不足，建议回到原文核对。")
    lines.append("")


def _build_recommendation_reason(payload: Dict[str, Any], response_language: str = "zh") -> str:
    language = _normalize_response_language(response_language)
    reasons: List[str] = []
    relevance_points = payload.get("relevance_points") or []
    reading_focus = payload.get("reading_focus") or []
    analysis_source = _clean_text(payload.get("analysis_source"))

    if relevance_points:
        reasons.append(_clean_text(relevance_points[0]))
    if analysis_source == "pdf":
        reasons.append(
            "This run used the full PDF structure, so method and result details are relatively more complete."
            if language == "en"
            else "这次已拿到 PDF 全文结构，方法和结果信息相对更完整。"
        )
    elif _clean_text(payload.get("analysis_note")):
        reasons.append(_clean_text(payload.get("analysis_note")))
    if reading_focus:
        reasons.append(
            f"Recommended first focus: {_clean_text(reading_focus[0])}"
            if language == "en"
            else f"建议优先看：{_clean_text(reading_focus[0])}"
        )

    if not reasons:
        reasons.append(
            "This recommendation is mainly based on title, abstract, metadata, and profile matching."
            if language == "en"
            else "当前推荐主要基于题目、摘要、元数据和你的画像匹配结果。"
        )
    return reasons[0]


def _looks_like_placeholder_title(title: str) -> bool:
    normalized = _clean_text(title).lower()
    if not normalized:
        return True
    return bool(re.fullmatch(r"(paper|test paper)\s*\d*", normalized))


def _format_direction_label(direction: str, response_language: str = "zh") -> str:
    language = _normalize_response_language(response_language)
    normalized = str(direction or "").strip()
    if not normalized:
        return "Current direction" if language == "en" else "当前方向"
    formatter = getattr(direction_lexicon, "format_direction_label", None)
    if callable(formatter):
        label = str(formatter(normalized, prefer_chinese=(language != "en")) or "").strip()
        if label:
            return label
    lowered = normalized.lower()
    if language == "en":
        return (
            normalized.replace("-", " ").replace("_", " ").title().replace("Gui", "GUI").replace("Ai", "AI")
        )
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
        "cvf_url",
        "ecva_url",
        "dblp_url",
        "journal",
        "source",
        "category",
    ):
        if field in normalized:
            normalized[field] = _clean_text(normalized.get(field))

    if "abstract" in normalized:
        normalized["abstract"] = _clean_abstract_text(normalized.get("abstract"))

    score = normalized.get("score")
    try:
        normalized["score"] = float(score)
    except (TypeError, ValueError):
        normalized["score"] = 0.0

    return normalized


def _is_direct_upload_request(request_metadata: Dict[str, Any]) -> bool:
    source_type = _clean_text((request_metadata or {}).get("report_source_type"))
    return source_type in {"feishu_file_key", "feishu_file_url", "feishu_message_id", "text_pdf_url"}


def _load_public_webhook_base_url() -> str:
    data_dir = Path(__file__).resolve().parents[2] / "data"
    ngrok_url_path = data_dir / "ngrok_url.txt"
    if not ngrok_url_path.exists():
        return ""
    try:
        return str(ngrok_url_path.read_text(encoding="utf-8").strip()).rstrip("/")
    except Exception:
        return ""


def _build_doc_tracking_url(
    *,
    doc_url: str,
    user_id: str,
    doc_token: str = "",
    paper_title: str = "",
) -> str:
    base_url = _load_public_webhook_base_url()
    normalized_doc_url = _clean_text(doc_url)
    if not base_url or not normalized_doc_url.startswith(("http://", "https://")):
        return normalized_doc_url

    params = [
        f"target={quote(normalized_doc_url, safe='')}",
        f"user_id={quote(str(user_id or '').strip(), safe='')}",
    ]
    if doc_token:
        params.append(f"doc_token={quote(str(doc_token).strip(), safe='')}")
    if paper_title:
        params.append(f"title={quote(_clean_text(paper_title), safe='')}")
    return f"{base_url}/r/doc?{'&'.join(params)}"


def _annotate_tracking_links(created_docs: List[Dict[str, Any]], user_id: str) -> None:
    for doc in created_docs:
        doc_url = _clean_text(doc.get("url"))
        if not doc_url:
            continue
        tracking_url = _build_doc_tracking_url(
            doc_url=doc_url,
            user_id=user_id,
            doc_token=_clean_text(doc.get("doc_token")),
            paper_title=_clean_text((doc.get("paper") or {}).get("title") or doc.get("title")),
        )
        if tracking_url and tracking_url != doc_url:
            doc["tracking_url"] = tracking_url


def _apply_direct_upload_reading_signal(
    *,
    user_id: str,
    profile: Dict[str, Any],
    paper: Dict[str, Any],
    parsed_pdf: Optional[Dict[str, Any]],
    request_metadata: Dict[str, Any],
    signal_time: Optional[datetime] = None,
) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Apply a weak reading signal for direct-upload PDFs after a report is created."""
    if not _is_direct_upload_request(request_metadata):
        return profile, None

    effective_time = signal_time or datetime.now()
    updated_profile = update_profile_with_reading_signal(
        profile,
        paper=paper,
        parsed_pdf=parsed_pdf,
        signal_strength="weak",
        current_time=effective_time,
        source_type=request_metadata.get("report_source_type", ""),
        source_key=request_metadata.get("report_source_key", ""),
    )
    last_signal = (
        (updated_profile.get("reading_signal_state", {}) or {}).get("last_signal", {}) or {}
    )
    signal_topics = last_signal.get("topics", []) or []
    if not signal_topics:
        return profile, None

    update_profile(user_id, updated_profile)
    metadata = {
        "signal_strength": last_signal.get("strength", "weak"),
        "signal_topics": signal_topics,
        "activated_topics": last_signal.get("activated_topics", []) or [],
        "source_type": last_signal.get("source_type") or request_metadata.get("report_source_type", ""),
        "source_key": last_signal.get("source_key") or request_metadata.get("report_source_key", ""),
        "paper_title": paper.get("title"),
    }
    return updated_profile, metadata
def format_created_docs_summary(created_docs: List[Dict[str, Any]]) -> str:
    """Format the reading-report completion message with direct document links."""
    lines = [
        "=" * 60,
        f"Reading reports ready ({len(created_docs)})",
        "=" * 60,
        "",
    ]

    for index, doc in enumerate(created_docs, start=1):
        title = doc.get("paper", {}).get("title") or doc.get("title", "Unknown")
        lines.append(f"{index:02d}. {title[:60]}")
        if doc.get("tracking_url"):
            lines.append(f"    {doc['tracking_url']}")
        elif doc.get("url"):
            lines.append(f"    {doc['url']}")
        elif doc.get("doc_token"):
            lines.append(f"    doc_token: {doc['doc_token']}")
        lines.append("")

    lines.append("Open the links above to start reading.")
    return "\n".join(lines)


def _build_reused_doc_entry(
    paper: Dict[str, Any],
    report_record: Dict[str, Any],
) -> Dict[str, Any]:
    """Convert a stored created_report record into the runtime doc payload shape."""
    paper_title = (
        _clean_text(paper.get("title"))
        or _clean_text(report_record.get("paper_title"))
        or "Unknown"
    )
    doc_title = _clean_text(report_record.get("doc_title")) or f"[精读] {paper_title[:80]}"
    return {
        "paper": {**paper, "title": paper_title},
        "doc_info": {},
        "title": doc_title,
        "url": _clean_text(report_record.get("doc_url")) or None,
        "doc_token": _clean_text(report_record.get("doc_token")) or None,
        "report_path": _clean_text((report_record.get("metadata") or {}).get("report_path")) or None,
        "pdf_path": _clean_text((report_record.get("metadata") or {}).get("pdf_path")) or None,
        "report_payload": None,
        "reused": True,
        "created_at": report_record.get("timestamp"),
    }


def _is_report_record_current(report_record: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(report_record, dict):
        return False
    metadata = report_record.get("metadata") or {}
    if not isinstance(metadata, dict):
        return False
    return _clean_text(metadata.get("report_version")) == READING_REPORT_OUTPUT_VERSION


def _report_record_matches_language(report_record: Optional[Dict[str, Any]], response_language: str) -> bool:
    if not isinstance(report_record, dict):
        return False
    language = _normalize_response_language(response_language)
    metadata = report_record.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    recorded = _clean_text(metadata.get("response_language") or metadata.get("language"))
    if not recorded:
        return language == "zh"
    return _normalize_response_language(recorded) == language


def _lookup_existing_pdf_report(
    user_id: str,
    request_metadata: Dict[str, Any],
    fallback_paper: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Find an already-created PDF reading report by its stable source key."""
    source_type = _clean_text(request_metadata.get("report_source_type"))
    source_key = _clean_text(request_metadata.get("report_source_key"))
    if not source_type or not source_key:
        return None

    report_record = get_recent_created_report_by_source(user_id, source_type, source_key)
    if not report_record:
        return None
    if not _is_report_record_current(report_record):
        return None
    if not _report_record_matches_language(report_record, request_metadata.get("response_language")):
        return None

    return _build_reused_doc_entry(fallback_paper, report_record)


def _merge_paper_details(base: Dict[str, Any], detail: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    detail = _normalize_paper(detail)
    prefer_detail_abstract = bool(base.get("_prefer_detail_abstract"))

    for key in ("arxiv_id", "doi", "pdf_url", "publish_date", "venue", "institution"):
        if not _clean_text(merged.get(key)):
            merged[key] = detail.get(key, merged.get(key))

    if _looks_like_placeholder_title(str(merged.get("title", ""))) and detail.get("title"):
        merged["title"] = detail["title"]

    if not merged.get("authors"):
        merged["authors"] = detail.get("authors", [])

    current_abstract_raw = merged.get("abstract")
    current_abstract = _clean_abstract_text(current_abstract_raw)
    detail_abstract = _clean_abstract_text(detail.get("abstract"))
    if detail_abstract and (
        prefer_detail_abstract
        or _prefer_candidate_abstract(current_abstract_raw, detail_abstract)
    ):
        merged["abstract"] = detail["abstract"]
    elif current_abstract:
        merged["abstract"] = current_abstract

    existing_metadata = dict(merged.get("metadata") or {})
    detail_metadata = dict(detail.get("metadata") or {})
    if detail_metadata:
        merged["metadata"] = {**existing_metadata, **detail_metadata}
    else:
        merged["metadata"] = existing_metadata
    merged.pop("_prefer_detail_abstract", None)

    return merged


def _normalize_source_page_document(document: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(document, dict):
        return None

    sections = document.get("sections") or {}
    normalized_sections: Dict[str, str] = {}
    if isinstance(sections, dict):
        for key, value in sections.items():
            cleaned_key = _clean_text(key).lower()
            cleaned_value = _clean_text(value)
            if cleaned_key and cleaned_value:
                normalized_sections[cleaned_key] = cleaned_value

    normalized_document = {
        "source_kind": "source_page",
        "source_url": _clean_text(document.get("source_url")),
        "abstract": _clean_text(document.get("abstract")),
        "sections": normalized_sections,
        "full_text": _clean_text(document.get("full_text")),
    }

    if not (
        normalized_document["abstract"]
        or normalized_document["sections"]
        or normalized_document["full_text"]
    ):
        return None

    if not normalized_document["full_text"]:
        ordered_parts: List[str] = []
        if normalized_document["abstract"]:
            ordered_parts.append(normalized_document["abstract"])
        for section_name in (
            "introduction",
            "background",
            "method",
            "results",
            "experiments",
            "discussion",
            "limitations",
            "conclusion",
        ):
            section_text = normalized_document["sections"].get(section_name)
            if section_text and section_text not in ordered_parts:
                ordered_parts.append(section_text)
        for section_text in normalized_document["sections"].values():
            if section_text and section_text not in ordered_parts:
                ordered_parts.append(section_text)
        normalized_document["full_text"] = " ".join(ordered_parts).strip()

    return normalized_document


def _get_source_page_document(paper: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    metadata = paper.get("metadata") or {}
    source_page = metadata.get("source_page")
    normalized = _normalize_source_page_document(source_page)
    if normalized:
        if not normalized.get("abstract"):
            normalized["abstract"] = _clean_text(paper.get("abstract"))
        return normalized
    return None


def _backfill_metadata_from_source_page(paper: Dict[str, Any]) -> Dict[str, Any]:
    if _paper_has_sufficient_metadata_for_report(paper) and not paper.get("_prefer_detail_abstract"):
        return paper

    source_urls = _collect_source_page_urls(paper)
    if not source_urls:
        return paper

    try:
        journal_fetcher = _load_journal_fetcher()
    except Exception as exc:
        print(f"Unable to load journal fetcher for metadata backfill: {exc}")
        return paper

    fetch_detail = getattr(journal_fetcher, "_fetch_article_detail", None)
    if not callable(fetch_detail):
        return paper

    enriched = dict(paper)
    for source_url in source_urls:
        try:
            detail = fetch_detail(source_url)
        except Exception as exc:
            print(f"  Metadata backfill failed for {source_url[:120]}: {exc}")
            continue

        if not isinstance(detail, dict) or detail.get("_skip"):
            continue

        merged = _merge_paper_details(enriched, detail)
        improved = (
            _clean_text(merged.get("abstract")) != _clean_text(enriched.get("abstract"))
            or _parse_jsonish_list(merged.get("authors")) != _parse_jsonish_list(enriched.get("authors"))
            or _clean_text(merged.get("pdf_url")) != _clean_text(enriched.get("pdf_url"))
        )
        enriched = merged
        if improved:
            print(f"  Metadata backfilled from source page: {source_url[:120]}")
        if _paper_has_sufficient_metadata_for_report(enriched):
            break

    return enriched


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
    source_page_metadata = metadata.get("source_page") or {}
    candidates = [
        paper.get("paper_url"),
        paper.get("url"),
        paper.get("doi_url"),
        paper.get("openreview_url"),
        paper.get("cvf_url"),
        paper.get("ecva_url"),
        paper.get("dblp_url"),
        metadata.get("paper_url"),
        metadata.get("url"),
        metadata.get("link"),
        metadata.get("doi_url"),
        metadata.get("openreview_url"),
        metadata.get("cvf_url"),
        metadata.get("ecva_url"),
        metadata.get("dblp_url"),
        source_page_metadata.get("source_url"),
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


def _build_pdf_url_candidates_from_source_url(source_url: str) -> List[str]:
    normalized = _clean_text(source_url)
    if not normalized.startswith(("http://", "https://")):
        return []

    parsed = urlparse(normalized)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""
    query = parsed.query or ""
    candidates: List[str] = []

    def add(candidate: str) -> None:
        cleaned = _clean_text(candidate)
        if cleaned.startswith(("http://", "https://")) and cleaned not in candidates:
            candidates.append(cleaned)

    if "nature.com" in host and path.startswith("/articles/") and not path.lower().endswith(".pdf"):
        add(urljoin(f"{parsed.scheme}://{parsed.netloc}", f"{path}_reference.pdf"))
        add(urljoin(f"{parsed.scheme}://{parsed.netloc}", f"{path}.pdf"))

    if "science.org" in host and "/doi/" in path:
        doi_match = re.search(r"/doi/(?:abs|full|epdf|pdf)/(.+)$", path, flags=re.I)
        if doi_match:
            doi_suffix = doi_match.group(1).strip("/")
            add(f"{parsed.scheme}://{parsed.netloc}/doi/pdf/{doi_suffix}?download=true")
            add(f"{parsed.scheme}://{parsed.netloc}/doi/pdf/{doi_suffix}")
            add(f"{parsed.scheme}://{parsed.netloc}/doi/epdf/{doi_suffix}")

    if "openreview.net" in host:
        forum_id = ""
        if parsed.query:
            query_match = re.search(r"(?:^|&)id=([^&]+)", parsed.query)
            if query_match:
                forum_id = query_match.group(1)
        if not forum_id:
            forum_match = re.search(r"/forum", path, flags=re.I)
            if forum_match and parsed.query:
                query_match = re.search(r"(?:^|&)id=([^&]+)", parsed.query)
                if query_match:
                    forum_id = query_match.group(1)
        if forum_id:
            add(f"{parsed.scheme}://{parsed.netloc}/pdf?id={forum_id}")

    if "openaccess.thecvf.com" in host and path.lower().endswith("_paper.html"):
        add(f"{parsed.scheme}://{parsed.netloc}{path[:-5]}.pdf")

    if "link.springer.com" in host:
        article_match = re.search(r"^/(?:article|chapter)/(.+)$", path, flags=re.I)
        if article_match:
            doi_suffix = article_match.group(1).strip("/")
            add(f"{parsed.scheme}://{parsed.netloc}/content/pdf/{doi_suffix}.pdf")
            add(f"{parsed.scheme}://{parsed.netloc}/content/pdf/{doi_suffix}.pdf?download=1")

    if any(token in host for token in ("biorxiv.org", "medrxiv.org")) and "/content/" in path:
        if not path.lower().endswith(".pdf"):
            suffix = ".full.pdf"
            if path.lower().endswith(".full"):
                suffix = ".pdf"
            candidate = f"{parsed.scheme}://{parsed.netloc}{path}{suffix}"
            if query:
                candidate = f"{candidate}?{query}"
            add(candidate)

    if "pnas.org" in host and "/doi/" in path:
        doi_match = re.search(r"/doi/(?:full|abs|pdf)/(.+)$", path, flags=re.I)
        if doi_match:
            doi_suffix = doi_match.group(1).strip("/")
            add(f"{parsed.scheme}://{parsed.netloc}/doi/pdf/{doi_suffix}")

    return candidates


def _resolve_pdf_url_from_source_page(source_url: str) -> str:
    response = _http_get(
        source_url,
        timeout=PDF_DOWNLOAD_TIMEOUT,
        allow_redirects=True,
    )

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

    heuristic_candidates = _build_pdf_url_candidates_from_source_url(final_url)
    if heuristic_candidates:
        return heuristic_candidates[0]

    return ""


def _pick_download_referer(paper: Dict[str, Any], pdf_url: str) -> Optional[str]:
    source_urls = _collect_source_page_urls(paper)
    if not source_urls:
        return None

    pdf_host = (urlparse(_clean_text(pdf_url)).netloc or "").lower()
    if pdf_host:
        for source_url in source_urls:
            if (urlparse(source_url).netloc or "").lower() == pdf_host:
                return source_url

    return source_urls[0]


def _build_pdf_download_candidates(paper: Dict[str, Any], primary_pdf_url: str) -> List[str]:
    candidates: List[str] = []

    def add(candidate: Any) -> None:
        text = _clean_text(candidate)
        if _looks_like_pdf_url(text) and text not in candidates:
            candidates.append(text)

    add(primary_pdf_url)
    for source_url in _collect_source_page_urls(paper):
        for candidate in _build_pdf_url_candidates_from_source_url(source_url):
            add(candidate)

    return candidates


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
            heuristic_candidates = _build_pdf_url_candidates_from_source_url(source_url)
            if heuristic_candidates:
                print(f"  Falling back to heuristic PDF URL: {heuristic_candidates[0][:120]}")
                return heuristic_candidates[0]
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
        _clean_abstract_text(paper.get("abstract"))
        and not _looks_like_feed_metadata_abstract(paper.get("abstract"))
        and _parse_jsonish_list(paper.get("authors"))
        and not _looks_like_placeholder_title(_clean_text(paper.get("title")))
    )


def _is_arxiv_pdf_url(pdf_url: str) -> bool:
    return "arxiv.org/" in _clean_text(pdf_url).lower()


def _is_research_journal_article_for_pdf_evidence(paper: Dict[str, Any]) -> bool:
    title = _clean_text(paper.get("title")).lower()
    if any(pattern in title for pattern in NON_RESEARCH_TITLE_PATTERNS):
        return False

    venue = _clean_text(paper.get("venue") or paper.get("journal") or paper.get("source")).lower()
    source_url = _get_first_url(paper, "paper_url", "url", "doi_url", "openreview_url").lower()

    if "nature.com/articles/d" in source_url:
        return False

    return any(
        token in venue or token in source_url
        for token in (
            "nature",
            "science",
            "cell",
            "pnas",
            "springer",
            "journal",
        )
    )


def _is_research_conference_article_for_pdf_evidence(paper: Dict[str, Any], pdf_url: str) -> bool:
    title = _clean_text(paper.get("title")).lower()
    if any(pattern in title for pattern in NON_RESEARCH_TITLE_PATTERNS):
        return False

    venue = _clean_text(paper.get("venue") or paper.get("journal") or paper.get("source")).lower()
    category = _clean_text(paper.get("category")).lower()
    source_url = _get_first_url(
        paper,
        "paper_url",
        "url",
        "openreview_url",
        "cvf_url",
        "ecva_url",
        "dblp_url",
        "doi_url",
    ).lower()
    pdf_host = (urlparse(_clean_text(pdf_url)).netloc or "").lower()

    conference_tokens = (
        "openreview",
        "cvf",
        "ecva",
        "conference",
        "iclr",
        "neurips",
        "icml",
        "acl",
        "emnlp",
        "cvpr",
        "iccv",
        "eccv",
        "acm mm",
    )
    return any(
        token in venue or token in category or token in source_url or token in pdf_host
        for token in conference_tokens
    )


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

    if _is_research_journal_article_for_pdf_evidence(paper):
        return True, "journal_pdf_evidence"

    if _is_research_conference_article_for_pdf_evidence(paper, pdf_url):
        return True, "conference_pdf_evidence"

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
        or paper.get("openreview_url")
        or paper.get("cvf_url")
        or paper.get("ecva_url")
        or paper.get("dblp_url")
        or paper.get("url")
        or (paper.get("metadata") or {}).get("paper_url")
        or (paper.get("metadata") or {}).get("openreview_url")
        or (paper.get("metadata") or {}).get("cvf_url")
        or (paper.get("metadata") or {}).get("ecva_url")
        or (paper.get("metadata") or {}).get("dblp_url")
        or (paper.get("metadata") or {}).get("url")
        or (paper.get("metadata") or {}).get("link")
    )
    if paper_url and all(paper_url != url for _, url in links):
        links.append(("原始链接", paper_url))

    return links


def _download_pdf(pdf_url: str, title: str, referer: Optional[str] = None) -> str:
    response = _http_get(
        pdf_url,
        timeout=PDF_DOWNLOAD_TIMEOUT,
        referer=referer,
        accept_pdf=True,
    )
    content_type = str(response.headers.get("Content-Type") or "").lower()
    if "application/pdf" not in content_type and not response.content.startswith(b"%PDF"):
        raise ValueError(
            f"Resolved URL did not return a PDF (content-type={content_type or 'unknown'})"
        )

    safe_prefix = re.sub(r"[^A-Za-z0-9]+", "_", title or "paper").strip("_")[:40] or "paper"
    with tempfile.NamedTemporaryFile(prefix=f"{safe_prefix}_", suffix=".pdf", delete=False) as temp_file:
        temp_file.write(response.content)
        return temp_file.name


def _persist_pdf_file(
    source_pdf_path: str,
    paper: Dict[str, Any],
    pdf_url: str = "",
    user_id: Optional[str] = None,
) -> Optional[str]:
    source_path = Path(source_pdf_path).expanduser()
    if not source_path.exists():
        return None
    target_dir = _resolve_configured_dir(
        "PAPERFLOW_PDF_DIR",
        "data/exports",
        paper,
        user_id=user_id,
        category="pdf",
    )
    target_path = target_dir / f"{_paper_file_stem(paper)}.pdf"
    if source_path.resolve() != target_path.resolve():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)
    print(f"  Saved PDF: {target_path}")
    return str(target_path)


def _obsidian_daily_note_path(report_path: Path, paper: Dict[str, Any]) -> Optional[Path]:
    deep_dir = report_path.parent
    year_dir = deep_dir.parent
    if not deep_dir.name.startswith("Deep Reading - ") or not re.fullmatch(r"Daily Note 20\d{2}", year_dir.name):
        return None
    return year_dir / _daily_note_file_name(paper)


def _obsidian_note_link(report_path: Path) -> str:
    year_dir = report_path.parent.parent
    try:
        relative = report_path.relative_to(year_dir).with_suffix("")
    except ValueError:
        relative = report_path.with_suffix("")
    return str(relative).replace(os.sep, "/")


def _daily_note_category(paper: Dict[str, Any], report_payload: Dict[str, Any]) -> str:
    values: List[str] = []
    for key in ("title", "abstract", "summary", "venue", "source"):
        values.append(_clean_text(paper.get(key)))
    for value in paper.get("subjects") or paper.get("categories") or []:
        values.append(_clean_text(value))
    for value in report_payload.get("keywords") or []:
        values.append(_clean_text(value))
    text = " ".join(value for value in values if value).lower()

    def has_any(terms: Tuple[str, ...]) -> bool:
        return any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) for term in terms)

    if has_any(("education", "classroom", "k-12", "school", "curriculum", "pedagogy")):
        return "AI for Education"
    if has_any(("protein", "molecular", "molecule", "biology", "bio", "chemistry", "materials science", "scientific discovery", "ai for science")):
        return "AI for Science"
    if has_any(("agent", "agents", "multi-agent", "tool", "orchestration")):
        return "AI Agents"
    if has_any(("vision", "image", "video", "3d", "segmentation")):
        return "Computer Vision"
    if has_any(("language", "llm", "nlp", "retrieval", "rag", "reasoning")):
        return "Language Models"
    if has_any(("reinforcement", "diffusion", "learning", "optimization", "distillation", "post-training", "on-policy")):
        return "Machine Learning"
    return "AI Research"


def _daily_note_entry(
    *,
    paper: Dict[str, Any],
    report_payload: Dict[str, Any],
    report_path: Path,
    report_content: str,
) -> str:
    title = _clean_text(paper.get("title")) or report_path.stem
    marker_key = _clean_text(paper.get("arxiv_id") or paper.get("doi") or title)
    marker = f"<!-- paperflow:{hashlib.sha1(marker_key.encode('utf-8')).hexdigest()[:16]} -->"
    note_link = _obsidian_note_link(report_path)
    pdf_url = _clean_text(paper.get("pdf_url")) or _get_direct_pdf_url(paper)
    summary = _clean_text(
        _extract_report_answer(report_content, "总结一下论文的主要内容")
        or report_payload.get("paper_summary")
        or report_payload.get("one_sentence_summary")
        or report_payload.get("clean_abstract_summary")
        or paper.get("abstract")
    )
    if len(summary) > 900:
        summary = summary[:900].rstrip() + "..."
    star = "⭐" if str(report_payload.get("recommendation_label") or "").lower() in {"highly_recommended", "must_read", "high_match"} else ""
    lines = [
        marker,
        f"## {star}{title}".rstrip(),
        "",
        f"[[{note_link}|Deep Reading]]",
    ]
    if pdf_url:
        lines.extend(["", f"[{pdf_url}]({pdf_url})"])
    if summary:
        lines.extend(["", f"- **{summary}**"])
    return "\n".join(lines).rstrip() + "\n"


def _extract_report_answer(report_content: str, question: str) -> str:
    text = str(report_content or "")
    if not text.strip():
        return ""
    escaped = re.escape(question)
    pattern = re.compile(
        rf"(?:^|\n)(?:#+\s*)?Q\d+\s*[:：]\s*{escaped}\s*\n+(.*?)(?=\n(?:#+\s*)?Q\d+\s*[:：]|\n##\s+|$)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return ""
    answer = match.group(1).strip()
    answer = re.sub(r"\n{3,}", "\n\n", answer)
    return answer


def _remove_daily_note_entry(current: str, marker: str) -> Optional[str]:
    marker_index = current.find(marker)
    if marker_index < 0:
        return None
    next_marker = current.find("\n<!-- paperflow:", marker_index + len(marker))
    next_section = current.find("\n# ", marker_index + len(marker))
    candidates = [index for index in (next_marker, next_section) if index >= 0]
    end_index = min(candidates) if candidates else len(current)
    return current[:marker_index].rstrip() + "\n\n" + current[end_index:].lstrip("\n")


def _prune_empty_daily_note_sections(text: str) -> str:
    lines = text.splitlines()
    output: List[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("# "):
            next_index = index + 1
            while next_index < len(lines) and not lines[next_index].startswith("# "):
                next_index += 1
            section_body = "\n".join(lines[index + 1 : next_index]).strip()
            if not section_body:
                index = next_index
                continue
        output.append(line)
        index += 1
    return "\n".join(output).strip()


def _sync_obsidian_daily_note(
    *,
    user_id: str,
    paper: Dict[str, Any],
    report_payload: Dict[str, Any],
    report_path: Path,
    report_content: str,
) -> Optional[str]:
    daily_note = _obsidian_daily_note_path(report_path, paper)
    if daily_note is None:
        return None
    daily_note.parent.mkdir(parents=True, exist_ok=True)
    category = _daily_note_category(paper, report_payload)
    entry = _daily_note_entry(
        paper=paper,
        report_payload=report_payload,
        report_path=report_path,
        report_content=report_content,
    )
    marker = entry.splitlines()[0]
    current = daily_note.read_text(encoding="utf-8") if daily_note.exists() else ""
    if marker in current:
        current = _remove_daily_note_entry(current, marker) or current
        current = _prune_empty_daily_note_sections(current)
    section_heading = f"# {category}"
    if section_heading not in current:
        current = current.rstrip() + ("\n\n" if current.strip() else "") + section_heading + "\n"
    insert_at = current.find(section_heading) + len(section_heading)
    next_section = current.find("\n# ", insert_at)
    if next_section == -1:
        updated = current.rstrip() + "\n\n" + entry
    else:
        updated = current[:next_section].rstrip() + "\n\n" + entry + "\n" + current[next_section:].lstrip("\n")
    user_profile = _daily_note_user_profile(user_id)
    updated = _refresh_daily_note_topic_summaries(updated, user_profile=user_profile)
    updated = _llm_review_daily_note_categories(updated, user_profile=user_profile)
    updated = _refresh_daily_note_topic_summaries(updated, user_profile=user_profile)
    daily_note.write_text(updated.rstrip() + "\n", encoding="utf-8")
    _sync_obsidian_toc(daily_note)
    return str(daily_note)


def _markdown_section_excerpt(content: str, *headings: str, max_chars: int = 900) -> str:
    text = str(content or "")
    for heading in headings:
        pattern = re.compile(
            rf"(?ms)^##\s+{re.escape(heading)}\s*$\n+(.*?)(?=^##\s+|\Z)"
        )
        match = pattern.search(text)
        if not match:
            continue
        excerpt = match.group(1).strip()
        excerpt = re.sub(r"(?m)^>\s*", "", excerpt)
        excerpt = re.sub(r"(?m)^[-*]\s+", "", excerpt)
        excerpt = re.sub(r"\n{3,}", "\n\n", excerpt).strip()
        if excerpt:
            return excerpt[:max_chars].rstrip()
    return ""


def _report_paper_from_metadata(metadata: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, Any]:
    title = _clean_text(metadata.get("title") or report.get("title"))
    return {
        "id": metadata.get("paper_id"),
        "arxiv_id": metadata.get("arxiv_id"),
        "doi": metadata.get("doi"),
        "title": title or "Untitled Paper",
        "authors": metadata.get("authors") or [],
        "abstract": metadata.get("abstract") or "",
        "publish_date": metadata.get("publish_date"),
        "pdf_path": metadata.get("pdf_path"),
        "pdf_url": metadata.get("pdf_url") or report.get("pdf_url"),
        "source": metadata.get("source") or "reading_report",
    }


def _report_payload_from_metadata(
    metadata: Dict[str, Any],
    report_content: str,
    report: Dict[str, Any],
) -> Dict[str, Any]:
    summary = (
        _markdown_section_excerpt(report_content, "一句话总结", "摘要")
        or _clean_text(report.get("snippet"))
    )
    return {
        "paper_summary": summary,
        "one_sentence_summary": summary,
        "recommendation_label": metadata.get("recommendation_label"),
        "generation_provider": metadata.get("generation_provider"),
        "generation_model": metadata.get("generation_model"),
        "report_style": metadata.get("report_style"),
        "response_language": metadata.get("response_language"),
    }


def sync_daily_notes_from_reports(
    *,
    user_id: str,
    reports: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Create or refresh Daily Notes from existing reading-report records."""
    scanned = 0
    synced = 0
    daily_notes: List[str] = []
    report_paths: List[str] = []
    errors: List[str] = []

    for report in reports or []:
        scanned += 1
        metadata = dict(report.get("metadata") or {})
        report_user = _clean_text(metadata.get("user_id") or report.get("user_id"))
        if user_id and report_user and report_user != user_id:
            continue
        report_content = str(report.get("markdown") or "")
        if not report_content.strip():
            continue
        paper = _report_paper_from_metadata(metadata, report)
        payload = _report_payload_from_metadata(metadata, report_content, report)
        try:
            saved_path = _save_reading_report_markdown(
                user_id=user_id or report_user,
                paper=paper,
                report_content=report_content,
                report_payload=payload,
                doc_url=metadata.get("doc_url") or report.get("doc_url"),
                doc_token=metadata.get("doc_token") or report.get("doc_token"),
            )
            synced += 1
            report_paths.append(saved_path)
            daily_note = _obsidian_daily_note_path(Path(saved_path), paper)
            if daily_note is not None:
                daily_notes.append(str(daily_note))
        except Exception as exc:
            errors.append(f"{paper.get('title') or report.get('report_path')}: {exc}")

    return {
        "scanned": scanned,
        "synced": synced,
        "daily_notes": sorted(set(daily_notes)),
        "report_paths": sorted(set(report_paths)),
        "errors": errors[:8],
    }


def refresh_daily_note_files(
    *,
    user_id: str,
    daily_note_paths: Iterable[str],
) -> Dict[str, Any]:
    """Reclassify and refresh summaries in existing Daily Note files."""
    user_profile = _daily_note_user_profile(user_id)
    scanned = 0
    refreshed = 0
    paths: List[str] = []
    errors: List[str] = []

    for raw_path in daily_note_paths or []:
        path = Path(str(raw_path or "")).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.exists() or not path.is_file():
            continue
        scanned += 1
        try:
            current = path.read_text(encoding="utf-8")
            updated = _refresh_daily_note_topic_summaries(current, user_profile=user_profile)
            updated = _llm_review_daily_note_categories(updated, user_profile=user_profile)
            updated = _refresh_daily_note_topic_summaries(updated, user_profile=user_profile)
            if updated.rstrip() + "\n" != current:
                path.write_text(updated.rstrip() + "\n", encoding="utf-8")
                _sync_obsidian_toc(path)
            refreshed += 1
            paths.append(str(path))
        except Exception as exc:
            errors.append(f"{path}: {exc}")

    return {
        "scanned": scanned,
        "refreshed": refreshed,
        "daily_notes": sorted(set(paths)),
        "errors": errors[:8],
    }


def _daily_note_user_profile(user_id: str) -> Dict[str, Any]:
    if not user_id:
        return {}
    try:
        profile = get_profile(user_id) or {}
        return ensure_profile_schema(profile) if isinstance(profile, dict) else {}
    except Exception as exc:
        print(f"  Daily Note profile lookup skipped: {exc}")
        return {}


def _daily_note_profile_terms(user_profile: Optional[Dict[str, Any]]) -> List[str]:
    profile = user_profile if isinstance(user_profile, dict) else {}
    terms: List[str] = []

    def add_term(value: Any) -> None:
        text = _clean_text(value)
        if not text:
            return
        text = re.sub(r"^(preference|prefer|methodology)[_-]+", "", text, flags=re.IGNORECASE)
        text = text.replace("_", " ").strip()
        if len(text) >= 2 and text.lower() not in {term.lower() for term in terms}:
            terms.append(text)

    def add_weighted_keys(mapping: Any) -> None:
        if not isinstance(mapping, dict):
            return
        weighted = []
        for key, value in mapping.items():
            try:
                weight = float(value)
            except (TypeError, ValueError):
                weight = 0.0
            weighted.append((str(key), weight))
        for key, _weight in sorted(weighted, key=lambda item: item[1], reverse=True):
            add_term(key)

    add_weighted_keys(profile.get("core_directions"))
    add_weighted_keys(profile.get("topic_weights"))

    preferences = profile.get("methodology_preferences") or {}
    if isinstance(preferences, dict):
        for key, value in preferences.items():
            if value:
                add_term(key)
                if isinstance(value, str):
                    add_term(value)
                elif isinstance(value, (list, tuple, set)):
                    for item in value:
                        add_term(item)

    must_read = profile.get("must_read") or {}
    if isinstance(must_read, dict):
        for keyword in must_read.get("keywords") or []:
            add_term(keyword)

    return terms


def _term_matches_daily_note_section(term: str, section_text: str) -> bool:
    normalized_term = _clean_text(term).replace("_", " ").replace("-", " ").lower()
    normalized_section = _clean_text(section_text).replace("_", " ").replace("-", " ").lower()
    if not normalized_term or not normalized_section:
        return False
    if normalized_term in normalized_section:
        return True
    tokens = [token for token in re.split(r"[^0-9a-zA-Z\u4e00-\u9fff]+", normalized_term) if len(token) >= 3]
    return bool(tokens) and all(token in normalized_section for token in tokens)


def _daily_note_topic_methods(section_body: str, user_profile: Optional[Dict[str, Any]]) -> List[str]:
    section_text = re.sub(r"\s+", " ", section_body)
    matches: List[str] = []
    for term in _daily_note_profile_terms(user_profile):
        if _term_matches_daily_note_section(term, section_text):
            matches.append(term)
    return matches[:8]


def _daily_note_profile_payload(user_profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    profile = user_profile if isinstance(user_profile, dict) else {}
    must_read = profile.get("must_read") or {}
    must_read_keywords = must_read.get("keywords") if isinstance(must_read, dict) else []
    return {
        "core_directions": profile.get("core_directions") or {},
        "topic_weights": profile.get("topic_weights") or {},
        "methodology_preferences": profile.get("methodology_preferences") or {},
        "must_read_keywords": must_read_keywords or [],
    }


def _daily_note_topic_summary(
    category: str,
    section_body: str,
    *,
    user_profile: Optional[Dict[str, Any]] = None,
) -> str:
    titles = re.findall(r"^##\s+(.+)$", section_body, flags=re.MULTILINE)
    method_terms = _daily_note_topic_methods(section_body, user_profile)
    paper_lines = "\n".join(f"- {title}" for title in titles[:8]) or "- 暂无精读论文"
    return "\n".join(
        [
            "<!-- paperflow-topic-summary:start -->",
            "## PaperFlow Summary",
            f"- 概念：{category}",
            f"- 方法：{', '.join(method_terms[:8]) if method_terms else '待从后续精读中沉淀'}",
            f"- 论文/报告：{len(titles)} 篇",
            paper_lines,
            "- 画像/前沿：该主题来自当前精读论文与研究画像的交集，供 Wiki 可视化和后续检索使用。",
            "<!-- paperflow-topic-summary:end -->",
        ]
    )


def _extract_daily_note_paper_blocks(content: str) -> List[Dict[str, str]]:
    text = re.sub(
        r"\n?<!-- paperflow-topic-summary:start -->.*?<!-- paperflow-topic-summary:end -->\n?",
        "\n",
        str(content or ""),
        flags=re.DOTALL,
    )
    sections = list(re.finditer(r"^#\s+(.+)$", text, flags=re.MULTILINE))
    blocks: List[Dict[str, str]] = []
    for section_index, section in enumerate(sections):
        category = section.group(1).strip()
        start = section.end()
        end = sections[section_index + 1].start() if section_index + 1 < len(sections) else len(text)
        body = text[start:end]
        matches = list(re.finditer(r"(?m)^<!-- paperflow:[0-9a-f]{16} -->$", body))
        for match_index, marker_match in enumerate(matches):
            block_start = marker_match.start()
            block_end = matches[match_index + 1].start() if match_index + 1 < len(matches) else len(body)
            block = body[block_start:block_end].strip()
            title_match = re.search(r"(?m)^##\s+(.+)$", block)
            if not title_match:
                continue
            marker = marker_match.group(0).strip()
            summary_match = re.search(r"-\s+\*\*(.*?)\*\*", block, flags=re.DOTALL)
            blocks.append(
                {
                    "marker": marker,
                    "title": title_match.group(1).strip(),
                    "category": category,
                    "summary": re.sub(r"\s+", " ", summary_match.group(1)).strip() if summary_match else "",
                    "block": block,
                }
            )
    return blocks


def _daily_note_classification_payload(
    blocks: List[Dict[str, str]],
    user_profile: Optional[Dict[str, Any]] = None,
) -> str:
    papers = [
        {
            "marker": block["marker"],
            "title": block["title"],
            "current_category": block["category"],
            "summary": block["summary"][:700],
        }
        for block in blocks
    ]
    return json.dumps(
        {
            "allowed_categories": DAILY_NOTE_CATEGORY_OPTIONS,
            "user_profile": _daily_note_profile_payload(user_profile),
            "papers": papers,
        },
        ensure_ascii=False,
    )


def _parse_daily_note_classification_response(text: str, markers: set[str]) -> Dict[str, str]:
    content = str(text or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        content = content[start : end + 1]
    parsed = _loads_daily_note_classification_json(content)
    assignments = parsed.get("assignments") if isinstance(parsed, dict) else None
    if not isinstance(assignments, list):
        return {}
    allowed = set(DAILY_NOTE_CATEGORY_OPTIONS)
    result: Dict[str, str] = {}
    for item in assignments:
        if not isinstance(item, dict):
            continue
        marker = str(item.get("marker") or "").strip()
        category = str(item.get("category") or "").strip()
        if marker in markers and category in allowed:
            result[marker] = category
    return result


def _loads_daily_note_classification_json(content: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    repaired = str(content or "")
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = re.sub(r"}\s*(?={)", "},", repaired)
    repaired = re.sub(r"}\s*\n\s*(?={)", "},\n", repaired)
    parsed = json.loads(repaired)
    return parsed if isinstance(parsed, dict) else {}


def _llm_daily_note_category_assignments(
    blocks: List[Dict[str, str]],
    user_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    if not blocks or not _env_flag("PAPERFLOW_DAILY_NOTE_LLM_CLASSIFY", True):
        return {}
    try:
        provider_module = importlib.import_module("paperflow.providers")
        llm = provider_module.build_llm_provider()
        if getattr(llm, "name", "") == "mock":
            return {}
        response = llm.generate(
            _daily_note_classification_payload(blocks, user_profile=user_profile),
            system=DAILY_NOTE_CLASSIFICATION_PROMPT,
            temperature=0.0,
            max_tokens=4096,
        )
        return _parse_daily_note_classification_response(
            response.text,
            {block["marker"] for block in blocks},
        )
    except Exception as exc:
        print(f"  Daily Note LLM classification skipped: {exc}")
        return {}


def _rebuild_daily_note_from_blocks(
    blocks: List[Dict[str, str]],
    assignments: Dict[str, str],
    *,
    user_profile: Optional[Dict[str, Any]] = None,
) -> str:
    grouped: Dict[str, List[Dict[str, str]]] = {}
    ordered_categories: List[str] = []
    for block in blocks:
        category = assignments.get(block["marker"]) or block["category"] or "AI Research"
        if category not in grouped:
            grouped[category] = []
            ordered_categories.append(category)
        grouped[category].append(block)
    preferred_order = [category for category in DAILY_NOTE_CATEGORY_OPTIONS if category in grouped]
    preferred_order.extend(category for category in ordered_categories if category not in preferred_order)
    sections = []
    for category in preferred_order:
        section_body = "\n\n".join(block["block"] for block in grouped[category])
        sections.append(
            f"# {category}\n\n"
            f"{_daily_note_topic_summary(category, section_body, user_profile=user_profile)}\n\n"
            f"{section_body}"
        )
    return "\n\n".join(sections).rstrip() + "\n"


def _llm_review_daily_note_categories(
    content: str,
    *,
    user_profile: Optional[Dict[str, Any]] = None,
) -> str:
    blocks = _extract_daily_note_paper_blocks(content)
    if not blocks:
        return content
    assignments = _llm_daily_note_category_assignments(blocks, user_profile=user_profile)
    if not assignments:
        return content
    return _rebuild_daily_note_from_blocks(blocks, assignments, user_profile=user_profile)


def _refresh_daily_note_topic_summaries(
    content: str,
    *,
    user_profile: Optional[Dict[str, Any]] = None,
) -> str:
    text = re.sub(
        r"\n?<!-- paperflow-topic-summary:start -->.*?<!-- paperflow-topic-summary:end -->\n?",
        "\n",
        str(content or ""),
        flags=re.DOTALL,
    )
    matches = list(re.finditer(r"^#\s+(.+)$", text, flags=re.MULTILINE))
    if not matches:
        return text
    pieces: List[str] = []
    for index, match in enumerate(matches):
        start = match.start()
        body_start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        if index == 0:
            pieces.append(text[:body_start])
        else:
            pieces.append(text[start:body_start])
        category = match.group(1).strip()
        section_body = text[body_start:end]
        pieces.append("\n\n")
        pieces.append(_daily_note_topic_summary(category, section_body, user_profile=user_profile))
        pieces.append("\n")
        pieces.append(section_body.strip("\n"))
        if index + 1 < len(matches):
            pieces.append("\n\n")
    return "\n".join(part.rstrip("\n") for part in pieces if part is not None).strip() + "\n"


def _sync_obsidian_toc(daily_note: Path) -> None:
    year_dir = daily_note.parent
    match = re.fullmatch(r"Daily Note - ([A-Za-z]+) (20\d{2})\.md", daily_note.name)
    if not match:
        return
    month_label, year = match.groups()
    toc = year_dir / f"Table of Content - {year}.md"
    link_name = daily_note.stem
    entry = f"# {link_name}\n[[{link_name}]]"
    current = toc.read_text(encoding="utf-8") if toc.exists() else ""
    if f"[[{link_name}]]" in current:
        return
    toc.write_text(current.rstrip() + ("\n" if current.strip() else "") + entry + "\n", encoding="utf-8")


def _save_reading_report_markdown(
    *,
    user_id: str,
    paper: Dict[str, Any],
    report_content: str,
    report_payload: Dict[str, Any],
    doc_url: Optional[str] = None,
    doc_token: Optional[str] = None,
) -> str:
    target_dir = _resolve_configured_dir(
        "PAPERFLOW_READING_REPORTS_DIR",
        "data/exports",
        paper,
        user_id=user_id,
        category="reading_reports",
    )
    obsidian_report = target_dir.name.startswith("Deep Reading - ")
    report_path = target_dir / (
        f"{_paper_title_file_stem(paper)}.md"
        if obsidian_report
        else f"{_paper_file_stem(paper)} - reading-report.md"
    )
    daily_note_path = _obsidian_daily_note_path(report_path, paper) if obsidian_report else None
    metadata = {
        "user_id": user_id,
        "paper_id": paper.get("id"),
        "arxiv_id": paper.get("arxiv_id"),
        "doi": paper.get("doi"),
        "title": paper.get("title"),
        "institution": report_payload.get("institution") or paper.get("institution") or paper.get("affiliation"),
        "publish_date": paper.get("publish_date"),
        "pdf_path": paper.get("pdf_path"),
        "pdf_url": paper.get("pdf_url"),
        "abs_url": paper.get("abs_url") or paper.get("paper_url") or paper.get("url"),
        "doc_url": doc_url,
        "doc_token": doc_token,
        "generation_provider": report_payload.get("generation_provider"),
        "generation_model": report_payload.get("generation_model"),
        "response_language": report_payload.get("response_language"),
        "report_version": READING_REPORT_OUTPUT_VERSION,
        "daily_note_path": str(daily_note_path) if daily_note_path else None,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    frontmatter = ["---"]
    for key, value in metadata.items():
        if value not in (None, "", [], {}):
            frontmatter.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    frontmatter.extend(["---", ""])
    report_path.write_text(
        "\n".join(frontmatter) + report_content.strip() + "\n",
        encoding="utf-8",
    )
    daily_note_written = _sync_obsidian_daily_note(
        user_id=user_id,
        paper=paper,
        report_payload=report_payload,
        report_path=report_path,
        report_content=report_content,
    )
    if daily_note_written:
        print(f"  Updated Daily Note: {daily_note_written}")
    print(f"  Saved reading markdown: {report_path}")
    return str(report_path)


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


def enrich_paper_for_reading_report(
    paper: Dict[str, Any],
    user_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[str]]:
    """
    Enrich paper data for reading report generation.

    If paper has 'pdf_path' key, use local PDF directly instead of downloading.
    """
    prefer_detail_abstract = _looks_like_feed_metadata_abstract((paper or {}).get("abstract"))
    enriched = _normalize_paper(paper)
    if prefer_detail_abstract:
        enriched["_prefer_detail_abstract"] = True
    pdf_error: Optional[str] = None
    parsed_pdf: Optional[Dict[str, Any]] = None
    detail_fetch_failed = False

    if prefer_detail_abstract or not _paper_has_sufficient_metadata_for_report(enriched):
        enriched = _backfill_metadata_from_source_page(enriched)

    source_page_document = _get_source_page_document(enriched)

    # If paper has local pdf_path, use it directly
    local_pdf_path = enriched.get("pdf_path")
    if local_pdf_path and os.path.exists(local_pdf_path):
        try:
            print(f"  Parsing local PDF: {local_pdf_path}")
            parsed_pdf = _parse_pdf_for_report(local_pdf_path)
            parsed_pdf["source_kind"] = "pdf"
            stored_pdf_path = _persist_pdf_file(
                local_pdf_path,
                enriched,
                _clean_text(enriched.get("pdf_url")),
                user_id=user_id,
            )
            if stored_pdf_path:
                enriched["pdf_path"] = stored_pdf_path
            print("  Local PDF parsed successfully")

            # Enrich metadata from parsed PDF
            if _looks_like_placeholder_title(enriched.get("title", "")) and _clean_text(parsed_pdf.get("title")):
                enriched["title"] = _clean_text(parsed_pdf.get("title"))
            if _prefer_candidate_abstract(enriched.get("abstract"), parsed_pdf.get("abstract")):
                enriched["abstract"] = _clean_text(parsed_pdf.get("abstract"))
            if not enriched.get("authors"):
                enriched["authors"] = _parse_jsonish_list(parsed_pdf.get("authors"))

            return enriched, parsed_pdf, None
        except Exception as exc:
            pdf_error = str(exc)
            print(f"Local PDF parsing failed: {exc}")

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
        if _env_flag("PAPERFLOW_SAVE_PDF_WITHOUT_ENRICHMENT", default=True):
            download_candidates = _build_pdf_download_candidates(enriched, pdf_url) or [pdf_url]
            stored_pdf_path: Optional[str] = None
            try:
                for download_candidate in download_candidates:
                    try:
                        download_referer = _pick_download_referer(enriched, download_candidate)
                        print(f"  Downloading PDF for storage: {download_candidate[:120]}")
                        temp_pdf_path = _download_pdf(
                            download_candidate,
                            enriched.get("title", "paper"),
                            referer=download_referer,
                        )
                        enriched["pdf_url"] = download_candidate
                        stored_pdf_path = _persist_pdf_file(
                            temp_pdf_path,
                            enriched,
                            download_candidate,
                            user_id=user_id,
                        )
                        if stored_pdf_path:
                            enriched["pdf_path"] = stored_pdf_path
                        break
                    except Exception as exc:
                        pdf_error = str(exc)
                        print(f"  PDF storage download failed ({download_candidate[:120]}): {exc}")
                        continue
            finally:
                if temp_pdf_path:
                    try:
                        temp_path = Path(temp_pdf_path)
                        if not stored_pdf_path or temp_path.resolve() != Path(stored_pdf_path).resolve():
                            temp_path.unlink(missing_ok=True)
                    except OSError:
                        pass

    if pdf_url and should_parse_pdf:
        download_candidates = _build_pdf_download_candidates(enriched, pdf_url) or [pdf_url]
        last_exception: Optional[Exception] = None
        stored_pdf_path: Optional[str] = None
        try:
            for download_candidate in download_candidates:
                try:
                    download_referer = _pick_download_referer(enriched, download_candidate)
                    print(f"  Downloading PDF for enrichment: {download_candidate[:120]}")
                    temp_pdf_path = _download_pdf(
                        download_candidate,
                        enriched.get("title", "paper"),
                        referer=download_referer,
                    )
                    parsed_pdf = _parse_pdf_for_report(temp_pdf_path)
                    parsed_pdf["source_kind"] = "pdf"
                    enriched["pdf_url"] = download_candidate
                    stored_pdf_path = _persist_pdf_file(
                        temp_pdf_path,
                        enriched,
                        download_candidate,
                        user_id=user_id,
                    )
                    if stored_pdf_path:
                        enriched["pdf_path"] = stored_pdf_path
                    pdf_error = None
                    print("  PDF enrichment parsed successfully")
                    break
                except Exception as exc:
                    last_exception = exc
                    pdf_error = str(exc)
                    print(
                        f"  PDF download attempt failed ({download_candidate[:120]}): {exc}"
                    )
                    continue
            if parsed_pdf is None and last_exception is not None:
                print(f"PDF enrichment failed for {enriched.get('title', 'Unknown')}: {last_exception}")
        finally:
            if temp_pdf_path:
                try:
                    temp_path = Path(temp_pdf_path)
                    if not stored_pdf_path or temp_path.resolve() != Path(stored_pdf_path).resolve():
                        temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    if parsed_pdf:
        if _looks_like_placeholder_title(enriched.get("title", "")) and _clean_text(parsed_pdf.get("title")):
            enriched["title"] = _clean_text(parsed_pdf.get("title"))
        if _prefer_candidate_abstract(enriched.get("abstract"), parsed_pdf.get("abstract")):
            enriched["abstract"] = _clean_text(parsed_pdf.get("abstract"))
        if not enriched.get("authors"):
            enriched["authors"] = _parse_jsonish_list(parsed_pdf.get("authors"))

    if parsed_pdf is None and source_page_document:
        parsed_pdf = source_page_document

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


def _format_pdf_section_label(section: str) -> str:
    normalized = _clean_text(section).replace("_", " ").replace("-", " ")
    if not normalized:
        return "PDF"
    return normalized.title()


def _summarize_profile_for_embedding(user_profile: Dict[str, Any]) -> str:
    core_directions = user_profile.get("core_directions", {}) or {}
    sorted_directions = sorted(
        core_directions.items(),
        key=lambda item: float(item[1]),
        reverse=True,
    )
    direction_parts = [
        f"{_format_direction_label(direction)} ({float(weight):.2f})"
        for direction, weight in sorted_directions[:4]
    ]

    preferences = user_profile.get("methodology_preferences", {}) or {}
    preference_parts: List[str] = []
    if preferences.get("preference_data_driven_over_theory"):
        preference_parts.append("data-driven empirical work")
    if preferences.get("preference_systematic_work_over_incremental"):
        preference_parts.append("systematic end-to-end frameworks")
    if preferences.get("preference_bio_science_application"):
        preference_parts.append("bio and science applications")

    blocks: List[str] = []
    if direction_parts:
        blocks.append("Research directions: " + ", ".join(direction_parts))
    if preference_parts:
        blocks.append("Method preferences: " + ", ".join(preference_parts))
    return ". ".join(blocks)


def _get_reading_evidence_cache_dir() -> Path:
    configured = os.environ.get("READING_REPORT_EVIDENCE_CACHE_DIR", "").strip()
    if configured:
        cache_dir = Path(configured).expanduser()
        if not cache_dir.is_absolute():
            cache_dir = (Path(__file__).resolve().parents[2] / cache_dir).resolve()
    else:
        cache_dir = (Path(__file__).resolve().parents[2] / "data" / "cache" / "reading_evidence").resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _build_evidence_cache_key(
    paper: Dict[str, Any],
    user_profile: Dict[str, Any],
    parsed_pdf: Optional[Dict[str, Any]],
    descriptor: str,
) -> str:
    sections = dict((parsed_pdf or {}).get("sections") or {})
    preferred_top_k = _preferred_evidence_top_k(user_profile)
    payload = {
        "paper": {
            "id": paper.get("id"),
            "title": _clean_text(paper.get("title")),
            "arxiv_id": _clean_text(paper.get("arxiv_id")),
            "doi": _clean_text(paper.get("doi")),
        },
        "profile_summary": _summarize_profile_for_embedding(user_profile),
        "profile_preferences": user_profile.get("methodology_preferences") or {},
        "evidence_version": READING_REPORT_EVIDENCE_VERSION,
        "descriptor": descriptor,
        "chunk_chars": READING_REPORT_CHUNK_CHARS,
        "chunk_overlap": READING_REPORT_CHUNK_OVERLAP,
        "top_k": preferred_top_k,
        "profile_retrieval_weight": READING_REPORT_PROFILE_RETRIEVAL_WEIGHT,
        "pdf": {
            "abstract": _clean_text((parsed_pdf or {}).get("abstract")),
            "full_text": _clean_text((parsed_pdf or {}).get("full_text")),
            "sections": {key: _clean_text(value) for key, value in sections.items()},
        },
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_cached_retrieved_evidence(cache_key: str) -> Optional[Dict[str, Any]]:
    if not READING_REPORT_EVIDENCE_CACHE_ENABLED:
        return None
    cache_path = _get_reading_evidence_cache_dir() / f"{cache_key}.json"
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _save_cached_retrieved_evidence(cache_key: str, evidence: Dict[str, Any]) -> None:
    if not READING_REPORT_EVIDENCE_CACHE_ENABLED or not isinstance(evidence, dict) or not evidence:
        return
    cache_path = _get_reading_evidence_cache_dir() / f"{cache_key}.json"
    try:
        cache_path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
    except OSError:
        return


def _chunk_text_with_overlap(
    text: str,
    section: str,
    max_chars: int = READING_REPORT_CHUNK_CHARS,
    overlap: int = READING_REPORT_CHUNK_OVERLAP,
) -> List[Dict[str, Any]]:
    normalized = _clean_pdf_evidence_text(text)
    if not normalized:
        return []

    if max_chars <= 0:
        max_chars = READING_REPORT_CHUNK_CHARS
    overlap = max(0, min(overlap, max_chars // 2 if max_chars > 1 else 0))

    chunks: List[Dict[str, Any]] = []
    start = 0
    text_length = len(normalized)
    while start < text_length:
        end = min(text_length, start + max_chars)
        if end < text_length:
            window = normalized[start:end]
            boundary_candidates = [
                window.rfind("\n\n"),
                window.rfind(". "),
                window.rfind("? "),
                window.rfind("! "),
                window.rfind("; "),
                window.rfind("。"),
                window.rfind("！"),
                window.rfind("？"),
                window.rfind("；"),
            ]
            boundary = max(boundary_candidates)
            if boundary >= max_chars // 2:
                boundary_len = 2 if window[boundary:boundary + 2] in {". ", "? ", "! ", "; ", "\n\n"} else 1
                end = start + boundary + boundary_len

        chunk_text = normalized[start:end].strip()
        chunk_text = _clean_pdf_evidence_text(chunk_text)
        if chunk_text and not _is_noisy_pdf_evidence_text(chunk_text):
            chunks.append(
                {
                    "section": _clean_text(section) or "full_text",
                    "text": chunk_text,
                    "start": start,
                    "end": end,
                    "chunk_index": len(chunks),
                }
            )

        if end >= text_length:
            break

        next_start = max(end - overlap, start + 1)
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks


def _build_pdf_chunks(parsed_pdf: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(parsed_pdf, dict):
        return []

    chunks: List[Dict[str, Any]] = []
    abstract = _clean_text(parsed_pdf.get("abstract"))
    if abstract:
        chunks.extend(_chunk_text_with_overlap(abstract, "abstract"))

    sections = parsed_pdf.get("sections") or {}
    if isinstance(sections, dict):
        preferred_order = [
            "introduction",
            "background",
            "method",
            "approach",
            "model",
            "results",
            "experiments",
            "evaluation",
            "discussion",
            "limitations",
            "conclusion",
        ]
        ordered_keys = preferred_order + [key for key in sections.keys() if key not in preferred_order]
        for section_name in ordered_keys:
            section_text = _clean_text(sections.get(section_name))
            if section_text:
                chunks.extend(_chunk_text_with_overlap(section_text, section_name))

    if not chunks:
        full_text = _clean_text(parsed_pdf.get("full_text"))
        if full_text:
            chunks.extend(_chunk_text_with_overlap(full_text, "full_text"))

    deduped: List[Dict[str, Any]] = []
    seen_texts = set()
    for chunk in chunks:
        key = chunk["text"].casefold()
        if key in seen_texts:
            continue
        seen_texts.add(key)
        deduped.append(chunk)
    return deduped


def _collect_evidence_sentences(
    evidence: Dict[str, Any],
    bucket: str,
    *,
    limit: int,
    cues: Tuple[str, ...] = (),
) -> List[str]:
    matches = ((evidence or {}).get("matches") or {}).get(bucket) or []
    collected: List[str] = []
    for match in matches:
        text = _clean_pdf_evidence_text(match.get("text"))
        if not text:
            continue
        picked = _pick_sentences(text, limit=limit, cues=cues)
        if picked:
            collected.extend(picked)
        elif not _is_noisy_pdf_evidence_text(text):
            collected.append(_truncate_text(text, 180))
        unique = _unique_preserve_order(collected)
        if len(unique) >= limit:
            return unique[:limit]
    return _unique_preserve_order(collected)[:limit]


def _collect_evidence_sections(evidence: Dict[str, Any], bucket: str, *, limit: int = 3) -> List[str]:
    matches = ((evidence or {}).get("matches") or {}).get(bucket) or []
    labels = [
        _format_pdf_section_label(match.get("section", ""))
        for match in matches
        if _clean_text(match.get("section"))
    ]
    return _unique_preserve_order(labels)[:limit]


def _format_evidence_anchor(match: Dict[str, Any]) -> str:
    section = _format_pdf_section_label(match.get("section", ""))
    text = _truncate_text(_clean_pdf_evidence_text(match.get("text")), 180)
    score = match.get("score")
    score_text = f" | score={float(score):.3f}" if isinstance(score, (int, float)) else ""
    return f"{section}{score_text} | {text}"


def _build_field_evidence_map(retrieved_evidence: Dict[str, Any]) -> Dict[str, List[str]]:
    matches = (retrieved_evidence or {}).get("matches") or {}

    def anchor_list(*buckets: str, limit: int = 2) -> List[str]:
        anchors: List[str] = []
        for bucket in buckets:
            for match in matches.get(bucket) or []:
                anchors.append(_format_evidence_anchor(match))
        return _unique_preserve_order(anchors)[:limit]

    return {
        "one_sentence_summary": anchor_list("method", "results", limit=2),
        "research_background": anchor_list("background", limit=2),
        "core_method": anchor_list("method", limit=2),
        "key_results": anchor_list("results", limit=2),
        "main_contributions": anchor_list("method", "results", limit=3),
        "limitations": anchor_list("limitations", limit=2),
        "relevance_points": anchor_list("relevance", limit=2),
        "reading_focus": anchor_list("relevance", "method", "results", limit=3),
    }


def _build_report_evidence_anchors(retrieved_evidence: Dict[str, Any]) -> Dict[str, List[str]]:
    matches = (retrieved_evidence or {}).get("matches") or {}
    top_k = int((retrieved_evidence or {}).get("top_k") or READING_REPORT_EVIDENCE_TOP_K)
    anchors: Dict[str, List[str]] = {}
    seen_texts: set[str] = set()
    for bucket in ("background", "method", "results", "limitations", "relevance"):
        bucket_matches = matches.get(bucket) or []
        preferred_items: List[str] = []
        fallback_items: List[str] = []
        for match in bucket_matches:
            if not isinstance(match, dict):
                continue
            text_key = _clean_text(match.get("text")).casefold()
            item = _format_evidence_anchor(match)
            if text_key and text_key not in seen_texts:
                preferred_items.append(item)
                seen_texts.add(text_key)
            else:
                fallback_items.append(item)
        items = _unique_preserve_order(preferred_items)[:top_k]
        if not items:
            items = _unique_preserve_order(fallback_items)[: min(top_k, 1)]
        if items:
            anchors[bucket] = items
    return anchors


def _retrieve_report_evidence(
    paper: Dict[str, Any],
    user_profile: Dict[str, Any],
    parsed_pdf: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    chunks = _build_pdf_chunks(parsed_pdf)
    if not chunks:
        return {}

    profile_summary = _summarize_profile_for_embedding(user_profile)
    title = _clean_text(paper.get("title"))
    abstract = _clean_text(paper.get("abstract"))

    query_specs = [
        {
            "bucket": "background",
            "query": f"{title}\n{abstract}\nresearch background motivation problem challenge prior work",
            "preferred_sections": ("abstract", "introduction", "background"),
        },
        {
            "bucket": "method",
            "query": f"{title}\n{abstract}\ncore method approach model framework algorithm training pipeline",
            "preferred_sections": ("method", "approach", "model", "full_text"),
        },
        {
            "bucket": "results",
            "query": f"{title}\n{abstract}\nmain results experiments evaluation outperform improvement benchmark ablation",
            "preferred_sections": ("results", "experiments", "evaluation"),
        },
        {
            "bucket": "limitations",
            "query": f"{title}\n{abstract}\nlimitations future work discussion challenge failure case",
            "preferred_sections": ("discussion", "limitations", "conclusion"),
        },
        {
            "bucket": "relevance",
            "query": (
                f"{title}\n{abstract}\n"
                f"reader research interests relevance use cases methodology overlap {profile_summary}"
            ),
            "preferred_sections": ("abstract", "introduction", "method", "results"),
        },
    ]

    try:
        embedding_module = _load_embedding_module()
        service = embedding_module.get_embedding_service()
        descriptor = getattr(service, "descriptor", "")
        cache_key = _build_evidence_cache_key(paper, user_profile, parsed_pdf, descriptor)
        cached = _load_cached_retrieved_evidence(cache_key)
        if cached:
            return cached
        query_texts = [item["query"] for item in query_specs]
        chunk_texts = [chunk["text"] for chunk in chunks]
        profile_query_text = profile_summary or title or abstract
        vectors = service.embed_batch(query_texts + chunk_texts + [profile_query_text])
        query_vectors = vectors[: len(query_specs)]
        chunk_vectors = vectors[len(query_specs):len(query_specs) + len(chunk_texts)]
        profile_vector = vectors[-1]

        top_k = _preferred_evidence_top_k(user_profile)
        matches: Dict[str, List[Dict[str, Any]]] = {}
        used_texts_global: set[str] = set()
        for query_spec, query_vector in zip(query_specs, query_vectors):
            preferred_sections = set(query_spec["preferred_sections"])
            preferred_available = any((chunk.get("section") or "") in preferred_sections for chunk in chunks)
            ranked: List[Dict[str, Any]] = []
            for chunk, chunk_vector in zip(chunks, chunk_vectors):
                section = _clean_text(chunk.get("section")).lower() or "full_text"
                score = float(service.cosine_similarity(query_vector, chunk_vector))
                profile_score = float(service.cosine_similarity(profile_vector, chunk_vector)) if profile_query_text else 0.0
                if section in preferred_sections:
                    score += 0.14
                elif preferred_available:
                    score -= 0.10
                elif section == "abstract":
                    score += 0.02

                bucket = query_spec["bucket"]
                if bucket == "background":
                    if section in {"method", "approach", "model", "results", "experiments", "evaluation"}:
                        score -= 0.08
                elif bucket == "method":
                    if preferred_available and section in {"abstract", "introduction", "background", "discussion", "conclusion"}:
                        score -= 0.12
                elif bucket == "results":
                    if preferred_available and section in {"abstract", "introduction", "background", "method", "approach", "model"}:
                        score -= 0.12
                elif bucket == "limitations":
                    if preferred_available and section in {
                        "abstract",
                        "introduction",
                        "background",
                        "method",
                        "approach",
                        "model",
                        "results",
                        "experiments",
                        "evaluation",
                    }:
                        score -= 0.14

                score += profile_score * READING_REPORT_PROFILE_RETRIEVAL_WEIGHT
                if bucket == "relevance":
                    score += profile_score * READING_REPORT_PROFILE_RETRIEVAL_WEIGHT
                    if section in {"method", "results", "discussion", "conclusion"}:
                        score += 0.05
                    elif section == "abstract":
                        score -= 0.02
                ranked.append({**chunk, "score": score, "profile_score": profile_score})

            ranked.sort(key=lambda item: item["score"], reverse=True)
            primary_ranked = (
                [item for item in ranked if _clean_text(item.get("section")).lower() in preferred_sections]
                if preferred_available
                else list(ranked)
            )
            if not primary_ranked:
                primary_ranked = list(ranked)
            selected: List[Dict[str, Any]] = []
            seen_texts_local = set()
            fallback_selected: List[Dict[str, Any]] = []
            for item in primary_ranked:
                key = item["text"].casefold()
                if key in seen_texts_local:
                    continue
                seen_texts_local.add(key)
                if key in used_texts_global:
                    fallback_selected.append(item)
                    continue
                selected.append(item)
                if len(selected) >= top_k:
                    break
            if len(selected) < top_k:
                for item in fallback_selected:
                    selected.append(item)
                    if len(selected) >= top_k:
                        break
            matches[query_spec["bucket"]] = selected
            used_texts_global.update(item["text"].casefold() for item in selected if item.get("text"))

        result = {
            "descriptor": getattr(service, "descriptor", ""),
            "chunk_count": len(chunks),
            "profile_retrieval_weight": READING_REPORT_PROFILE_RETRIEVAL_WEIGHT,
            "top_k": top_k,
            "matches": matches,
        }
        _save_cached_retrieved_evidence(cache_key, result)
        return result
    except Exception as exc:
        print(f"PDF evidence retrieval failed: {exc}")
        return {}


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
    response_language: str = "zh",
) -> List[str]:
    is_en = _normalize_response_language(response_language) == "en"
    text_lower = combined_text.lower()
    points: List[str] = []

    core_directions = user_profile.get("core_directions", {}) or {}
    sorted_directions = sorted(core_directions.items(), key=lambda item: float(item[1]), reverse=True)

    matched: List[str] = []
    for direction, weight in sorted_directions[:3]:
        tokens = str(direction).lower().replace("-", " ").replace("_", " ").split()
        if str(direction).lower() in text_lower or any(token in text_lower for token in tokens if len(token) >= 4):
            if is_en:
                matched.append(f"{_format_direction_label(direction, response_language)} (weight {float(weight):.2f})")
            else:
                matched.append(f"{_format_direction_label(direction)}（权重 {float(weight):.2f}）")

    if matched:
        points.append(
            f"This paper directly overlaps with the current profile directions: {', '.join(matched)}."
            if is_en
            else f"这篇论文和你当前画像里的方向有直接重合：{', '.join(matched)}。"
        )
    elif sorted_directions:
        direction_label = _format_direction_label(sorted_directions[0][0], response_language)
        points.append(
            f"It may not exactly match the current core direction, {direction_label}, but its method design and evaluation structure are worth inspecting."
            if is_en
            else f"它不一定和你当前最核心的 {direction_label} 完全同题，但方法设计和评测组织值得借鉴。"
        )
    else:
        points.append(
            "The current profile is still learning; this paper can act as a new interest anchor for deciding whether to keep tracking the topic."
            if is_en
            else "你当前画像还在持续学习阶段，这篇论文适合作为新的兴趣锚点来判断后续是否继续追踪。"
        )

    preferences = user_profile.get("methodology_preferences", {}) or {}
    if preferences.get("preference_data_driven_over_theory"):
        points.append(
            "Methodologically, it leans toward a data-driven or empirically validated path, which matches the current profile preference."
            if is_en
            else "从方法论上看，它偏向数据驱动或实验验证路径，和你当前偏好比较一致。"
        )
    if preferences.get("preference_systematic_work_over_incremental"):
        points.append(
            "If the profile favors systematic work, focus on how the paper organizes the task setup, experiment protocol, and overall framework."
            if is_en
            else "如果你更看重系统性工作，可以重点看它如何组织任务设定、实验协议和整体框架。"
        )
    if preferences.get("preference_bio_science_application"):
        points.append(
            "For bio or science-application interests, pay extra attention to the task setting, data source, and deployment boundary."
            if is_en
            else "若你当前关注生物或科学应用，建议额外留意论文中的任务场景、数据来源和落地边界。"
        )
    if parsed_pdf and parsed_pdf.get("sections", {}).get("results"):
        points.append(
            "Spend time on Results / Experiments to judge whether the gains come from the core method rather than experimental tricks."
            if is_en
            else "建议把精力放在 Results/Experiments 部分，判断提升是否真正来自核心方法而不是实验技巧。"
        )

    score = float(paper.get("score") or 0.0)
    if score > 0:
        points.append(
            f"The current recommendation score is about {score:.2f}; the system sees some relevance to the profile."
            if is_en
            else f"当前推荐分约为 {score:.2f}，系统判断它与画像存在一定相关性。"
        )

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


def _extract_heuristic_keywords(
    paper: Dict[str, Any],
    abstract: str,
    parsed_pdf: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Heuristic keyword extraction (fallback when LLM doesn't return keywords).

    Picks 5-8 short noun phrases from title + abstract by frequency,
    excluding stopwords. Each phrase is 1-3 lowercase words.
    """
    title = _clean_text(paper.get("title")) or ""
    abstract_text = _clean_text(abstract) or ""
    pdf_text = ""
    if parsed_pdf:
        pdf_text = _clean_text(parsed_pdf.get("abstract") or parsed_pdf.get("body_text") or "")
    corpus = " ".join(filter(None, [title, abstract_text, pdf_text[:2000]])).lower()
    if not corpus:
        return []

    stop = {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
        "by", "is", "are", "was", "were", "be", "been", "being", "this", "that",
        "these", "those", "we", "our", "ours", "i", "me", "my", "they", "them",
        "their", "it", "its", "as", "at", "from", "into", "than", "but",
        "can", "could", "may", "might", "must", "should", "would", "will",
        "have", "has", "had", "do", "does", "did", "not", "no", "yes", "if",
        "while", "such", "more", "most", "less", "least", "very", "much",
        "however", "thus", "hence", "also", "only", "even", "still", "yet",
        "show", "shows", "showed", "shown", "use", "used", "using", "uses",
        "propose", "proposed", "proposes", "proposing", "present", "presents",
        "presented", "presenting", "introduce", "introduces", "introduced",
        "achieve", "achieves", "achieved", "based", "method", "methods",
        "approach", "approaches", "model", "models", "result", "results",
        "paper", "papers", "study", "studies", "studied", "work", "works",
        "experiment", "experiments", "task", "tasks", "data", "dataset",
        "datasets", "table", "tables", "figure", "figures", "section",
        "sections", "appendix", "et", "al", "etc", "ie", "eg",
    }
    tokens = re.findall(r"[a-z][a-z0-9\-]+", corpus)
    tokens = [t for t in tokens if t not in stop and len(t) > 2]

    bigrams = [f"{tokens[i]} {tokens[i + 1]}" for i in range(len(tokens) - 1)]
    bigrams = [b for b in bigrams if not any(w in stop for w in b.split())]

    counts: Dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    bigram_counts: Dict[str, int] = {}
    for bigram in bigrams:
        bigram_counts[bigram] = bigram_counts.get(bigram, 0) + 1

    picked: List[str] = []
    for bigram, count in sorted(bigram_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if count < 2:
            break
        picked.append(bigram)
        if len(picked) >= 5:
            break

    bigram_words = {word for phrase in picked for word in phrase.split()}
    for token, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if count < 3 or token in bigram_words:
            continue
        if token in {p.split()[0] for p in picked} | {p.split()[-1] for p in picked}:
            continue
        picked.append(token)
        if len(picked) >= 8:
            break

    return picked[:8]


def build_heuristic_report_payload(
    paper: Dict[str, Any],
    user_profile: Dict[str, Any],
    parsed_pdf: Optional[Dict[str, Any]] = None,
    pdf_error: Optional[str] = None,
    response_language: str = "zh",
) -> Dict[str, Any]:
    language = _normalize_response_language(response_language)
    is_en = language == "en"
    sections = dict((parsed_pdf or {}).get("sections") or {})
    parsed_source_kind = _clean_text((parsed_pdf or {}).get("source_kind")).lower() or ("pdf" if parsed_pdf else "abstract")
    if _prefer_candidate_abstract(paper.get("abstract"), (parsed_pdf or {}).get("abstract")):
        abstract = _clean_abstract_text((parsed_pdf or {}).get("abstract"))
    else:
        abstract = _clean_abstract_text(_first_non_empty(paper.get("abstract"), (parsed_pdf or {}).get("abstract")))
    introduction = _truncate_text(sections.get("introduction"), MAX_SECTION_CHARS)
    method = _truncate_text(sections.get("method"), MAX_SECTION_CHARS)
    results = _truncate_text(sections.get("results"), MAX_SECTION_CHARS)
    discussion = _truncate_text(sections.get("discussion"), MAX_SECTION_CHARS)
    conclusion = _truncate_text(sections.get("conclusion"), MAX_SECTION_CHARS)
    retrieved_evidence = _retrieve_report_evidence(paper, user_profile, parsed_pdf)

    # 优先使用 PDF 切块后的语义检索证据，其次回退到章节摘要/abstract 启发式
    bg_from_evidence = " ".join(_collect_evidence_sentences(retrieved_evidence, "background", limit=2))
    bg_from_pdf = " ".join(_pick_sentences(introduction, limit=2)) if introduction else ""
    bg_from_abstract = _infer_section_from_abstract(abstract, "background")
    research_background = _first_non_empty(bg_from_evidence, bg_from_pdf, bg_from_abstract)
    if not research_background:
        research_background = (
            "Start with the original abstract and introduction to understand the research background."
            if is_en
            else "建议先查看原文摘要和引言部分以了解研究背景。"
        )

    method_from_evidence = " ".join(
        _collect_evidence_sentences(
            retrieved_evidence,
            "method",
            limit=2,
            cues=CONTRIBUTION_CUES,
        )
    )
    method_from_pdf = " ".join(_pick_sentences(method, limit=2, cues=CONTRIBUTION_CUES)) if method else ""
    method_from_abstract = _infer_section_from_abstract(abstract, "method")
    core_method = _first_non_empty(method_from_evidence, method_from_pdf, method_from_abstract)
    if not core_method:
        core_method = (
            "Method details were not extracted reliably; focus on the Method / Approach section in the original paper."
            if is_en
            else "方法细节建议重点查看原文的 Method / Approach 部分。"
        )

    results_from_evidence = " ".join(
        _collect_evidence_sentences(
            retrieved_evidence,
            "results",
            limit=2,
            cues=RESULT_CUES,
        )
    )
    results_from_pdf = " ".join(_pick_sentences(results, limit=2, cues=RESULT_CUES)) if results else ""
    results_from_abstract = _infer_section_from_abstract(abstract, "results")
    key_results = _first_non_empty(results_from_evidence, results_from_pdf, results_from_abstract)
    if not key_results:
        key_results = (
            "Experimental results were not extracted reliably; check the tables, figures, and main metrics in the original paper."
            if is_en
            else "实验结果建议重点核对原文表格、图示和主要指标。"
        )

    summary_candidates = _pick_sentences(abstract, limit=1, cues=CONTRIBUTION_CUES + RESULT_CUES)
    if not summary_candidates:
        summary_candidates = _collect_evidence_sentences(
            retrieved_evidence,
            "method",
            limit=1,
            cues=CONTRIBUTION_CUES,
        )
    if not summary_candidates:
        summary_candidates = _pick_sentences(introduction or abstract, limit=1)
    one_sentence_summary = summary_candidates[0] if summary_candidates else (
        "The core claim still needs to be verified against the original paper."
        if is_en
        else "本文的核心信息仍建议结合原文进一步核对。"
    )

    main_contributions = _unique_preserve_order(
        _collect_evidence_sentences(retrieved_evidence, "method", limit=2, cues=CONTRIBUTION_CUES)
        + _collect_evidence_sentences(retrieved_evidence, "results", limit=1, cues=RESULT_CUES)
        + _pick_sentences(abstract, limit=3, cues=CONTRIBUTION_CUES)
        + _pick_sentences(method, limit=2, cues=CONTRIBUTION_CUES)
        + _pick_sentences(results, limit=1, cues=RESULT_CUES)
    )[:3]
    if not main_contributions:
        main_contributions = (
            [
                "The paper gives a clear problem definition and task setup, making it useful as an entry point into the area.",
                "The method thread is worth following directly; use the original figures to understand how the modules connect.",
                "The experiments should be checked carefully to verify whether the conclusion really follows from the method contribution.",
            ]
            if is_en
            else [
                "论文给出了明确的问题定义和任务设定，适合作为领域入口文献来读。",
                "文中提供了可直接关注的方法主线，建议结合原文图表理解其模块关系。",
                "实验部分值得重点核对，以确认结论是否和方法创新真正对应。",
            ]
        )

    limitations = _unique_preserve_order(
        _collect_evidence_sentences(retrieved_evidence, "limitations", limit=2, cues=LIMITATION_CUES)
        + _pick_sentences(conclusion, limit=2, cues=LIMITATION_CUES)
        + _pick_sentences(discussion, limit=2, cues=LIMITATION_CUES)
    )
    if not limitations:
        limitations = [
            (
                "The limitations are not clearly expanded in the extracted text; check data coverage, evaluation setup, and generalization boundaries."
                if is_en
                else "文中未明显展开局限性，阅读时建议重点核对数据覆盖范围、评测设置和泛化边界。"
            )
        ]
        if pdf_error:
            limitations.append(
                "The PDF was not fetched successfully, so method and experiment details should still be verified in the original paper."
                if is_en
                else "本次未成功抓取 PDF，方法与实验细节部分仍应以原文为准。"
            )

    reading_focus = []
    evidence_sections = _collect_evidence_sections(retrieved_evidence, "relevance")
    if evidence_sections:
        reading_focus.append(
            f"First verify the full-text sections hit by semantic retrieval: {' / '.join(evidence_sections)}."
            if is_en
            else f"优先核对语义命中的全文片段：{' / '.join(evidence_sections)}。"
        )
    if introduction:
        reading_focus.append(
            "Start with the Introduction to identify the exact gap the paper claims to fill."
            if is_en
            else "先看 Introduction，确认论文到底在补哪一块空白。"
        )
    if method:
        reading_focus.append(
            "Then read Method / Approach to clarify the core modules, training objective, and input-output relationships."
            if is_en
            else "再看 Method / Approach，把核心模块、训练目标和输入输出关系理清。"
        )
    if results:
        reading_focus.append(
            "Focus on Experiments / Results to verify where the improvement comes from and whether the baselines are fair."
            if is_en
            else "重点看 Experiments / Results，确认提升来自哪里，以及 baseline 是否公平。"
        )
    if conclusion or discussion:
        reading_focus.append(
            "Finally read Conclusion / Discussion to see how the authors define boundaries and next steps."
            if is_en
            else "最后看 Conclusion / Discussion，判断作者自己如何定义边界与下一步。"
        )
    if not reading_focus:
        reading_focus.append(
            "Start with the abstract, then use figures and section titles in the original paper to locate method and experiment details."
            if is_en
            else "当前建议先读摘要，再回到原文按图表和章节标题定位方法与实验细节。"
        )

    combined_text = "\n".join(
        item for item in [paper.get("title"), abstract, introduction, method, results, conclusion, discussion] if item
    )

    analysis_note = (
        ("This report used the PDF full-text structure for automatic extraction." if is_en else "本报告已结合 PDF 全文结构做自动提炼。")
        if parsed_source_kind == "pdf"
        else (
            ("This report used source-page text structure for automatic extraction." if is_en else "本报告已结合源站正文结构做自动提炼。")
            if parsed_source_kind == "source_page"
            else (
                "This report was generated from the abstract and metadata; verify method and experiment details in the original paper."
                if is_en
                else "本报告当前基于摘要和元数据自动生成，方法与实验细节建议回到原文核对。"
            )
        )
    )
    if retrieved_evidence:
        analysis_note = _append_analysis_note(
            analysis_note,
            (
                "Full-text chunk retrieval evidence was used during generation."
                if is_en
                else "已结合全文切块语义检索证据生成。"
            ),
        )
        if _clean_text(_summarize_profile_for_embedding(user_profile)):
            analysis_note = _append_analysis_note(
                analysis_note,
                (
                    "The user-interest embedding retrieval path was used as one of the main evidence-ranking signals."
                    if is_en
                    else "当前精读正文已将用户兴趣 embedding 检索链路作为主要证据排序信号之一。"
                ),
            )
    if pdf_error:
        fallback_mode = "source_page" if parsed_source_kind == "source_page" else "abstract"
        analysis_note = _append_analysis_note(
            analysis_note,
            _describe_pdf_fallback(pdf_error, fallback_mode=fallback_mode, response_language=language),
        )

    relevance_points = _build_relevance_points(
        paper,
        user_profile,
        combined_text,
        parsed_pdf,
        response_language=language,
    )
    if evidence_sections:
        relevance_points = _unique_preserve_order(
            [
                (
                    f"Semantic retrieval suggests the most relevant evidence is concentrated in: {' / '.join(evidence_sections)}."
                    if is_en
                    else f"从全文语义检索命中的片段看，相关信息主要落在 {' / '.join(evidence_sections)} 部分。"
                )
            ]
            + list(relevance_points)
        )[:4]
    field_evidence_map = _build_field_evidence_map(retrieved_evidence)
    report_evidence_anchors = _build_report_evidence_anchors(retrieved_evidence)
    keywords = _extract_heuristic_keywords(paper, abstract, parsed_pdf)

    return {
        "abstract": abstract,
        "one_sentence_summary": one_sentence_summary,
        "research_background": research_background,
        "core_method": core_method,
        "key_results": key_results,
        "main_contributions": main_contributions,
        "limitations": limitations[:3],
        "relevance_points": relevance_points,
        "reading_focus": _unique_preserve_order(reading_focus)[:4],
        "keywords": keywords,
        "estimated_reading_minutes": _estimate_reading_minutes(parsed_pdf, abstract),
        "analysis_source": "pdf" if parsed_source_kind == "pdf" else ("source_page" if parsed_source_kind == "source_page" else "abstract"),
        "analysis_note": analysis_note,
        "generation_provider": "heuristic",
        "generation_model": "PaperFlow template",
        "recommendation_label": calibrate_recommendation_label(
            paper,
            _recommendation_label(paper),
            "pdf" if parsed_source_kind == "pdf" else ("source_page" if parsed_source_kind == "source_page" else "abstract"),
        ),
        "retrieved_evidence": retrieved_evidence,
        "field_evidence_map": field_evidence_map,
        "report_evidence_anchors": report_evidence_anchors,
        "response_language": language,
    }


def _normalize_string_list(value: Any, limit: int = 4, max_chars: int = 180) -> List[str]:
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
            items.append(_truncate_text(cleaned, max_chars))
    return _unique_preserve_order(items)[:limit]


def _looks_like_extraction_noise(text: str) -> bool:
    cleaned = _clean_text(text)
    if not cleaned:
        return False
    lowered = cleaned.lower()
    noise_markers = (
        "arxiv:",
        "[cs.",
        "correspondence to:",
        "copyright",
        "accepted by",
        "proceedings of",
        "doi:",
    )
    marker_hits = sum(1 for marker in noise_markers if marker in lowered)
    short_line_count = sum(1 for line in cleaned.splitlines() if 0 < len(line.strip()) <= 18)
    digit_ratio = sum(ch.isdigit() for ch in cleaned) / max(1, len(cleaned))
    return marker_hits >= 2 or short_line_count >= 6 or digit_ratio > 0.12


def _append_template_qa_block(
    lines: List[str],
    qid: str,
    question: str,
    content: Any,
    response_language: str = "zh",
) -> None:
    fallback = (
        "Current information is insufficient; check the corresponding section in the original paper."
        if _normalize_response_language(response_language) == "en"
        else "当前信息不足，建议回到原文对应章节核对。"
    )
    lines.append(f"{qid}: {question}")
    lines.append("")
    if isinstance(content, list):
        values = [_clean_text(item) for item in content if _clean_text(item)]
        if values:
            for item in values:
                lines.append(f"- {item}")
        else:
            lines.append(fallback)
    else:
        text = _clean_text(content)
        if text:
            for paragraph in re.split(r"\n{2,}", text):
                paragraph = paragraph.strip()
                if paragraph:
                    lines.append(paragraph)
                    lines.append("")
            if lines and lines[-1] == "":
                lines.pop()
        else:
            lines.append(fallback)
    lines.append("")


def _synthesize_report_with_llm(
    paper: Dict[str, Any],
    user_profile: Dict[str, Any],
    parsed_pdf: Optional[Dict[str, Any]],
    heuristic_payload: Dict[str, Any],
    response_language: str = "zh",
) -> Optional[Dict[str, Any]]:
    language = _normalize_response_language(response_language)
    fallback_note = (
        "The generative reading supplement did not return this time; the report is still generated from the reading template, metadata, abstract, and available PDF snippets."
        if language == "en"
        else "生成式精读补充本次未返回，当前内容仍按精读模板基于已拿到的摘要、元数据和可用 PDF 片段生成。"
    )

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
            response_language=language,
        )
        if isinstance(result, dict) and result:
            return result
        return {"analysis_note": fallback_note}
    except Exception as exc:
        print(f"LLM reading synthesis failed: {exc}")
        return {"analysis_note": fallback_note}


def _enrich_paper_for_reading_report_compat(
    paper: Dict[str, Any],
    *,
    user_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[str]]:
    """Call the enrichment hook while tolerating older one-argument test doubles."""
    try:
        signature = inspect.signature(enrich_paper_for_reading_report)
        if "user_id" in signature.parameters:
            return enrich_paper_for_reading_report(paper, user_id=user_id)
    except (TypeError, ValueError):
        pass
    return enrich_paper_for_reading_report(paper)


def _merge_report_payload(base: Dict[str, Any], llm_payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(llm_payload, dict):
        return base

    merged = dict(base)
    for key in (
        "one_sentence_summary",
        "clean_abstract_summary",
        "problem_analysis",
        "related_work",
        "solution_approach",
        "experiments",
        "future_directions",
        "paper_summary",
        "research_background",
        "core_method",
        "key_results",
        "institution",
        "affiliation",
    ):
        value = _clean_text(llm_payload.get(key))
        if value:
            merged["institution" if key == "affiliation" else key] = value

    analysis_note = _clean_text(llm_payload.get("analysis_note"))
    if analysis_note:
        merged["analysis_note"] = _append_analysis_note(merged.get("analysis_note"), analysis_note)

    for key in ("main_contributions", "limitations", "relevance_points", "reading_focus"):
        values = _normalize_string_list(llm_payload.get(key), max_chars=320)
        if values:
            merged[key] = values

    keyword_values = _normalize_string_list(llm_payload.get("keywords"), limit=8)
    if keyword_values:
        merged["keywords"] = keyword_values

    recommendation_label = _clean_text(llm_payload.get("recommendation_label"))
    if recommendation_label:
        merged["recommendation_label"] = recommendation_label

    for key in ("generation_provider", "generation_model"):
        value = _clean_text(llm_payload.get(key))
        if value:
            merged[key] = value

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


def _normalize_report_style(value: Any) -> str:
    style = _clean_text(value).lower()
    return style if style in {"standard", "deep", "brief"} else "standard"


def _report_style_label(style: str) -> str:
    return {
        "standard": "standard",
        "deep": "deep technical analysis",
        "brief": "brief scan",
    }.get(style, "standard")


def generate_reading_report(
    paper: Dict[str, Any],
    user_profile: Dict[str, Any],
    report_payload: Optional[Dict[str, Any]] = None,
    response_language: str = "zh",
) -> str:
    payload = report_payload or build_heuristic_report_payload(
        paper,
        user_profile,
        response_language=response_language,
    )
    language = _normalize_response_language(payload.get("response_language") or response_language)
    is_en = language == "en"
    labels = {
        "untitled": "Untitled Paper" if is_en else "Untitled Paper",
        "source_no_abstract_link": "The source did not return a usable abstract. View the original paper here:" if is_en else "源站暂未返回可用摘要。请直接查看原文链接：",
        "source_no_abstract": "The source did not return a usable abstract. Check the original PDF or paper page directly." if is_en else "源站暂未返回可用摘要，建议直接查看原文 PDF 或论文主页。",
        "analysis_pdf": "PDF full text" if is_en else "PDF 全文",
        "analysis_source_page": "source page + metadata" if is_en else "源站正文 + 元数据",
        "analysis_metadata": "abstract + metadata" if is_en else "摘要 + 元数据",
        "about_minutes": "about" if is_en else "约",
        "minutes": "min" if is_en else "分钟",
        "model": "model" if is_en else "模型",
        "keywords": "Keywords" if is_en else "关键词",
        "one_sentence": "One-Sentence Summary" if is_en else "一句话总结",
        "one_sentence_empty": "There is not enough information to generate a one-sentence summary yet." if is_en else "当前没有足够信息生成一句话总结。",
        "abstract": "Abstract" if is_en else "摘要",
        "problem_empty": "Start from the abstract and introduction to verify the research problem." if is_en else "建议先回到原文摘要和引言确认研究问题。",
        "related_empty": "The automatic parser did not extract a stable Related Work thread. Check the introduction, related-work section, and citations to identify the main compared methods." if is_en else "当前自动解析没有稳定提取出 Related Work 的完整脉络。可先从论文引言、相关工作章节和引用线索核对它主要对比了哪些方法。",
        "related_prefix": "Based on current evidence, the paper is positioned around: " if is_en else "从当前证据可见，论文的定位至少包括：",
        "solution_empty": "Method details were not extracted reliably; focus on the Method / Approach section." if is_en else "当前未成功提炼方法细节，请重点阅读 Method / Approach 部分。",
        "experiments_empty": "No clear experimental setup was extracted; check Experiments / Results, tables, figures, and key metrics." if is_en else "当前没有提炼出明确实验设置，请重点核对 Experiments / Results、表格、图示和主要指标。",
        "future_empty": "Current information is insufficient; revisit limitations, failure cases, ablation gaps, and cross-domain generalization in the paper." if is_en else "当前信息不足，建议从局限性、失败案例、消融缺口和跨领域泛化四个角度回原文继续挖掘。",
        "contributions_prefix": "Main contributions include: " if is_en else "主要贡献包括：",
        "limitations_prefix": "Important boundaries include: " if is_en else "需要注意的边界包括：",
        "relevance_prefix": "Relationship to the user profile: " if is_en else "与用户画像的关系：",
        "summary_empty": "Current information is insufficient; connect the abstract, introduction, method, and conclusion in the original paper." if is_en else "当前信息不足，建议回到原文摘要、引言、方法和结论串联主线。",
        "recommendation": "Recommendation" if is_en else "推荐指数",
        "reason": "Reason" if is_en else "推荐理由",
        "details": "Paper Details" if is_en else "基本信息",
        "authors": "Authors" if is_en else "作者",
        "affiliation": "Affiliation" if is_en else "机构",
        "source": "Source" if is_en else "来源",
        "subjects": "Subjects/Categories" if is_en else "主题/分类",
        "date": "Date" if is_en else "日期",
        "recommendation_level": "Recommendation" if is_en else "推荐级别",
        "estimated_reading_time": "Estimated reading time" if is_en else "预计阅读时间",
        "analysis_source": "Analysis source" if is_en else "解析来源",
        "generation_model": "Generation model" if is_en else "生成模型",
        "not_provided": "Not provided" if is_en else "未提供",
        "unknown": "Unknown" if is_en else "未知",
        "analysis_note": "Analysis note" if is_en else "解析说明",
    }
    field_sep = ": " if is_en else "："
    list_joiner = "; " if is_en else "；"
    sentence_end = "." if is_en else "。"
    report_style = _normalize_report_style(payload.get("report_style"))
    title = _clean_text(paper.get("title")) or labels["untitled"]
    abstract = _clean_abstract_text(payload.get("abstract") or paper.get("abstract"))
    clean_abstract_summary = _clean_text(payload.get("clean_abstract_summary"))
    if clean_abstract_summary and (not _clean_text(abstract) or _looks_like_extraction_noise(abstract)):
        abstract = clean_abstract_summary
    if not _clean_text(abstract):
        fallback_source = _get_direct_pdf_url(paper) or _get_first_url(
            paper,
            "paper_url",
            "openreview_url",
            "cvf_url",
            "ecva_url",
            "dblp_url",
            "doi_url",
            "url",
        )
        if fallback_source:
            abstract = f"{labels['source_no_abstract_link']} {fallback_source}" if is_en else f"{labels['source_no_abstract_link']}{fallback_source}"
        else:
            abstract = labels["source_no_abstract"]
    arxiv_id = _clean_text(paper.get("arxiv_id"))
    doi = _clean_text(paper.get("doi"))
    recommendation_label = payload.get("recommendation_label") or _recommendation_label(paper)
    recommendation_label = calibrate_recommendation_label(
        paper,
        recommendation_label,
        payload.get("analysis_source"),
    )
    recommendation_score = _recommendation_score(recommendation_label)
    recommendation_display_label = _recommendation_display_label(recommendation_label, response_language=language)
    recommendation_stars = "★" * recommendation_score + "☆" * (5 - recommendation_score)
    analysis_source = _clean_text(payload.get("analysis_source"))
    analysis_source_label = (
        labels["analysis_pdf"]
        if analysis_source == "pdf"
        else (labels["analysis_source_page"] if analysis_source == "source_page" else labels["analysis_metadata"])
    )
    analysis_note = _clean_text(payload.get("analysis_note"))
    subjects = _format_subjects(paper)
    if subjects == "未知" and is_en:
        subjects = labels["unknown"]
    generation_provider = _clean_text(payload.get("generation_provider")) or "heuristic"
    generation_model = _clean_text(payload.get("generation_model")) or "PaperFlow template"
    recommendation_reason = _build_recommendation_reason(payload, response_language=language)

    lines = []
    lines.append(f"# {title}")
    lines.append("")

    lines.append(
        f"> {recommendation_stars} {recommendation_display_label} · "
        f"{labels['about_minutes']} {int(payload.get('estimated_reading_minutes') or 8)} {labels['minutes']} · "
        f"{labels['model']} {generation_provider}/{generation_model}"
    )
    lines.append("")

    if report_style == "brief":
        lines.append("## Brief Scan")
        lines.append("")
        lines.append(payload.get("one_sentence_summary") or "No one-sentence summary is available yet.")
        lines.append("")
    elif report_style == "deep":
        lines.append("## Deep-Dive Checklist")
        lines.append("")
        lines.append("- Verify the core assumption against the method section.")
        lines.append("- Check whether the evidence supports the claimed improvement.")
        lines.append("- Compare the limitation section with your current research direction.")
        lines.append("")

    keywords = payload.get("keywords") or []
    if isinstance(keywords, (list, tuple)):
        clean_keywords = [str(k).strip() for k in keywords if str(k).strip()]
    else:
        clean_keywords = []
    if clean_keywords:
        lines.append(f"🏷 {labels['keywords']}{field_sep}{' · '.join(clean_keywords[:8])}")
        lines.append("")

    lines.append(f"## {labels['one_sentence']}")
    lines.append("")
    lines.append(payload.get("one_sentence_summary") or labels["one_sentence_empty"])
    lines.append("")

    lines.append(f"## {labels['abstract']}")
    lines.append("")
    for paragraph in _clean_text(abstract).split("\n"):
        if paragraph.strip():
            lines.append(f"> {paragraph.strip()}")
    lines.append("")

    problem_analysis = payload.get("problem_analysis") or payload.get("research_background") or labels["problem_empty"]
    related_work = payload.get("related_work")
    if not related_work:
        related_work_items = payload.get("main_contributions") or []
        related_work = labels["related_empty"]
        if related_work_items:
            related_work += "\n\n" + labels["related_prefix"] + list_joiner.join(str(item) for item in related_work_items[:3]) + sentence_end
    solution_approach = payload.get("solution_approach") or payload.get("core_method") or labels["solution_empty"]
    experiments = payload.get("experiments")
    if not experiments:
        result_text = _clean_text(payload.get("key_results"))
        experiments = result_text or labels["experiments_empty"]
    future_directions = payload.get("future_directions")
    if not future_directions:
        future_items = []
        future_items.extend(payload.get("limitations") or [])
        future_items.extend(payload.get("reading_focus") or [])
        future_directions = future_items or [labels["future_empty"]]
    paper_summary = payload.get("paper_summary")
    if not paper_summary:
        summary_parts = [
            _clean_text(payload.get("one_sentence_summary")),
            _clean_text(payload.get("research_background")),
            _clean_text(payload.get("core_method")),
            _clean_text(payload.get("key_results")),
        ]
        contributions = payload.get("main_contributions") or []
        limitations = payload.get("limitations") or []
        relevance = payload.get("relevance_points") or []
        if contributions:
            summary_parts.append(labels["contributions_prefix"] + list_joiner.join(str(item) for item in contributions[:4]) + sentence_end)
        if limitations:
            summary_parts.append(labels["limitations_prefix"] + list_joiner.join(str(item) for item in limitations[:3]) + sentence_end)
        if relevance:
            summary_parts.append(labels["relevance_prefix"] + list_joiner.join(str(item) for item in relevance[:3]) + sentence_end)
        paper_summary = "\n\n".join(part for part in summary_parts if part) or labels["summary_empty"]

    qa_questions = (
        [
            ("Q1", "What problem does this paper try to solve?"),
            ("Q2", "What related work does it build on or compare against?"),
            ("Q3", "How does the paper solve the problem?"),
            ("Q4", "What experiments does the paper run?"),
            ("Q5", "What directions are worth exploring next?"),
            ("Q6", "Summarize the main content of the paper."),
        ]
        if is_en
        else [
            ("Q1", "这篇论文试图解决什么问题？"),
            ("Q2", "有哪些相关研究？"),
            ("Q3", "论文如何解决这个问题？"),
            ("Q4", "论文做了哪些实验？"),
            ("Q5", "有什么可以进一步探索的点？"),
            ("Q6", "总结一下论文的主要内容"),
        ]
    )
    for (qid, question_text), content in zip(
        qa_questions,
        [problem_analysis, related_work, solution_approach, experiments, future_directions, paper_summary],
    ):
        _append_template_qa_block(lines, qid, question_text, content, response_language=language)

    lines.append(f"## {labels['recommendation']}")
    lines.append("")
    lines.append(
        f"{recommendation_stars} ({recommendation_score}/5)"
        if is_en
        else f"{recommendation_stars}（{recommendation_score}/5）"
    )
    lines.append(f"- {labels['reason']}{field_sep}{recommendation_reason}")
    lines.append("")

    lines.append(f"## {labels['details']}")
    lines.append("")
    authors_text = _format_authors(paper.get("authors"))
    if authors_text == "未知" and is_en:
        authors_text = labels["unknown"]
    lines.append(f"- {labels['authors']}{field_sep}{authors_text}")
    institution = _clean_text(payload.get("institution") or paper.get("institution") or paper.get("affiliation"))
    lines.append(f"- {labels['affiliation']}{field_sep}{institution or labels['not_provided']}")
    lines.append(f"- {labels['source']}{field_sep}{_clean_text(paper.get('venue') or paper.get('journal') or paper.get('source')) or labels['unknown']}")
    lines.append(f"- {labels['subjects']}{field_sep}{subjects}")
    lines.append(f"- {labels['date']}{field_sep}{_clean_text(paper.get('publish_date')) or labels['unknown']}")
    lines.append(f"- {labels['recommendation_level']}{field_sep}**{recommendation_display_label}**")
    lines.append(f"- {labels['estimated_reading_time']}{field_sep}{labels['about_minutes']} {int(payload.get('estimated_reading_minutes') or 8)} {labels['minutes']}")
    lines.append(f"- {labels['analysis_source']}{field_sep}{analysis_source_label}")
    lines.append(f"- {labels['generation_model']}{field_sep}{generation_provider} / {generation_model}")
    if arxiv_id:
        lines.append(f"- arXiv ID{field_sep}`{arxiv_id}`")
    if doi:
        lines.append(f"- DOI{field_sep}`{doi}`")
    if analysis_note:
        lines.append(f"- {labels['analysis_note']}{field_sep}{analysis_note}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def resolve_selected_papers(paper_refs: List[int], papers: List[Dict]) -> List[Dict]:
    """Resolve paper references from either 1-based positions or actual paper IDs.

    If paper_refs is empty but papers is not, return all papers directly.
    """
    # If no refs provided but papers exist, return all papers (for direct PDF input)
    if not paper_refs and papers:
        return papers

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
    request_metadata: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    print(f"Creating reading reports for user: {user_id}")
    print(f"Selected papers: {paper_ids}")

    target_id = chat_id or feishu_user_id
    use_chat_id = chat_id is not None
    request_metadata = dict(request_metadata or {})
    report_style = _normalize_report_style(request_metadata.get("report_style"))
    response_language = _normalize_response_language(request_metadata.get("response_language"))
    request_metadata["response_language"] = response_language

    profile = get_profile(user_id)
    if not profile:
        print(f"Warning: No profile found for user {user_id}, using default")
        profile = {"core_directions": {}, "methodology_preferences": {}}
    profile = ensure_profile_schema(profile)

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

    # 1. If this request comes from a specific uploaded PDF, reuse the existing
    # report when the same source key has already been processed successfully.
    existing_pdf_doc = None
    if request_metadata.get("report_source_type") and request_metadata.get("report_source_key"):
        existing_pdf_doc = _lookup_existing_pdf_report(user_id, request_metadata, selected_papers[0])
        if existing_pdf_doc:
            print(
                "Reusing existing PDF reading report for "
                f"{request_metadata.get('report_source_type')}={request_metadata.get('report_source_key')}"
            )
            if send_to_feishu and target_id:
                summary_text = format_created_docs_summary([existing_pdf_doc])
                try:
                    send_text(target_id, summary_text, use_chat_id=use_chat_id)
                    print(f"\nNotification sent to Feishu target: {target_id}")
                except Exception as exc:
                    print(f"\nFailed to send reused PDF doc summary to Feishu: {exc}")
            return [existing_pdf_doc]

    # 2. For pushed/selected papers, reuse already-created docs by paper_id and
    # only generate reports for the missing subset.
    existing_reports_by_paper_id: Dict[int, Dict[str, Any]] = {}
    selected_paper_ids = []
    for paper in selected_papers:
        paper_id = paper.get("id")
        if paper_id is None:
            continue
        try:
            selected_paper_ids.append(int(paper_id))
        except (TypeError, ValueError):
            continue

    if selected_paper_ids:
        existing_reports_by_paper_id = get_existing_reading_reports_for_papers(user_id, selected_paper_ids)

    prepared_docs: List[Optional[Dict[str, Any]]] = [None] * len(selected_papers)
    pending_entries: List[Tuple[int, Dict[str, Any]]] = []
    reused_count = 0
    for index, raw_paper in enumerate(selected_papers):
        paper_id = raw_paper.get("id")
        try:
            normalized_paper_id = int(paper_id) if paper_id is not None else None
        except (TypeError, ValueError):
            normalized_paper_id = None

        report_record = (
            existing_reports_by_paper_id.get(normalized_paper_id)
            if normalized_paper_id is not None
            else None
        )
        normalized_raw_paper = _normalize_paper(raw_paper)
        should_reuse_report = bool(report_record)
        if should_reuse_report and not _is_report_record_current(report_record):
            should_reuse_report = False
            print(
                "Existing reading report found but it was generated by an older template version; "
                "regenerating."
            )
        if should_reuse_report and not _report_record_matches_language(report_record, response_language):
            should_reuse_report = False
            print("Existing reading report found but language does not match; regenerating.")
        if should_reuse_report and not _paper_has_sufficient_metadata_for_report(normalized_raw_paper):
            should_reuse_report = False
            print(
                "Existing reading report found but paper metadata is incomplete; "
                "regenerating to backfill missing abstract/authors."
            )

        if should_reuse_report:
            prepared_docs[index] = _build_reused_doc_entry(raw_paper, report_record)
            reused_count += 1
        else:
            pending_entries.append((index, raw_paper))

    if reused_count:
        print(f"Reusing {reused_count} existing reading report(s); generating only missing ones.")

    def build_pending_report(display_index: int, target_index: int, raw_paper: Dict[str, Any]) -> Dict[str, Any]:
        try:
            print(
                f"\n[{display_index}/{len(pending_entries)}] Processing: "
                f"{str(raw_paper.get('title', 'Unknown'))[:60]}"
            )
            enriched_paper, parsed_pdf, pdf_error = _enrich_paper_for_reading_report_compat(
                raw_paper,
                user_id=user_id,
            )
            heuristic_payload = build_heuristic_report_payload(
                enriched_paper,
                profile,
                parsed_pdf=parsed_pdf,
                pdf_error=pdf_error,
                response_language=response_language,
            )
            llm_payload = _synthesize_report_with_llm(
                enriched_paper,
                profile,
                parsed_pdf=parsed_pdf,
                heuristic_payload=heuristic_payload,
                response_language=response_language,
            )
            report_payload = _merge_report_payload(heuristic_payload, llm_payload)
            proposed_label = report_payload.get("recommendation_label")
            report_payload["recommendation_label"] = calibrate_recommendation_label(
                enriched_paper,
                proposed_label,
                report_payload.get("analysis_source"),
            )
            report_payload["recommendation_calibration"] = build_recommendation_calibration_metadata(
                enriched_paper,
                proposed_label,
                report_payload.get("recommendation_label"),
                report_payload.get("analysis_source"),
            )
            report_payload["report_style"] = report_style
            report_payload["response_language"] = response_language
            report_content = generate_reading_report(
                enriched_paper,
                profile,
                report_payload=report_payload,
                response_language=response_language,
            )

            doc_prefix = "[Reading]" if response_language == "en" else "[精读]"
            doc_title = f"{doc_prefix} {enriched_paper.get('title', 'Unknown')[:80]}"
            return {
                "target_index": target_index,
                "enriched_paper": enriched_paper,
                "parsed_pdf": parsed_pdf,
                "report_payload": report_payload,
                "report_content": report_content,
                "doc_title": doc_title,
            }
        except Exception as exc:
            print(f"  Error creating reading report: {exc}")
            return {"target_index": target_index, "error": str(exc)}

    pending_results: List[Dict[str, Any]] = []
    concurrency = _reading_report_concurrency_limit(len(pending_entries))
    if len(pending_entries) > 1 and concurrency > 1:
        print(f"Generating {len(pending_entries)} missing reading report(s) with concurrency={concurrency}.")
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(build_pending_report, display_index, target_index, raw_paper)
                for display_index, (target_index, raw_paper) in enumerate(pending_entries, start=1)
            ]
            for future in as_completed(futures):
                try:
                    pending_results.append(future.result())
                except Exception as exc:
                    print(f"  Error creating reading report: {exc}")
    else:
        pending_results = [
            build_pending_report(display_index, target_index, raw_paper)
            for display_index, (target_index, raw_paper) in enumerate(pending_entries, start=1)
        ]

    for result in sorted(pending_results, key=lambda item: int(item.get("target_index", 0))):
        if result.get("error"):
            continue
        target_index = int(result["target_index"])
        enriched_paper = result["enriched_paper"]
        parsed_pdf = result["parsed_pdf"]
        report_payload = result["report_payload"]
        report_content = result["report_content"]
        doc_title = result["doc_title"]

        try:
            doc_info: Dict[str, Any] = {"title": doc_title, "local_only": True}
            doc_url = None
            doc_token = None
            feishu_error = None
            if send_to_feishu:
                try:
                    doc_info = create_doc(title=doc_title, content=report_content, folder_id=folder_id)
                    doc_url = extract_doc_url(doc_info)
                    doc_token = extract_doc_token(doc_info)
                    if not doc_url and doc_token:
                        doc_url = _resolve_doc_url_from_meta(doc_token)
                except Exception as doc_exc:
                    feishu_error = str(doc_exc)
                    print(
                        "  Feishu document creation failed; "
                        f"local markdown will still be saved: {doc_exc}"
                    )

            report_path = _save_reading_report_markdown(
                user_id=user_id,
                paper=enriched_paper,
                report_content=report_content,
                report_payload=report_payload,
                doc_url=doc_url,
                doc_token=doc_token,
            )
            wiki_ingest_info = ingest_reading_report_to_wiki(
                user_id=user_id,
                paper=enriched_paper,
                report_content=report_content,
                report_payload=report_payload,
                report_path=report_path,
                doc_url=doc_url,
                doc_token=doc_token,
            )

            created_doc = {
                "paper": enriched_paper,
                "doc_info": doc_info,
                "title": doc_title,
                "url": doc_url,
                "doc_token": doc_token,
                "report_path": report_path,
                "pdf_path": enriched_paper.get("pdf_path"),
                "report_payload": report_payload,
                "wiki_ingest": wiki_ingest_info,
            }
            if feishu_error:
                created_doc["feishu_error"] = feishu_error
            prepared_docs[target_index] = created_doc

            behavior_metadata = {
                "arxiv_id": enriched_paper.get("arxiv_id"),
                "doc_title": doc_title,
                "paper_title": enriched_paper.get("title"),
                "doc_token": doc_token,
                "doc_url": doc_url,
                "report_path": report_path,
                "pdf_path": enriched_paper.get("pdf_path"),
                "analysis_source": report_payload.get("analysis_source"),
                "report_version": READING_REPORT_OUTPUT_VERSION,
                "report_style": report_style,
                "response_language": response_language,
            }
            if feishu_error:
                behavior_metadata["feishu_error"] = feishu_error
            if wiki_ingest_info:
                behavior_metadata["wiki_paper_node"] = wiki_ingest_info.get("paper_node")
                behavior_metadata["wiki_section_count"] = wiki_ingest_info.get("section_count")
            for key in (
                "report_source_type",
                "report_source_key",
                "report_source_name",
                "report_source_message_id",
                "selection_push_id",
            ):
                value = request_metadata.get(key)
                if value not in (None, "", [], {}):
                    behavior_metadata[key] = value

            signal_time = datetime.now()
            reading_signal_metadata = None
            try:
                profile, reading_signal_metadata = _apply_direct_upload_reading_signal(
                    user_id=user_id,
                    profile=profile,
                    paper=enriched_paper,
                    parsed_pdf=parsed_pdf,
                    request_metadata=request_metadata,
                    signal_time=signal_time,
                )
            except Exception as signal_exc:
                print(f"  Reading-signal update skipped due to error: {signal_exc}")
            if reading_signal_metadata:
                behavior_metadata["reading_signal_topics"] = reading_signal_metadata.get("signal_topics", [])
                behavior_metadata["reading_signal_activated_topics"] = reading_signal_metadata.get("activated_topics", [])

            log_behavior(
                user_id=user_id,
                push_id="reading_report",
                paper_id=enriched_paper.get("id"),
                action="created_report",
                action_type="reading",
                category="reading_agent",
                metadata=behavior_metadata,
            )
            if reading_signal_metadata:
                log_behavior(
                    user_id=user_id,
                    push_id="reading_signal",
                    paper_id=enriched_paper.get("id"),
                    action="profile_updated",
                    action_type="reading_signal",
                    category=reading_signal_metadata.get("signal_strength", "weak"),
                    metadata={
                        **reading_signal_metadata,
                        "trigger": "direct_upload_pdf",
                        "signal_timestamp": signal_time.isoformat(),
                    },
                )
            print(f"  Created reading doc: {doc_url or doc_token or '[no link yet]'}")
        except Exception as exc:
            print(f"  Error creating reading report: {exc}")

    created_docs = [doc for doc in prepared_docs if doc]
    _annotate_tracking_links(created_docs, user_id)

    if created_docs:
        print()
        print(format_created_docs_summary(created_docs))

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
    parser.add_argument("--push-id", type=str, help="指定要读取的 push_id；默认使用该用户最新一次推送")

    args = parser.parse_args()

    push_info = get_push_papers(args.push_id) if args.push_id else get_latest_push(args.user_id)
    if not push_info or not push_info.get("papers"):
        source = f"push_id={args.push_id}" if args.push_id else f"user={args.user_id}"
        print(f"No pushed papers found for {source}. Run `paperflow daily` first.")
        raise SystemExit(1)

    print(f"Using push: {push_info.get('push_id', args.push_id or 'latest')}")

    create_reading_report(
        user_id=args.user_id,
        paper_ids=args.paper_ids,
        papers=push_info["papers"],
        folder_id=args.folder_id,
        send_to_feishu=not args.no_feishu,
        feishu_user_id=args.feishu_user_id
    )
