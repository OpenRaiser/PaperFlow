import importlib.util
import json
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
SCHEDULER_PATH = PROJECT_ROOT / "services" / "webhook-server" / "scripts" / "scheduler.py"

spec = importlib.util.spec_from_file_location("scitaste_scheduler_test", SCHEDULER_PATH)
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

    monkeypatch.setenv("SCITASTE_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("SCITASTE_TIMEZONE", "Asia/Shanghai")
    monkeypatch.setenv("SCITASTE_DAILY_PUSH_TIME", "09:00")
    monkeypatch.setenv("SCITASTE_WEEKLY_REPORT_TIME", "10:00")
    monkeypatch.setenv("SCITASTE_WEEKLY_REPORT_WEEKDAY", "0")
    monkeypatch.setenv("SCITASTE_SCHEDULER_GRACE_MINUTES", "10")

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

    monkeypatch.setenv("SCITASTE_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("SCITASTE_TIMEZONE", "Asia/Shanghai")
    monkeypatch.setenv("SCITASTE_DAILY_PUSH_TIME", "09:00")
    monkeypatch.setenv("SCITASTE_WEEKLY_REPORT_TIME", "10:00")
    monkeypatch.setenv("SCITASTE_WEEKLY_REPORT_WEEKDAY", "0")
    monkeypatch.setenv("SCITASTE_SCHEDULER_GRACE_MINUTES", "10")

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
    assert monday_results == [{"job": "weekly_report", "role_name": "rolea", "status": "success"}]
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

    monkeypatch.setenv("SCITASTE_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("SCITASTE_TIMEZONE", "Asia/Shanghai")
    monkeypatch.setenv("SCITASTE_DAILY_PUSH_TIME", "09:00")
    monkeypatch.setenv("SCITASTE_WEEKLY_REPORT_TIME", "10:00")
    monkeypatch.setenv("SCITASTE_WEEKLY_REPORT_WEEKDAY", "0")
    monkeypatch.setenv("SCITASTE_SCHEDULER_GRACE_MINUTES", "10")

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

    monkeypatch.setenv("SCITASTE_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("SCITASTE_DAILY_PUSH_TIME", "09:00")
    monkeypatch.setenv("SCITASTE_SCHEDULER_GRACE_MINUTES", "10")

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
