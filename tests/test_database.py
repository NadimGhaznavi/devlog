from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from zoneinfo import ZoneInfo

import pytest

from devlog.activity.Report import Report
from devlog.entity.TrackingError import TrackingError
from devlog.interface.DbMgr import DbMgr
from devlog.interface.TaskDb import TaskDb


pytestmark = pytest.mark.database
A, B = "github.com/example/a", "github.com/example/b"


def test_switch_resume_pause_commit_and_new_task(tasks):
    t = lambda hour: datetime(2026, 10, 24, hour)
    first = tasks.start(A, now=t(10))["task_id"]
    assert tasks.start(A, now=t(10))["task_id"] == first
    second = tasks.start(B, now=t(11))["task_id"]
    tasks.pause(B, now=t(12))
    assert tasks.start(A, now=t(13))["task_id"] == first
    tasks.pause(B, now=t(13))  # Pausing B must leave A running.
    tasks.complete(A, first, "a" * 40, "完成 ' %s", now=t(14))
    tasks.complete(A, first, "a" * 40, "duplicate ignored", now=t(15))
    assert tasks.db.query("SELECT COUNT(*) AS n FROM intervals WHERE ended_at IS NULL")[0]["n"] == 0
    rows = tasks.db.query("SELECT task_id, status, commit_message FROM tasks ORDER BY task_id")
    assert rows == [dict(task_id=first, status="completed", commit_message="完成 ' %s"),
                    dict(task_id=second, status="paused", commit_message=None)]
    report = Report(tasks, ZoneInfo("UTC")).read(start="2026-10-24", end="2026-10-24", now=t(15).replace(tzinfo=timezone.utc))
    assert report["total_hours"] == 3
    assert report["days"] == [dict(date="2026-10-24", hours=3, projects={A: 2, B: 1})]
    report = Report(tasks, ZoneInfo("UTC")).read(repository=A, start="2026-10-24", end="2026-10-24", now=t(15).replace(tzinfo=timezone.utc))
    assert report["total_hours"] == 2
    assert report["days"] == [dict(date="2026-10-24", hours=2, projects={A: 2})]
    assert tasks.start(A, now=t(16))["task_id"] != first


def test_switch_failure_rolls_back_previous_pause(tasks, monkeypatch):
    first = tasks.start(A)["task_id"]
    insert = tasks.db.insert

    def fail_new_interval(sql, params=()):
        if "INSERT INTO intervals" in sql:
            raise RuntimeError("injected write failure")
        return insert(sql, params)

    monkeypatch.setattr(tasks.db, "insert", fail_new_interval)
    with pytest.raises(RuntimeError, match="injected"):
        tasks.start(B)
    assert tasks.db.query("SELECT active_task_id FROM tracker_state")[0]["active_task_id"] == first
    assert tasks.db.query("SELECT status FROM tasks WHERE task_id = %s", (first,))[0]["status"] == "running"
    assert tasks.db.query("SELECT COUNT(*) AS n FROM intervals WHERE ended_at IS NULL")[0]["n"] == 1
    assert tasks.repositories() == [A]


def test_concurrent_starts_leave_one_active_task(db_options):
    barrier = Barrier(2)

    def start(repository):
        with DbMgr(**db_options) as db:
            barrier.wait(timeout=5)
            return TaskDb(db).start(repository)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(start, name) for name in (A, B)]
        for future in futures:
            future.result(timeout=10)
    with DbMgr(**db_options) as db:
        assert db.query("SELECT COUNT(*) AS n FROM intervals WHERE ended_at IS NULL")[0]["n"] == 1
        assert db.query("SELECT COUNT(*) AS n FROM tasks WHERE status = 'running'")[0]["n"] == 1


@pytest.mark.parametrize("day,start,end,hours", [
    ("2026-03-08", datetime(2026, 3, 8, 5), datetime(2026, 3, 9, 4), 23),
    ("2026-11-01", datetime(2026, 11, 1, 4), datetime(2026, 11, 2, 5), 25),
])
def test_local_days_include_dst(tasks, day, start, end, hours):
    task = tasks.start(A, now=start)
    tasks.complete(A, task["task_id"], "b" * 40, "DST", now=end)
    report = Report(tasks, ZoneInfo("America/Toronto")).read(start=day, end=day, now=end.replace(tzinfo=timezone.utc))
    assert report["total_hours"] == hours
    assert report["days"][0]["projects"] == {A: hours}


def test_midnight_splits_and_open_intervals_survive_new_connection(tasks, db_options):
    tasks.start(A, now=datetime(2026, 10, 24, 3, 30))
    with DbMgr(**db_options) as db:
        report = Report(TaskDb(db), ZoneInfo("America/Toronto")).read(
            start="2026-10-23", end="2026-10-24", now=datetime(2026, 10, 24, 5, tzinfo=timezone.utc))
    assert [day["hours"] for day in report["days"]] == [.5, 1]
    assert [day["projects"] for day in report["days"]] == [{A: .5}, {A: 1}]


def test_project_stacks_across_midnight_and_empty_days(tasks):
    tasks.start(A, now=datetime(2026, 10, 24, 23))
    tasks.start(B, now=datetime(2026, 10, 25, 1))
    report = Report(tasks, ZoneInfo("UTC")).read(
        start="2026-10-23", end="2026-10-26", now=datetime(2026, 10, 25, 3, tzinfo=timezone.utc))
    assert report["days"] == [
        dict(date="2026-10-23", hours=0, projects={}),
        dict(date="2026-10-24", hours=1, projects={A: 1}),
        dict(date="2026-10-25", hours=3, projects={A: 1, B: 2}),
        dict(date="2026-10-26", hours=0, projects={}),
    ]
    assert report["total_hours"] == 4


def test_reject_missing_task_and_conflicting_completion(tasks):
    with pytest.raises(TrackingError, match="no_task"):
        tasks.prepare_commit(A)
    task = tasks.start(A)["task_id"]
    tasks.complete(A, task, "c" * 40, "done")
    assert tasks.prepare_commit(A, commit_sha="c" * 40)["status"] == "completed"
    with pytest.raises(TrackingError, match="task_conflict"):
        tasks.complete(A, task, "d" * 40, "wrong")


def test_manager_transaction_rollback_and_parameters(tasks):
    before = tasks.db.query("SELECT COUNT(*) AS n FROM repositories")[0]["n"]
    with pytest.raises(RuntimeError):
        with tasks.db.transaction():
            tasks.db.insert("INSERT INTO repositories (identity) VALUES (%s)", ("Unicode 完成 ' OR 1=1",))
            raise RuntimeError("rollback")
    assert tasks.db.query("SELECT COUNT(*) AS n FROM repositories")[0]["n"] == before
