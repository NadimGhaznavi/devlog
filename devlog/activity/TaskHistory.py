"""Present task history and validate retrospective pauses in the report timezone."""

from datetime import datetime, timezone

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

    def read(self, task_id, *, now=None):
        task = self.tasks.task_detail(task_id)
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        timeline, total = [], 0
        cursor = task["started_at"]
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
                    total_hours=total / 3600, timezone=str(self.zone))

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
