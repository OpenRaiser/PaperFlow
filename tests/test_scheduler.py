import importlib.util
import json
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
SCHEDULER_PATH = PROJECT_ROOT / "deployments" / "feishu" / "webhook-server" / "scripts" / "scheduler.py"

spec = importlib.util.spec_from_file_location("paperflow_scheduler_test", SCHEDULER_PATH)
scheduler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler)


def test_run_due_jobs_triggers_daily_push_once_per_role(tmp_path, monkeypatch):
    roles_path = tmp_path / "roles.json"
    roles_path.write_text(
        json.dumps(
            {
                "roles": {
                    "rolea": {"user_id": "user_rolea", "feishu_chat_id": "oc_rolea"},
                    "roleb": {"user_id": "user_roleb", "feishu_chat_id": "oc_roleb"},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    state_path = tmp_path / "scheduler_state.json"

    monkeypatch.setenv("PAPERFLOW_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("PAPERFLOW_TIMEZONE", "Asia/Shanghai")
    monkeypatch.setenv("PAPERFLOW_DAILY_PUSH_TIME", "09:00")
    monkeypatch.setenv("PAPERFLOW_WEEKLY_REPORT_TIME", "10:00")
    monkeypatch.setenv("PAPERFLOW_WEEKLY_REPORT_WEEKDAY", "0")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_GRACE_MINUTES", "10")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_DAILY_COMPENSATION_HOURS", "0")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_WEEKLY_COMPENSATION_HOURS", "0")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_DAILY_COMPENSATION_HOURS", "0")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_WEEKLY_COMPENSATION_HOURS", "0")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_DAILY_COMPENSATION_HOURS", "0")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_WEEKLY_COMPENSATION_HOURS", "0")

    daily_runs = []
    monkeypatch.setattr(
        scheduler,
        "_trigger_daily_push",
        lambda role_name, user_id, chat_id: daily_runs.append((role_name, user_id, chat_id)),
    )
    monkeypatch.setattr(scheduler, "_trigger_weekly_report", lambda *args, **kwargs: None)

    now = datetime(2026, 4, 13, 9, 5)
    results = scheduler.run_due_jobs(now=now, roles_path=roles_path, state_path=state_path)

    assert daily_runs == [
        ("rolea", "user_rolea", "oc_rolea"),
        ("roleb", "user_roleb", "oc_roleb"),
    ]
    assert [item["job"] for item in results] == ["daily_push", "daily_push"]
    assert scheduler.load_scheduler_state(state_path)["jobs"] == {
        "daily_push:rolea": "2026-04-13",
        "daily_push:roleb": "2026-04-13",
    }

    daily_runs.clear()
    second_results = scheduler.run_due_jobs(now=now, roles_path=roles_path, state_path=state_path)
    assert daily_runs == []
    assert second_results == []


def test_run_due_jobs_triggers_weekly_report_on_monday_only(tmp_path, monkeypatch):
    roles_path = tmp_path / "roles.json"
    roles_path.write_text(
        json.dumps(
            {
                "roles": {
                    "rolea": {"user_id": "user_rolea", "feishu_chat_id": "oc_rolea"},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    state_path = tmp_path / "scheduler_state.json"
    scheduler.save_scheduler_state(
        {"jobs": {"daily_push:rolea": "2026-04-13"}},
        state_path,
    )

    monkeypatch.setenv("PAPERFLOW_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("PAPERFLOW_TIMEZONE", "Asia/Shanghai")
    monkeypatch.setenv("PAPERFLOW_DAILY_PUSH_TIME", "09:00")
    monkeypatch.setenv("PAPERFLOW_WEEKLY_REPORT_TIME", "10:00")
    monkeypatch.setenv("PAPERFLOW_WEEKLY_REPORT_WEEKDAY", "0")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_GRACE_MINUTES", "10")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_DAILY_COMPENSATION_HOURS", "0")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_WEEKLY_COMPENSATION_HOURS", "0")

    weekly_runs = []
    monkeypatch.setattr(scheduler, "_trigger_daily_push", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        scheduler,
        "_trigger_weekly_report",
        lambda role_name, user_id, chat_id: weekly_runs.append((role_name, user_id, chat_id)),
    )

    monday = datetime(2026, 4, 13, 10, 5)
    monday_results = scheduler.run_due_jobs(now=monday, roles_path=roles_path, state_path=state_path)
    assert weekly_runs == [("rolea", "user_rolea", "oc_rolea")]
    assert monday_results == [{"job": "weekly_report", "role_name": "rolea", "status": "success", "trigger": "scheduled"}]
    assert scheduler.load_scheduler_state(state_path)["jobs"]["weekly_report:rolea"] == "2026-W16"

    weekly_runs.clear()
    tuesday = datetime(2026, 4, 14, 10, 5)
    tuesday_results = scheduler.run_due_jobs(now=tuesday, roles_path=roles_path, state_path=state_path)
    assert weekly_runs == []
    assert tuesday_results == []


def test_run_due_jobs_does_not_backfill_late_restart(tmp_path, monkeypatch):
    roles_path = tmp_path / "roles.json"
    roles_path.write_text(
        json.dumps(
            {
                "roles": {
                    "rolea": {"user_id": "user_rolea", "feishu_chat_id": "oc_rolea"},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    state_path = tmp_path / "scheduler_state.json"

    monkeypatch.setenv("PAPERFLOW_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("PAPERFLOW_TIMEZONE", "Asia/Shanghai")
    monkeypatch.setenv("PAPERFLOW_DAILY_PUSH_TIME", "09:00")
    monkeypatch.setenv("PAPERFLOW_WEEKLY_REPORT_TIME", "10:00")
    monkeypatch.setenv("PAPERFLOW_WEEKLY_REPORT_WEEKDAY", "2")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_GRACE_MINUTES", "10")

    daily_runs = []
    weekly_runs = []
    monkeypatch.setattr(
        scheduler,
        "_trigger_daily_push",
        lambda role_name, user_id, chat_id: daily_runs.append((role_name, user_id, chat_id)),
    )
    monkeypatch.setattr(
        scheduler,
        "_trigger_weekly_report",
        lambda role_name, user_id, chat_id: weekly_runs.append((role_name, user_id, chat_id)),
    )

    results = scheduler.run_due_jobs(
        now=datetime(2026, 4, 13, 19, 5),
        roles_path=roles_path,
        state_path=state_path,
    )

    assert results == []
    assert daily_runs == []
    assert weekly_runs == []
    assert scheduler.load_scheduler_state(state_path)["jobs"] == {}


def test_run_due_jobs_skips_roles_without_chat_id(tmp_path, monkeypatch):
    roles_path = tmp_path / "roles.json"
    roles_path.write_text(
        json.dumps(
            {
                "roles": {
                    "rolea": {"user_id": "user_rolea", "feishu_chat_id": ""},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    state_path = tmp_path / "scheduler_state.json"

    monkeypatch.setenv("PAPERFLOW_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("PAPERFLOW_DAILY_PUSH_TIME", "09:00")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_GRACE_MINUTES", "10")

    called = []
    monkeypatch.setattr(
        scheduler,
        "_trigger_daily_push",
        lambda role_name, user_id, chat_id: called.append((role_name, user_id, chat_id)),
    )

    results = scheduler.run_due_jobs(
        now=datetime(2026, 4, 13, 9, 1),
        roles_path=roles_path,
        state_path=state_path,
    )

    assert called == []
    assert results == []
    assert scheduler.load_scheduler_state(state_path)["jobs"] == {}


def test_run_due_jobs_compensates_recent_missed_daily_push(tmp_path, monkeypatch):
    roles_path = tmp_path / "roles.json"
    roles_path.write_text(
        json.dumps(
            {"roles": {"rolea": {"user_id": "user_rolea", "feishu_chat_id": "oc_rolea"}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    state_path = tmp_path / "scheduler_state.json"

    monkeypatch.setenv("PAPERFLOW_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("PAPERFLOW_DAILY_PUSH_TIME", "09:00")
    monkeypatch.setenv("PAPERFLOW_WEEKLY_REPORT_TIME", "10:00")
    monkeypatch.setenv("PAPERFLOW_WEEKLY_REPORT_WEEKDAY", "2")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_GRACE_MINUTES", "10")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_DAILY_COMPENSATION_HOURS", "6")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_WEEKLY_COMPENSATION_HOURS", "0")

    calls = []
    monkeypatch.setattr(
        scheduler,
        "_trigger_daily_push",
        lambda role_name, user_id, chat_id: calls.append((role_name, user_id, chat_id)),
    )
    monkeypatch.setattr(scheduler, "_trigger_weekly_report", lambda *args, **kwargs: None)

    results = scheduler.run_due_jobs(
        now=datetime(2026, 4, 13, 12, 30),
        roles_path=roles_path,
        state_path=state_path,
    )

    assert calls == [("rolea", "user_rolea", "oc_rolea")]
    assert results == [{"job": "daily_push", "role_name": "rolea", "status": "success", "trigger": "compensation"}]


def test_run_due_jobs_schedules_retry_after_failure_and_retries_later(tmp_path, monkeypatch):
    roles_path = tmp_path / "roles.json"
    roles_path.write_text(
        json.dumps(
            {"roles": {"rolea": {"user_id": "user_rolea", "feishu_chat_id": "oc_rolea"}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    state_path = tmp_path / "scheduler_state.json"

    monkeypatch.setenv("PAPERFLOW_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("PAPERFLOW_DAILY_PUSH_TIME", "09:00")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_GRACE_MINUTES", "10")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_MAX_RETRIES", "2")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_RETRY_BACKOFF_MINUTES", "15")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_DAILY_COMPENSATION_HOURS", "0")
    monkeypatch.setenv("PAPERFLOW_SCHEDULER_WEEKLY_COMPENSATION_HOURS", "0")

    calls = {"count": 0}

    def flaky_daily_push(role_name, user_id, chat_id):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary failure")

    monkeypatch.setattr(scheduler, "_trigger_daily_push", flaky_daily_push)
    monkeypatch.setattr(scheduler, "_trigger_weekly_report", lambda *args, **kwargs: None)
    monkeypatch.setattr(scheduler, "_send_scheduler_alert", lambda *args, **kwargs: None)

    first = scheduler.run_due_jobs(
        now=datetime(2026, 4, 13, 9, 5),
        roles_path=roles_path,
        state_path=state_path,
    )
    state_after_first = scheduler.load_scheduler_state(state_path)

    assert first == [
        {
            "job": "daily_push",
            "role_name": "rolea",
            "status": "error",
            "trigger": "scheduled",
            "retry_scheduled": True,
        }
    ]
    assert "daily_push:rolea" in state_after_first["retries"]

    second = scheduler.run_due_jobs(
        now=datetime(2026, 4, 13, 9, 21),
        roles_path=roles_path,
        state_path=state_path,
    )
    state_after_second = scheduler.load_scheduler_state(state_path)

    assert second == [
        {
            "job": "daily_push",
            "role_name": "rolea",
            "status": "success",
            "trigger": "retry",
        }
    ]
    assert "daily_push:rolea" not in state_after_second["retries"]
    assert state_after_second["jobs"]["daily_push:rolea"] == "2026-04-13"


def test_scheduler_status_snapshot_exposes_runtime_and_retry_state(tmp_path, monkeypatch):
    state_path = tmp_path / "scheduler_state.json"
    scheduler.save_scheduler_state(
        {
            "jobs": {"daily_push:rolea": "2026-04-13"},
            "retries": {"weekly_report:rolea": {"marker": "2026-W16", "attempts": 1}},
            "runtime": {"heartbeat_at": "2026-04-13T09:05:00"},
        },
        state_path,
    )

    monkeypatch.setenv("PAPERFLOW_SCHEDULER_ENABLED", "true")

    snapshot = scheduler.get_scheduler_status_snapshot(state_path)

    assert snapshot["enabled"] is True
    assert snapshot["completed_markers"]["daily_push:rolea"] == "2026-04-13"
    assert snapshot["retry_jobs"]["weekly_report:rolea"]["attempts"] == 1
    assert snapshot["runtime"]["heartbeat_at"] == "2026-04-13T09:05:00"
