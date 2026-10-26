"""Present task history and validate retrospective pauses in the report timezone."""

from datetime import datetime, timedelta, timezone

from devlog.activity.Report import Report
from devlog.constants.DText import DText
from devlog.constants.DTracking import DTracking, TaskStatus
from devlog.entity.TrackingError import TrackingError


class TaskHistory:
    def __init__(self, tasks, zone):
        self.tasks = tasks
        self.zone = zone

    def _time(self, value):
        return value.replace(tzinfo=timezone.utc).astimezone(self.zone).strftime(DTracking.HISTORY_TIME_FORMAT)

    def _present(self, row):
        return {key: self._time(value) if isinstance(value, datetime) else value for key, value in row.items()}

    def list(self, *, day="", **filters):
        if day:
            filters.update(start=day, end=day)
        report = Report(self.tasks, self.zone).read(include_tasks=True, **filters)
        report["tasks"] = [self._present(task) for task in report["tasks"]]
        return report

    def read(self, task_id, *, now=None, include_editor=False):
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        task = self.tasks.task_detail(task_id, context_at=now) if include_editor else self.tasks.task_detail(task_id)
        editor = None
        if include_editor and task["status"] == TaskStatus.COMPLETED:
            context = task.pop("context")
            revision = task.pop(DTracking.REVISION)
            if (task["intervals"] and len(task["intervals"]) <= DTracking.MAX_TIMING_INTERVALS
                    and all(i["ended_at"] and i["started_at"] < i["ended_at"] <= now
                            for i in task["intervals"])):
                def wire(row):
                    return {key: str(value) if key in {DTracking.INTERVAL_ID, DTracking.TASK_ID}
                            else value.replace(tzinfo=timezone.utc).isoformat()
                            if isinstance(value, datetime) else value for key, value in row.items()}

                anchor = min(task["started_at"], task["intervals"][0]["started_at"])
                lower = min([anchor, *(i["started_at"] for i in context)])
                if not any(i["ended_at"] is not None and i["ended_at"] <= anchor for i in context):
                    lower = min(lower, anchor - timedelta(seconds=DTracking.TIMING_CONTEXT_SECONDS))
                editor = dict(task_id=str(task_id), revision=revision, loaded_at=wire({"time": now})["time"],
                              range_start=wire({"time": lower})["time"],
                              completed_at=wire({"time": task["completed_at"]})["time"],
                              timezone=str(self.zone), intervals=[wire(i) for i in task["intervals"]],
                              context=[wire(i) for i in context])
        timeline, total = [], 0
        cursor = min([task["started_at"], *(i["started_at"] for i in task["intervals"])])
        for interval in task.pop("intervals"):
            if cursor < interval["started_at"]:
                timeline.append(dict(interval_id=None, started_at=cursor, ended_at=interval["started_at"]))
            cursor = interval["ended_at"] or now
            timeline.append(dict(interval))
        end = task["completed_at"] or now
        if cursor < end and task["status"] != TaskStatus.RUNNING:
            timeline.append(dict(interval_id=None, started_at=cursor, ended_at=task["completed_at"]))
        for interval in timeline:
            elapsed = ((interval["ended_at"] or now) - interval["started_at"]).total_seconds()
            hours, remainder = divmod(int(elapsed), 3600)
            minutes, seconds = divmod(remainder, 60)
            interval["elapsed_time"] = f"{hours:02}:{minutes:02}:{seconds:02}"
            if interval["interval_id"]:
                total += elapsed
        return dict(self._present(task), timeline=[self._present(row) for row in timeline],
                    total_hours=total / 3600, timezone=str(self.zone), editor=editor)

    def _parse_time(self, value):
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                local = parsed.replace(tzinfo=self.zone)
                # Ambiguous/nonexistent wall times need an explicit UTC offset.
                if (local.utcoffset() != local.replace(fold=1).utcoffset()
                        or local.astimezone(timezone.utc).astimezone(self.zone).replace(tzinfo=None) != parsed):
                    raise ValueError("Use an explicit UTC offset")
                parsed = local
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        except (ValueError, OverflowError) as error:
            raise TrackingError("bad_time", DText.BAD_TIME) from error

    def insert_pause(self, task_id, payload):
        if set(payload) != {DTracking.INTERVAL_ID, DTracking.PAUSE_START, DTracking.PAUSE_END}:
            raise TrackingError("bad_edit", DText.BAD_EDIT)
        try:
            interval_id = int(payload[DTracking.INTERVAL_ID])
            if interval_id <= 0:
                raise ValueError("Invalid interval")
        except ValueError as error:
            raise TrackingError("bad_edit", DText.BAD_EDIT) from error
        start = self._parse_time(payload[DTracking.PAUSE_START].strip())
        until = payload[DTracking.PAUSE_END].strip()
        self.tasks.insert_pause(task_id, interval_id, start, self._parse_time(until) if until else None)

    def save_timing(self, task_id, payload):
        fields = {DTracking.REVISION, DTracking.LOADED_AT, DTracking.INTERVALS}
        interval_fields = {DTracking.INTERVAL_ID, DTracking.STARTED_AT, DTracking.ENDED_AT}
        if (not isinstance(payload, dict) or set(payload) != fields
                or not isinstance(payload[DTracking.REVISION], str)
                or len(payload[DTracking.REVISION]) != 64
                or any(c not in "0123456789abcdef" for c in payload[DTracking.REVISION])
                or not isinstance(payload[DTracking.INTERVALS], list)
                or not 0 < len(payload[DTracking.INTERVALS]) <= DTracking.MAX_TIMING_INTERVALS):
            raise TrackingError("bad_timing", DText.BAD_TIMING)

        def timestamp(value):
            if not isinstance(value, str) or len(value) > 40:
                raise TrackingError("bad_timing", DText.BAD_TIMING)
            try:
                parsed = datetime.fromisoformat(value)
                if parsed.tzinfo is None:
                    raise ValueError("An explicit UTC offset is required")
                result = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                if result.year < DTracking.MIN_TIMING_YEAR:
                    raise ValueError("Timestamp is outside the database range")
                return result
            except (ValueError, OverflowError) as error:
                raise TrackingError("bad_timing", DText.BAD_TIMING) from error

        loaded_at = timestamp(payload[DTracking.LOADED_AT])
        intervals = []
        for row in payload[DTracking.INTERVALS]:
            if (not isinstance(row, dict) or set(row) != interval_fields
                    or not (type(row[DTracking.INTERVAL_ID]) is int
                            or (isinstance(row[DTracking.INTERVAL_ID], str)
                                and row[DTracking.INTERVAL_ID].isascii()
                                and row[DTracking.INTERVAL_ID].isdecimal()
                                and len(row[DTracking.INTERVAL_ID]) <= 20))
                    or not 0 < int(row[DTracking.INTERVAL_ID]) < 2 ** 64):
                raise TrackingError("bad_timing", DText.BAD_TIMING)
            intervals.append({DTracking.INTERVAL_ID: int(row[DTracking.INTERVAL_ID]),
                              DTracking.STARTED_AT: timestamp(row[DTracking.STARTED_AT]),
                              DTracking.ENDED_AT: timestamp(row[DTracking.ENDED_AT])})
        self.tasks.save_timing(task_id, payload[DTracking.REVISION], intervals, loaded_at)
