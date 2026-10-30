"""Completed-task timing corrections across validation, storage and HTTP."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pytest

from devlog.activity.Report import Report
from devlog.activity.TaskHistory import TaskHistory
from devlog.entity.TrackingError import TrackingError


A, B = "github.com/example/edited", "github.com/example/previous"
BASE = datetime(2026, 10, 24)


def at(hour):
    return BASE + timedelta(hours=hour)


def completed_task(tasks):
    task_id = tasks.start(A, now=at(12))["task_id"]
    tasks.pause(A, now=at(14))
    tasks.start(A, now=at(15))
    tasks.complete(A, task_id, "a" * 40, "Keep this commit", now=at(17))
    # Deliberately create the chronological predecessor with a greater task ID.
    previous = tasks.start(B, now=at(10))["task_id"]
    tasks.complete(B, previous, "b" * 40, "Previous", now=at(11))
    return task_id, previous


def editor_payload(tasks, task_id, now=None):
    editor = TaskHistory(tasks, ZoneInfo("UTC")).read(task_id, now=now, include_editor=True)["editor"]
    return {key: deepcopy(editor[key]) for key in ("revision", "loaded_at", "intervals")}


def utc(value):
    return value.replace(tzinfo=timezone.utc).isoformat()


@pytest.mark.parametrize("payload", [None, [], {},
    {"revision": "x" * 64, "loaded_at": utc(at(20)), "intervals": []},
    {"revision": "a" * 64, "loaded_at": utc(at(20)), "intervals": [
        {"interval_id": True, "started_at": utc(at(12)), "ended_at": utc(at(13))}]},
    {"revision": "a" * 64, "loaded_at": utc(at(20)), "intervals": [
        {"interval_id": 1, "started_at": "2026-11-01T01:30:00", "ended_at": utc(at(13))}]},
    {"revision": "a" * 64, "loaded_at": 123, "intervals": [
        {"interval_id": 1, "started_at": utc(at(12)), "ended_at": utc(at(13))}]},
])
def test_invalid_timing_payloads_cannot_reach_storage(payload):
    history = TaskHistory(SimpleNamespace(), ZoneInfo("UTC"))
    with pytest.raises(TrackingError, match="bad_timing"):
        history.save_timing(1, payload)


def test_offset_timestamps_and_large_ids_preserve_exact_values():
    calls = []
    history = TaskHistory(SimpleNamespace(save_timing=lambda *args: calls.append(args)), ZoneInfo("America/Toronto"))
    history.save_timing(1, {"revision": "a" * 64, "loaded_at": "2026-11-02T00:00:00Z", "intervals": [
        {"interval_id": "18446744073709551614", "started_at": "2026-11-01T01:30:00.123456-04:00",
         "ended_at": "2026-11-01T01:30:00.123456-05:00"}]})
    row = calls[0][2][0]
    assert row["interval_id"] == 18446744073709551614
    assert row["started_at"] == datetime(2026, 11, 1, 5, 30, 0, 123456)
    assert row["ended_at"] - row["started_at"] == timedelta(hours=1)


@pytest.mark.database
def test_snapshot_context_and_four_boundary_corrections_preserve_events(tasks):
    task_id, previous = completed_task(tasks)
    before = tasks.task_detail(task_id)
    detail = TaskHistory(tasks, ZoneInfo("UTC")).read(task_id, now=at(20), include_editor=True)
    assert [row["task_id"] for row in detail["editor"]["context"]] == [str(previous)]
    assert detail["editor"]["loaded_at"] == utc(at(20))
    payload = editor_payload(tasks, task_id, at(20))
    payload["intervals"][0].update(started_at=utc(at(11)), ended_at=utc(at(13)))
    payload["intervals"][1].update(started_at=utc(at(16)), ended_at=utc(at(16.5)))
    TaskHistory(tasks, ZoneInfo("UTC")).save_timing(task_id, payload)
    after = tasks.task_detail(task_id)
    assert {k: v for k, v in after.items() if k != "intervals"} == {
        k: v for k, v in before.items() if k != "intervals"}
    assert [(i["started_at"], i["ended_at"]) for i in after["intervals"]] == [(at(11), at(13)), (at(16), at(16.5))]
    report = Report(tasks, ZoneInfo("UTC")).read(start="2026-10-24", end="2026-10-24", repository=A)
    assert report["total_hours"] == 2.5
    with pytest.raises(TrackingError, match="timing_conflict"):
        TaskHistory(tasks, ZoneInfo("UTC")).save_timing(task_id, payload)


@pytest.mark.database
@pytest.mark.parametrize("change,error", [
    (lambda p: p["intervals"][0].update(started_at=utc(at(10.5))), "timing_overlap"),
    (lambda p: p["intervals"][0].update(ended_at=utc(at(16))), "bad_timing"),
    (lambda p: p["intervals"][0].update(ended_at=utc(at(12))), "bad_timing"),
    (lambda p: p["intervals"][1].update(ended_at=utc(at(21))), "bad_timing"),
    (lambda p: p["intervals"][1].update(ended_at=utc(at(18))), "bad_timing"),
    (lambda p: p["intervals"][0].update(interval_id=99999), "bad_timing"),
    (lambda p: p.update(loaded_at=utc(datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1))), "bad_timing"),
])
def test_invalid_corrections_leave_all_recorded_work_unchanged(tasks, change, error):
    task_id, _ = completed_task(tasks)
    payload = editor_payload(tasks, task_id, at(20))
    before = tasks.db.query("SELECT * FROM intervals ORDER BY interval_id")
    change(payload)
    with pytest.raises(TrackingError, match=error):
        TaskHistory(tasks, ZoneInfo("UTC")).save_timing(task_id, payload)
    assert tasks.db.query("SELECT * FROM intervals ORDER BY interval_id") == before


@pytest.mark.database
def test_conflict_with_work_recorded_after_page_load_and_rollback(tasks, monkeypatch):
    task_id, _ = completed_task(tasks)
    payload = editor_payload(tasks, task_id, at(20))
    new_repo = "github.com/example/new"
    other = tasks.start(new_repo, now=at(14.25))["task_id"]
    tasks.pause(new_repo, now=at(14.75))
    tasks.start(new_repo, now=at(18))
    payload["intervals"][0]["ended_at"] = utc(at(14.5))
    before = tasks.task_detail(task_id)
    with pytest.raises(TrackingError, match="timing_overlap"):
        TaskHistory(tasks, ZoneInfo("UTC")).save_timing(task_id, payload)
    assert tasks.status()["task_id"] == other
    payload["intervals"][0].update(started_at=utc(at(11.5)), ended_at=utc(at(14)))
    payload["intervals"][1]["ended_at"] = utc(at(16.5))
    execute = tasks.db.execute
    writes = 0

    def fail_second_update(sql, params=()):
        nonlocal writes
        if "UPDATE intervals SET started_at" in sql:
            writes += 1
            if writes == 2:
                raise RuntimeError("injected timing write failure")
        return execute(sql, params)

    monkeypatch.setattr(tasks.db, "execute", fail_second_update)
    with pytest.raises(RuntimeError, match="injected timing"):
        TaskHistory(tasks, ZoneInfo("UTC")).save_timing(task_id, payload)
    assert writes == 2
    assert tasks.task_detail(task_id) == before
    assert tasks.status()["task_id"] == other


@pytest.mark.database
def test_corrected_work_before_original_start_remains_discoverable(tasks):
    task_id = tasks.start(A, now=at(12))["task_id"]
    tasks.complete(A, task_id, "a" * 40, "Event metadata", now=at(17))
    payload = editor_payload(tasks, task_id, at(40))
    payload["intervals"][0].update(started_at=utc(at(-1)), ended_at=utc(at(17)))
    history = TaskHistory(tasks, ZoneInfo("UTC"))
    history.save_timing(task_id, payload)
    assert history.list(day="2026-10-23")["tasks"][0]["hours"] == 1
    assert history.list(day="2026-10-24")["tasks"][0]["hours"] == 17
    assert history.read(task_id)["timeline"][0]["started_at"] == "2026-10-23 23:00:00"
    assert tasks.task_detail(task_id)["completed_at"] == at(17)


@pytest.mark.database
def test_unfinished_and_empty_tasks_have_no_completed_editor(tasks):
    task_id = tasks.start(A, now=at(12))["task_id"]
    history = TaskHistory(tasks, ZoneInfo("UTC"))
    assert history.read(task_id, include_editor=True)["editor"] is None
    rows = tasks.task_detail(task_id)["intervals"]
    with pytest.raises(TrackingError, match="timing_conflict"):
        tasks.save_timing(task_id, tasks.timing_revision(tasks.task_detail(task_id)), rows, at(20))
    tasks.complete(A, task_id, "a" * 40, "Done", now=at(17))
    interval_id = tasks.task_detail(task_id)["intervals"][0]["interval_id"]
    tasks.insert_pause(task_id, interval_id, at(12), at(17))
    assert history.read(task_id, include_editor=True)["editor"] is None


@pytest.mark.database
def test_timing_http_save_conflict_and_request_boundaries(service, tasks):
    task_id, _ = completed_task(tasks)
    endpoint = service["url"] + f"/tasks/{task_id}/timing?lang=en"
    payload = editor_payload(tasks, task_id)
    payload["intervals"][1]["ended_at"] = utc(at(16))

    def post(body, headers=None):
        return urlopen(Request(endpoint, data=body, headers=headers or {
            "Origin": service["url"], "Content-Type": "application/json"}))

    for body, headers, status in [
        (b"{}", {"Content-Type": "application/json"}, 403),
        (b"{}", {"Origin": "http://elsewhere.invalid", "Content-Type": "application/json"}, 403),
        (b"{}", {"Origin": service["url"], "Content-Type": "text/plain"}, 400),
        (b"{", None, 400), (b'{"revision":1,"revision":2}', None, 400),
        (b"x" * 262145, None, 400), (b"null", None, 400),
    ]:
        before = tasks.task_detail(task_id)
        with pytest.raises(HTTPError) as error:
            post(body, headers)
        assert error.value.code == status
        assert tasks.task_detail(task_id) == before
    encoded = json.dumps(payload).encode()
    with post(encoded) as response:
        assert response.status == 200
        accepted = json.load(response)
        assert accepted["saved"] is True
        editor = accepted["task"]["editor"]
        assert editor["revision"] != payload["revision"]
        assert editor["intervals"] == payload["intervals"]
        assert accepted["task"]["total_hours"] == 3
        assert accepted["task"]["commit_sha"] == "a" * 40
        assert response.headers["Cache-Control"] == "no-store"
    with pytest.raises(HTTPError) as error:
        post(encoded)
    assert error.value.code == 409
    assert json.load(error.value)["code"] == "error.timing_conflict"

    with urlopen(endpoint) as response:
        snapshot = json.load(response)["task"]
        assert snapshot["editor"]["revision"] == editor["revision"]
        assert snapshot["editor"]["intervals"] == editor["intervals"]
        assert response.headers["Cache-Control"] == "no-store"
    with urlopen(Request(endpoint, method="HEAD")) as response:
        assert response.status == 200 and response.read() == b""
    with pytest.raises(HTTPError) as error:
        urlopen(endpoint + "&group=forged")
    assert error.value.code == 400
