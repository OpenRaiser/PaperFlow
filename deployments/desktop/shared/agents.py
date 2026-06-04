"""GUI-facing wrappers around PaperFlow agents and storage.

The local GUI should only pass simple JSON-like values through this module.
Kebab-case agent directories are imported with importlib here, so the HTTP
server and future GUI stacks do not need to know about those details.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import threading
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set
from uuid import uuid4


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


def _configured_path(env_name: str, default_relative: str) -> str:
    raw = os.environ.get(env_name, "").strip()
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return str(path)
    return str(PROJECT_ROOT / default_relative)


def _safe_env() -> Dict[str, str]:
    prefixes = ("PAPERFLOW_", "OPENAI_", "ANTHROPIC_", "OLLAMA_", "DASHSCOPE_", "FEISHU_", "NGROK_")
    sensitive = ("KEY", "TOKEN", "SECRET", "PASSWORD")
    result: Dict[str, str] = {}
    for key, value in sorted(os.environ.items()):
        if not key.startswith(prefixes):
            continue
        result[key] = "***" if any(part in key for part in sensitive) and value else value
    return result


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


def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "project_root": str(PROJECT_ROOT),
        "database": str(db_ops.DB_PATH),
        "database_exists": Path(db_ops.DB_PATH).exists(),
    }


def settings() -> Dict[str, Any]:
    return {
        "project_root": str(PROJECT_ROOT),
        "database": str(db_ops.DB_PATH),
        "paths": {
            "pdf_dir": _configured_path("PAPERFLOW_PDF_DIR", "data/exports"),
            "reading_reports_dir": _configured_path("PAPERFLOW_READING_REPORTS_DIR", "data/exports"),
            "wiki_dir": _configured_path("PAPERFLOW_WIKI_DIR", "data/wiki"),
            "monthly_report_dir": _configured_path("PAPERFLOW_MONTHLY_REPORT_DIR", "data/exports"),
            "topic_index_dir": _configured_path("PAPERFLOW_TOPIC_INDEX_DIR", "data/exports"),
            "role_subdir": _env_bool("PAPERFLOW_STORAGE_ROLE_SUBDIR", default=True),
            "category_subdir": _env_bool("PAPERFLOW_STORAGE_CATEGORY_SUBDIR", default=True),
            "monthly_subdir": _env_bool("PAPERFLOW_STORAGE_MONTHLY_SUBDIR", default=True),
            "wiki_ingest": _env_bool("PAPERFLOW_WIKI_INGEST", default=True),
            "write_feishu": _env_bool("PAPERFLOW_WRITE_FEISHU", default=False),
        },
        "env": _safe_env(),
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


def create_or_update_profile(
    *,
    user_id: str,
    natural_language: str = "",
    scholar_url: str = "",
    homepage_url: str = "",
    pdf_paths: Optional[List[str]] = None,
    reset_existing: bool = False,
) -> Dict[str, Any]:
    if not user_id.strip():
        raise ValueError("user_id is required")
    result = coldstart_agent.cold_start(
        user_id=user_id.strip(),
        natural_language=natural_language.strip() or None,
        pdf_paths=pdf_paths or None,
        scholar_url=scholar_url.strip() or None,
        homepage_url=homepage_url.strip() or None,
        reset_existing=reset_existing,
        send_to_feishu=False,
    )
    return {"result": result, "profile": _profile_summary(db_ops.get_profile(user_id.strip()))}


def run_daily_push(user_id: str, days: int = 1, limit_per_source: int = 30) -> Dict[str, Any]:
    result = daily_agent.daily_push(
        user_id=user_id,
        days=max(1, int(days or 1)),
        limit_per_source=max(1, int(limit_per_source or 30)),
        send_to_feishu=False,
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
    return deepcopy({key: value for key, value in task.items() if key != "thread"})


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
        limit_per_source = int(task.get("limit_per_source") or 30)

    try:
        result = run_daily_push(user_id, days=days, limit_per_source=limit_per_source)
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


def start_daily_push_task(user_id: str, days: int = 1, limit_per_source: int = 30) -> Dict[str, Any]:
    cleaned_user_id = str(user_id or "").strip()
    if not cleaned_user_id:
        raise ValueError("user_id is required")

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
            "days": max(1, int(days or 1)),
            "limit_per_source": max(1, int(limit_per_source or 30)),
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "result": None,
            "push": None,
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
) -> Dict[str, Any]:
    push = db_ops.get_push_papers(push_id)
    if not push or not push.get("papers"):
        raise ValueError(f"Push not found: {push_id}")

    papers = list(push["papers"])
    selected = set(_unique_ints(selected_numbers, maximum=len(papers)))
    skipped = set(_unique_ints(skipped_numbers, maximum=len(papers))) - selected

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

    profile_before = db_ops.get_profile(user_id) or {}
    updated_profile: Dict[str, Any] = profile_before
    if selected or skipped:
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
        evidence_numbers = sorted(selected | skipped)
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
        "profile": _profile_summary(updated_profile),
    }


def create_reading_reports(
    *,
    user_id: str,
    push_id: str,
    paper_numbers: Iterable[Any],
    write_feishu: Optional[bool] = None,
) -> Dict[str, Any]:
    push = db_ops.get_push_papers(push_id)
    if not push or not push.get("papers"):
        raise ValueError(f"Push not found: {push_id}")
    papers = list(push["papers"])
    selected = _unique_ints(paper_numbers, maximum=len(papers))
    should_write_feishu = _env_bool("PAPERFLOW_WRITE_FEISHU", default=False) if write_feishu is None else bool(write_feishu)
    if not selected:
        return _reports_payload([], write_feishu_requested=should_write_feishu)

    with _local_only_feishu_doc_patch(not should_write_feishu):
        docs = reading_agent.create_reading_report(
            user_id=user_id,
            paper_ids=selected,
            papers=papers,
            send_to_feishu=should_write_feishu,
            request_metadata={"selection_push_id": push_id, "report_source_type": "desktop_gui"},
        )

    return _reports_payload(docs, write_feishu_requested=should_write_feishu)


def _normalize_arxiv_id(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("arxiv_id is required")
    raw = raw.removeprefix("https://arxiv.org/abs/").removeprefix("http://arxiv.org/abs/")
    raw = raw.removeprefix("https://arxiv.org/pdf/").removeprefix("http://arxiv.org/pdf/")
    raw = raw.removesuffix(".pdf")
    return raw.strip()


def read_arxiv(user_id: str, arxiv_id: str, write_feishu: Optional[bool] = None) -> Dict[str, Any]:
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
    with _local_only_feishu_doc_patch(not should_write_feishu):
        docs = reading_agent.create_reading_report(
            user_id=user_id,
            paper_ids=[],
            papers=[paper],
            send_to_feishu=should_write_feishu,
            request_metadata={
                "report_source_type": "desktop_arxiv",
                "report_source_key": normalized_arxiv_id,
                "report_source_name": normalized_arxiv_id,
            },
        )
    return _reports_payload(docs, write_feishu_requested=should_write_feishu)


def read_local_pdf(
    user_id: str,
    pdf_path: str,
    title: str = "",
    write_feishu: Optional[bool] = None,
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
    with _local_only_feishu_doc_patch(not should_write_feishu):
        docs = reading_agent.create_reading_report(
            user_id=user_id,
            paper_ids=[],
            papers=[paper],
            send_to_feishu=should_write_feishu,
            request_metadata={
                "report_source_type": "desktop_pdf_path",
                "report_source_key": str(path),
                "report_source_name": path.name,
            },
        )
    return _reports_payload(docs, write_feishu_requested=should_write_feishu)


def _doc_payloads(docs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "title": doc.get("title"),
            "url": doc.get("url"),
            "doc_token": doc.get("doc_token"),
            "report_path": doc.get("report_path"),
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


def submit_and_read(
    *,
    user_id: str,
    push_id: str,
    selected_numbers: Iterable[Any],
    skipped_numbers: Iterable[Any],
    generate_reports: bool = True,
    write_feishu: Optional[bool] = None,
) -> Dict[str, Any]:
    feedback = submit_gui_feedback(
        user_id=user_id,
        push_id=push_id,
        selected_numbers=selected_numbers,
        skipped_numbers=skipped_numbers,
    )
    reports = {"created_docs": [], "count": 0}
    if generate_reports and feedback["selected_numbers"]:
        reports = create_reading_reports(
            user_id=user_id,
            push_id=push_id,
            paper_numbers=feedback["selected_numbers"],
            write_feishu=write_feishu,
        )
    return {"feedback": feedback, "reports": reports}


def wiki_stats(user_id: str) -> Dict[str, Any]:
    return wiki_db.stats(user_id)


def wiki_search(user_id: str, query: str = "", node_type: Optional[str] = None, limit: int = 12) -> Dict[str, Any]:
    nodes = wiki_db.search_nodes(user_id, query, node_type=node_type or None, limit=limit)
    return {
        "nodes": [
            {
                "node_id": node.get("node_id"),
                "node_type": node.get("node_type"),
                "title": node.get("title"),
                "body": str(node.get("body") or "")[:800],
                "keywords": node.get("keywords"),
                "file_path": node.get("file_path"),
                "metadata": node.get("metadata") or {},
                "score": node.get("score"),
                "updated_at": node.get("updated_at"),
            }
            for node in nodes
        ]
    }


def wiki_ask(user_id: str, question: str, limit: int = 8) -> Dict[str, Any]:
    return wiki_answer.answer_question(user_id, question, limit=limit)


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
