#!/usr/bin/env python3
"""
Background scheduler for automatic daily pushes and weekly reports.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.9+ should provide this
    ZoneInfo = None


ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR / "data"
ROLE_META_PATH = DATA_DIR / "roles.json"
SCHEDULER_STATE_PATH = DATA_DIR / "scheduler_state.json"

LOGGER = logging.getLogger("scitaste-scheduler")

_THREAD_LOCK = threading.Lock()
_SCHEDULER_THREAD: Optional[threading.Thread] = None
_SCHEDULER_STOP_EVENT: Optional[threading.Event] = None
_INFLIGHT_LOCK = threading.Lock()
_INFLIGHT_JOBS: set[str] = set()


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name, "true" if default else "false").strip().lower()
    return raw not in {"0", "false", "no", "off", "disabled"}


def scheduler_enabled() -> bool:
    return _env_flag("SCITASTE_SCHEDULER_ENABLED", True)


def get_scheduler_timezone_name() -> str:
    return os.environ.get("SCITASTE_TIMEZONE", "Asia/Shanghai").strip() or "Asia/Shanghai"


def get_scheduler_timezone() -> Optional[ZoneInfo]:
    if ZoneInfo is None:
        return None

    timezone_name = get_scheduler_timezone_name()
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        LOGGER.warning("Invalid scheduler timezone %r, falling back to local time", timezone_name)
        return None


def get_scheduler_now(now: Optional[datetime] = None) -> datetime:
    timezone = get_scheduler_timezone()
    if now is None:
        return datetime.now(timezone) if timezone else datetime.now()
    if timezone and now.tzinfo is None:
        return now.replace(tzinfo=timezone)
    if timezone and now.tzinfo is not None:
        return now.astimezone(timezone)
    return now


def _parse_hhmm(value: str, default: str) -> tuple[int, int]:
    raw = (value or default).strip()
    try:
        hour_str, minute_str = raw.split(":", 1)
        hour = max(0, min(23, int(hour_str)))
        minute = max(0, min(59, int(minute_str)))
        return hour, minute
    except Exception:
        fallback_hour, fallback_minute = default.split(":", 1)
        return int(fallback_hour), int(fallback_minute)


def get_daily_push_time() -> tuple[int, int]:
    return _parse_hhmm(os.environ.get("SCITASTE_DAILY_PUSH_TIME", "09:00"), "09:00")


def get_weekly_report_time() -> tuple[int, int]:
    return _parse_hhmm(os.environ.get("SCITASTE_WEEKLY_REPORT_TIME", "10:00"), "10:00")


def get_weekly_report_weekday() -> int:
    raw = os.environ.get("SCITASTE_WEEKLY_REPORT_WEEKDAY", "0").strip()
    try:
        return max(0, min(6, int(raw)))
    except ValueError:
        return 0


def get_poll_seconds() -> int:
    raw = os.environ.get("SCITASTE_SCHEDULER_POLL_SECONDS", "30").strip()
    try:
        return max(5, int(raw))
    except ValueError:
        return 30


def get_scheduler_grace_minutes() -> int:
    raw = os.environ.get("SCITASTE_SCHEDULER_GRACE_MINUTES", "10").strip()
    try:
        return max(0, min(180, int(raw)))
    except ValueError:
        return 10


def _minutes_since_midnight(value: datetime) -> int:
    return (value.hour * 60) + value.minute


def _is_within_schedule_window(now: datetime, hour: int, minute: int) -> bool:
    scheduled_minutes = (hour * 60) + minute
    delta_minutes = _minutes_since_midnight(now) - scheduled_minutes
    return 0 <= delta_minutes <= get_scheduler_grace_minutes()


def describe_schedule() -> str:
    daily_hour, daily_minute = get_daily_push_time()
    weekly_hour, weekly_minute = get_weekly_report_time()
    weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday = weekday_names[get_weekly_report_weekday()]
    return (
        f"daily push {daily_hour:02d}:{daily_minute:02d}, "
        f"weekly report {weekday} {weekly_hour:02d}:{weekly_minute:02d}, "
        f"timezone={get_scheduler_timezone_name()}, "
        f"grace={get_scheduler_grace_minutes()}m"
    )


def load_roles_meta(roles_path: Path = ROLE_META_PATH) -> Dict[str, Any]:
    try:
        return json.loads(roles_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        LOGGER.warning("roles.json not found at %s", roles_path)
    except json.JSONDecodeError as exc:
        LOGGER.error("Failed to parse roles.json at %s: %s", roles_path, exc)
    return {"roles": {}, "current_role": None}


def get_scheduled_roles(roles_meta: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    meta = roles_meta or load_roles_meta()
    roles = []
    for role_name, role_data in (meta.get("roles") or {}).items():
        if not isinstance(role_data, dict):
            continue
        user_id = str(role_data.get("user_id") or f"user_{role_name}").strip()
        chat_id = str(role_data.get("feishu_chat_id") or "").strip()
        roles.append(
            {
                "role_name": str(role_name),
                "user_id": user_id,
                "chat_id": chat_id,
            }
        )
    return roles


def load_scheduler_state(state_path: Path = SCHEDULER_STATE_PATH) -> Dict[str, Any]:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        state = {}
    except json.JSONDecodeError as exc:
        LOGGER.warning("Failed to parse scheduler state at %s: %s", state_path, exc)
        state = {}

    jobs = state.get("jobs")
    if not isinstance(jobs, dict):
        jobs = {}
    return {"jobs": jobs}


def save_scheduler_state(state: Dict[str, Any], state_path: Path = SCHEDULER_STATE_PATH) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"jobs": dict(state.get("jobs") or {})}
    temp_path = state_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(state_path)


def _daily_marker(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def _weekly_marker(now: datetime) -> str:
    iso = now.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _already_ran(state: Dict[str, Any], job_key: str, marker: str) -> bool:
    return str((state.get("jobs") or {}).get(job_key, "")) == marker


def _mark_ran(state: Dict[str, Any], job_key: str, marker: str) -> None:
    state.setdefault("jobs", {})[job_key] = marker


def should_run_daily_push(now: datetime, role_name: str, state: Dict[str, Any]) -> bool:
    marker = _daily_marker(now)
    if _already_ran(state, f"daily_push:{role_name}", marker):
        return False

    hour, minute = get_daily_push_time()
    return _is_within_schedule_window(now, hour, minute)


def should_run_weekly_report(now: datetime, role_name: str, state: Dict[str, Any]) -> bool:
    if now.weekday() != get_weekly_report_weekday():
        return False

    marker = _weekly_marker(now)
    if _already_ran(state, f"weekly_report:{role_name}", marker):
        return False

    hour, minute = get_weekly_report_time()
    return _is_within_schedule_window(now, hour, minute)


def _trigger_daily_push(role_name: str, user_id: str, chat_id: str) -> None:
    daily_push_agent = importlib.import_module("agents.daily-push-agent.main")
    LOGGER.info("Running scheduled daily push for %s (%s)", role_name, user_id)
    daily_push_agent.daily_push(
        user_id=user_id,
        send_to_feishu=True,
        feishu_chat_id=chat_id,
    )


def _trigger_weekly_report(role_name: str, user_id: str, chat_id: str) -> None:
    profile_report_agent = importlib.import_module("agents.profile-report-agent.main")
    LOGGER.info("Running scheduled weekly report for %s (%s)", role_name, user_id)
    profile_report_agent.send_weekly_report(
        user_id=user_id,
        send_to_feishu=True,
        feishu_chat_id=chat_id,
        role_name=role_name,
    )


def _acquire_job(job_key: str) -> bool:
    with _INFLIGHT_LOCK:
        if job_key in _INFLIGHT_JOBS:
            return False
        _INFLIGHT_JOBS.add(job_key)
        return True


def _release_job(job_key: str) -> None:
    with _INFLIGHT_LOCK:
        _INFLIGHT_JOBS.discard(job_key)


def run_due_jobs(
    *,
    now: Optional[datetime] = None,
    roles_path: Path = ROLE_META_PATH,
    state_path: Path = SCHEDULER_STATE_PATH,
) -> List[Dict[str, str]]:
    if not scheduler_enabled():
        return []

    current_time = get_scheduler_now(now)
    state = load_scheduler_state(state_path)
    roles = get_scheduled_roles(load_roles_meta(roles_path))
    results: List[Dict[str, str]] = []
    state_changed = False

    for role in roles:
        role_name = role["role_name"]
        user_id = role["user_id"]
        chat_id = role["chat_id"]

        if not chat_id:
            LOGGER.warning("Skipping scheduled jobs for %s: missing feishu_chat_id", role_name)
            continue

        daily_job_key = f"daily_push:{role_name}"
        if should_run_daily_push(current_time, role_name, state) and _acquire_job(daily_job_key):
            try:
                _trigger_daily_push(role_name, user_id, chat_id)
                _mark_ran(state, daily_job_key, _daily_marker(current_time))
                state_changed = True
                results.append({"job": "daily_push", "role_name": role_name, "status": "success"})
            except Exception as exc:
                LOGGER.exception("Scheduled daily push failed for %s: %s", role_name, exc)
                results.append({"job": "daily_push", "role_name": role_name, "status": "error"})
            finally:
                _release_job(daily_job_key)

        weekly_job_key = f"weekly_report:{role_name}"
        if should_run_weekly_report(current_time, role_name, state) and _acquire_job(weekly_job_key):
            try:
                _trigger_weekly_report(role_name, user_id, chat_id)
                _mark_ran(state, weekly_job_key, _weekly_marker(current_time))
                state_changed = True
                results.append({"job": "weekly_report", "role_name": role_name, "status": "success"})
            except Exception as exc:
                LOGGER.exception("Scheduled weekly report failed for %s: %s", role_name, exc)
                results.append({"job": "weekly_report", "role_name": role_name, "status": "error"})
            finally:
                _release_job(weekly_job_key)

    if state_changed:
        save_scheduler_state(state, state_path)

    return results


def scheduler_loop(stop_event: threading.Event) -> None:
    LOGGER.info("Scheduler loop started: %s", describe_schedule())
    poll_seconds = get_poll_seconds()
    while not stop_event.is_set():
        try:
            run_due_jobs()
        except Exception as exc:
            LOGGER.exception("Unexpected scheduler loop error: %s", exc)
        stop_event.wait(poll_seconds)
    LOGGER.info("Scheduler loop stopped")


def start_scheduler_thread() -> Optional[threading.Thread]:
    global _SCHEDULER_THREAD, _SCHEDULER_STOP_EVENT

    if not scheduler_enabled():
        LOGGER.info("Scheduler disabled by SCITASTE_SCHEDULER_ENABLED")
        return None

    with _THREAD_LOCK:
        if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
            return _SCHEDULER_THREAD

        _SCHEDULER_STOP_EVENT = threading.Event()
        _SCHEDULER_THREAD = threading.Thread(
            target=scheduler_loop,
            args=(_SCHEDULER_STOP_EVENT,),
            name="scitaste-scheduler",
            daemon=True,
        )
        _SCHEDULER_THREAD.start()
        return _SCHEDULER_THREAD


def stop_scheduler_thread() -> None:
    global _SCHEDULER_THREAD, _SCHEDULER_STOP_EVENT

    with _THREAD_LOCK:
        if _SCHEDULER_STOP_EVENT:
            _SCHEDULER_STOP_EVENT.set()
        _SCHEDULER_THREAD = None
        _SCHEDULER_STOP_EVENT = None
