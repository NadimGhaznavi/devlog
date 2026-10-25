from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from devlog.activity.TaskHistory import TaskHistory
from devlog.entity.TrackingError import TrackingError


@pytest.mark.parametrize("value, expected", [
    ("2026-10-24 22:30", datetime(2026, 10, 25, 2, 30)),
    ("2026-10-25 08:00", datetime(2026, 10, 25, 12)),
    ("2026-11-01 01:30-04:00", datetime(2026, 11, 1, 5, 30)),
    ("2026-10-24T22:30", datetime(2026, 10, 25, 2, 30)),
    ("2026-10-25T08:00:00-04:00", datetime(2026, 10, 25, 12)),
    ("2026-11-01T01:30:00-04:00", datetime(2026, 11, 1, 5, 30)),
    ("2026-11-01T01:30:00-05:00", datetime(2026, 11, 1, 6, 30)),
])
def test_pause_inputs_use_report_timezone_and_explicit_dst_offsets(value, expected):
    calls = []
    history = TaskHistory(SimpleNamespace(insert_pause=lambda *args: calls.append(args)), ZoneInfo("America/Toronto"))
    history.insert_pause(1, dict(interval_id="2", pause_start=value, pause_end=""))
    assert calls == [(1, 2, expected, None)]


@pytest.mark.parametrize("value", ["garbage", "", "2026-11-01 01:30", "2026-03-08 02:30",
                                 "2026-11-01T01:30", "2026-03-08T02:30"])
def test_invalid_or_ambiguous_times_cannot_write(value):
    history = TaskHistory(None, ZoneInfo("America/Toronto"))
    with pytest.raises(TrackingError, match="bad_time"):
        history.insert_pause(1, dict(interval_id="2", pause_start=value, pause_end=""))


@pytest.mark.parametrize("payload", [
    dict(interval_id="0", pause_start="2026-10-24T10:00", pause_end=""),
    dict(interval_id="x", pause_start="2026-10-24T10:00", pause_end=""),
    dict(interval_id="2", pause_start="2026-10-24T10:00"),
    dict(interval_id="2", pause_start="2026-10-24T10:00", pause_end="", extra="x"),
])
def test_pause_form_schema_is_validated_before_writing(payload):
    with pytest.raises(TrackingError, match="bad_edit"):
        TaskHistory(None, ZoneInfo("UTC")).insert_pause(1, payload)


@pytest.mark.parametrize("paused", [False, True])
@pytest.mark.parametrize("start,end,local_start,local_end,elapsed", [
    (datetime(2026, 10, 25, 2, 21, 21, 836282), datetime(2026, 10, 25, 8, 50, 29, 208005),
     "2026-10-24 22:21:21", "2026-10-25 04:50:29", "06:29:07"),
    (datetime(2026, 3, 8, 6, 30), datetime(2026, 3, 8, 7, 30),
     "2026-03-08 01:30:00", "2026-03-08 03:30:00", "01:00:00"),
    (datetime(2026, 11, 1, 5, 30), datetime(2026, 11, 1, 6, 30),
     "2026-11-01 01:30:00", "2026-11-01 01:30:00", "01:00:00"),
    (datetime(2026, 10, 24, 1), datetime(2026, 10, 25, 13),
     "2026-10-23 21:00:00", "2026-10-25 09:00:00", "36:00:00"),
])
def test_history_formats_local_times_and_actual_elapsed_duration(start, end, local_start, local_end, elapsed, paused):
    tasks = SimpleNamespace(task_detail=lambda task_id: dict(
        started_at=start, completed_at=end, status="completed",
        intervals=[] if paused else [dict(interval_id=1, started_at=start, ended_at=end)]))
    detail = TaskHistory(tasks, ZoneInfo("America/Toronto")).read(1)
    assert detail["started_at"] == local_start
    assert detail["completed_at"] == local_end
    assert detail["timeline"] == [dict(interval_id=None if paused else 1, started_at=local_start, ended_at=local_end,
                                       elapsed_time=elapsed)]
    assert detail["total_hours"] == (0 if paused else (end - start).total_seconds() / 3600)


def test_running_interval_elapsed_excludes_previous_pause():
    start, resume, now = datetime(2026, 10, 25, 1), datetime(2026, 10, 25, 3), datetime(2026, 10, 25, 4, 2, 3)
    tasks = SimpleNamespace(task_detail=lambda task_id: dict(
        started_at=start, completed_at=None, status="running",
        intervals=[dict(interval_id=1, started_at=start, ended_at=datetime(2026, 10, 25, 2)),
                   dict(interval_id=2, started_at=resume, ended_at=None)]))
    detail = TaskHistory(tasks, ZoneInfo("America/Toronto")).read(1, now=now)
    assert detail["timeline"] == [
        dict(interval_id=1, started_at="2026-10-24 21:00:00", ended_at="2026-10-24 22:00:00", elapsed_time="01:00:00"),
        dict(interval_id=None, started_at="2026-10-24 22:00:00", ended_at="2026-10-24 23:00:00", elapsed_time="01:00:00"),
        dict(interval_id=2, started_at="2026-10-24 23:00:00", ended_at=None, elapsed_time="01:02:03"),
    ]
    assert detail["total_hours"] == 1 + (now - resume).total_seconds() / 3600


def test_ongoing_pause_elapsed_excludes_pauses_from_task_total():
    tasks = SimpleNamespace(task_detail=lambda task_id: dict(
        started_at=datetime(2026, 10, 25, 0), completed_at=None, status="paused",
        intervals=[dict(interval_id=1, started_at=datetime(2026, 10, 25, 1), ended_at=datetime(2026, 10, 25, 2))]))
    detail = TaskHistory(tasks, ZoneInfo("America/Toronto")).read(1, now=datetime(2026, 10, 25, 4, 2, 3))
    assert detail["timeline"] == [
        dict(interval_id=None, started_at="2026-10-24 20:00:00", ended_at="2026-10-24 21:00:00", elapsed_time="01:00:00"),
        dict(interval_id=1, started_at="2026-10-24 21:00:00", ended_at="2026-10-24 22:00:00", elapsed_time="01:00:00"),
        dict(interval_id=None, started_at="2026-10-24 22:00:00", ended_at=None, elapsed_time="02:02:03"),
    ]
    assert detail["total_hours"] == 1
