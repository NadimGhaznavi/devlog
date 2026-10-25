from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from devlog.activity.TaskHistory import TaskHistory
from devlog.entity.TrackingError import TrackingError


@pytest.mark.parametrize("value, expected", [
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


@pytest.mark.parametrize("value", ["garbage", "", "2026-11-01T01:30", "2026-03-08T02:30"])
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
