"""Role-name helpers for user-scoped local storage paths."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def slug(value: Any, *, max_len: int = 96) -> str:
    """Return a filesystem-safe label while preserving readable Unicode names."""
    text = re.sub(r"[^\w.\-]+", "-", str(value or "").strip(), flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return (text or "user")[:max_len]


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "off", "no", ""}


def roles_path(*, project_root: Optional[Path] = None) -> Path:
    """Resolve the role metadata file used to map role names to user ids."""
    root = project_root or PROJECT_ROOT
    configured = os.environ.get("PAPERFLOW_ROLES_PATH", "").strip()
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_absolute() else root / path
    return root / "data" / "roles.json"


def load_roles_meta(*, project_root: Optional[Path] = None) -> Dict[str, Any]:
    path = roles_path(project_root=project_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"roles": {}, "current_role": None}
    return data if isinstance(data, dict) else {"roles": {}, "current_role": None}


def role_name_for_user_id(user_id: str, *, project_root: Optional[Path] = None) -> str:
    """Return the user-facing role name for a user id, or the user id itself."""
    cleaned_user_id = str(user_id or "").strip()
    if not cleaned_user_id:
        return ""

    roles = load_roles_meta(project_root=project_root).get("roles") or {}
    if not isinstance(roles, dict):
        return cleaned_user_id

    for role_name, role_info in roles.items():
        if not isinstance(role_info, dict):
            continue
        if str(role_info.get("user_id") or "").strip() == cleaned_user_id:
            cleaned_role_name = str(role_name or "").strip()
            return cleaned_role_name or cleaned_user_id
    return cleaned_user_id


def storage_label_for_user_id(user_id: str, *, project_root: Optional[Path] = None) -> str:
    """Return the role-name-based filesystem label for a user id."""
    return slug(role_name_for_user_id(user_id, project_root=project_root))


def role_storage_subdir_enabled() -> bool:
    """Whether exported local files should be grouped by role/user label."""
    return env_flag("PAPERFLOW_STORAGE_ROLE_SUBDIR", default=True)


def category_storage_subdir_enabled() -> bool:
    """Whether exported local files should be grouped by output category."""
    return env_flag("PAPERFLOW_STORAGE_CATEGORY_SUBDIR", default=True)


def apply_user_scope(path: Path, user_id: str, *, project_root: Optional[Path] = None) -> Path:
    """Append the role/user storage label unless role subdirectories are disabled."""
    if not role_storage_subdir_enabled() or not str(user_id or "").strip():
        return path
    label = storage_label_for_user_id(user_id, project_root=project_root)
    if label in path.parts:
        return path
    return path / label


def _normalized_part_labels(path: Path) -> set[str]:
    return {slug(part).lower() for part in path.parts if part}


def _category_labels(category: str) -> set[str]:
    normalized = slug(category).lower()
    aliases = {
        "pdf": {"pdf", "paper", "papers"},
        "reading_reports": {"reading-reports", "reading_reports", "reading", "reports"},
        "monthly_reports": {"monthly-reports", "monthly_reports", "monthly"},
        "topic_index": {"topic-index", "topic_index", "topic"},
    }
    return aliases.get(normalized, {normalized})


def apply_output_scope(
    path: Path,
    user_id: str,
    *,
    category: str = "",
    project_root: Optional[Path] = None,
) -> Path:
    """Append role and category directories for local export targets."""
    original_labels = _normalized_part_labels(path)
    scoped = apply_user_scope(path, user_id, project_root=project_root)
    if not category or not category_storage_subdir_enabled():
        return scoped
    labels = _category_labels(category)
    if original_labels.intersection(labels) or slug(scoped.name).lower() in labels:
        return scoped
    return scoped / slug(category)
