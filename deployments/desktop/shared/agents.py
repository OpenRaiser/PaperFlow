"""GUI-facing wrappers around PaperFlow agents and storage.

The local GUI should only pass simple JSON-like values through this module.
Kebab-case agent directories are imported with importlib here, so the HTTP
server and future GUI stacks do not need to know about those details.
"""

from __future__ import annotations

import importlib
import hashlib
import json
import os
import re
import subprocess
import threading
import time
import zipfile
import yaml
from paperflow.providers import build_llm_provider
from paperflow import roles as role_utils
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple
from uuid import uuid4

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]

db_ops = importlib.import_module("skills.storage-helper.scripts.db_ops")
daily_agent = importlib.import_module("deployments.feishu.daily-push-agent.main")
feedback_agent = importlib.import_module("agents.feedback-agent.main")
reading_agent = importlib.import_module("agents.reading-agent.main")
coldstart_agent = importlib.import_module("agents.coldstart-agent.main")
role_manager = importlib.import_module("agents.role-manager.main")
must_read_agent = importlib.import_module("agents.must-read-manager.main")
arxiv_fetcher = importlib.import_module("skills.arxiv-fetcher.scripts.fetch_arxiv")
wiki_db = importlib.import_module("skills.wiki-store.scripts.wiki_db")
wiki_answer = importlib.import_module("agents.wiki-agent.retrieve.answer")


_FEISHU_DOC_PATCH_LOCK = threading.Lock()
_DAILY_TASK_LOCK = threading.Lock()
_DAILY_TASKS: Dict[str, Dict[str, Any]] = {}
_DAILY_TASK_BY_USER: Dict[str, str] = {}

ENV_PATH = PROJECT_ROOT / ".env"


def _normalize_response_language(value: Any = None) -> str:
    raw = str(value or "").strip().lower().replace("_", "-")
    return "en" if raw.startswith("en") or raw in {"english"} else "zh"


EDITABLE_ENV_KEYS = [
    "PAPERFLOW_LLM_PROVIDER",
    "PAPERFLOW_LLM_MODEL",
    "PAPERFLOW_EMBED_PROVIDER",
    "PAPERFLOW_EMBED_MODEL",
    "PAPERFLOW_EMBED_DIMENSIONS",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_API_TIMEOUT",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_API_TIMEOUT",
    "OLLAMA_BASE_URL",
    "OLLAMA_API_TIMEOUT",
    "PAPERFLOW_NOTES_ROOT_DIR",
    "PAPERFLOW_PDF_DIR",
    "PAPERFLOW_READING_REPORTS_DIR",
    "PAPERFLOW_MONTHLY_REPORT_DIR",
    "PAPERFLOW_TOPIC_INDEX_DIR",
    "PAPERFLOW_WIKI_DIR",
    "PAPERFLOW_WIKI_INGEST",
    "PAPERFLOW_READING_NOTES_GIT_DIR",
    "PAPERFLOW_READING_NOTES_GIT_REMOTE",
    "PAPERFLOW_READING_NOTES_GIT_BRANCH",
    "PAPERFLOW_READING_NOTES_GIT_LLM_REVIEW",
    "PAPERFLOW_WRITE_FEISHU",
    "PAPERFLOW_DEFAULT_ARXIV_CATEGORIES",
    "PAPERFLOW_DEFAULT_CONFERENCES",
    "PAPERFLOW_DEFAULT_JOURNALS",
    "PAPERFLOW_CUSTOM_RSS_URLS",
    "PAPERFLOW_ENABLE_ARXIV",
    "PAPERFLOW_ENABLE_SEMANTIC_SCHOLAR",
    "PAPERFLOW_ENABLE_OPENREVIEW",
    "PAPERFLOW_ENABLE_CUSTOM_RSS",
    "PAPERFLOW_CONFERENCE_ACCESS_MODE",
    "PAPERFLOW_CONFERENCE_COOKIE_FILE",
    "SEMANTIC_SCHOLAR_API_KEY",
    "OPENREVIEW_USERNAME",
    "OPENREVIEW_TOKEN",
    "OPENREVIEW_COOKIE_FILE",
    "PAPERFLOW_REPORT_STYLE",
    "PAPERFLOW_DAILY_LIMIT",
    "PAPERFLOW_RELEVANCE_THRESHOLD",
    "PAPERFLOW_MAX_CONCURRENCY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_BOT_NAME",
    "FEISHU_USER_ID",
    "FEISHU_CLI_CMD",
    "FEISHU_IM_IDENTITY",
    "FEISHU_VERIFICATION_TOKEN",
]


def _load_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = default
    return max(1, parsed)


def _unique_ints(values: Iterable[Any], *, minimum: int = 1, maximum: Optional[int] = None) -> List[int]:
    seen: Set[int] = set()
    result: List[int] = []
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number < minimum:
            continue
        if maximum is not None and number > maximum:
            continue
        if number in seen:
            continue
        seen.add(number)
        result.append(number)
    return result


def _string_list(values: Any) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    result: List[str] = []
    seen: Set[str] = set()
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _paper_metadata(paper: Dict[str, Any]) -> Dict[str, Any]:
    metadata = paper.get("metadata") or {}
    if isinstance(metadata, str):
        metadata = _load_json(metadata, {})
    return dict(metadata) if isinstance(metadata, dict) else {}


def _first_text(paper: Dict[str, Any], metadata: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(paper.get(key) or metadata.get(key) or "").strip()
        if value:
            return value
    return ""


def _doi_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lower = text.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/"):
        if lower.startswith(prefix):
            return text[len(prefix) :].strip("/")
    if lower.startswith("doi:"):
        return text[4:].strip()
    return text


def _doi_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith(("http://", "https://")):
        return text
    if text.lower().startswith("doi.org/"):
        return f"https://{text}"
    doi = _doi_value(text)
    return f"https://doi.org/{doi}" if doi else ""


def _paper_doi(paper: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str:
    metadata = metadata if metadata is not None else _paper_metadata(paper)
    return _doi_value(_first_text(paper, metadata, "doi", "doi_url"))


def _extract_arxiv_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"(?:arxiv\.org/(?:abs|pdf)/)?(\d{4}\.\d{4,6}(?:v\d+)?)", text, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _paper_arxiv_id(paper: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str:
    metadata = metadata if metadata is not None else _paper_metadata(paper)
    explicit = _first_text(paper, metadata, "arxiv_id")
    if explicit:
        return _extract_arxiv_id(explicit) or explicit
    for key in ("paper_url", "url", "pdf_url", "source_url"):
        arxiv_id = _extract_arxiv_id(paper.get(key) or metadata.get(key))
        if arxiv_id:
            return arxiv_id
    return ""


def _paper_url(paper: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str:
    metadata = metadata if metadata is not None else _paper_metadata(paper)
    explicit_url = _first_text(paper, metadata, "paper_url", "url", "openreview_url")
    if explicit_url:
        return explicit_url
    arxiv_id = _paper_arxiv_id(paper, metadata)
    if arxiv_id:
        return f"https://arxiv.org/abs/{arxiv_id}"
    doi_url = _first_text(paper, metadata, "doi_url")
    if doi_url:
        return _doi_url(doi_url)
    return _doi_url(_paper_doi(paper, metadata))


def _paper_pdf_url(paper: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str:
    metadata = metadata if metadata is not None else _paper_metadata(paper)
    value = _first_text(paper, metadata, "pdf_url")
    if value:
        return value
    arxiv_id = _paper_arxiv_id(paper, metadata)
    return f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""


def _paper_card(paper: Dict[str, Any], number: int) -> Dict[str, Any]:
    metadata = _paper_metadata(paper)
    authors = paper.get("authors") or []
    if isinstance(authors, str):
        authors = _load_json(authors, [authors])
    categories = paper.get("categories") or metadata.get("categories") or []
    if isinstance(categories, str):
        categories = _load_json(categories, [categories])

    return {
        "number": number,
        "id": paper.get("id"),
        "arxiv_id": _paper_arxiv_id(paper, metadata),
        "doi": _paper_doi(paper, metadata),
        "title": str(paper.get("title") or "Untitled"),
        "authors": authors[:8] if isinstance(authors, list) else [],
        "abstract": str(paper.get("abstract") or ""),
        "category": paper.get("category") or metadata.get("category") or "unknown",
        "score": _to_float(paper.get("score") or metadata.get("score")),
        "rank": paper.get("rank") or metadata.get("rank") or number,
        "source": paper.get("source") or metadata.get("source") or "",
        "venue": paper.get("venue") or paper.get("journal") or metadata.get("venue") or "",
        "publish_date": paper.get("publish_date") or metadata.get("publish_date") or "",
        "categories": categories if isinstance(categories, list) else [],
        "url": _paper_url(paper, metadata),
        "pdf_url": _paper_pdf_url(paper, metadata),
        "metadata": metadata,
    }


def _push_payload(push: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not push:
        return None
    papers = list(push.get("papers") or [])
    return {
        "push_id": push.get("push_id"),
        "push_time": push.get("push_time") or push.get("created_at"),
        "papers": [_paper_card(paper, index) for index, paper in enumerate(papers, start=1)],
        "metadata": dict(push.get("metadata") or {}),
    }


def _preview_key(paper: Dict[str, Any]) -> str:
    return str(
        paper.get("id")
        or paper.get("arxiv_id")
        or paper.get("doi")
        or paper.get("title")
        or ""
    ).strip().casefold()


def _preview_payload(task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    items = list(task.get("preview_items") or [])
    if not items:
        return None
    return {
        "push_id": task.get("task_id"),
        "push_time": task.get("started_at") or task.get("created_at"),
        "papers": [_paper_card(paper, index) for index, paper in enumerate(items, start=1)],
        "metadata": {
            "preview": True,
            "phase": task.get("progress_phase") or task.get("status"),
            "fetched_count": int(task.get("fetched_count") or 0),
            "ranked_count": int(task.get("ranked_count") or 0),
            "total_fetched": int(task.get("fetched_count") or len(items)),
        },
    }


def _profile_summary(profile: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not profile:
        return None
    directions = profile.get("core_directions") or {}
    topics = profile.get("topic_weights") or {}
    return {
        "user_id": profile.get("user_id"),
        "version": profile.get("version"),
        "updated_at": profile.get("updated_at"),
        "core_directions": directions,
        "top_directions": sorted(directions.items(), key=lambda item: _to_float(item[1]), reverse=True)[:8],
        "top_topics": sorted(topics.items(), key=lambda item: _to_float(item[1]), reverse=True)[:8],
        "must_read": profile.get("must_read") or {},
        "drift_state": profile.get("drift_state") or {},
    }


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, min_value: int = 1, max_value: int = 100000) -> int:
    try:
        value = int(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(max_value, value))


def _configured_path(env_name: str, default_relative: str) -> str:
    notes_root = _configured_notes_root_dir()
    if notes_root is not None:
        if env_name in {"PAPERFLOW_PDF_DIR", "PAPERFLOW_READING_REPORTS_DIR"}:
            return str(notes_root)
        if env_name == "PAPERFLOW_WIKI_DIR":
            return str(notes_root / "wiki")
    raw = os.environ.get(env_name, "").strip()
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return str(path)
    return str(PROJECT_ROOT / default_relative)


def _configured_notes_root_dir() -> Optional[Path]:
    if (
        os.environ.get("PAPERFLOW_READING_REPORTS_DIR", "").strip()
        or os.environ.get("PAPERFLOW_PDF_DIR", "").strip()
        or os.environ.get("PAPERFLOW_WIKI_DIR", "").strip()
    ):
        return None
    raw = os.environ.get("PAPERFLOW_NOTES_ROOT_DIR", "").strip()
    if raw:
        path = Path(raw).expanduser()
        return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
    file_raw = _read_env_file().get("PAPERFLOW_NOTES_ROOT_DIR", "").strip()
    if file_raw:
        path = Path(file_raw).expanduser()
        return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
    for env_name in ("PAPERFLOW_READING_REPORTS_DIR", "PAPERFLOW_PDF_DIR"):
        legacy = _env_text(env_name, "")
        if legacy:
            path = Path(legacy).expanduser()
            return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
    return None


def _configured_notes_root_dir_text() -> str:
    path = _configured_notes_root_dir()
    return str(path) if path else ""


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved)


def _directory_size_bytes(path: Path, max_files: int = 5000) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    total = 0
    count = 0
    for item in path.rglob("*"):
        if count >= max_files:
            break
        try:
            if item.is_file():
                total += item.stat().st_size
                count += 1
        except OSError:
            continue
    return total


def _format_bytes(value: int) -> str:
    size = float(max(0, int(value or 0)))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)}B"
            return f"{size:.1f}{unit}"
        size /= 1024
    return "0B"


def _storage_stats(paths: Dict[str, Any]) -> Dict[str, Any]:
    tracked = [
        paths.get("pdf_dir"),
        paths.get("reading_reports_dir"),
        paths.get("wiki_dir"),
    ]
    total = 0
    for raw_path in tracked:
        if not raw_path:
            continue
        total += _directory_size_bytes(Path(str(raw_path)).expanduser())
    return {
        "cache_bytes": total,
        "cache_display": _format_bytes(total),
    }


def _reading_report_dirs() -> List[Path]:
    configured = Path(_configured_path("PAPERFLOW_READING_REPORTS_DIR", "data/exports")).resolve()
    if _env_text("PAPERFLOW_READING_REPORTS_DIR", ""):
        return [configured] if configured.exists() and configured.is_dir() else [configured]
    fallback = (PROJECT_ROOT / "data" / "reading_reports").resolve()
    legacy_exports = (PROJECT_ROOT / "data" / "exports").resolve()
    ordered = [configured, fallback, legacy_exports]
    results: List[Path] = []
    seen: Set[str] = set()
    for candidate in ordered:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and candidate.is_dir():
            results.append(candidate)
    if not results:
        results.append(configured)
    return results


def _report_id(path: Path) -> str:
    return hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:20]


def _extract_frontmatter(raw: str) -> Tuple[Dict[str, Any], str]:
    if not raw.startswith("---"):
        return {}, raw
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, raw
    end_index = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
    if end_index is None:
        return {}, raw
    frontmatter_text = "\n".join(lines[1:end_index]).strip()
    body = "\n".join(lines[end_index + 1 :]).lstrip()
    if not frontmatter_text:
        return {}, body
    try:
        parsed = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}, body


def _report_title(body: str, path: Path) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or path.stem
    return path.stem


def _first_matching_url(text: str, needle: str) -> str:
    pattern = re.compile(r"https?://[^\s)>\]]+", flags=re.IGNORECASE)
    for match in pattern.findall(text or ""):
        if needle.lower() in match.lower():
            return match.rstrip(".,")
    return ""


def _report_snippet(body: str) -> str:
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        line = re.sub(r"^>+\s*", "", line)
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"`([^`]*)`", r"\1", line)
        if not line:
            continue
        return line[:240]
    return ""


def _report_record(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    metadata, body = _extract_frontmatter(raw)
    stat = path.stat()
    title = str(metadata.get("title") or _report_title(body, path))
    saved_at = str(
        metadata.get("saved_at")
        or metadata.get("updated_at")
        or datetime.fromtimestamp(stat.st_mtime).replace(microsecond=0).isoformat()
    )
    updated_at = datetime.fromtimestamp(stat.st_mtime).replace(microsecond=0).isoformat()
    doc_url = str(metadata.get("doc_url") or "")
    pdf_url = str(metadata.get("pdf_url") or _first_matching_url(body, "/pdf/"))
    abs_url = str(metadata.get("abs_url") or _first_matching_url(body, "/abs/"))
    return {
        "report_id": _report_id(path),
        "title": title,
        "user_id": str(metadata.get("user_id") or "").strip(),
        "paper_id": metadata.get("paper_id"),
        "arxiv_id": str(metadata.get("arxiv_id") or "").strip(),
        "saved_at": saved_at,
        "updated_at": updated_at,
        "report_path": _display_path(path),
        "doc_url": doc_url,
        "doc_token": str(metadata.get("doc_token") or "").strip(),
        "pdf_url": pdf_url,
        "abs_url": abs_url,
        "report_version": str(metadata.get("report_version") or "").strip(),
        "generation_provider": str(metadata.get("generation_provider") or "").strip(),
        "generation_model": str(metadata.get("generation_model") or "").strip(),
        "snippet": _report_snippet(body),
        "metadata": metadata,
        "markdown": body,
        "_sort_ts": stat.st_mtime,
    }


def _is_reading_report_record(report: Dict[str, Any]) -> bool:
    metadata = report.get("metadata") or {}
    if metadata.get("report_version") or metadata.get("generation_provider") or metadata.get("generation_model"):
        return True
    if metadata.get("pdf_path") or metadata.get("doc_token") or metadata.get("doc_url"):
        return True
    source_type = str(metadata.get("report_source_type") or metadata.get("source_type") or "").strip()
    return source_type in {"arxiv", "pdf", "local_pdf", "feishu_file_key", "reading_report"}


def _all_report_records() -> List[Dict[str, Any]]:
    reports: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for root in _reading_report_dirs():
        for path in root.rglob("*.md"):
            if not path.is_file():
                continue
            resolved_key = str(path.resolve())
            if resolved_key in seen:
                continue
            seen.add(resolved_key)
            report = _report_record(path)
            if not _is_reading_report_record(report):
                continue
            reports.append(report)
    reports.sort(key=lambda item: item["_sort_ts"], reverse=True)
    return reports


def _safe_env() -> Dict[str, str]:
    prefixes = (
        "PAPERFLOW_",
        "OPENAI_",
        "ANTHROPIC_",
        "OLLAMA_",
        "DASHSCOPE_",
        "FEISHU_",
        "NGROK_",
        "SEMANTIC_SCHOLAR_",
        "OPENREVIEW_",
        "HTTP_PROXY",
        "HTTPS_PROXY",
    )
    sensitive = ("KEY", "TOKEN", "SECRET", "PASSWORD")
    result: Dict[str, str] = {}
    for key, value in sorted(os.environ.items()):
        if not key.startswith(prefixes):
            continue
        result[key] = "***" if any(part in key for part in sensitive) and value else value
    return result


def _read_env_file() -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _env_edit_payload() -> List[Dict[str, str]]:
    file_values = _read_env_file()
    sensitive = ("KEY", "TOKEN", "SECRET", "PASSWORD")
    rows = []
    for key in EDITABLE_ENV_KEYS:
        raw_value = file_values.get(key, os.environ.get(key, ""))
        rows.append(
            {
                "key": key,
                "value": "***" if any(part in key for part in sensitive) and raw_value else str(raw_value),
                "is_secret": bool(any(part in key for part in sensitive)),
                "present": bool(str(raw_value).strip()),
            }
        )
    return rows


def _serialize_env_value(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if any(char.isspace() for char in text) or "#" in text:
        escaped = text.replace('"', '\\"')
        return f'"{escaped}"'
    return text


def _env_text(name: str, default: str = "") -> str:
    file_values = _read_env_file()
    return str(file_values.get(name, os.environ.get(name, default)) or default).strip()


def _configured_reading_notes_git_branch() -> str:
    return _env_text("PAPERFLOW_READING_NOTES_GIT_BRANCH", "main") or "main"


def _configured_reading_notes_git_remote() -> str:
    return _env_text("PAPERFLOW_READING_NOTES_GIT_REMOTE", "")


def _default_reading_notes_git_dir() -> Optional[Path]:
    current_year = datetime.now().year
    notes_root = _configured_notes_root_dir()
    if notes_root is not None:
        if notes_root.name == f"Daily Note {current_year}":
            return notes_root.resolve()
        return (notes_root / f"Daily Note {current_year}").resolve()
    for root in _daily_note_roots():
        candidates = []
        if root.name == f"Daily Note {current_year}":
            candidates.append(root)
        candidates.append(root / f"Daily Note {current_year}")
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
    return None


def _configured_reading_notes_git_dir() -> Optional[Path]:
    if _configured_notes_root_dir() is not None:
        return _default_reading_notes_git_dir()
    raw = _env_text("PAPERFLOW_READING_NOTES_GIT_DIR", "")
    if raw:
        path = Path(raw).expanduser()
        return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
    return _default_reading_notes_git_dir()


def _configured_reading_notes_git_dir_text() -> str:
    path = _configured_reading_notes_git_dir()
    return str(path) if path else ""


def _env_list(name: str, default: Optional[List[str]] = None) -> List[str]:
    raw = _env_text(name)
    if not raw:
        return list(default or [])
    parsed = _load_json(raw, None)
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [item.strip() for item in re.split(r"[,;\n]", raw) if item.strip()]


def _merge_env_file(updates: Dict[str, str]) -> None:
    existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    used: Set[str] = set()
    next_lines: List[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            next_lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            next_lines.append(f"{key}={_serialize_env_value(updates[key])}")
            used.add(key)
        else:
            next_lines.append(line)

    missing = [key for key in EDITABLE_ENV_KEYS if key in updates and key not in used]
    if missing and next_lines and next_lines[-1].strip():
        next_lines.append("")
    for key in missing:
        next_lines.append(f"{key}={_serialize_env_value(updates[key])}")

    ENV_PATH.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")


def save_settings(values: Dict[str, Any]) -> Dict[str, Any]:
    updates: Dict[str, str] = {}
    for key, value in (values or {}).items():
        normalized_key = str(key or "").strip()
        if normalized_key not in EDITABLE_ENV_KEYS:
            continue
        text = str(value or "").strip()
        if text == "***":
            continue
        updates[normalized_key] = text

    if not updates:
        return settings()

    _merge_env_file(updates)
    if "PAPERFLOW_NOTES_ROOT_DIR" in updates:
        for legacy_key in (
            "PAPERFLOW_PDF_DIR",
            "PAPERFLOW_READING_REPORTS_DIR",
            "PAPERFLOW_WIKI_DIR",
            "PAPERFLOW_READING_NOTES_GIT_DIR",
        ):
            os.environ.pop(legacy_key, None)
    for key, value in updates.items():
        os.environ[key] = value
    return settings()


def source_options() -> Dict[str, Any]:
    arxiv_items = [
        {"id": key, "label": f"{key} - {label}"}
        for key, label in sorted(getattr(arxiv_fetcher, "CATEGORIES", {}).items())
    ]

    conferences: List[Dict[str, Any]] = []
    try:
        config = yaml.safe_load((PROJECT_ROOT / "config" / "conferences.yaml").read_text(encoding="utf-8")) or {}
        for item in config.get("conferences", []) or []:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            conferences.append(
                {
                    "id": name,
                    "label": name,
                    "group": str(item.get("venue_type") or ""),
                    "source": str(item.get("source") or ""),
                    "venue_id": str(item.get("venue_id") or ""),
                    "acceptance_timeline": str(item.get("acceptance_timeline") or ""),
                    "conference_date": str(item.get("conference_date") or ""),
                    "enabled": bool(item.get("enabled", True)),
                }
            )
    except Exception:
        conferences = [{"id": name, "label": name, "enabled": True} for name in daily_agent.load_default_conferences()]

    journals: List[Dict[str, Any]] = []
    try:
        config = yaml.safe_load((PROJECT_ROOT / "config" / "journals.yaml").read_text(encoding="utf-8")) or {}
        for group, items in (config.get("journals", {}) or {}).items():
            for item in items or []:
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                journals.append(
                    {
                        "id": name,
                        "label": name,
                        "group": str(group or ""),
                        "enabled": bool(item.get("enabled", True)),
                    }
                )
    except Exception:
        journals = [{"id": name, "label": name, "enabled": True} for name in daily_agent.load_default_journals()]

    return {
        "arxiv_categories": arxiv_items,
        "conferences": conferences,
        "journals": journals,
    }


@contextmanager
def _local_only_feishu_doc_patch(enabled: bool):
    if not enabled:
        yield
        return
    with _FEISHU_DOC_PATCH_LOCK:
        original = reading_agent.create_doc

        def fake_create_doc(title: str, content: str, folder_id: Optional[str] = None) -> Dict[str, Any]:
            return {
                "url": None,
                "obj_token": None,
                "local_only": True,
                "title": title,
                "folder_id": folder_id,
            }

        reading_agent.create_doc = fake_create_doc
        try:
            yield
        finally:
            reading_agent.create_doc = original


@contextmanager
def _reading_agent_output_env_patch():
    """Expose GUI-derived output paths to reading-agent, which reads os.environ directly."""
    patched = {
        "PAPERFLOW_READING_REPORTS_DIR": _configured_path("PAPERFLOW_READING_REPORTS_DIR", "data/exports"),
        "PAPERFLOW_PDF_DIR": _configured_path("PAPERFLOW_PDF_DIR", "data/exports"),
    }
    previous = {key: os.environ.get(key) for key in patched}
    os.environ.update(patched)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "project_root": str(PROJECT_ROOT),
        "database": str(db_ops.DB_PATH),
        "database_exists": Path(db_ops.DB_PATH).exists(),
    }


def settings() -> Dict[str, Any]:
    source_preferences = {
        "enable_arxiv": _env_text("PAPERFLOW_ENABLE_ARXIV", "true").lower() not in {"0", "false", "no", "off"},
        "enable_semantic_scholar": _env_text("PAPERFLOW_ENABLE_SEMANTIC_SCHOLAR", "true").lower() not in {"0", "false", "no", "off"},
        "enable_openreview": _env_text("PAPERFLOW_ENABLE_OPENREVIEW", "true").lower() not in {"0", "false", "no", "off"},
        "enable_custom_rss": _env_text("PAPERFLOW_ENABLE_CUSTOM_RSS", "false").lower() in {"1", "true", "yes", "on"},
        "arxiv_categories": _env_list("PAPERFLOW_DEFAULT_ARXIV_CATEGORIES", ["cs.CL", "cs.AI", "cs.IR", "cs.LG"]),
        "conferences": _env_list("PAPERFLOW_DEFAULT_CONFERENCES", ["ICLR", "NeurIPS", "ACL", "SIGIR"]),
        "journals": _env_list("PAPERFLOW_DEFAULT_JOURNALS", []),
        "custom_rss_urls": _env_list("PAPERFLOW_CUSTOM_RSS_URLS", ["https://arxiv.org/rss/cs.CL"]),
        "conference_access_mode": _env_text("PAPERFLOW_CONFERENCE_ACCESS_MODE", "public") or "public",
        "auth_status": {
            "semantic_scholar_api_key": bool(_env_text("SEMANTIC_SCHOLAR_API_KEY")),
            "openreview_username": bool(_env_text("OPENREVIEW_USERNAME")),
            "openreview_token": bool(_env_text("OPENREVIEW_TOKEN")),
            "openreview_cookie_file": bool(_env_text("OPENREVIEW_COOKIE_FILE")),
            "conference_cookie_file": bool(_env_text("PAPERFLOW_CONFERENCE_COOKIE_FILE")),
        },
    }
    report_preferences = {
        "style": _env_text("PAPERFLOW_REPORT_STYLE", "standard") or "standard",
        "write_feishu": _env_bool("PAPERFLOW_WRITE_FEISHU", default=False),
        "wiki_ingest": _env_bool("PAPERFLOW_WIKI_INGEST", default=True),
    }
    advanced = {
        "daily_limit": int(_to_float(_env_text("PAPERFLOW_DAILY_LIMIT", "30"), 30)),
        "relevance_threshold": int(_to_float(_env_text("PAPERFLOW_RELEVANCE_THRESHOLD", "60"), 60)),
        "http_proxy": _env_text("HTTP_PROXY", _env_text("HTTPS_PROXY", "")),
    }
    paths = {
        "notes_root_dir": _configured_notes_root_dir_text(),
        "pdf_dir": _configured_path("PAPERFLOW_PDF_DIR", "data/exports"),
        "reading_reports_dir": _configured_path("PAPERFLOW_READING_REPORTS_DIR", "data/exports"),
        "wiki_dir": _configured_path("PAPERFLOW_WIKI_DIR", "data/wiki"),
        "reading_notes_git_dir": _configured_reading_notes_git_dir_text(),
        "reading_notes_git_remote": _configured_reading_notes_git_remote(),
        "reading_notes_git_branch": _configured_reading_notes_git_branch(),
        "reading_notes_git_llm_review": _env_bool("PAPERFLOW_READING_NOTES_GIT_LLM_REVIEW", default=True),
        "monthly_report_dir": _configured_path("PAPERFLOW_MONTHLY_REPORT_DIR", "data/exports"),
        "topic_index_dir": _configured_path("PAPERFLOW_TOPIC_INDEX_DIR", "data/exports"),
        "role_subdir": _env_bool("PAPERFLOW_STORAGE_ROLE_SUBDIR", default=True),
        "category_subdir": _env_bool("PAPERFLOW_STORAGE_CATEGORY_SUBDIR", default=True),
        "monthly_subdir": _env_bool("PAPERFLOW_STORAGE_MONTHLY_SUBDIR", default=True),
        "wiki_ingest": _env_bool("PAPERFLOW_WIKI_INGEST", default=True),
        "write_feishu": _env_bool("PAPERFLOW_WRITE_FEISHU", default=False),
    }
    return {
        "project_root": str(PROJECT_ROOT),
        "env_path": str(ENV_PATH),
        "database": str(db_ops.DB_PATH),
        "paths": paths,
        "storage_stats": _storage_stats(paths),
        "source_preferences": source_preferences,
        "report_preferences": report_preferences,
        "advanced": advanced,
        "env": _safe_env(),
        "editable_env": _env_edit_payload(),
    }


def _configured_daily_limit(value: Any = None) -> int:
    if value in (None, ""):
        return _to_positive_int(_env_text("PAPERFLOW_DAILY_LIMIT", "30"), 30)
    return _to_positive_int(value, 30)


def _configured_relevance_threshold() -> int:
    return int(_to_float(_env_text("PAPERFLOW_RELEVANCE_THRESHOLD", "60"), 60))


def _normalized_cache_list(value: Any) -> List[str]:
    return sorted(_string_list(value))


def _cache_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _daily_cache_matches_settings(
    cached_push: Dict[str, Any],
    *,
    days: int,
    limit_per_source: int,
    target_date: str,
    sources: Dict[str, Any],
) -> bool:
    metadata = dict(cached_push.get("metadata") or {})
    try:
        cached_daily_limit = int(_to_float(metadata.get("daily_limit"), -1))
    except (TypeError, ValueError):
        cached_daily_limit = -1
    if cached_daily_limit != int(limit_per_source):
        return False
    if int(_to_float(metadata.get("limit_per_source"), -1)) != int(limit_per_source):
        return False
    if int(_to_float(metadata.get("relevance_threshold"), -1)) != _configured_relevance_threshold():
        return False
    if int(_to_float(metadata.get("fetch_days"), -1)) != max(1, int(days or 1)):
        return False
    requested_target_date = str(target_date or "").strip()
    cached_target_date = str(metadata.get("target_date") or "").strip()
    if requested_target_date and cached_target_date != requested_target_date:
        return False
    if cached_target_date and cached_target_date != requested_target_date:
        return False

    for key in ("arxiv_categories", "conferences", "journals", "custom_rss_urls"):
        if _normalized_cache_list(metadata.get(key)) != _normalized_cache_list(sources.get(key)):
            return False
    for key in ("enable_semantic_scholar", "enable_custom_rss"):
        if _cache_bool(metadata.get(key)) != bool(sources.get(key)):
            return False
    return True


def _normalize_push_date(value: Any = None) -> str:
    raw = str(value or "").strip()
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
        except ValueError:
            pass
    return datetime.now().date().isoformat()


def _configured_report_style() -> str:
    style = (_env_text("PAPERFLOW_REPORT_STYLE", "standard") or "standard").strip().lower()
    return style if style in {"standard", "deep", "brief"} else "standard"


def _configured_daily_sources(
    *,
    arxiv_categories: Optional[Iterable[Any]],
    conferences: Optional[Iterable[Any]],
    journals: Optional[Iterable[Any]],
) -> Dict[str, List[str]]:
    source_preferences = settings().get("source_preferences", {})
    resolved_arxiv = (
        _string_list(arxiv_categories)
        if arxiv_categories is not None
        else _string_list(source_preferences.get("arxiv_categories"))
    )
    resolved_conferences = (
        _string_list(conferences)
        if conferences is not None
        else _string_list(source_preferences.get("conferences"))
    )
    resolved_journals = (
        _string_list(journals)
        if journals is not None
        else _string_list(source_preferences.get("journals"))
    )

    if arxiv_categories is None and source_preferences.get("enable_arxiv") is False:
        resolved_arxiv = []
    if conferences is None and source_preferences.get("enable_openreview") is False:
        resolved_conferences = []

    return {
        "arxiv_categories": resolved_arxiv,
        "conferences": resolved_conferences,
        "journals": resolved_journals,
        "custom_rss_urls": _string_list(source_preferences.get("custom_rss_urls"))
        if source_preferences.get("enable_custom_rss")
        else [],
        "enable_semantic_scholar": bool(source_preferences.get("enable_semantic_scholar")),
        "enable_custom_rss": bool(source_preferences.get("enable_custom_rss")),
    }


def test_provider(kind: str) -> Dict[str, Any]:
    """Run an opt-in provider smoke test for the settings page."""
    normalized = (kind or "").strip().lower()
    if normalized == "llm":
        from paperflow.providers import build_llm_provider

        provider = build_llm_provider()
        response = provider.generate(
            "Reply with exactly: pong",
            system="You are a provider health checker.",
            temperature=0.0,
            max_tokens=8,
        )
        return {
            "kind": "llm",
            "ok": True,
            "provider": getattr(provider, "name", "unknown"),
            "model": getattr(provider, "model", "unknown"),
            "response": response.text,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
        }
    if normalized == "embedding":
        from paperflow.providers import build_embedding_provider

        provider = build_embedding_provider()
        vector = provider.embed("PaperFlow provider health check")
        return {
            "kind": "embedding",
            "ok": True,
            "provider": getattr(provider, "name", "unknown"),
            "model": getattr(provider, "model", "unknown"),
            "dimensions": len(vector),
        }
    raise ValueError("kind must be 'llm' or 'embedding'")


def _export_root() -> Path:
    root = PROJECT_ROOT / "data" / "desktop_exports"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _export_sources() -> List[Tuple[str, Path]]:
    return [
        ("papers", Path(_configured_path("PAPERFLOW_PDF_DIR", "data/exports")).resolve()),
        ("reading_reports", Path(_configured_path("PAPERFLOW_READING_REPORTS_DIR", "data/exports")).resolve()),
        ("wiki", Path(_configured_path("PAPERFLOW_WIKI_DIR", "data/wiki")).resolve()),
    ]


def export_data(user_id: str, export_format: str = "markdown") -> Dict[str, Any]:
    normalized = str(export_format or "markdown").strip().lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = _export_root()

    if normalized in {"markdown", "md"}:
        output = root / f"paperflow_{user_id or 'all'}_{timestamp}.md"
        reports = list_reports(user_id=user_id, days=3650, limit=200).get("reports") or []
        wiki_nodes = wiki_db.list_nodes(user_id, limit=200) if user_id else []
        filtered_wiki_nodes = _filter_wiki_nodes_for_configured_dir(wiki_nodes)
        if filtered_wiki_nodes is not None:
            wiki_nodes = filtered_wiki_nodes
        lines = [
            f"# PaperFlow Export - {user_id or 'all'}",
            "",
            f"- Exported at: {datetime.now().isoformat(sep=' ', timespec='seconds')}",
            f"- Reports: {len(reports)}",
            f"- Wiki nodes: {len(wiki_nodes)}",
            "",
            "## Reading Reports",
            "",
        ]
        for report in reports:
            lines.extend(
                [
                    f"### {report.get('title') or 'Untitled Report'}",
                    "",
                    f"- Path: {report.get('report_path') or ''}",
                    f"- Saved: {report.get('saved_at') or ''}",
                    "",
                    str(report.get("snippet") or "").strip(),
                    "",
                ]
            )
        lines.extend(["## Wiki Nodes", ""])
        for node in wiki_nodes:
            lines.extend(
                [
                    f"### {node.get('title') or node.get('node_id')}",
                    "",
                    f"- Type: {node.get('node_type') or ''}",
                    f"- Path: {node.get('file_path') or ''}",
                    "",
                    str(node.get("body") or "")[:1200],
                    "",
                ]
            )
        output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return {"format": "markdown", "path": str(output), "display_path": _display_path(output), "count": len(reports) + len(wiki_nodes)}

    if normalized == "zip":
        output = root / f"paperflow_{user_id or 'all'}_{timestamp}.zip"
        count = 0
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for label, path in _export_sources():
                if not path.exists():
                    continue
                if path.is_file():
                    archive.write(path, arcname=f"{label}/{path.name}")
                    count += 1
                    continue
                for file_path in path.rglob("*"):
                    if not file_path.is_file():
                        continue
                    if file_path.name.startswith("."):
                        continue
                    archive.write(file_path, arcname=f"{label}/{file_path.relative_to(path)}")
                    count += 1
        return {"format": "zip", "path": str(output), "display_path": _display_path(output), "count": count}

    raise ValueError("export_format must be markdown or zip")


def _run_git(args: List[str], cwd: Path, *, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=check,
        timeout=timeout,
    )


def _git_output(args: List[str], cwd: Path, *, timeout: int = 60) -> str:
    result = _run_git(args, cwd, timeout=timeout)
    return (result.stdout or "").strip()


def _git_ahead_behind(repo_dir: Path, branch: str) -> Tuple[int, int]:
    try:
        output = _git_output(["rev-list", "--left-right", "--count", f"HEAD...origin/{branch}"], repo_dir)
        ahead_text, behind_text = output.split()
        return int(ahead_text), int(behind_text)
    except Exception:
        return 0, 0


def _ensure_notes_gitignore(repo_dir: Path) -> None:
    ignore_path = repo_dir / ".gitignore"
    existing = ignore_path.read_text(encoding="utf-8").splitlines() if ignore_path.exists() else []
    needed = ["*.pdf", ".DS_Store", "*.bak-*"]
    next_lines = list(existing)
    for pattern in needed:
        if pattern not in next_lines:
            next_lines.append(pattern)
    if next_lines != existing:
        ignore_path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")


def _notes_git_remote(repo_dir: Path) -> str:
    del repo_dir
    return _configured_reading_notes_git_remote()


def _ensure_notes_git_repo(repo_dir: Path, remote_url: str, branch: str) -> None:
    if not (repo_dir / ".git").exists():
        _run_git(["init"], repo_dir)
    remotes = set(_git_output(["remote"], repo_dir).splitlines())
    if remote_url:
        if "origin" in remotes:
            current = _git_output(["remote", "get-url", "origin"], repo_dir)
            if current != remote_url:
                _run_git(["remote", "set-url", "origin", remote_url], repo_dir)
        else:
            _run_git(["remote", "add", "origin", remote_url], repo_dir)
    if remote_url:
        _run_git(["fetch", "origin", branch], repo_dir, timeout=120)
        try:
            _git_output(["rev-parse", "--verify", "HEAD"], repo_dir)
        except subprocess.CalledProcessError:
            _run_git(["symbolic-ref", "HEAD", f"refs/heads/{branch}"], repo_dir)
            _run_git(["update-ref", f"refs/heads/{branch}", f"refs/remotes/origin/{branch}"], repo_dir)
            _run_git(["reset", "--mixed"], repo_dir)


def _rebase_notes_branch(repo_dir: Path, branch: str, language: str) -> str:
    try:
        result = _run_git(["rebase", f"origin/{branch}"], repo_dir, timeout=120)
        return (result.stdout or result.stderr or "").strip()
    except subprocess.CalledProcessError as exc:
        rebase_output = (exc.stderr or exc.stdout or str(exc)).strip()
        _run_git(["rebase", "--abort"], repo_dir, check=False, timeout=60)
        raise RuntimeError(
            (
                "GitHub sync needs remote changes, but automatic rebase conflicted. "
                f"Resolve the reading-notes repo manually, then sync again: {rebase_output}"
            )
            if language == "en"
            else (
                "GitHub 同步需要合并远端新提交，但自动 rebase 发生冲突。"
                f"请手动处理阅读笔记仓库冲突后再同步：{rebase_output}"
            )
        ) from exc


def _is_non_fast_forward_push(output: str) -> bool:
    normalized = output.lower()
    return "non-fast-forward" in normalized or "fetch first" in normalized


def _notes_llm_sync_review(
    repo_dir: Path,
    branch: str,
    enabled: bool,
    response_language: str = "zh",
) -> Dict[str, Any]:
    language = _normalize_response_language(response_language)
    if not enabled:
        return {
            "enabled": False,
            "reviewed": False,
            "summary": "LLM review is disabled." if language == "en" else "LLM 校对已关闭。",
        }
    try:
        provider = build_llm_provider()
        if getattr(provider, "name", "") == "mock":
            return {
                "enabled": True,
                "reviewed": False,
                "summary": (
                    "The current LLM provider is mock; semantic review was skipped."
                    if language == "en"
                    else "当前 LLM provider 为 mock，跳过语义校对。"
                ),
            }
        status = _git_output(["status", "--short"], repo_dir)
        staged_stat = _git_output(["diff", "--cached", "--stat"], repo_dir)
        try:
            remote_stat = _git_output(["diff", "--stat", f"HEAD..origin/{branch}"], repo_dir)
        except Exception:
            remote_stat = ""
        staged_diff = _git_output(["diff", "--cached", "--", "*.md"], repo_dir)
        if len(staged_diff) > 12000:
            staged_diff = staged_diff[:12000] + "\n\n[diff truncated]"
        output_rule = (
            "Return concise English JSON with keys: risk_level, summary, suggested_action."
            if language == "en"
            else "Return concise Chinese JSON with keys: risk_level, summary, suggested_action."
        )
        prompt = "\n".join(
            [
                "Review this PaperFlow reading-notes Git sync before commit.",
                "Check whether local Daily Note and Deep Reading markdown changes look like additive preservation rather than accidental deletion.",
                output_rule,
                "",
                f"branch: {branch}",
                "git status:",
                status or "(clean)",
                "",
                "staged stat:",
                staged_stat or "(none)",
                "",
                "remote stat:",
                remote_stat or "(none)",
                "",
                "staged markdown diff:",
                staged_diff or "(none)",
            ]
        )
        response = provider.generate(
            prompt,
            system="You are a careful Git sync reviewer for an Obsidian reading-notes repository.",
            temperature=0.0,
            max_tokens=900,
        )
        return {
            "enabled": True,
            "reviewed": True,
            "provider": getattr(provider, "name", "unknown"),
            "model": getattr(provider, "model", "unknown"),
            "summary": str(getattr(response, "text", "") or "").strip(),
        }
    except Exception as exc:
        return {
            "enabled": True,
            "reviewed": False,
            "error": str(exc),
            "summary": f"LLM review failed: {exc}" if language == "en" else f"LLM 校对失败：{exc}",
        }


def sync_reading_notes_github(user_id: str = "", response_language: str = "zh") -> Dict[str, Any]:
    del user_id
    language = _normalize_response_language(response_language)
    repo_dir = _configured_reading_notes_git_dir()
    if repo_dir is None:
        raise ValueError(
            "Reading notes Git directory was not found. Configure PAPERFLOW_READING_NOTES_GIT_DIR in Settings."
            if language == "en"
            else "未找到阅读笔记 Git 目录，请在设置里配置 PAPERFLOW_READING_NOTES_GIT_DIR。"
        )
    repo_dir.mkdir(parents=True, exist_ok=True)
    branch = _configured_reading_notes_git_branch()
    remote_url = _notes_git_remote(repo_dir)
    if not remote_url:
        raise ValueError(
            "Reading notes GitHub remote is not configured. Configure PAPERFLOW_READING_NOTES_GIT_REMOTE in Settings."
            if language == "en"
            else "未配置阅读笔记 GitHub 远端，请在设置里配置 PAPERFLOW_READING_NOTES_GIT_REMOTE。"
        )

    _ensure_notes_git_repo(repo_dir, remote_url, branch)
    _ensure_notes_gitignore(repo_dir)

    _run_git(["fetch", "origin", branch], repo_dir, timeout=120)
    pulled = False
    pull_warning = ""

    _run_git(["add", "."], repo_dir)
    llm_review = _notes_llm_sync_review(
        repo_dir,
        branch,
        _env_bool("PAPERFLOW_READING_NOTES_GIT_LLM_REVIEW", default=True),
        response_language=language,
    )
    staged_status = _git_output(["status", "--short"], repo_dir)
    committed = False
    commit_hash = ""
    if staged_status:
        message = f"Sync PaperFlow reading notes {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        _run_git(["commit", "-m", message], repo_dir, timeout=120)
        committed = True
        commit_hash = _git_output(["rev-parse", "--short", "HEAD"], repo_dir)

    rebased = False
    rebase_output = ""
    _local_ahead, remote_ahead = _git_ahead_behind(repo_dir, branch)
    if remote_ahead:
        rebase_output = _rebase_notes_branch(repo_dir, branch, language)
        rebased = True
        pulled = True

    local_ahead, _remote_ahead = _git_ahead_behind(repo_dir, branch)
    pushed = False
    push_output = ""
    if local_ahead:
        try:
            result = _run_git(["push", "-u", "origin", branch], repo_dir, timeout=120)
            push_output = (result.stdout or result.stderr or "").strip()
            pushed = True
        except subprocess.CalledProcessError as exc:
            push_output = (exc.stderr or exc.stdout or str(exc)).strip()
            if not _is_non_fast_forward_push(push_output):
                raise RuntimeError(
                    f"GitHub push failed: {push_output}" if language == "en" else f"GitHub push 失败：{push_output}"
                ) from exc
            _run_git(["fetch", "origin", branch], repo_dir, timeout=120)
            retry_rebase_output = _rebase_notes_branch(repo_dir, branch, language)
            rebase_output = "\n".join([item for item in [rebase_output, retry_rebase_output] if item]).strip()
            rebased = True
            pulled = True
            retry_ahead, _retry_behind = _git_ahead_behind(repo_dir, branch)
            if retry_ahead:
                try:
                    result = _run_git(["push", "-u", "origin", branch], repo_dir, timeout=120)
                    push_output = (result.stdout or result.stderr or "").strip()
                    pushed = True
                except subprocess.CalledProcessError as retry_exc:
                    push_output = (retry_exc.stderr or retry_exc.stdout or str(retry_exc)).strip()
                    raise RuntimeError(
                        f"GitHub push failed: {push_output}" if language == "en" else f"GitHub push 失败：{push_output}"
                    ) from retry_exc
            else:
                push_output = ""

    final_status = _git_output(["status", "--short", "--ignored"], repo_dir)
    return {
        "ok": True,
        "repo_dir": str(repo_dir),
        "remote": remote_url,
        "branch": branch,
        "pulled": pulled,
        "rebased": rebased,
        "committed": committed,
        "commit": commit_hash,
        "pushed": pushed,
        "pull_warning": pull_warning,
        "rebase_output": rebase_output,
        "push_output": push_output,
        "llm_review": llm_review,
        "status": final_status,
    }


def list_users() -> Dict[str, Any]:
    db_ops.init_db()
    users: Dict[str, Dict[str, Any]] = {}

    try:
        roles = role_manager.list_roles()
        for role in roles.get("roles") or []:
            user_id = str(role.get("user_id") or "").strip()
            if not user_id:
                continue
            users[user_id] = {
                "user_id": user_id,
                "role_name": role.get("name"),
                "description": role.get("description", ""),
                "is_current": bool(role.get("is_current")),
                "source": "roles.json",
            }
    except Exception:
        pass

    conn = db_ops.get_connection()
    rows = conn.execute(
        """
        SELECT user_id, updated_at
        FROM profiles
        ORDER BY updated_at DESC, user_id ASC
        """
    ).fetchall()
    conn.close()

    for row in rows:
        user_id = str(row["user_id"])
        item = users.setdefault(
            user_id,
            {
                "user_id": user_id,
                "role_name": "",
                "description": "",
                "is_current": False,
                "source": "profiles",
            },
        )
        item["updated_at"] = row["updated_at"]
        item["has_profile"] = True

    return {"users": list(users.values())}


def list_roles() -> Dict[str, Any]:
    """Return role metadata in a GUI-friendly shape."""
    try:
        result = role_manager.list_roles()
    except Exception as exc:
        return {"roles": [], "current_role": None, "error": str(exc)}
    roles = []
    for role in result.get("roles") or []:
        roles.append(
            {
                "name": role.get("name"),
                "user_id": role.get("user_id"),
                "description": role.get("description", ""),
                "is_current": bool(role.get("is_current")),
            }
        )
    return {"roles": roles, "current_role": result.get("current_role")}


def create_role(role_name: str, description: str = "", feishu_chat_id: str = "") -> Dict[str, Any]:
    role_name = str(role_name or "").strip()
    if not role_name:
        raise ValueError("role_name is required")
    result = role_manager.create_role(
        role_name=role_name,
        description=str(description or "").strip(),
        natural_language=str(description or "").strip(),
        feishu_chat_id=str(feishu_chat_id or "").strip() or None,
    )
    return {"result": result, **list_roles()}


def switch_role(role_name: str) -> Dict[str, Any]:
    role_name = str(role_name or "").strip()
    if not role_name:
        raise ValueError("role_name is required")
    result = role_manager.switch_role(role_name)
    return {"result": result, **list_roles()}


def delete_role(role_name: str) -> Dict[str, Any]:
    role_name = str(role_name or "").strip()
    if not role_name:
        raise ValueError("role_name is required")
    result = role_manager.delete_role(role_name)
    return {"result": result, **list_roles()}


def get_profile(user_id: str) -> Dict[str, Any]:
    profile = db_ops.get_profile(user_id)
    return {"profile": _profile_summary(profile), "raw": profile}


def list_must_read(user_id: str) -> Dict[str, Any]:
    profile = db_ops.get_profile(user_id) or {}
    must_read = profile.get("must_read") or {"authors": [], "institutions": [], "keywords": []}
    return {
        "must_read": {
            "authors": list(must_read.get("authors") or []),
            "institutions": list(must_read.get("institutions") or []),
            "keywords": list(must_read.get("keywords") or []),
        }
    }


def update_must_read(user_id: str, item_type: str, value: str, action: str) -> Dict[str, Any]:
    normalized_type = (item_type or "").strip().lower()
    normalized_action = (action or "").strip().lower()
    if normalized_type not in {"author", "institution", "keyword"}:
        raise ValueError("item_type must be author, institution, or keyword")
    if normalized_action not in {"add", "remove"}:
        raise ValueError("action must be add or remove")
    cleaned_value = str(value or "").strip()
    if not cleaned_value:
        raise ValueError("value is required")

    profile = db_ops.get_profile(user_id)
    if not profile:
        raise ValueError(f"Profile not found: {user_id}")

    if normalized_action == "add":
        result = must_read_agent.add_must_read(profile, normalized_type, cleaned_value)
    else:
        result = must_read_agent.remove_must_read(profile, normalized_type, cleaned_value)

    if result.get("success"):
        db_ops.update_profile(user_id, profile)
        db_ops.log_behavior(
            user_id=user_id,
            push_id="desktop_gui",
            paper_id=None,
            action=f"{normalized_action}_{normalized_type}",
            action_type="must_read_update",
            category="desktop_gui",
            metadata={"value": cleaned_value, "item_type": normalized_type},
        )

    return {
        "result": result,
        "profile": _profile_summary(profile),
        **list_must_read(user_id),
    }


def _parse_weight_text(value: Any) -> Dict[str, float]:
    result: Dict[str, float] = {}
    for item in _string_list(str(value or "").replace("\n", ";").split(";")):
        label = item
        weight = 1.0
        if ":" in item:
            label, raw_weight = item.rsplit(":", 1)
        elif "=" in item:
            label, raw_weight = item.rsplit("=", 1)
        else:
            raw_weight = ""
        label = str(label or "").strip()
        if not label:
            continue
        if raw_weight:
            weight = max(0.0, min(1.0, _to_float(raw_weight, 1.0)))
        result[label] = round(weight, 4)
    return result


def _manual_profile_updates(
    *,
    affiliation: str = "",
    core_directions_text: str = "",
    topic_weights_text: str = "",
    must_read_keywords: Optional[List[str]] = None,
    must_read_authors: Optional[List[str]] = None,
    must_read_institutions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    updates: Dict[str, Any] = {}
    cleaned_affiliation = str(affiliation or "").strip()
    if cleaned_affiliation:
        updates["affiliation"] = cleaned_affiliation
    core_directions = _parse_weight_text(core_directions_text)
    if core_directions:
        updates["core_directions"] = core_directions
    topic_weights = _parse_weight_text(topic_weights_text)
    if topic_weights:
        updates["topic_weights"] = topic_weights

    must_read: Dict[str, List[str]] = {}
    if must_read_keywords is not None:
        must_read["keywords"] = _string_list(must_read_keywords)
    if must_read_authors is not None:
        must_read["authors"] = _string_list(must_read_authors)
    if must_read_institutions is not None:
        must_read["institutions"] = _string_list(must_read_institutions)
    if must_read:
        updates["must_read"] = must_read
    return updates


def _apply_manual_profile_updates(user_id: str, updates: Dict[str, Any]) -> None:
    if not updates:
        return
    existing_profile = db_ops.get_profile(user_id)
    profile = existing_profile or {
        "user_id": user_id,
        "version": "0.1",
        "core_directions": {},
        "topic_weights": {},
        "must_read": {"authors": [], "institutions": [], "keywords": []},
    }
    profile["user_id"] = user_id
    if "affiliation" in updates:
        profile["affiliation"] = updates["affiliation"]
    if "core_directions" in updates:
        profile["core_directions"] = updates["core_directions"]
    if "topic_weights" in updates:
        profile["topic_weights"] = updates["topic_weights"]
    if "must_read" in updates:
        must_read = dict(profile.get("must_read") or {})
        for key, values in updates["must_read"].items():
            must_read[key] = values
        for key in ("authors", "institutions", "keywords"):
            must_read.setdefault(key, [])
        profile["must_read"] = must_read
    if existing_profile:
        db_ops.update_profile(user_id, profile)
    else:
        db_ops.create_profile(user_id, profile)


def create_or_update_profile(
    *,
    user_id: str,
    natural_language: str = "",
    scholar_url: str = "",
    homepage_url: str = "",
    pdf_paths: Optional[List[str]] = None,
    affiliation: str = "",
    core_directions_text: str = "",
    topic_weights_text: str = "",
    must_read_keywords: Optional[List[str]] = None,
    must_read_authors: Optional[List[str]] = None,
    must_read_institutions: Optional[List[str]] = None,
    reset_existing: bool = False,
) -> Dict[str, Any]:
    if not user_id.strip():
        raise ValueError("user_id is required")
    normalized_user_id = user_id.strip()
    result = coldstart_agent.cold_start(
        user_id=normalized_user_id,
        natural_language=natural_language.strip() or None,
        pdf_paths=pdf_paths or None,
        scholar_url=scholar_url.strip() or None,
        homepage_url=homepage_url.strip() or None,
        reset_existing=reset_existing,
        send_to_feishu=False,
    )
    manual_updates = _manual_profile_updates(
        affiliation=affiliation,
        core_directions_text=core_directions_text,
        topic_weights_text=topic_weights_text,
        must_read_keywords=must_read_keywords,
        must_read_authors=must_read_authors,
        must_read_institutions=must_read_institutions,
    )
    _apply_manual_profile_updates(normalized_user_id, manual_updates)
    profile = db_ops.get_profile(normalized_user_id)
    return {"result": result, "profile": _profile_summary(profile), "raw": profile}


def run_daily_push(
    user_id: str,
    days: int = 1,
    limit_per_source: Optional[int] = None,
    arxiv_categories: Optional[Iterable[Any]] = None,
    conferences: Optional[Iterable[Any]] = None,
    journals: Optional[Iterable[Any]] = None,
    target_date: Optional[str] = None,
    progress_callback: Optional[Any] = None,
) -> Dict[str, Any]:
    sources = _configured_daily_sources(
        arxiv_categories=arxiv_categories,
        conferences=conferences,
        journals=journals,
    )
    result = daily_agent.daily_push(
        user_id=user_id,
        days=max(1, int(days or 1)),
        arxiv_categories=sources["arxiv_categories"],
        conferences=sources["conferences"],
        journals=sources["journals"],
        custom_rss_urls=sources["custom_rss_urls"],
        enable_semantic_scholar=sources["enable_semantic_scholar"],
        enable_custom_rss=sources["enable_custom_rss"],
        limit_per_source=_configured_daily_limit(limit_per_source),
        push_limit=_configured_daily_limit(limit_per_source),
        target_date=_normalize_push_date(target_date) if target_date else None,
        send_to_feishu=False,
        progress_callback=progress_callback,
    )
    push = None
    if isinstance(result, dict) and result.get("push_id"):
        push = db_ops.get_push_papers(result["push_id"])
    if push is None:
        push = db_ops.get_latest_push(user_id)
    push_payload = _push_payload(push)
    if push_payload is not None and isinstance(result, dict):
        metadata = dict(push_payload.get("metadata") or {})
        for key in (
            "paper_count",
            "total_fetched",
            "reason",
            "fallback_used",
            "fallback_days",
            "fallback_total_fetched",
            "fallback_filtered_already_handled",
            "fallback_kept_candidates",
            "fallback_relaxed",
            "fallback_source_scope",
        ):
            if key in result and key not in metadata:
                metadata[key] = result[key]
        push_payload["metadata"] = metadata
    return {"result": result, "push": push_payload}


def _task_timestamp() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _daily_task_payload(task: Dict[str, Any]) -> Dict[str, Any]:
    payload = deepcopy(
        {
            key: value
            for key, value in task.items()
            if key not in {"thread", "preview_items_by_key"}
        }
    )
    payload["preview_push"] = _preview_payload(task)
    return payload


def _make_daily_progress_callback(task_id: str):
    def callback(event: Dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        phase = str(event.get("phase") or "").strip()
        paper = event.get("paper")
        with _DAILY_TASK_LOCK:
            task = _DAILY_TASKS.get(task_id)
            if not task:
                return
            task["progress_phase"] = phase or task.get("progress_phase")
            task["updated_at"] = _task_timestamp()
            if phase == "source_complete":
                task.setdefault("source_counts", {})[str(event.get("source") or "unknown")] = int(event.get("count") or 0)
            if phase == "deduplicated":
                task["deduplicated_count"] = int(event.get("count") or 0)
            if phase == "scored":
                task["scored_count"] = int(event.get("count") or 0)
            if not isinstance(paper, dict):
                return

            key = _preview_key(paper)
            if not key:
                return
            by_key = task.setdefault("preview_items_by_key", {})
            items = task.setdefault("preview_items", [])

            if phase == "ranked" and task.get("preview_mode") != "ranked":
                task["preview_mode"] = "ranked"
                by_key.clear()
                items.clear()

            item = dict(paper)
            if phase == "fetched":
                item.setdefault("category", "pending")
            if phase == "ranked":
                item["score"] = event.get("score")
                item["category"] = event.get("category") or item.get("category") or "unknown"
                item["rank"] = event.get("rank") or len(items) + 1

            if key in by_key:
                index = by_key[key]
                items[index].update(item)
            else:
                by_key[key] = len(items)
                items.append(item)

            task["fetched_count"] = max(int(task.get("fetched_count") or 0), len(items))
            if phase == "ranked":
                task["ranked_count"] = int(task.get("ranked_count") or 0) + 1

    return callback


def _finish_daily_task(task_id: str) -> None:
    with _DAILY_TASK_LOCK:
        task = _DAILY_TASKS.get(task_id)
        if not task:
            return
        task["status"] = "running"
        task["started_at"] = _task_timestamp()
        task["updated_at"] = task["started_at"]
        user_id = str(task["user_id"])
        days = int(task.get("days") or 1)
        limit_per_source = _configured_daily_limit(task.get("limit_per_source"))
        arxiv_categories = task.get("arxiv_categories")
        conferences = task.get("conferences")
        journals = task.get("journals")
        target_date = task.get("target_date")

    try:
        result = run_daily_push(
            user_id,
            days=days,
            limit_per_source=limit_per_source,
            arxiv_categories=arxiv_categories,
            conferences=conferences,
            journals=journals,
            target_date=target_date,
            progress_callback=_make_daily_progress_callback(task_id),
        )
    except Exception as exc:  # pragma: no cover - exercised through GUI/server boundary
        with _DAILY_TASK_LOCK:
            task = _DAILY_TASKS.get(task_id)
            if task:
                task["status"] = "failed"
                task["error"] = str(exc)
                task["completed_at"] = _task_timestamp()
                task["updated_at"] = task["completed_at"]
        return

    with _DAILY_TASK_LOCK:
        task = _DAILY_TASKS.get(task_id)
        if task:
            task["status"] = "completed"
            task["result"] = result.get("result")
            task["push"] = result.get("push")
            task["completed_at"] = _task_timestamp()
            task["updated_at"] = task["completed_at"]


def start_daily_push_task(
    user_id: str,
    days: int = 1,
    limit_per_source: Optional[int] = None,
    arxiv_categories: Optional[Iterable[Any]] = None,
    conferences: Optional[Iterable[Any]] = None,
    journals: Optional[Iterable[Any]] = None,
    target_date: Optional[str] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    cleaned_user_id = str(user_id or "").strip()
    if not cleaned_user_id:
        raise ValueError("user_id is required")
    normalized_target_date = _normalize_push_date(target_date)
    requested_days = max(1, int(days or 1))
    requested_limit = _configured_daily_limit(limit_per_source)
    requested_sources = _configured_daily_sources(
        arxiv_categories=arxiv_categories,
        conferences=conferences,
        journals=journals,
    )

    if not force_refresh:
        cached_push = _push_payload(db_ops.get_push_for_date(cleaned_user_id, normalized_target_date))
        if cached_push is not None and _daily_cache_matches_settings(
            cached_push,
            days=requested_days,
            limit_per_source=requested_limit,
            target_date=normalized_target_date,
            sources=requested_sources,
        ):
            metadata = dict(cached_push.get("metadata") or {})
            metadata["cached"] = True
            metadata["cached_for_date"] = normalized_target_date
            cached_push["metadata"] = metadata
            now = _task_timestamp()
            cached_task = {
                "task_id": f"cached_{normalized_target_date}_{cleaned_user_id}",
                "kind": "daily_push",
                "user_id": cleaned_user_id,
                "status": "completed",
                "days": requested_days,
                "limit_per_source": requested_limit,
                "arxiv_categories": cached_push.get("metadata", {}).get("arxiv_categories"),
                "conferences": cached_push.get("metadata", {}).get("conferences"),
                "journals": cached_push.get("metadata", {}).get("journals"),
                "target_date": normalized_target_date,
                "cached": True,
                "created_at": now,
                "updated_at": now,
                "started_at": now,
                "completed_at": now,
                "error": None,
                "result": {
                    "success": True,
                    "push_id": cached_push.get("push_id"),
                    "cached": True,
                    "target_date": normalized_target_date,
                },
                "push": cached_push,
                "preview_items": [],
                "preview_mode": "cached",
                "progress_phase": "cached",
                "fetched_count": cached_push.get("metadata", {}).get("total_fetched", len(cached_push.get("papers") or [])),
                "ranked_count": cached_push.get("metadata", {}).get("paper_count", len(cached_push.get("papers") or [])),
            }
            return {"task": _daily_task_payload(cached_task), "already_running": False, "cached": True}

    with _DAILY_TASK_LOCK:
        existing_id = _DAILY_TASK_BY_USER.get(cleaned_user_id)
        existing = _DAILY_TASKS.get(existing_id or "")
        if existing and existing.get("status") in {"queued", "running"}:
            return {"task": _daily_task_payload(existing), "already_running": True}

        now = _task_timestamp()
        task_id = f"daily_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
        task: Dict[str, Any] = {
            "task_id": task_id,
            "kind": "daily_push",
            "user_id": cleaned_user_id,
            "status": "queued",
            "days": requested_days,
            "limit_per_source": requested_limit,
            "arxiv_categories": requested_sources["arxiv_categories"],
            "conferences": requested_sources["conferences"],
            "journals": requested_sources["journals"],
            "target_date": normalized_target_date,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "result": None,
            "push": None,
            "preview_items": [],
            "preview_items_by_key": {},
            "preview_mode": "fetched",
            "progress_phase": "queued",
            "fetched_count": 0,
            "ranked_count": 0,
        }
        thread = threading.Thread(target=_finish_daily_task, args=(task_id,), daemon=True)
        task["thread"] = thread
        _DAILY_TASKS[task_id] = task
        _DAILY_TASK_BY_USER[cleaned_user_id] = task_id
        payload = _daily_task_payload(task)

    thread.start()
    return {"task": payload, "already_running": False}


def get_daily_push_task(task_id: str = "", user_id: str = "") -> Dict[str, Any]:
    with _DAILY_TASK_LOCK:
        task = _DAILY_TASKS.get(str(task_id or "").strip())
        if task is None and str(user_id or "").strip():
            task = _DAILY_TASKS.get(_DAILY_TASK_BY_USER.get(str(user_id).strip(), ""))
        return {"task": _daily_task_payload(task) if task else None}


def load_latest_push(user_id: str) -> Dict[str, Any]:
    return {"push": _push_payload(db_ops.get_latest_push(user_id))}


def _log_feedback_event(
    *,
    user_id: str,
    push_id: str,
    paper_number: int,
    paper: Dict[str, Any],
    action: str,
    action_type: str,
    category: str,
) -> int:
    metadata = {
        "paper_number": paper_number,
        "arxiv_id": paper.get("arxiv_id"),
        "push_context": "desktop_gui",
        "selection_state": action_type,
    }
    behavior_log_id = db_ops.log_behavior(
        user_id=user_id,
        push_id=push_id,
        paper_id=paper.get("id"),
        action=action,
        action_type=action,
        category=category,
        metadata=metadata,
    )
    feedback_agent.ingest_feedback_to_wiki(
        user_id=user_id,
        push_id=push_id,
        paper=paper,
        action=action,
        action_type=action,
        category=category,
        metadata=metadata,
        behavior_log_id=behavior_log_id,
    )
    return behavior_log_id


def submit_gui_feedback(
    *,
    user_id: str,
    push_id: str,
    selected_numbers: Iterable[Any],
    skipped_numbers: Iterable[Any],
    later_numbers: Iterable[Any] = (),
) -> Dict[str, Any]:
    push = db_ops.get_push_papers(push_id)
    if not push or not push.get("papers"):
        raise ValueError(f"Push not found: {push_id}")

    papers = list(push["papers"])
    selected = set(_unique_ints(selected_numbers, maximum=len(papers)))
    skipped = set(_unique_ints(skipped_numbers, maximum=len(papers))) - selected
    later = (set(_unique_ints(later_numbers, maximum=len(papers))) - selected) - skipped

    current_timestamp = datetime.now()
    previously_selected = feedback_agent.get_existing_selected_numbers(user_id, push_id, papers)
    new_selected = selected - previously_selected

    for paper_number in sorted(new_selected):
        paper = papers[paper_number - 1]
        _log_feedback_event(
            user_id=user_id,
            push_id=push_id,
            paper_number=paper_number,
            paper=paper,
            action="selected",
            action_type="gui_selected",
            category=paper.get("category", "unknown"),
        )

    for paper_number in sorted(skipped):
        paper = papers[paper_number - 1]
        _log_feedback_event(
            user_id=user_id,
            push_id=push_id,
            paper_number=paper_number,
            paper=paper,
            action="skipped",
            action_type="gui_skipped",
            category=paper.get("category", "unknown"),
        )

    for paper_number in sorted(later):
        paper = papers[paper_number - 1]
        _log_feedback_event(
            user_id=user_id,
            push_id=push_id,
            paper_number=paper_number,
            paper=paper,
            action="later",
            action_type="gui_later",
            category=paper.get("category", "unknown"),
        )

    profile_before = db_ops.get_profile(user_id) or {}
    updated_profile: Dict[str, Any] = profile_before
    if selected or skipped or later:
        history_before_update = db_ops.get_recent_selected_papers(
            user_id,
            limit=60,
            days=60,
            before_timestamp=current_timestamp.isoformat(sep=" "),
        )
        strength, _latency = feedback_agent.estimate_feedback_strength_multiplier(push_id, current_timestamp)
        updated_profile = feedback_agent.update_profile_based_on_selection(
            user_id=user_id,
            selected_paper_ids=sorted(selected),
            skipped_paper_ids=sorted(skipped),
            papers=papers,
            historical_selected_papers=history_before_update,
            current_timestamp=current_timestamp,
            feedback_strength_multiplier=strength,
        )
        evidence_numbers = sorted(selected | skipped | later)
        evidence_papers = [papers[number - 1] for number in evidence_numbers if 1 <= number <= len(papers)]
        feedback_agent.ingest_profile_drift_to_wiki(
            user_id=user_id,
            before=profile_before,
            after=updated_profile or {},
            evidence_papers=evidence_papers,
            source_ref=push_id,
        )

    return {
        "status": "success",
        "push_id": push_id,
        "selected_numbers": sorted(selected),
        "newly_selected_numbers": sorted(new_selected),
        "skipped_numbers": sorted(skipped),
        "later_numbers": sorted(later),
        "profile": _profile_summary(updated_profile),
    }


def _resolve_project_path(value: Any) -> Optional[Path]:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _backfill_docs_to_wiki(user_id: str, docs: Iterable[Dict[str, Any]]) -> int:
    """Best-effort Wiki ingest for reused reading reports returned by the GUI."""
    ingest = getattr(reading_agent, "ingest_reading_report_to_wiki", None)
    if ingest is None:
        return 0

    backfilled = 0
    for doc in docs or []:
        if doc.get("wiki_ingest"):
            continue
        report_path = _resolve_project_path(doc.get("report_path"))
        if not report_path or not report_path.exists() or not report_path.is_file():
            continue
        try:
            raw = report_path.read_text(encoding="utf-8")
            metadata, body = _extract_frontmatter(raw)
            paper = dict(doc.get("paper") or {})
            for key in ("paper_id", "arxiv_id", "doi", "title", "pdf_path", "pdf_url", "publish_date"):
                if metadata.get(key) not in (None, "", [], {}) and paper.get(key) in (None, "", [], {}):
                    paper[key] = metadata.get(key)
            result = ingest(
                user_id=user_id,
                paper=paper,
                report_content=body or raw,
                report_payload=doc.get("report_payload") or {},
                report_path=str(report_path),
                doc_url=doc.get("url") or metadata.get("doc_url"),
                doc_token=doc.get("doc_token") or metadata.get("doc_token"),
            )
        except Exception as exc:
            doc["wiki_ingest_error"] = str(exc)
            continue
        if result:
            doc["wiki_ingest"] = result
            backfilled += 1
    return backfilled


def create_reading_reports(
    *,
    user_id: str,
    push_id: str,
    paper_numbers: Iterable[Any],
    write_feishu: Optional[bool] = None,
    response_language: str = "zh",
) -> Dict[str, Any]:
    push = db_ops.get_push_papers(push_id)
    if not push or not push.get("papers"):
        raise ValueError(f"Push not found: {push_id}")
    papers = list(push["papers"])
    selected = _unique_ints(paper_numbers, maximum=len(papers))
    should_write_feishu = _env_bool("PAPERFLOW_WRITE_FEISHU", default=False) if write_feishu is None else bool(write_feishu)
    language = _normalize_response_language(response_language)
    if not selected:
        return _reports_payload([], write_feishu_requested=should_write_feishu)

    with _reading_agent_output_env_patch(), _local_only_feishu_doc_patch(not should_write_feishu):
        docs = reading_agent.create_reading_report(
            user_id=user_id,
            paper_ids=selected,
            papers=papers,
            send_to_feishu=should_write_feishu,
            request_metadata={
                "selection_push_id": push_id,
                "report_source_type": "desktop_gui",
                "report_style": _configured_report_style(),
                "response_language": language,
            },
        )

    wiki_backfilled = _backfill_docs_to_wiki(user_id, docs)
    payload = _reports_payload(docs, write_feishu_requested=should_write_feishu)
    payload["wiki_backfilled"] = wiki_backfilled
    return payload


def _normalize_arxiv_id(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("arxiv_id is required")
    raw = raw.removeprefix("https://arxiv.org/abs/").removeprefix("http://arxiv.org/abs/")
    raw = raw.removeprefix("https://arxiv.org/pdf/").removeprefix("http://arxiv.org/pdf/")
    raw = raw.removesuffix(".pdf")
    return raw.strip()


def read_arxiv(
    user_id: str,
    arxiv_id: str,
    write_feishu: Optional[bool] = None,
    response_language: str = "zh",
) -> Dict[str, Any]:
    normalized_arxiv_id = _normalize_arxiv_id(arxiv_id)
    paper = db_ops.get_paper_by_arxiv_id(normalized_arxiv_id)
    if not paper:
        detail = arxiv_fetcher.get_paper_detail(normalized_arxiv_id)
        if not detail:
            raise ValueError(f"Could not fetch arXiv paper: {normalized_arxiv_id}")
        paper_id = db_ops.save_paper(
            arxiv_id=detail.get("arxiv_id") or normalized_arxiv_id,
            doi=detail.get("doi"),
            title=detail.get("title") or normalized_arxiv_id,
            authors=detail.get("authors") or [],
            abstract=detail.get("abstract") or "",
            categories=detail.get("categories") or [],
            source="arxiv",
            publish_date=detail.get("publish_date"),
        )
        paper = {**detail, "id": paper_id, "source": "arxiv"}

    should_write_feishu = _env_bool("PAPERFLOW_WRITE_FEISHU", default=False) if write_feishu is None else bool(write_feishu)
    language = _normalize_response_language(response_language)
    with _reading_agent_output_env_patch(), _local_only_feishu_doc_patch(not should_write_feishu):
        docs = reading_agent.create_reading_report(
            user_id=user_id,
            paper_ids=[],
            papers=[paper],
            send_to_feishu=should_write_feishu,
            request_metadata={
                "report_source_type": "desktop_arxiv",
                "report_source_key": normalized_arxiv_id,
                "report_source_name": normalized_arxiv_id,
                "report_style": _configured_report_style(),
                "response_language": language,
            },
        )
    wiki_backfilled = _backfill_docs_to_wiki(user_id, docs)
    payload = _reports_payload(docs, write_feishu_requested=should_write_feishu)
    payload["wiki_backfilled"] = wiki_backfilled
    return payload


def read_local_pdf(
    user_id: str,
    pdf_path: str,
    title: str = "",
    write_feishu: Optional[bool] = None,
    response_language: str = "zh",
) -> Dict[str, Any]:
    path = Path(str(pdf_path or "")).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists() or not path.is_file():
        raise ValueError(f"PDF not found: {path}")

    paper = {
        "title": title.strip() or path.stem,
        "authors": [],
        "abstract": "",
        "source": "local_pdf",
        "pdf_path": str(path),
        "url": str(path),
    }
    should_write_feishu = _env_bool("PAPERFLOW_WRITE_FEISHU", default=False) if write_feishu is None else bool(write_feishu)
    language = _normalize_response_language(response_language)
    with _reading_agent_output_env_patch(), _local_only_feishu_doc_patch(not should_write_feishu):
        docs = reading_agent.create_reading_report(
            user_id=user_id,
            paper_ids=[],
            papers=[paper],
            send_to_feishu=should_write_feishu,
            request_metadata={
                "report_source_type": "desktop_pdf_path",
                "report_source_key": str(path),
                "report_source_name": path.name,
                "report_style": _configured_report_style(),
                "response_language": language,
            },
        )
    wiki_backfilled = _backfill_docs_to_wiki(user_id, docs)
    payload = _reports_payload(docs, write_feishu_requested=should_write_feishu)
    payload["wiki_backfilled"] = wiki_backfilled
    return payload


def _doc_payloads(docs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "title": doc.get("title"),
            "url": doc.get("url"),
            "doc_token": doc.get("doc_token"),
            "report_path": doc.get("report_path"),
            "report_id": (
                _report_id(
                    Path(doc["report_path"])
                    if Path(doc["report_path"]).is_absolute()
                    else (PROJECT_ROOT / str(doc["report_path"]))
                )
                if doc.get("report_path")
                else ""
            ),
            "pdf_path": doc.get("pdf_path"),
            "paper": _paper_card(doc.get("paper") or {}, index + 1),
            "reused": bool(doc.get("reused")),
            "feishu_error": doc.get("feishu_error"),
        }
        for index, doc in enumerate(docs or [])
    ]


def _reports_payload(docs: Iterable[Dict[str, Any]], *, write_feishu_requested: bool) -> Dict[str, Any]:
    created_docs = _doc_payloads(docs)
    feishu_errors = [
        str(doc.get("feishu_error") or "").strip()
        for doc in created_docs
        if str(doc.get("feishu_error") or "").strip()
    ]
    feishu_warning = None
    if write_feishu_requested and feishu_errors:
        feishu_warning = (
            "飞书文档发送失败，已保留本地 Markdown。"
            "请检查 FEISHU_CLI_CMD / lark-cli 登录状态，以及 FEISHU_APP_ID、FEISHU_APP_SECRET 等飞书环境变量。"
            f"错误：{feishu_errors[0]}"
        )
    elif write_feishu_requested and created_docs and not any(doc.get("url") for doc in created_docs):
        feishu_warning = (
            "未拿到飞书文档链接，已保留本地 Markdown。"
            "请检查飞书环境变量和 lark-cli 登录状态。"
        )
    return {
        "created_docs": created_docs,
        "count": len(created_docs),
        "write_feishu_requested": write_feishu_requested,
        "feishu_warning": feishu_warning,
    }


def _report_summary_payload(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "report_id": report["report_id"],
        "title": report["title"],
        "user_id": report["user_id"],
        "paper_id": report["paper_id"],
        "arxiv_id": report["arxiv_id"],
        "saved_at": report["saved_at"],
        "updated_at": report["updated_at"],
        "report_path": report["report_path"],
        "doc_url": report["doc_url"],
        "doc_token": report["doc_token"],
        "pdf_url": report["pdf_url"],
        "abs_url": report["abs_url"],
        "report_version": report["report_version"],
        "generation_provider": report["generation_provider"],
        "generation_model": report["generation_model"],
        "snippet": report["snippet"],
    }


def list_reports(
    user_id: str = "",
    query: str = "",
    days: int = 30,
    limit: int = 80,
    exact_date: str = "",
) -> Dict[str, Any]:
    normalized_user = str(user_id or "").strip()
    normalized_query = str(query or "").strip().lower()
    normalized_date = str(exact_date or "").strip()
    max_age_days = max(1, int(days or 30))
    max_items = max(1, int(limit or 80))
    cutoff = datetime.now() - timedelta(days=max_age_days)

    reports = []
    for report in _all_report_records():
        report_dt = datetime.fromtimestamp(report["_sort_ts"])
        if normalized_date:
            report_date = str(report.get("saved_at") or report.get("updated_at") or "")[:10]
            if report_date != normalized_date:
                continue
        elif report_dt < cutoff:
            continue
        if normalized_user and report["user_id"] != normalized_user:
            continue
        haystack = " ".join(
            [
                str(report.get("title") or ""),
                str(report.get("user_id") or ""),
                str(report.get("arxiv_id") or ""),
                str(report.get("snippet") or ""),
                str(report.get("report_path") or ""),
            ]
        ).lower()
        if normalized_query and normalized_query not in haystack:
            continue
        reports.append(_report_summary_payload(report))
        if len(reports) >= max_items:
            break

    return {
        "reports": reports,
        "count": len(reports),
        "source_dirs": [_display_path(path) for path in _reading_report_dirs()],
    }


def get_report_content(report_id: str) -> Dict[str, Any]:
    normalized_id = str(report_id or "").strip()
    if not normalized_id:
        raise ValueError("report_id is required")
    for report in _all_report_records():
        if report["report_id"] != normalized_id:
            continue
        return {
            "report": {
                **_report_summary_payload(report),
                "metadata": report["metadata"],
                "markdown": report["markdown"],
            }
        }
    raise ValueError(f"Report not found: {normalized_id}")


def _report_doc_for_wiki_backfill(report: Dict[str, Any]) -> Dict[str, Any]:
    metadata = dict(report.get("metadata") or {})
    paper = {
        "id": metadata.get("paper_id"),
        "arxiv_id": metadata.get("arxiv_id") or report.get("arxiv_id"),
        "doi": metadata.get("doi"),
        "title": metadata.get("title") or report.get("title"),
        "authors": metadata.get("authors") or [],
        "abstract": metadata.get("abstract") or "",
        "publish_date": metadata.get("publish_date"),
        "pdf_path": metadata.get("pdf_path"),
        "pdf_url": metadata.get("pdf_url") or report.get("pdf_url"),
        "source": metadata.get("source") or "reading_report",
    }
    summary = str(report.get("snippet") or "").strip()
    return {
        "paper": paper,
        "title": report.get("title"),
        "url": metadata.get("doc_url") or report.get("doc_url"),
        "doc_token": metadata.get("doc_token") or report.get("doc_token"),
        "report_path": report.get("report_path"),
        "pdf_path": metadata.get("pdf_path"),
        "report_payload": {
            "paper_summary": summary,
            "one_sentence_summary": summary,
            "recommendation_label": metadata.get("recommendation_label"),
            "generation_provider": metadata.get("generation_provider"),
            "generation_model": metadata.get("generation_model"),
            "report_style": metadata.get("report_style"),
        },
    }


def refresh_wiki(user_id: str) -> Dict[str, Any]:
    normalized_user = str(user_id or "").strip()
    if not normalized_user:
        raise ValueError("user_id is required")

    daily_note_paths = [str(path) for path in _all_daily_note_paths()]
    refresh_daily_notes = getattr(reading_agent, "refresh_daily_note_files", None)
    daily_note_result = (
        refresh_daily_notes(user_id=normalized_user, daily_note_paths=daily_note_paths)
        if callable(refresh_daily_notes)
        else {"scanned": len(daily_note_paths), "refreshed": 0, "daily_notes": daily_note_paths, "errors": []}
    )
    return {
        "daily_notes": daily_note_result,
        "wiki_backfilled": 0,
        "reports_scanned": 0,
        "reports_indexed": 0,
        "stats": wiki_stats(normalized_user),
    }


def submit_and_read(
    *,
    user_id: str,
    push_id: str,
    selected_numbers: Iterable[Any],
    skipped_numbers: Iterable[Any],
    later_numbers: Iterable[Any] = (),
    generate_reports: bool = True,
    write_feishu: Optional[bool] = None,
    response_language: str = "zh",
) -> Dict[str, Any]:
    feedback = submit_gui_feedback(
        user_id=user_id,
        push_id=push_id,
        selected_numbers=selected_numbers,
        skipped_numbers=skipped_numbers,
        later_numbers=later_numbers,
    )
    reports = {"created_docs": [], "count": 0}
    if generate_reports and feedback["selected_numbers"]:
        reports = create_reading_reports(
            user_id=user_id,
            push_id=push_id,
            paper_numbers=feedback["selected_numbers"],
            write_feishu=write_feishu,
            response_language=response_language,
        )
    return {"feedback": feedback, "reports": reports}


def wiki_stats(user_id: str) -> Dict[str, Any]:
    stats = wiki_db.stats(user_id)
    nodes = _filter_wiki_nodes_for_configured_dir(wiki_db.list_nodes(user_id, limit=10000))
    if nodes is None:
        return {**stats, "wiki_dir": str(_effective_wiki_dir_for_user(user_id) or stats.get("wiki_dir") or "")}

    by_type: Dict[str, int] = {}
    latest = None
    for node in nodes:
        node_type = str(node.get("node_type") or "node")
        by_type[node_type] = by_type.get(node_type, 0) + 1
        updated_at = node.get("updated_at")
        if updated_at and (latest is None or str(updated_at) > str(latest)):
            latest = updated_at

    visible_ids = {str(node.get("node_id") or "") for node in nodes if node.get("node_id")}
    edge_count = 0
    citation_count = 0
    if visible_ids:
        conn = db_ops.get_connection()
        placeholders = ",".join("?" for _ in visible_ids)
        edge_count = int(
            conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM wiki_edges
                WHERE user_id = ?
                  AND src_id IN ({placeholders})
                  AND dst_id IN ({placeholders})
                """,
                [user_id, *visible_ids, *visible_ids],
            ).fetchone()["count"]
            or 0
        )
        citation_count = int(
            conn.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM wiki_citations
                WHERE user_id = ?
                  AND node_id IN ({placeholders})
                """,
                [user_id, *visible_ids],
            ).fetchone()["count"]
            or 0
        )
        conn.close()

    return {
        **stats,
        "nodes": len(nodes),
        "nodes_by_type": by_type,
        "edges": edge_count,
        "citations": citation_count,
        "latest_update": latest,
        "wiki_dir": str(_effective_wiki_dir_for_user(user_id) or stats.get("wiki_dir") or ""),
    }


def wiki_search(user_id: str, query: str = "", node_type: Optional[str] = None, limit: int = 12) -> Dict[str, Any]:
    nodes = wiki_db.search_nodes(user_id, query, node_type=node_type or None, limit=limit)
    filtered_nodes = _filter_wiki_nodes_for_configured_dir(nodes)
    if filtered_nodes is not None:
        nodes = filtered_nodes
    nodes = sorted(nodes, key=_wiki_display_priority)
    return {
        "nodes": [
            {
                "node_id": node.get("node_id"),
                "node_type": node.get("node_type"),
                "title": node.get("title"),
                "body": str(node.get("body") or "")[:800],
                "keywords": node.get("keywords"),
                "file_path": node.get("file_path"),
                "metadata": _compact_wiki_metadata(node.get("metadata") or {}),
                "score": node.get("score"),
                "updated_at": node.get("updated_at"),
            }
            for node in nodes
        ]
    }


def _configured_wiki_root() -> Optional[Path]:
    raw = _env_text("PAPERFLOW_WIKI_DIR", "")
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _effective_wiki_dir_for_user(user_id: str) -> Optional[Path]:
    root = _configured_wiki_root()
    if root is None:
        return None
    label = role_utils.storage_label_for_user_id(user_id, project_root=PROJECT_ROOT)
    if root.name == label:
        return root
    scoped = root / label
    return scoped if scoped.exists() else root


def _wiki_node_file_exists(root: Path, relative_path: str) -> bool:
    if not relative_path:
        return False
    relative = Path(relative_path)
    if (root / relative).exists():
        return True
    if root.name and relative.parts and relative.parts[0] == root.name:
        return (root / Path(*relative.parts[1:])).exists()
    return False


def _filter_wiki_nodes_for_configured_dir(nodes: Iterable[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    root = _configured_wiki_root()
    if root is None:
        return None
    filtered = []
    for node in nodes or []:
        relative_path = str(node.get("file_path") or "").strip()
        if _wiki_node_file_exists(root, relative_path):
            filtered.append(node)
    return filtered


def _visible_wiki_node_ids(user_id: str) -> Optional[Set[str]]:
    nodes = _filter_wiki_nodes_for_configured_dir(wiki_db.list_nodes(user_id, limit=10000))
    if nodes is None:
        return None
    return {str(node.get("node_id") or "") for node in nodes if str(node.get("node_id") or "")}


def _wiki_node_is_visible(node: Optional[Dict[str, Any]]) -> bool:
    if not node:
        return False
    filtered = _filter_wiki_nodes_for_configured_dir([node])
    return filtered is None or bool(filtered)


def _wiki_node_payload(node: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "node_id": node.get("node_id"),
        "node_type": node.get("node_type"),
        "title": node.get("title"),
        "body": str(node.get("body") or "")[:800],
        "keywords": node.get("keywords"),
        "file_path": node.get("file_path"),
        "metadata": _compact_wiki_metadata(node.get("metadata") or {}),
        "score": node.get("score"),
        "updated_at": node.get("updated_at"),
    }


def _compact_wiki_metadata(value: Any, *, depth: int = 0) -> Any:
    if depth > 3:
        return None
    if isinstance(value, dict):
        compact: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if re.search(r"(embedding|vector|long_term_vector|short_term_vector)", key_text, re.I):
                continue
            cleaned = _compact_wiki_metadata(item, depth=depth + 1)
            if cleaned is not None:
                compact[key_text] = cleaned
        return compact
    if isinstance(value, list):
        if len(value) > 24 and all(isinstance(item, (int, float)) for item in value):
            return None
        return [_compact_wiki_metadata(item, depth=depth + 1) for item in value[:24]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _wiki_display_priority(node: Dict[str, Any]) -> Tuple[int, float]:
    node_type = str(node.get("node_type") or "")
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    section_kind = str(metadata.get("section_kind") or "").lower()
    type_rank = {
        "paper": 0,
        "topic": 1,
        "trajectory": 2,
        "section": 3,
    }.get(node_type, 4)
    if node_type == "section":
        if "q6" in section_kind or "summary" in section_kind or "tldr" in section_kind:
            type_rank = 1
        elif "abstract" in section_kind:
            type_rank = 5
    try:
        score = float(node.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    return type_rank, -score


def _wiki_graph_node_visible(node: Dict[str, Any]) -> bool:
    return str(node.get("node_type") or "").strip().lower() != "section"


def _wiki_graph_paper_is_reading_report(node: Dict[str, Any]) -> bool:
    if str(node.get("node_type") or "").strip().lower() != "paper":
        return False
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    return str(node.get("source_type") or "") == "reading_report" or bool(metadata.get("report_path"))


def _wiki_keyword_tokens(value: Any) -> Set[str]:
    text = str(value or "").lower()
    return {token for token in re.split(r"[\s,;，；/]+", text) if token}


def _wiki_topic_tokens(node: Dict[str, Any]) -> Set[str]:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    tokens = _wiki_keyword_tokens(node.get("keywords"))
    tokens.update(_wiki_keyword_tokens(metadata.get("canonical_name")))
    tokens.update(_wiki_keyword_tokens(node.get("title")))
    return tokens


def _daily_note_roots() -> List[Path]:
    roots: List[Path] = []
    for env_name in ("PAPERFLOW_READING_REPORTS_DIR", "PAPERFLOW_PDF_DIR"):
        path = Path(_configured_path(env_name, "data/exports")).expanduser()
        roots.append(path if path.is_absolute() else PROJECT_ROOT / path)
    unique: List[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def _daily_note_sort_key(path: Path) -> Tuple[int, int, float]:
    match = re.fullmatch(r"Daily Note - ([A-Za-z]+) (20\d{2})\.md", path.name)
    month_order = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sept": 9,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    if match:
        month, year = match.groups()
        return int(year), month_order.get(month.lower(), 0), path.stat().st_mtime
    return 0, 0, path.stat().st_mtime


def _all_daily_note_paths() -> List[Path]:
    candidates: List[Path] = []
    for root in _daily_note_roots():
        if root.name.startswith("Daily Note 20"):
            candidates.extend(root.glob("Daily Note - * 20[0-9][0-9].md"))
        candidates.extend(root.glob("Daily Note 20[0-9][0-9]/Daily Note - * 20[0-9][0-9].md"))
    existing = [path for path in candidates if path.exists()]
    return sorted(set(existing), key=_daily_note_sort_key)


def _daily_note_paths_for_graph(scope: str = "latest", month: str = "") -> List[Path]:
    paths = _all_daily_note_paths()
    if not paths:
        return []
    normalized_scope = str(scope or "latest").strip().lower()
    normalized_month = str(month or "").strip()
    if normalized_scope == "all":
        return paths
    if normalized_scope == "month" and normalized_month:
        year, _, month_number = normalized_month.partition("-")
        month_labels = {
            "01": "Jan",
            "02": "Feb",
            "03": "Mar",
            "04": "Apr",
            "05": "May",
            "06": "Jun",
            "07": "Jul",
            "08": "Aug",
            "09": "Sept",
            "10": "Oct",
            "11": "Nov",
            "12": "Dec",
        }
        expected = f"Daily Note - {month_labels.get(month_number, '')} {year}.md"
        return [path for path in paths if path.name == expected]
    return [paths[-1]]


def _normalize_title_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _extract_daily_note_summary(lines: List[str]) -> str:
    text = "\n".join(lines)
    match = re.search(r"-\s+\*\*(.*?)\*\*", text, flags=re.DOTALL)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    paragraphs = [
        re.sub(r"\s+", " ", line.strip("- ").strip()).strip()
        for line in lines
        if line.strip() and not line.strip().startswith("[[") and "paperflow:" not in line
    ]
    return "\n".join(paragraphs).strip()


def _parse_daily_note_entries(path: Path) -> List[Dict[str, str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: List[Dict[str, str]] = []
    current_topic = "未分类"
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if line.startswith("# ") and not line.startswith("## "):
            current_topic = line[2:].strip() or "未分类"
            index += 1
            continue
        if line.startswith("## "):
            title = line[3:].strip()
            body_lines: List[str] = []
            index += 1
            while index < len(lines) and not lines[index].startswith("## ") and not lines[index].startswith("# "):
                body_lines.append(lines[index])
                index += 1
            if title == "PaperFlow Summary":
                continue
            entries.append(
                {
                    "topic": current_topic,
                    "title": title,
                    "summary": _extract_daily_note_summary(body_lines),
                    "body": "\n".join(body_lines).strip(),
                }
            )
            continue
        index += 1
    return [entry for entry in entries if entry.get("title")]


def _daily_note_entry_report_path(daily_note: Path, body: str) -> Optional[Path]:
    match = re.search(r"\[\[([^|\]]*Deep Reading - [^|\]]+)(?:\|[^\]]*)?\]\]", str(body or ""))
    if not match:
        return None
    link = match.group(1).strip()
    if not link:
        return None
    candidate = (daily_note.parent / link).with_suffix(".md")
    try:
        return candidate.resolve()
    except OSError:
        return candidate


def _daily_note_entry_pdf_url(body: str) -> str:
    match = re.search(r"https://arxiv\.org/pdf/[^\s)\]]+", str(body or ""))
    return match.group(0).strip() if match else ""


def _daily_note_reading_entries(scope: str = "latest", month: str = "", query: str = "", limit: int = 12) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    normalized_query = str(query or "").strip().lower()
    for daily_note in _daily_note_paths_for_graph(scope=scope, month=month):
        for entry in _parse_daily_note_entries(daily_note):
            report_path = _daily_note_entry_report_path(daily_note, entry.get("body") or "")
            if not report_path or not report_path.exists():
                continue
            haystack = " ".join(
                [
                    str(entry.get("title") or ""),
                    str(entry.get("topic") or ""),
                    str(entry.get("summary") or ""),
                    str(entry.get("body") or ""),
                ]
            ).lower()
            if normalized_query and normalized_query not in haystack:
                query_tokens = _local_paper_query_tokens(normalized_query)
                if query_tokens and not any(token in haystack for token in query_tokens):
                    continue
                if not query_tokens:
                    continue
            item = dict(entry)
            item.update(
                {
                    "daily_note": str(daily_note),
                    "report_path": str(report_path),
                    "pdf_url": _daily_note_entry_pdf_url(entry.get("body") or ""),
                }
            )
            entries.append(item)
            if len(entries) >= max(1, int(limit or 12)):
                return entries
    return entries


def _daily_note_reading_node(entry: Dict[str, Any]) -> Dict[str, Any]:
    title = str(entry.get("title") or "").strip()
    report_path = Path(str(entry.get("report_path") or ""))
    report_content = ""
    if report_path.exists():
        try:
            report_content = report_path.read_text(encoding="utf-8")
        except OSError:
            report_content = ""
    summary = str(entry.get("summary") or "").strip()
    body = "\n\n".join(
        part
        for part in [
            f"Daily Note topic: {entry.get('topic') or '未分类'}",
            f"Daily Note summary: {summary}" if summary else "",
            "Deep Reading report:",
            report_content or str(entry.get("body") or ""),
        ]
        if part
    )
    key = str(entry.get("report_path") or title)
    return {
        "node_id": f"daily-reading:{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}",
        "node_type": "paper",
        "title": title,
        "body": body,
        "keywords": " ".join([str(entry.get("topic") or ""), title, "daily note deep reading"]).strip(),
        "file_path": str(entry.get("report_path") or ""),
        "metadata": {
            "source": "daily_note_deep_reading",
            "daily_note": entry.get("daily_note"),
            "daily_note_topic": entry.get("topic"),
            "report_path": entry.get("report_path"),
            "pdf_url": entry.get("pdf_url") or "",
        },
        "source_type": "reading_report",
        "source_ref": str(entry.get("report_path") or ""),
        "score": 1.0,
        "updated_at": None,
    }


def daily_note_mentions(user_id: str, query: str = "", limit: int = 8) -> Dict[str, Any]:
    del user_id
    entries = _daily_note_reading_entries(scope="all", query=query, limit=limit)
    nodes = []
    for entry in entries:
        node = _daily_note_reading_node(entry)
        nodes.append(
            {
                "node_id": node["node_id"],
                "node_type": "paper",
                "title": node["title"],
                "body": str(entry.get("summary") or "")[:500],
                "score": 1.0,
                "metadata": node["metadata"],
            }
        )
    return {"nodes": nodes, "source": "daily_note_deep_reading"}


def _parse_daily_note_topic_summaries(path: Path) -> Dict[str, Dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    summaries: Dict[str, Dict[str, Any]] = {}
    current_topic = ""
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if line.startswith("# ") and not line.startswith("## "):
            current_topic = line[2:].strip()
            index += 1
            continue
        if current_topic and line == "## PaperFlow Summary":
            block: List[str] = []
            index += 1
            while index < len(lines) and not lines[index].startswith("## ") and not lines[index].startswith("# "):
                block.append(lines[index].strip())
                index += 1
            methods: List[str] = []
            frontier = ""
            concept = current_topic
            for item in block:
                if item.startswith("- 概念："):
                    concept = item.split("：", 1)[1].strip() or concept
                elif item.startswith("- 方法："):
                    raw_methods = item.split("：", 1)[1].strip()
                    if raw_methods and raw_methods != "待从后续精读中沉淀":
                        methods = [part.strip() for part in re.split(r"[,，、]+", raw_methods) if part.strip()]
                elif item.startswith("- 画像/前沿："):
                    frontier = item.split("：", 1)[1].strip()
            summaries[current_topic] = {
                "concept": concept,
                "methods": methods,
                "frontier": frontier,
            }
            continue
        index += 1
    return summaries


def _daily_note_graph(user_id: str, limit: int, *, scope: str = "latest", month: str = "") -> Optional[Dict[str, Any]]:
    daily_notes = _daily_note_paths_for_graph(scope, month)
    if not daily_notes:
        return None
    entries: List[Dict[str, str]] = []
    topic_summaries: Dict[str, Dict[str, Any]] = {}
    for daily_note in daily_notes:
        topic_summaries.update(_parse_daily_note_topic_summaries(daily_note))
        for entry in _parse_daily_note_entries(daily_note):
            entry["daily_note"] = str(daily_note)
            entries.append(entry)
    if not entries:
        return None

    wiki_nodes = _filter_wiki_nodes_for_configured_dir(wiki_db.list_nodes(user_id, limit=10000))
    if wiki_nodes is None:
        wiki_nodes = wiki_db.list_nodes(user_id, limit=10000)
    paper_nodes = [
        node
        for node in wiki_nodes
        if str(node.get("node_type") or "").lower() == "paper"
        and _wiki_graph_paper_is_reading_report(node)
    ]
    by_title = {_normalize_title_key(node.get("title")): node for node in paper_nodes}

    graph_nodes: List[Dict[str, Any]] = []
    graph_edges: List[Dict[str, Any]] = []
    topic_ids: Dict[str, str] = {}
    topic_method_ids: Dict[str, Set[str]] = {}
    seen_nodes: Set[str] = set()

    def add_node(node: Dict[str, Any]) -> None:
        node_id = str(node.get("node_id") or "").strip()
        if node_id and node_id not in seen_nodes:
            seen_nodes.add(node_id)
            graph_nodes.append(node)

    for entry in entries[: max(1, limit)]:
        topic = entry["topic"]
        topic_id = topic_ids.get(topic)
        if topic_id is None:
            topic_id = f"daily-topic:{role_utils.slug(topic, max_len=72)}"
            topic_ids[topic] = topic_id
            summary_info = topic_summaries.get(topic) or {}
            add_node(
                {
                    "node_id": topic_id,
                    "node_type": "topic",
                    "title": topic,
                    "body": f"## 概念\n{summary_info.get('concept') or topic}\n\n## 来源\nDaily Note topic from {len(daily_notes)} note(s).",
                    "keywords": topic,
                    "file_path": entry.get("daily_note") or "",
                    "metadata": {"source": "daily_note", "daily_notes": [str(path) for path in daily_notes]},
                    "score": 1.0,
                    "updated_at": None,
                }
            )
            method_ids: Set[str] = set()
            for method in (summary_info.get("methods") or [])[:8]:
                method_id = f"daily-method:{role_utils.slug(method, max_len=96)}"
                method_ids.add(method_id)
                add_node(
                    {
                        "node_id": method_id,
                        "node_type": "method",
                        "title": method,
                        "body": f"Daily Note method shared by one or more topics.",
                        "keywords": method,
                        "file_path": entry.get("daily_note") or "",
                        "metadata": {"source": "daily_note"},
                        "score": 0.85,
                        "updated_at": None,
                    }
                )
                graph_edges.append(
                    {
                        "src_id": topic_id,
                        "dst_id": method_id,
                        "relation": "has_method",
                        "weight": 0.8,
                        "metadata": {"source": "daily_note"},
                    }
                )
            topic_method_ids[topic] = method_ids

        matched = by_title.get(_normalize_title_key(entry["title"]))
        if matched:
            paper_node = _wiki_node_payload(matched)
            paper_node["body"] = entry.get("summary") or paper_node.get("body") or ""
            metadata = dict(paper_node.get("metadata") or {})
            metadata["daily_note_topic"] = topic
            metadata["daily_note"] = entry.get("daily_note")
            paper_node["metadata"] = metadata
        else:
            paper_node = {
                "node_id": f"daily-paper:{hashlib.sha1(entry['title'].encode('utf-8')).hexdigest()[:16]}",
                "node_type": "paper",
                "title": entry["title"],
                "body": entry.get("summary") or entry.get("body") or "",
                "keywords": topic,
                "file_path": entry.get("daily_note") or "",
                "metadata": {"source": "daily_note", "daily_note_topic": topic, "daily_note": entry.get("daily_note")},
                "score": 1.0,
                "updated_at": None,
            }
        add_node(paper_node)
        graph_edges.append(
            {
                "src_id": topic_id,
                "dst_id": paper_node["node_id"],
                "relation": "daily_note_topic",
                "weight": 1.0,
                "metadata": {"source": "daily_note", "daily_note": entry.get("daily_note")},
            }
        )
        for method_id in topic_method_ids.get(topic, set()):
            graph_edges.append(
                {
                    "src_id": method_id,
                    "dst_id": paper_node["node_id"],
                    "relation": "method_evidence",
                    "weight": 0.45,
                    "metadata": {"source": "daily_note"},
                }
            )

    return {
        "nodes": graph_nodes,
        "edges": graph_edges,
        "source": "daily_note",
        "query": "",
        "daily_notes": [str(path) for path in daily_notes],
        "daily_scope": scope,
        "daily_month": month,
    }


def wiki_graph(user_id: str, query: str = "", limit: int = 24, daily_scope: str = "latest", daily_month: str = "") -> Dict[str, Any]:
    """Return user-scoped wiki nodes and edges for the desktop graph view."""
    safe_limit = max(4, min(160, int(limit or 24)))
    query = str(query or "").strip()
    user_node_id = f"user:{user_id}"
    if not query and str(daily_scope or "").strip().lower() != "wiki_db":
        daily_graph = _daily_note_graph(user_id, safe_limit, scope=daily_scope, month=daily_month)
        if daily_graph and daily_graph.get("nodes"):
            return daily_graph

    def row_to_node(row: Any) -> Dict[str, Any]:
        node = dict(row)
        try:
            node["metadata"] = json.loads(node.pop("metadata_json", None) or "{}")
        except (TypeError, json.JSONDecodeError):
            node["metadata"] = {}
        return node

    conn = db_ops.get_connection()

    def remember_nodes(nodes: Iterable[Dict[str, Any]], node_by_id: Dict[str, Dict[str, Any]]) -> None:
        for node in nodes or []:
            node_id = str(node.get("node_id") or "").strip()
            if node_id:
                node_by_id.setdefault(node_id, node)

    def fetch_nodes_by_ids(candidate_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        cleaned_ids = []
        for node_id in candidate_ids:
            normalized = str(node_id or "").strip()
            if normalized and normalized != user_node_id and normalized not in cleaned_ids:
                cleaned_ids.append(normalized)
        if not cleaned_ids:
            return {}
        placeholders = ",".join("?" for _ in cleaned_ids)
        rows = conn.execute(
            f"""
            SELECT *
            FROM wiki_nodes
            WHERE user_id = ?
              AND node_id IN ({placeholders})
            """,
            [user_id, *cleaned_ids],
        ).fetchall()
        node_by_id: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            node = row_to_node(row)
            node_id = str(node.get("node_id") or "").strip()
            if node_id:
                node_by_id[node_id] = node
        return node_by_id

    def fetch_top_edges() -> List[Any]:
        return conn.execute(
            """
            SELECT src_id, dst_id, relation, weight, metadata_json, created_at
            FROM wiki_edges
            WHERE user_id = ?
            ORDER BY weight DESC, created_at DESC
            LIMIT ?
            """,
            (user_id, safe_limit * 4),
        ).fetchall()

    def fetch_edges_for_ids(candidate_ids: List[str]) -> List[Any]:
        if not candidate_ids:
            return []
        candidate_placeholders = ",".join("?" for _ in candidate_ids)
        return conn.execute(
            f"""
            SELECT src_id, dst_id, relation, weight, metadata_json, created_at
            FROM wiki_edges
            WHERE user_id = ?
              AND (
                (src_id IN ({candidate_placeholders}) AND dst_id IN ({candidate_placeholders}))
                OR (src_id = ? AND dst_id IN ({candidate_placeholders}))
              )
            ORDER BY weight DESC, created_at DESC
            LIMIT ?
            """,
            [user_id, *candidate_ids, *candidate_ids, user_node_id, *candidate_ids, safe_limit * 4],
        ).fetchall()

    node_by_id: Dict[str, Dict[str, Any]] = {}
    synthetic_edges: List[Dict[str, Any]] = []
    if query:
        remember_nodes(wiki_db.search_nodes(user_id, query, limit=safe_limit), node_by_id)
        rows = fetch_edges_for_ids(list(node_by_id))
        edge_node_ids: List[str] = []
        for row in rows:
            for endpoint in (str(row["src_id"] or ""), str(row["dst_id"] or "")):
                if endpoint and endpoint != user_node_id and endpoint not in node_by_id and endpoint not in edge_node_ids:
                    edge_node_ids.append(endpoint)
        remaining_slots = max(0, safe_limit - len(node_by_id))
        node_by_id.update(fetch_nodes_by_ids(edge_node_ids[:remaining_slots]))
    else:
        rows = []
        all_nodes = wiki_db.list_nodes(user_id, limit=10000)
        filtered_all_nodes = _filter_wiki_nodes_for_configured_dir(all_nodes)
        if filtered_all_nodes is not None:
            all_nodes = filtered_all_nodes
        reading_papers = [node for node in all_nodes if _wiki_graph_paper_is_reading_report(node)]
        topic_nodes = [
            node
            for node in all_nodes
            if str(node.get("node_type") or "").strip().lower() == "topic"
        ]
        paper_tokens = {
            str(paper.get("node_id") or ""): _wiki_keyword_tokens(paper.get("keywords"))
            for paper in reading_papers
        }
        matched_topics: Dict[str, Dict[str, Any]] = {}
        for topic in topic_nodes:
            topic_id = str(topic.get("node_id") or "")
            tokens = _wiki_topic_tokens(topic)
            for paper_id, tokens_for_paper in paper_tokens.items():
                if tokens and tokens_for_paper and tokens.intersection(tokens_for_paper):
                    matched_topics[topic_id] = topic
                    synthetic_edges.append(
                        {
                            "src_id": paper_id,
                            "dst_id": topic_id,
                            "relation": "belongs_to",
                            "weight": 0.75,
                            "metadata": {"source": "keyword_match"},
                        }
                    )
        ordered_nodes = reading_papers + list(matched_topics.values())
        for node in ordered_nodes[:safe_limit]:
            node_id = str(node.get("node_id") or "").strip()
            if node_id:
                node_by_id[node_id] = node
        rows = fetch_edges_for_ids(list(node_by_id))

    rows = rows or fetch_edges_for_ids(list(node_by_id))
    conn.close()

    filtered_nodes = _filter_wiki_nodes_for_configured_dir(node_by_id.values())
    if filtered_nodes is not None:
        node_by_id = {
            str(node.get("node_id") or ""): node
            for node in filtered_nodes
            if str(node.get("node_id") or "")
        }
    node_by_id = {
        node_id: node
        for node_id, node in node_by_id.items()
        if _wiki_graph_node_visible(node)
    }

    if not node_by_id:
        return {"nodes": [], "edges": [], "source": "wiki_db", "query": query}

    edges = []
    include_user_node = False
    for row in rows:
        src_id = str(row["src_id"] or "")
        dst_id = str(row["dst_id"] or "")
        if src_id == user_node_id or dst_id == user_node_id:
            include_user_node = True
        if src_id not in node_by_id and src_id != user_node_id:
            continue
        if dst_id not in node_by_id and dst_id != user_node_id:
            continue
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        edges.append(
            {
                "src_id": src_id,
                "dst_id": dst_id,
                "relation": row["relation"],
                "weight": float(row["weight"] or 1.0),
                "metadata": _compact_wiki_metadata(metadata),
            }
        )
    edges.extend(
        edge
        for edge in synthetic_edges
        if edge["src_id"] in node_by_id and edge["dst_id"] in node_by_id
    )

    degree: Dict[str, float] = {}
    for edge in edges:
        weight = float(edge.get("weight") or 1.0)
        degree[edge["src_id"]] = degree.get(edge["src_id"], 0.0) + weight
        degree[edge["dst_id"]] = degree.get(edge["dst_id"], 0.0) + weight
    ordered_node_ids = sorted(node_by_id, key=lambda node_id: degree.get(node_id, 0.0), reverse=True)
    graph_nodes = [_wiki_node_payload(node_by_id[node_id]) for node_id in ordered_node_ids]
    if include_user_node:
        graph_nodes.insert(
            0,
            {
                "node_id": user_node_id,
                "node_type": "trajectory",
                "title": "当前用户画像",
                "body": "用户反馈、精读和跳过记录形成的本地研究状态。",
                "keywords": user_id,
                "file_path": "",
                "metadata": {"user_id": user_id},
                "score": 1.0,
                "updated_at": None,
            },
        )
    return {"nodes": graph_nodes, "edges": edges, "source": "wiki_db", "query": query}


def update_wiki_node(user_id: str, node_id: str, title: str = "", body: str = "") -> Dict[str, Any]:
    cleaned_node_id = str(node_id or "").strip()
    if not user_id or not cleaned_node_id:
        raise ValueError("user_id and node_id are required")
    existing = wiki_db.get_node(user_id, cleaned_node_id)
    if not existing:
        raise ValueError(f"Wiki node not found: {cleaned_node_id}")
    updated = wiki_db.upsert_node(
        user_id=user_id,
        node_id=cleaned_node_id,
        node_type=str(existing.get("node_type") or "topic"),
        title=str(title or existing.get("title") or cleaned_node_id),
        body=str(body or ""),
        metadata=existing.get("metadata") or {},
        keywords=str(existing.get("keywords") or ""),
        source_type=existing.get("source_type"),
        source_ref=existing.get("source_ref"),
        file_path=existing.get("file_path"),
        write_mirror=True,
    )
    return {"node": _wiki_node_payload(updated)}


_MENTION_LINK_RE = re.compile(r"@\[([^\]]{1,180})\]\(([^)\s]{1,240})\)")
_MENTION_TOKEN_RE = re.compile(r"@([^\s@\]\)（），。；;、,]{1,120})")

_LOCAL_WIKI_TERMS = (
    "@",
    "wiki",
    "知识库",
    "本地",
    "精读",
    "报告",
    "论文",
    "paper",
    "paperflow",
    "这篇",
    "这两篇",
    "两篇",
    "对比",
    "比较",
    "差异",
    "总结",
    "趋势",
    "动态",
    "热点",
    "主题",
    "最近",
    "一周",
    "今天",
    "引用",
    "证据",
    "根据",
    "我的",
    "方向",
    "画像",
    "推荐",
    "候选",
    "条目",
    "节点",
)

_TREND_QUESTION_TERMS = (
    "趋势",
    "动态",
    "方向",
    "热点",
    "主题",
    "总结一下我的论文",
    "总结我的论文",
    "阅读趋势",
    "论文趋势",
    "research trend",
    "paper trend",
)

_RECENT_PAPER_QUERY_TERMS = (
    "论文",
    "文献",
    "paper",
    "papers",
    "arxiv",
)

_RECENT_CONTEXT_QUERY_TERMS = (
    "最近",
    "一周",
    "7天",
    "七天",
    "今天",
    "今日",
    "推送",
    "推荐",
    "候选",
    "相关",
    "趋势",
    "动态",
    "方向",
    "热点",
    "主题",
    "rag",
)

_COMPARE_QUERY_TERMS = (
    "对比",
    "比较",
    "差异",
    "不同",
    "这两篇",
    "两篇",
)

_LOCAL_PAPER_STOP_TOKENS = {
    "paper",
    "papers",
    "arxiv",
    "research",
    "trend",
    "trends",
    "related",
    "recent",
    "week",
    "summary",
    "summarize",
    "compare",
    "method",
    "methods",
}

_DIRECT_STARTERS = (
    "什么是",
    "解释一下",
    "解释下",
    "介绍一下",
    "介绍下",
    "如何理解",
    "define ",
    "what is ",
    "explain ",
)

DIRECT_ANSWER_PROMPT_ZH = """You are PaperFlow's desktop research assistant.

The user asked a general question that does not require local Wiki retrieval.
Answer directly and concisely in Chinese by default. Do not add fake citations
or [N] markers. If the question asks for local papers, reports, user profile,
or Wiki evidence, say that local Wiki retrieval is required instead."""

DIRECT_ANSWER_PROMPT_EN = """You are PaperFlow's desktop research assistant.

The user asked a general question that does not require local Wiki retrieval.
Answer directly and concisely in English. Do not add fake citations or [N]
markers. If the question asks for local papers, reports, user profile, or Wiki
evidence, say that local Wiki retrieval is required instead."""

DIRECT_ANSWER_PROMPT = DIRECT_ANSWER_PROMPT_ZH


def _direct_answer_prompt(response_language: str) -> str:
    return DIRECT_ANSWER_PROMPT_EN if _normalize_response_language(response_language) == "en" else DIRECT_ANSWER_PROMPT_ZH


def _direct_answer_max_tokens() -> int:
    return _env_int("PAPERFLOW_DIRECT_ANSWER_MAX_TOKENS", 1400, min_value=512, max_value=4096)


def _extract_question_mentions(question: str) -> List[Dict[str, str]]:
    text = str(question or "")
    mentions: List[Dict[str, str]] = []
    for match in _MENTION_LINK_RE.finditer(text):
        mentions.append({"title": match.group(1).strip(), "node_id": match.group(2).strip()})
    stripped = _MENTION_LINK_RE.sub(" ", text)
    for match in _MENTION_TOKEN_RE.finditer(stripped):
        token = match.group(1).strip()
        if token:
            mentions.append({"title": token, "node_id": ""})
    return mentions


def _normalize_requested_mentions(mentions: Any) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    if not isinstance(mentions, list):
        return normalized
    for item in mentions:
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("label") or "").strip()
            node_id = str(item.get("node_id") or item.get("id") or "").strip()
            if title or node_id:
                normalized.append({"title": title, "node_id": node_id})
        else:
            token = str(item or "").strip()
            if token:
                normalized.append({"title": token, "node_id": ""})
    return normalized


def _resolve_wiki_mentions(
    user_id: str,
    question: str,
    mentions: Any = None,
    *,
    limit: int = 6,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, str]]]:
    requested = [*_normalize_requested_mentions(mentions), *_extract_question_mentions(question)]
    resolved_nodes: List[Dict[str, Any]] = []
    resolved_payloads: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, str]] = []
    seen_requests: Set[Tuple[str, str]] = set()
    seen_nodes: Set[str] = set()

    for request in requested[: max(1, int(limit))]:
        title = str(request.get("title") or "").strip()
        node_id = str(request.get("node_id") or "").strip()
        request_key = (title.lower(), node_id.lower())
        if request_key in seen_requests:
            continue
        seen_requests.add(request_key)

        node: Optional[Dict[str, Any]] = None
        if node_id:
            db_node = wiki_db.get_node(user_id, node_id)
            if _wiki_node_is_visible(db_node):
                node = db_node
        if node is None:
            daily_node = None
            for entry in _daily_note_reading_entries(scope="all", query=title or node_id, limit=8):
                candidate = _daily_note_reading_node(entry)
                if node_id and str(candidate.get("node_id") or "") == node_id:
                    daily_node = candidate
                    break
                if title and str(candidate.get("title") or "").strip().lower() == title.lower():
                    daily_node = candidate
                    break
                if daily_node is None:
                    daily_node = candidate
            if daily_node is not None:
                node = daily_node
        if node is None:
            query = title or node_id
            if query:
                hits = wiki_db.search_nodes(user_id, query, limit=5)
                filtered_hits = _filter_wiki_nodes_for_configured_dir(hits)
                if filtered_hits is not None:
                    hits = filtered_hits
                lowered_title = title.lower()
                lowered_node_id = node_id.lower()
                exact = next(
                    (
                        hit
                        for hit in hits
                        if str(hit.get("node_id") or "").lower() == lowered_node_id
                        or str(hit.get("title") or "").lower() == lowered_title
                    ),
                    None,
                )
                node = exact or (hits[0] if hits else None)

        if not node:
            unresolved.append({"title": title, "node_id": node_id})
            continue

        resolved_node_id = str(node.get("node_id") or "").strip()
        if not resolved_node_id or resolved_node_id in seen_nodes:
            continue
        seen_nodes.add(resolved_node_id)
        resolved_nodes.append(node)
        payload = _wiki_node_payload(node)
        payload["mention"] = title or node.get("title") or resolved_node_id
        payload["selected"] = True
        resolved_payloads.append(payload)

    return resolved_nodes, resolved_payloads, unresolved


def _question_route(question: str, scope: str, resolved_mentions: List[Dict[str, Any]]) -> Tuple[str, str]:
    normalized_scope = str(scope or "all").strip().lower()
    normalized_question = str(question or "").strip().lower()
    if resolved_mentions or "@" in normalized_question:
        return "wiki", "explicit_mention"
    if normalized_scope in {"recent", "profile"}:
        return "wiki", f"scope_{normalized_scope}"
    if any(term in normalized_question for term in _LOCAL_WIKI_TERMS):
        return "wiki", "local_research_context"
    if normalized_question.startswith(_DIRECT_STARTERS):
        return "direct", "general_question"
    return "direct", "no_local_context_signal"


def _is_trend_question(question: str) -> bool:
    normalized = str(question or "").strip().lower()
    if not normalized:
        return False
    return any(term in normalized for term in _TREND_QUESTION_TERMS)


def _should_pin_recent_papers(question: str, scope: str) -> bool:
    normalized = str(question or "").strip().lower()
    normalized_scope = str(scope or "").strip().lower()
    if not normalized:
        return False
    if normalized_scope == "recent" or _is_trend_question(normalized):
        return True
    has_paper_signal = any(term in normalized for term in _RECENT_PAPER_QUERY_TERMS)
    has_recent_signal = any(term in normalized for term in _RECENT_CONTEXT_QUERY_TERMS)
    return has_paper_signal and has_recent_signal


def _comparison_needs_mentions(question: str, resolved_nodes: List[Dict[str, Any]]) -> bool:
    normalized = str(question or "").strip().lower()
    if len(resolved_nodes or []) >= 2:
        return False
    has_deictic_pair = any(term in normalized for term in ("这两篇", "这两个", "上述两篇", "上面两篇"))
    return has_deictic_pair and any(term in normalized for term in _COMPARE_QUERY_TERMS)


def _local_paper_query_tokens(question: str) -> List[str]:
    tokens: List[str] = []
    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_+-]{1,}", str(question or "").lower()):
        if token not in _LOCAL_PAPER_STOP_TOKENS and token not in tokens:
            tokens.append(token)
    return tokens[:8]


def _compact_list(value: Any, limit: int = 6) -> List[str]:
    if isinstance(value, list):
        items = value
    else:
        parsed = _load_json(value, None)
        if isinstance(parsed, list):
            items = parsed
        else:
            items = re.split(r"[,;，、]\s*", str(value or ""))
    if not isinstance(items, list):
        return []
    return [str(item).strip() for item in items[: max(1, int(limit))] if str(item or "").strip()]


def _paper_query_haystack(paper: Dict[str, Any]) -> str:
    raw_metadata = paper.get("metadata") or {}
    metadata = raw_metadata if isinstance(raw_metadata, dict) else _load_json(raw_metadata, {})
    if not isinstance(metadata, dict):
        metadata = {}
    pieces = [
        paper.get("title"),
        paper.get("abstract"),
        paper.get("summary"),
        paper.get("keywords"),
        paper.get("category"),
        paper.get("source"),
        paper.get("subjects"),
        paper.get("categories"),
        metadata.get("category"),
        metadata.get("keywords"),
        metadata.get("subjects"),
        metadata.get("categories"),
    ]
    return " ".join(
        " ".join(_compact_list(piece, limit=12)) if isinstance(piece, (list, tuple)) else str(piece or "")
        for piece in pieces
    ).lower()


def _recent_paper_context_nodes(user_id: str, question: str = "", limit: int = 8) -> List[Dict[str, Any]]:
    try:
        papers = db_ops.get_recent_pushes(user_id, limit=max(12, min(50, int(limit or 8) * 4))) or []
    except Exception:
        papers = []
    if not papers:
        try:
            latest = db_ops.get_latest_push(user_id) or {}
        except Exception:
            latest = {}
        papers = list(latest.get("papers") or [])[: max(12, min(50, int(limit or 8) * 4))]
    query_tokens = _local_paper_query_tokens(question)
    if query_tokens:
        matched = [paper for paper in papers if isinstance(paper, dict) and any(token in _paper_query_haystack(paper) for token in query_tokens)]
        if matched:
            papers = matched

    nodes: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for index, paper in enumerate(papers, start=1):
        if not isinstance(paper, dict):
            continue
        title = str(paper.get("title") or "").strip()
        if not title:
            continue
        arxiv_id = _paper_arxiv_id(paper)
        key = arxiv_id or str(paper.get("doi") or paper.get("id") or title).strip()
        node_id = f"paper:{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}"
        if node_id in seen:
            continue
        seen.add(node_id)
        authors = _compact_list(paper.get("authors"), limit=6)
        subjects = _compact_list(paper.get("subjects") or paper.get("categories"), limit=8)
        abstract = str(paper.get("abstract") or paper.get("summary") or "").strip()
        raw_metadata = paper.get("metadata") or {}
        metadata = raw_metadata if isinstance(raw_metadata, dict) else _load_json(raw_metadata, {})
        if not isinstance(metadata, dict):
            metadata = {}
        push_id = paper.get("push_id") or metadata.get("push_id")
        rank = paper.get("rank") or metadata.get("rank")
        score = paper.get("score") or paper.get("relevance") or metadata.get("score")
        category = paper.get("category") or metadata.get("category")
        body_parts = [
            f"Recent PaperFlow pushed paper #{index}.",
            f"Title: {title}",
            f"Authors: {', '.join(authors)}" if authors else "",
            f"Subjects: {', '.join(subjects)}" if subjects else "",
            f"Category: {category}" if category else "",
            f"Rank: {rank}" if rank else "",
            f"Score: {score}" if score else "",
            f"Push batch: {push_id}" if push_id else "",
            f"Abstract: {abstract}" if abstract else "Abstract: no abstract stored; use title/category as weak evidence.",
        ]
        nodes.append(
            {
                "node_id": node_id,
                "node_type": "paper",
                "title": title,
                "body": "\n".join(part for part in body_parts if part),
                "keywords": " ".join([title, category or "", " ".join(subjects), "recent trend daily push"]).strip(),
                "file_path": "",
                "metadata": {
                    "paper_id": paper.get("id"),
                    "arxiv_id": arxiv_id,
                    "doi": paper.get("doi"),
                    "authors": authors,
                    "subjects": subjects,
                    "url": paper.get("url") or paper.get("abs_url") or "",
                    "pdf_url": paper.get("pdf_url") or "",
                    "push_id": push_id,
                    "rank": rank,
                    "score": score,
                    "category": category,
                    "source": "recent_daily_push",
                },
                "score": _to_float(score, 1.0),
                "updated_at": paper.get("pushed_at") or paper.get("updated_at") or "",
            }
        )
        if len(nodes) >= max(1, int(limit or 8)):
            break
    return nodes


def _chat_pinned_nodes(
    *,
    user_id: str,
    question: str,
    resolved_nodes: List[Dict[str, Any]],
    limit: int,
    scope: str = "all",
) -> List[Dict[str, Any]]:
    pinned = list(resolved_nodes or [])
    if _should_pin_recent_papers(question, scope) or pinned:
        seen = {str(node.get("node_id") or "") for node in pinned}
        remaining = max(0, int(limit or 8) - len(pinned))
        query = question if _local_paper_query_tokens(question) else ""
        for entry in _daily_note_reading_entries(scope="all", query=query, limit=remaining or int(limit or 8)):
            node = _daily_note_reading_node(entry)
            node_id = str(node.get("node_id") or "")
            if node_id and node_id not in seen:
                pinned.append(node)
                seen.add(node_id)
    return pinned


def _chat_allowed_node_ids(user_id: str, pinned_nodes: List[Dict[str, Any]]) -> Set[str]:
    del user_id
    return {str(node.get("node_id") or "") for node in pinned_nodes if str(node.get("node_id") or "").strip()}


def _citation_source_payload(citation: Dict[str, Any]) -> Dict[str, Any]:
    metadata = citation.get("metadata") or {}
    node_type = str(citation.get("node_type") or "").strip()
    source_type = str(citation.get("source_type") or "").strip()
    source_id = str(citation.get("source_id") or "").strip()
    source_label = {
        "reading_report": "精读报告",
        "daily_push": "论文推荐",
        "manual": "手动导入",
    }.get(source_type, "")
    meta_parts = [part for part in [source_label, source_id] if part]
    return {
        "index": citation.get("index"),
        "node_id": citation.get("node_id"),
        "node_type": node_type,
        "title": citation.get("title") or citation.get("node_id") or "未命名来源",
        "meta": " · ".join(meta_parts) if meta_parts else "参考文献",
        "snippet": citation.get("excerpt") or "",
        "excerpt": citation.get("excerpt") or "",
        "source_type": source_type,
        "source_id": source_id,
        "anchor": citation.get("anchor"),
        "metadata": metadata,
        "url": metadata.get("url") or metadata.get("abs_url") or metadata.get("pdf_url") or "",
    }


def _direct_answer(question: str, response_language: str = "zh") -> Dict[str, Any]:
    started = time.time()
    language = _normalize_response_language(response_language)
    llm = build_llm_provider()
    llm_error = None
    response = None
    if getattr(llm, "name", "") == "mock":
        text = (
            "This question does not require the local Wiki. No usable LLM is configured, "
            "so the offline desktop app cannot generate a general answer right now. "
            "Use @ to select papers or switch to a Wiki scope for local-paper answers."
            if language == "en"
            else "这个问题不需要调用本地 Wiki。当前未配置可用 LLM，因此离线版无法生成通用回答；如需基于本地论文回答，请用 @ 选择论文或切换到 Wiki 范围。"
        )
    else:
        try:
            response = llm.generate(
                question,
                system=_direct_answer_prompt(language),
                temperature=0.0,
                max_tokens=_direct_answer_max_tokens(),
            )
            text = response.text
        except Exception as exc:
            llm_error = str(exc)
            text = (
                f"This was routed as a general question and does not need local Wiki citations, "
                f"but the current LLM call failed: {llm_error}"
                if language == "en"
                else f"这个问题被判定为通用问题，不需要引用本地 Wiki；但当前 LLM 调用失败：{llm_error}"
            )
    return {
        "text": text,
        "citations": [],
        "sources": [],
        "elapsed_ms": int((time.time() - started) * 1000),
        "response_language": language,
        "token_usage": {
            "provider": getattr(llm, "name", "unknown"),
            "model": getattr(llm, "model", "unknown"),
            "prompt_tokens": response.prompt_tokens if response else 0,
            "completion_tokens": response.completion_tokens if response else 0,
            "llm_error": llm_error,
        },
    }


def _text_chunks(text: str, size: int = 24) -> Iterator[str]:
    content = str(text or "")
    for index in range(0, len(content), max(1, int(size))):
        yield content[index : index + size]


def _selection_required_answer(message: str, response_language: str = "zh") -> Dict[str, Any]:
    return {
        "text": message,
        "citations": [],
        "sources": [],
        "elapsed_ms": 0,
        "response_language": _normalize_response_language(response_language),
        "token_usage": {},
        "streaming": {"provider": False, "transport": "json"},
    }


def _selection_required_answer_stream(message: str, response_language: str = "zh") -> Iterator[Dict[str, Any]]:
    result = _selection_required_answer(message, response_language=response_language)
    yield {"event": "meta", "data": {key: value for key, value in result.items() if key != "text"}}
    for chunk in _text_chunks(message):
        yield {"event": "chunk", "data": {"text": chunk}}
    yield {"event": "done", "data": result}


def _apply_chat_metadata(
    result: Dict[str, Any],
    *,
    mode: str,
    retrieval_required: bool,
    routing_reason: str,
    mentions: List[Dict[str, Any]],
    unresolved_mentions: List[Dict[str, str]],
    scope: str,
    response_language: str = "zh",
) -> Dict[str, Any]:
    citations = result.get("citations") or []
    result["sources"] = [_citation_source_payload(citation) for citation in citations]
    result.update(
        {
            "mode": mode,
            "retrieval_required": retrieval_required,
            "routing_reason": routing_reason,
            "mentions": mentions,
            "unresolved_mentions": unresolved_mentions,
            "scope": scope if scope in {"all", "recent", "profile"} else "all",
            "response_language": _normalize_response_language(response_language),
        }
    )
    return result


def _chat_turn_metadata(result: Dict[str, Any]) -> Dict[str, Any]:
    metadata_keys = [
        "citations",
        "sources",
        "mode",
        "retrieval_required",
        "routing_reason",
        "mentions",
        "unresolved_mentions",
        "scope",
        "elapsed_ms",
        "token_usage",
        "streaming",
        "response_language",
    ]
    return {key: deepcopy(result.get(key)) for key in metadata_keys if key in result}


def _persist_chat_turn(
    user_id: str,
    session_id: str,
    question: str,
    result: Dict[str, Any],
) -> str:
    session = db_ops.create_chat_session(user_id=user_id, title=question, session_id=session_id or None)
    saved_session_id = session["session_id"]
    db_ops.save_chat_message(
        user_id=user_id,
        session_id=saved_session_id,
        role="user",
        content=question,
        metadata={
            "scope": result.get("scope"),
            "mentions": result.get("mentions") or [],
            "unresolved_mentions": result.get("unresolved_mentions") or [],
        },
    )
    db_ops.save_chat_message(
        user_id=user_id,
        session_id=saved_session_id,
        role="assistant",
        content=str(result.get("text") or ""),
        metadata=_chat_turn_metadata(result),
    )
    result["session_id"] = saved_session_id
    return saved_session_id


def _attach_chat_session(
    result: Dict[str, Any],
    *,
    user_id: str,
    session_id: str,
    question: str,
    persist_chat: bool,
) -> Dict[str, Any]:
    if persist_chat:
        _persist_chat_turn(user_id, session_id, question, result)
    elif session_id:
        result["session_id"] = session_id
    return result


def _direct_answer_stream(question: str, response_language: str = "zh") -> Iterator[Dict[str, Any]]:
    started = time.time()
    language = _normalize_response_language(response_language)
    llm = build_llm_provider()
    llm_error = None
    text_parts: List[str] = []
    meta = {
        "citations": [],
        "sources": [],
        "elapsed_ms": 0,
        "response_language": language,
        "token_usage": {
            "provider": getattr(llm, "name", "unknown"),
            "model": getattr(llm, "model", "unknown"),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "llm_error": None,
        },
        "streaming": {"provider": getattr(llm, "name", "") != "mock", "transport": "sse"},
    }
    yield {"event": "meta", "data": meta}
    if getattr(llm, "name", "") == "mock":
        text = (
            "This question does not require the local Wiki. No usable LLM is configured, "
            "so the offline desktop app cannot generate a general answer right now. "
            "Use @ to select papers or switch to a Wiki scope for local-paper answers."
            if language == "en"
            else "这个问题不需要调用本地 Wiki。当前未配置可用 LLM，因此离线版无法生成通用回答；如需基于本地论文回答，请用 @ 选择论文或切换到 Wiki 范围。"
        )
        for chunk in _text_chunks(text):
            text_parts.append(chunk)
            yield {"event": "chunk", "data": {"text": chunk}}
    else:
        try:
            for chunk in llm.stream_generate(
                question,
                system=_direct_answer_prompt(language),
                temperature=0.0,
                max_tokens=_direct_answer_max_tokens(),
            ):
                if not chunk:
                    continue
                text_parts.append(chunk)
                yield {"event": "chunk", "data": {"text": chunk}}
        except Exception as exc:
            llm_error = str(exc)
            text = (
                f"This was routed as a general question and does not need local Wiki citations, "
                f"but the current LLM streaming call failed: {llm_error}"
                if language == "en"
                else f"这个问题被判定为通用问题，不需要引用本地 Wiki；但当前 LLM 流式调用失败：{llm_error}"
            )
            text_parts = [text]
            yield {"event": "chunk", "data": {"text": text}}

    result = {
        "text": "".join(text_parts),
        "citations": [],
        "sources": [],
        "elapsed_ms": int((time.time() - started) * 1000),
        "response_language": language,
        "token_usage": {
            "provider": getattr(llm, "name", "unknown"),
            "model": getattr(llm, "model", "unknown"),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "llm_error": llm_error,
        },
        "streaming": {"provider": getattr(llm, "name", "") != "mock" and not llm_error, "transport": "sse"},
    }
    yield {"event": "done", "data": result}


def _wiki_scope_hint(scope: str, response_language: str) -> str:
    language = _normalize_response_language(response_language)
    if language == "en":
        return {
            "recent": " Prioritize recently updated wiki nodes and recent reading reports.",
            "profile": " Prioritize profile, trajectory, preference, and research-direction wiki nodes.",
        }.get(scope, "")
    return {
        "recent": " 请优先参考最近更新的 Wiki 节点和近期精读报告。",
        "profile": " 请优先参考用户画像、研究轨迹、偏好和研究方向相关 Wiki 节点。",
    }.get(scope, "")


def _comparison_selection_required_message(response_language: str) -> str:
    if _normalize_response_language(response_language) == "en":
        return (
            "Please use @ in the input box to select two specific papers first, "
            "or open a reference from the right panel before comparing them. "
            "Otherwise the local Wiki cannot know which two papers you mean."
        )
    return "请先在输入框用 @ 选择两篇具体论文，或从右侧参考文献点“查看来源”后再对比。否则本地 Wiki 无法判断你说的“这两篇”是哪两篇。"


def wiki_ask(
    user_id: str,
    question: str,
    limit: int = 8,
    scope: str = "all",
    mentions: Any = None,
    session_id: str = "",
    persist_chat: bool = False,
    response_language: str = "zh",
) -> Dict[str, Any]:
    if not user_id:
        raise ValueError("user_id is required")
    cleaned_question = str(question or "").strip()
    if not cleaned_question:
        raise ValueError("question is required")
    language = _normalize_response_language(response_language)
    safe_limit = max(1, min(12, int(limit or 8)))
    normalized_scope = str(scope or "all").strip().lower()
    scope_hint = _wiki_scope_hint(normalized_scope, language)
    resolved_nodes, resolved_mentions, unresolved_mentions = _resolve_wiki_mentions(
        user_id,
        cleaned_question,
        mentions,
        limit=6,
    )
    mode, routing_reason = _question_route(cleaned_question, normalized_scope, resolved_mentions)
    if _comparison_needs_mentions(cleaned_question, resolved_nodes):
        result = _selection_required_answer(
            _comparison_selection_required_message(language),
            response_language=language,
        )
        _apply_chat_metadata(
            result,
            mode="wiki",
            retrieval_required=True,
            routing_reason="mention_required",
            mentions=resolved_mentions,
            unresolved_mentions=unresolved_mentions,
            scope=normalized_scope,
            response_language=language,
        )
        _attach_chat_session(
            result,
            user_id=user_id,
            session_id=session_id,
            question=cleaned_question,
            persist_chat=persist_chat,
        )
        return result
    if mode == "direct":
        result = _direct_answer(cleaned_question, response_language=language)
        result["streaming"] = {"provider": False, "transport": "json"}
        _apply_chat_metadata(
            result,
            mode="direct",
            retrieval_required=False,
            routing_reason=routing_reason,
            mentions=[],
            unresolved_mentions=unresolved_mentions,
            scope=normalized_scope,
            response_language=language,
        )
    else:
        pinned_nodes = _chat_pinned_nodes(
            user_id=user_id,
            question=cleaned_question,
            resolved_nodes=resolved_nodes,
            limit=safe_limit,
            scope=normalized_scope,
        )
        result = wiki_answer.answer_question(
            user_id,
            f"{cleaned_question}{scope_hint}",
            limit=safe_limit,
            pinned_nodes=pinned_nodes,
            allowed_node_ids=_visible_wiki_node_ids(user_id),
            response_language=language,
        )
        result["streaming"] = {"provider": False, "transport": "json"}
        _apply_chat_metadata(
            result,
            mode="wiki",
            retrieval_required=True,
            routing_reason=routing_reason,
            mentions=resolved_mentions,
            unresolved_mentions=unresolved_mentions,
            scope=normalized_scope,
            response_language=language,
        )
    _attach_chat_session(
        result,
        user_id=user_id,
        session_id=session_id,
        question=cleaned_question,
        persist_chat=persist_chat,
    )
    return result


def wiki_ask_stream(
    user_id: str,
    question: str,
    limit: int = 8,
    scope: str = "all",
    mentions: Any = None,
    session_id: str = "",
    persist_chat: bool = False,
    response_language: str = "zh",
) -> Iterator[Dict[str, Any]]:
    if not user_id:
        raise ValueError("user_id is required")
    cleaned_question = str(question or "").strip()
    if not cleaned_question:
        raise ValueError("question is required")
    language = _normalize_response_language(response_language)
    safe_limit = max(1, min(12, int(limit or 8)))
    normalized_scope = str(scope or "all").strip().lower()
    scope_hint = _wiki_scope_hint(normalized_scope, language)
    resolved_nodes, resolved_mentions, unresolved_mentions = _resolve_wiki_mentions(
        user_id,
        cleaned_question,
        mentions,
        limit=6,
    )
    mode, routing_reason = _question_route(cleaned_question, normalized_scope, resolved_mentions)
    if _comparison_needs_mentions(cleaned_question, resolved_nodes):
        for event in _selection_required_answer_stream(
            _comparison_selection_required_message(language),
            response_language=language,
        ):
            if event["event"] in {"meta", "done"}:
                _apply_chat_metadata(
                    event["data"],
                    mode="wiki",
                    retrieval_required=True,
                    routing_reason="mention_required",
                    mentions=resolved_mentions,
                    unresolved_mentions=unresolved_mentions,
                    scope=normalized_scope,
                    response_language=language,
                )
            if event["event"] == "meta" and session_id:
                event["data"]["session_id"] = session_id
            if event["event"] == "done":
                _attach_chat_session(
                    event["data"],
                    user_id=user_id,
                    session_id=session_id,
                    question=cleaned_question,
                    persist_chat=persist_chat,
                )
            yield event
        return
    if mode == "direct":
        for event in _direct_answer_stream(cleaned_question, response_language=language):
            if event["event"] in {"meta", "done"}:
                _apply_chat_metadata(
                    event["data"],
                    mode="direct",
                    retrieval_required=False,
                    routing_reason=routing_reason,
                    mentions=[],
                    unresolved_mentions=unresolved_mentions,
                    scope=normalized_scope,
                    response_language=language,
                )
            if event["event"] == "meta" and session_id:
                event["data"]["session_id"] = session_id
            if event["event"] == "done":
                _attach_chat_session(
                    event["data"],
                    user_id=user_id,
                    session_id=session_id,
                    question=cleaned_question,
                    persist_chat=persist_chat,
                )
            yield event
        return

    pinned_nodes = _chat_pinned_nodes(
        user_id=user_id,
        question=cleaned_question,
        resolved_nodes=resolved_nodes,
        limit=safe_limit,
        scope=normalized_scope,
    )
    for event in wiki_answer.answer_question_stream(
        user_id,
        f"{cleaned_question}{scope_hint}",
        limit=safe_limit,
        pinned_nodes=pinned_nodes,
        allowed_node_ids=_visible_wiki_node_ids(user_id),
        response_language=language,
    ):
        if event["event"] in {"meta", "done"}:
            _apply_chat_metadata(
                event["data"],
                mode="wiki",
                retrieval_required=True,
                routing_reason=routing_reason,
                mentions=resolved_mentions,
                unresolved_mentions=unresolved_mentions,
                scope=normalized_scope,
                response_language=language,
            )
        if event["event"] == "meta" and session_id:
            event["data"]["session_id"] = session_id
        if event["event"] == "done":
            _attach_chat_session(
                event["data"],
                user_id=user_id,
                session_id=session_id,
                question=cleaned_question,
                persist_chat=persist_chat,
            )
        yield event


def chat_sessions(user_id: str, days: int = 30, limit: int = 80) -> Dict[str, Any]:
    if not user_id:
        raise ValueError("user_id is required")
    return db_ops.list_chat_sessions(user_id=user_id, days=days, limit=limit)


def chat_session(user_id: str, session_id: str) -> Dict[str, Any]:
    if not user_id or not session_id:
        raise ValueError("user_id and session_id are required")
    payload = db_ops.get_chat_session(user_id=user_id, session_id=session_id)
    if not payload:
        raise ValueError("chat session not found")
    return payload


def create_chat_session(user_id: str, title: str = "") -> Dict[str, Any]:
    if not user_id:
        raise ValueError("user_id is required")
    return {"session": db_ops.create_chat_session(user_id=user_id, title=title or "新对话")}


def delete_chat_session(user_id: str, session_id: str) -> Dict[str, Any]:
    if not user_id or not session_id:
        raise ValueError("user_id and session_id are required")
    return {"deleted": db_ops.delete_chat_session(user_id=user_id, session_id=session_id)}


def clear_chat_sessions(user_id: str) -> Dict[str, Any]:
    if not user_id:
        raise ValueError("user_id is required")
    return {"deleted": db_ops.clear_chat_sessions(user_id=user_id)}


def recent_activity(user_id: str, days: int = 14, limit: int = 80) -> Dict[str, Any]:
    since = (datetime.now() - timedelta(days=max(1, int(days)))).isoformat(sep=" ")
    conn = db_ops.get_connection()
    rows = conn.execute(
        """
        SELECT bl.id, bl.push_id, bl.paper_id, bl.action, bl.action_type,
               bl.category, bl.timestamp, bl.metadata, p.title AS paper_title
        FROM behavior_logs bl
        LEFT JOIN papers p ON p.id = bl.paper_id
        WHERE bl.user_id = ?
          AND bl.timestamp >= ?
        ORDER BY bl.timestamp DESC, bl.id DESC
        LIMIT ?
        """,
        (user_id, since, max(1, int(limit))),
    ).fetchall()
    conn.close()
    return {
        "activity": [
            {
                "id": row["id"],
                "push_id": row["push_id"],
                "paper_id": row["paper_id"],
                "paper_title": row["paper_title"],
                "action": row["action"],
                "action_type": row["action_type"],
                "category": row["category"],
                "timestamp": row["timestamp"],
                "metadata": _load_json(row["metadata"], {}),
            }
            for row in rows
        ]
    }
