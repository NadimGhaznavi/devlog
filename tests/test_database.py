from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from zoneinfo import ZoneInfo

import pytest

from devlog.activity.Report import Report
from devlog.activity.TaskHistory import TaskHistory
from devlog.entity.TrackingError import TrackingError
from devlog.interface.DbMgr import DbMgr
from devlog.interface.TaskDb import TaskDb


pytestmark = pytest.mark.database
A, B = "github.com/example/a", "github.com/example/b"


def test_status_is_global_and_read_only(tasks):
    def status(expected):
        before = {table: tasks.db.query(f"SELECT * FROM {table}")
                  for table in ("repositories", "tasks", "intervals", "tracker_state")}
        assert tasks.status() == expected
        assert {table: tasks.db.query(f"SELECT * FROM {table}") for table in before} == before

    status({"task_id": None, "repository": None})
    first = tasks.start(A)["task_id"]
    status({"task_id": first, "repository": A})
    second = tasks.start(B)["task_id"]
    status({"task_id": second, "repository": B})
    tasks.pause(B)
    status({"task_id": None, "repository": None})
    tasks.start(A)
    status({"task_id": first, "repository": A})
    tasks.complete(A, first, "a" * 40, "done")
    status({"task_id": None, "repository": None})


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
    assert report["days"] == [dict(date="2026-10-24", hours=3, projects={A: 2, B: 1},
                                   task_hours={A: [2], B: [1]})]
    report = Report(tasks, ZoneInfo("UTC")).read(repository=A, start="2026-10-24", end="2026-10-24", now=t(15).replace(tzinfo=timezone.utc))
    assert report["total_hours"] == 2
    assert report["days"] == [dict(date="2026-10-24", hours=2, projects={A: 2}, task_hours={A: [2]})]
    assert tasks.start(A, now=t(16))["task_id"] != first
    report = Report(tasks, ZoneInfo("UTC")).read(
        repository=A, start="2026-10-24", end="2026-10-24", now=t(19).replace(tzinfo=timezone.utc))
    assert report["days"] == [dict(date="2026-10-24", hours=5, projects={A: 5}, task_hours={A: [2, 3]})]


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
    assert report["days"][0]["task_hours"] == {A: [hours]}


def test_midnight_splits_and_open_intervals_survive_new_connection(tasks, db_options):
    tasks.start(A, now=datetime(2026, 10, 24, 3, 30))
    with DbMgr(**db_options) as db:
        report = Report(TaskDb(db), ZoneInfo("America/Toronto")).read(
            start="2026-10-23", end="2026-10-24", now=datetime(2026, 10, 24, 5, tzinfo=timezone.utc))
    assert [day["hours"] for day in report["days"]] == [.5, 1]
    assert [day["projects"] for day in report["days"]] == [{A: .5}, {A: 1}]
    assert [day["task_hours"] for day in report["days"]] == [{A: [.5]}, {A: [1]}]


def test_project_stacks_across_midnight_and_empty_days(tasks):
    tasks.start(A, now=datetime(2026, 10, 24, 23))
    tasks.start(B, now=datetime(2026, 10, 25, 1))
    report = Report(tasks, ZoneInfo("UTC")).read(
        start="2026-10-23", end="2026-10-26", now=datetime(2026, 10, 25, 3, tzinfo=timezone.utc))
    assert report["days"] == [
        dict(date="2026-10-23", hours=0, projects={}, task_hours={}),
        dict(date="2026-10-24", hours=1, projects={A: 1}, task_hours={A: [1]}),
        dict(date="2026-10-25", hours=3, projects={A: 1, B: 2}, task_hours={A: [1], B: [2]}),
        dict(date="2026-10-26", hours=0, projects={}, task_hours={}),
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


def overnight_task(tasks):
    task_id = tasks.start(A, now=datetime(2026, 10, 25, 1))["task_id"]  # 21:00 Toronto
    tasks.complete(A, task_id, "e" * 40, "Overnight task", now=datetime(2026, 10, 25, 13))
    interval_id = tasks.task_detail(task_id)["intervals"][0]["interval_id"]
    return task_id, interval_id


def test_insert_overnight_pause_recalculates_days_and_preserves_commit(tasks):
    task_id, interval_id = overnight_task(tasks)
    before = tasks.task_detail(task_id)
    history = TaskHistory(tasks, ZoneInfo("America/Toronto"))
    history.insert_pause(task_id, dict(interval_id=str(interval_id), pause_start="2026-10-24T22:00",
                                       pause_end="2026-10-25T08:00"))
    report = Report(tasks, history.zone).read(start="2026-10-24", end="2026-10-25")
    assert [day["hours"] for day in report["days"]] == [1, 1]
    assert [day["task_hours"] for day in report["days"]] == [{A: [1]}, {A: [1]}]
    assert report["total_hours"] == 2
    detail = tasks.task_detail(task_id)
    assert {k: v for k, v in detail.items() if k != "intervals"} == {
        k: v for k, v in before.items() if k != "intervals"}
    timeline = history.read(task_id)["timeline"]
    assert len(timeline) == 3
    assert timeline[1] == dict(interval_id=None, started_at="2026-10-24 22:00:00",
                               ended_at="2026-10-25 08:00:00", elapsed_time="10:00:00")
    assert [task["task_id"] for task in history.list(day="2026-10-25")["tasks"]] == [task_id]
    assert history.list(day="2026-10-25")["tasks"][0]["hours"] == 1
    other = tasks.start(B, now=datetime(2026, 10, 25, 14))["task_id"]
    tasks.pause(B, now=datetime(2026, 10, 25, 15))
    filtered = history.list(day="2026-10-25", repository=B)["tasks"]
    assert [(task["task_id"], task["hours"]) for task in filtered] == [(other, 1)]
    with pytest.raises(TrackingError, match="pause_conflict"):
        history.insert_pause(task_id, dict(interval_id=str(interval_id), pause_start="2026-10-24T22:00",
                                           pause_end="2026-10-25T08:00"))


@pytest.mark.parametrize("start,end,expected", [
    (datetime(2026, 10, 25, 2), None, [(datetime(2026, 10, 25, 1), datetime(2026, 10, 25, 2))]),
    (datetime(2026, 10, 25, 1), datetime(2026, 10, 25, 12),
     [(datetime(2026, 10, 25, 12), datetime(2026, 10, 25, 13))]),
    (datetime(2026, 10, 25, 1), None, []),
])
def test_pause_can_trim_either_edge_or_exclude_the_whole_interval(tasks, start, end, expected):
    task_id, interval_id = overnight_task(tasks)
    tasks.insert_pause(task_id, interval_id, start, end)
    assert [(i["started_at"], i["ended_at"]) for i in tasks.task_detail(task_id)["intervals"]] == expected
    # Even a task with all active time removed remains discoverable.
    assert TaskHistory(tasks, ZoneInfo("UTC")).list(day="2026-10-25")["tasks"][0]["task_id"] == task_id


@pytest.mark.parametrize("start,end", [
    (datetime(2026, 10, 25, 0), datetime(2026, 10, 25, 2)),
    (datetime(2026, 10, 25, 2), datetime(2026, 10, 25, 14)),
    (datetime(2026, 10, 25, 3), datetime(2026, 10, 25, 2)),
    (datetime(2026, 10, 25, 2), datetime(2026, 10, 25, 2)),
])
def test_invalid_pause_leaves_intervals_unchanged(tasks, start, end):
    task_id, interval_id = overnight_task(tasks)
    before = tasks.task_detail(task_id)
    with pytest.raises(TrackingError, match="bad_pause"):
        tasks.insert_pause(task_id, interval_id, start, end)
    assert tasks.task_detail(task_id) == before


def test_pause_replacement_rolls_back_on_failure(tasks, monkeypatch):
    task_id, interval_id = overnight_task(tasks)
    before = tasks.task_detail(task_id)
    insert = tasks.db.insert
    writes = []

    def fail_second_interval(sql, params=()):
        writes.append(params)
        if len(writes) == 2:
            raise RuntimeError("injected interval failure")
        return insert(sql, params)

    monkeypatch.setattr(tasks.db, "insert", fail_second_interval)
    with pytest.raises(RuntimeError, match="injected"):
        tasks.insert_pause(task_id, interval_id, datetime(2026, 10, 25, 2), datetime(2026, 10, 25, 12))
    assert tasks.task_detail(task_id) == before


def test_corrections_leave_active_timer_intact_and_reject_open_or_wrong_task_intervals(tasks):
    old, old_interval = overnight_task(tasks)
    active = tasks.start(B, now=datetime(2026, 10, 25, 14))["task_id"]
    open_interval = tasks.task_detail(active)["intervals"][0]["interval_id"]
    for task_id, interval_id in ((active, open_interval), (active, old_interval)):
        with pytest.raises(TrackingError, match="pause_conflict"):
            tasks.insert_pause(task_id, interval_id, datetime(2026, 10, 25, 15), None)
    tasks.insert_pause(old, old_interval, datetime(2026, 10, 25, 2), None)
    assert tasks.db.query("SELECT active_task_id FROM tracker_state")[0]["active_task_id"] == active
    assert tasks.task_detail(active)["intervals"][0]["ended_at"] is None


def test_task_drilldown_uses_local_midnight_as_an_exclusive_end(tasks):
    task_id = tasks.start(A, now=datetime(2026, 10, 24, 23))["task_id"]
    tasks.complete(A, task_id, "f" * 40, "Before midnight", now=datetime(2026, 10, 25, 4))
    history = TaskHistory(tasks, ZoneInfo("America/Toronto"))
    assert history.list(day="2026-10-24")["tasks"][0]["hours"] == 5
    assert history.list(day="2026-10-25")["tasks"] == []
