from datetime import date, datetime, time, timedelta, timezone

from devlog.constants.DTracking import DTracking


class Report:
    def __init__(self, tasks, zone):
        self.tasks = tasks
        self.zone = zone

    def read(self, *, repository="", start="", end="", now=None):
        now = now or datetime.now(timezone.utc)
        last = date.fromisoformat(end) if end else now.astimezone(self.zone).date()
        first = date.fromisoformat(start) if start else last - timedelta(days=DTracking.REPORT_DAYS - 1)
        if first > last or (last - first).days >= DTracking.MAX_REPORT_DAYS:
            raise ValueError("Invalid report range")
        days = []
        day = first
        while day <= last:
            lower = datetime.combine(day, time.min, self.zone).astimezone(timezone.utc).replace(tzinfo=None)
            upper = datetime.combine(day + timedelta(days=1), time.min, self.zone).astimezone(timezone.utc).replace(tzinfo=None)
            days.append((day.isoformat(), lower, upper))
            day += timedelta(days=1)
        with self.tasks.db.transaction(read_only=True):
            repositories = self.tasks.repositories()
            if repository and repository not in repositories:
                raise ValueError("Unknown repository")
            totals = self.tasks.daily_totals(days, repository, now.astimezone(timezone.utc).replace(tzinfo=None))
        return dict(repositories=repositories, repository=repository, start=first.isoformat(), end=last.isoformat(),
                    days=totals, total_hours=sum(day["hours"] for day in totals), timezone=str(self.zone))
