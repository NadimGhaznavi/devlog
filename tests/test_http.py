from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pytest
import pymysql

from conftest import dl
from devlog.activity.Application import Application
from devlog.entity.ServiceUnavailable import ServiceUnavailable
from devlog.interface.Localizer import Localizer
from devlog.interface.ZMQClient import ZMQClient
from devlog.server.main import ReportServer
from devlog.server.ReportHandler import ReportHandler


@contextmanager
def display(application):
    server = ReportServer(("127.0.0.1", 0), ReportHandler)
    server.application = application
    # Unit tests supply an application facade, without the persistent worker supervisor.
    server.service_actions = lambda: None
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": .05})
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class ReportApplication:
    localizer = Localizer(Path(__file__).parents[1] / "devlog/locales")
    config = SimpleNamespace(zone=ZoneInfo("America/Toronto"))
    current_task = dict(task_id=None, repository=None, active_seconds=0)
    total_hours = 2.5

    def report(self, **filters):
        return dict(repositories=['<script>alert("unsafe")</script>'], repository="", start="2026-10-24",
                    end="2026-10-24", timezone="America/Toronto", total_hours=self.total_hours, current_task=self.current_task,
                    days=[dict(date="2026-10-24", hours=self.total_hours,
                               projects={'<script>alert("unsafe")</script>': self.total_hours})])

    def health(self):
        return dict(status="ok", components={"http": "ok", "zmq": "ok", "db-server": "ok"})


class TaskListApplication(ReportApplication):
    total_seconds = 2 * 3600 + 32 * 60
    commit_message = '<script>alert("unsafe")</script>\nKeep the full commit message'

    def daily_task_list(self, **filters):
        return dict(self.task_list(**filters), repositories=["github.com/example/MyCount"])

    def task_list(self, **filters):
        day = filters.get("day")
        return dict(repository=filters.get("repository", ""),
                    start=day or filters.get("start", "2026-10-27"),
                    end=day or filters.get("end", "2026-10-27"),
                    timezone="America/Toronto", total_hours=self.total_seconds / 3600,
                    tasks=[dict(task_id=123, started_at="2026-10-27 09:15:42",
                                repository="github.com/example/MyCount",
                                commit_message=self.commit_message, status="running",
                                hours=self.total_seconds / 3600)])


@pytest.mark.parametrize("seconds, total, duration", [
    (0, "0 seconds", "00:00"),
    (1, "1 second", "00:00"),
    (59.999999, "59 seconds", "00:00"),
    (60, "1 minute", "00:01"),
    (152, "2 minutes 32 seconds", "00:02"),
    (299.999999, "4 minutes 59 seconds", "00:04"),
    (300, "5 minutes", "00:05"),
    (301, "5 minutes", "00:05"),
    (3599, "59 minutes", "00:59"),
    (3600, "1 hour", "01:00"),
    (7260, "2 hours 1 minute", "02:01"),
    (9120, "2 hours 32 minutes", "02:32"),
    (129600, "36 hours", "36:00"),
])
def test_tasks_table_title_total_and_time_formats(seconds, total, duration):
    app = TaskListApplication()
    app.total_seconds = seconds
    query = "?" + urlencode(dict(repository="github.com/example/MyCount", day="2026-10-27", lang="en"))
    with display(app) as url:
        with urlopen(url + "/tasks" + query) as response:
            html = response.read().decode()
    assert '<h1 id="tasks-heading">Repository (MyCount) Tasks - 27 Oct 2026</h1>' in html
    assert '<title>DevLog · Repository (MyCount) Tasks - 27 Oct 2026</title>' in html
    assert f'<div class="total task-total"><span>Total time</span><strong>{total}</strong></div>' in html
    headings = [f'<th scope="col">{label}</th>' for label in ("Task #", "Start Time", "Description", "Duration")]
    assert all(heading in html for heading in headings)
    assert [html.index(heading) for heading in headings] == sorted(html.index(heading) for heading in headings)
    assert '<time>09:15</time>' in html
    assert f'<td>{duration}</td>' in html
    assert '/tasks/123?repository=github.com%2Fexample%2FMyCount&amp;day=2026-10-27&amp;lang=en' in html
    assert 'aria-label="Task #123">123</a>' in html
    assert '&lt;script&gt;alert(&#34;unsafe&#34;)&lt;/script&gt;\nKeep the full commit message' in html
    assert '<script>alert("unsafe")</script>' not in html


@pytest.mark.parametrize("filters, title", [
    ({"day": "2026-10-27"}, "Tasks - 27 Oct 2026"),
    ({"start": "2026-10-26", "end": "2026-10-27"}, "Tasks - 26 Oct 2026 to 27 Oct 2026"),
    ({"repository": "github.com/example/MyCount", "start": "2026-10-26", "end": "2026-10-27"},
     "Repository (MyCount) Tasks - 26 Oct 2026 to 27 Oct 2026"),
])
def test_tasks_title_keeps_day_and_range_navigation_usable(filters, title):
    app = TaskListApplication()
    app.commit_message = None
    with display(app) as url:
        with urlopen(url + "/tasks?" + urlencode(filters)) as response:
            html = response.read().decode()
    assert f'<h1 id="tasks-heading">{title}</h1>' in html
    assert '<td class="task-description">Running</td>' in html


def test_restored_project_name_in_task_title_is_escaped():
    query = urlencode(dict(repository='github.com/example/<img onerror="unsafe">', day="2026-10-27"))
    with display(TaskListApplication()) as url:
        with urlopen(url + "/tasks?" + query) as response:
            html = response.read().decode()
    assert 'Repository (&lt;img onerror=&#34;unsafe&#34;&gt;) Tasks - 27 Oct 2026' in html
    assert '<img onerror="unsafe">' not in html


def test_daily_defaults_to_today_in_configured_timezone_and_preserves_day(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 28, 2, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr("devlog.server.ReportHandler.datetime", Clock)
    calls = []

    class DailyApplication(TaskListApplication):
        def task_list(self, **filters):
            calls.append(filters)
            return super().task_list(**filters)

    with display(DailyApplication()) as url:
        with urlopen(url + "/daily?lang=en") as response:
            html = response.read().decode()
        assert '<h1 id="tasks-heading">Daily Task Report - 27 Oct 2026</h1>' in html
        assert '<title>DevLog · Daily Task Report - 27 Oct 2026</title>' in html
        assert 'href="/daily?day=2026-10-27&amp;lang=en" aria-current="page">Daily</a>' in html
        assert 'name="day" value="2026-10-27" required' in html
        assert '<option value="">*</option>' in html
        assert html.index('id="day"') < html.index('id="project"') < html.index('>Show Report</button>')
        assert '<th scope="col">Task #</th><th scope="col">Project</th><th scope="col">Start Time</th>' in html
        assert '<td>MyCount</td>' in html
        assert '/tasks/123?day=2026-10-27&amp;lang=en' in html
        assert '<span>Total time</span><strong>2 hours 32 minutes</strong>' in html
        with urlopen(Request(url + "/daily?day=2026-10-26&lang=en", method="HEAD")) as response:
            assert response.status == 200 and response.read() == b""
    assert calls == [{"day": "2026-10-27"}, {"day": "2026-10-26"}]


def test_daily_links_drop_repository_and_range_filters():
    with display(TaskListApplication()) as url:
        with urlopen(url + "/tasks?repository=github.com/example/MyCount&start=2026-10-26&end=2026-10-27&day=2026-10-27") as response:
            html = response.read().decode()
        assert 'href="/daily?day=2026-10-27&amp;lang=en">Daily</a>' in html
        with urlopen(url + "/?repository=github.com/example/MyCount&start=2026-10-26&end=2026-10-27") as response:
            html = response.read().decode()
        assert 'href="/daily?lang=en">Daily</a>' in html
        assert 'href="/daily?lang=en&amp;day=2026-10-24">Daily Task Report - 24 Oct 2026</a>' in html
        assert '"dailyUrl": "/daily?lang=en"' in html
        for query in ("end=2026-10-27", "start=2026-10-26", "day=a&day=b"):
            with pytest.raises(HTTPError) as error:
                urlopen(url + "/daily?" + query)
            assert error.value.code == 400


@pytest.mark.database
def test_daily_lists_all_projects_with_hours_clipped_to_local_day(service, tasks):
    for repository, start, end, message in (
        ("previous", datetime(2026, 10, 25, 2), datetime(2026, 10, 25, 3), "Outside before day"),
        ("overnight", datetime(2026, 10, 25, 3), datetime(2026, 10, 25, 5), "Overnight work"),
        ('<img onerror="unsafe">', datetime(2026, 10, 25, 6), datetime(2026, 10, 25, 8), "Second project"),
        ("next", datetime(2026, 10, 26, 4), datetime(2026, 10, 26, 5), "Outside after day"),
    ):
        repository = "github.com/example/" + repository
        task_id = tasks.start(repository, now=start)["task_id"]
        tasks.complete(repository, task_id, "a" * 40, message, now=end)
    with urlopen(service["url"] + "/daily?day=2026-10-25&lang=en") as response:
        html = response.read().decode()
    assert '<h1 id="tasks-heading">Daily Task Report - 25 Oct 2026</h1>' in html
    assert '<span>Total time</span><strong>3 hours</strong>' in html
    assert '<td>overnight</td>' in html and '<td>&lt;img onerror=&#34;unsafe&#34;&gt;</td>' in html
    assert '<td>01:00</td>' in html and '<td>02:00</td>' in html
    assert '<td>previous</td>' not in html and '<td>next</td>' not in html
    assert '<option value="github.com/example/previous"' not in html
    assert '<option value="github.com/example/next"' not in html
    assert '<img onerror="unsafe">' not in html
    with urlopen(service["url"] + "/daily?" + urlencode(dict(
            day="2026-10-25", repository="github.com/example/overnight", lang="en"))) as response:
        html = response.read().decode()
    assert '<option value="github.com/example/overnight" selected>overnight</option>' in html
    assert '<option value="github.com/example/&lt;img onerror=&#34;unsafe&#34;&gt;">' in html
    assert '<td>overnight</td>' in html and '<td>&lt;img' not in html
    assert '<span>Total time</span><strong>1 hour</strong>' in html
    assert 'repository=github.com%2Fexample%2Fovernight&amp;lang=en' in html
    with urlopen(service["url"] + "/daily?" + urlencode(dict(
            day="2026-10-25", repository="github.com/example/next"))) as response:
        html = response.read().decode()
    assert '<span>Total time</span><strong>3 hours</strong>' in html
    assert '<td>overnight</td>' in html and '<td>&lt;img' in html
    assert 'repository=github.com%2Fexample%2Fnext' not in html
    for day in ("2026-10-27", "2026-10-24"):
        with urlopen(service["url"] + "/daily?day=" + day) as response:
            html = response.read().decode()
        if day == "2026-10-27":
            assert 'class="empty"' in html and '<strong>0 seconds</strong>' in html
        else:
            assert '<span>Total time</span><strong>2 hours</strong>' in html
            assert '<td>overnight</td>' in html and '<td>previous</td>' in html
    with pytest.raises(HTTPError) as error:
        urlopen(service["url"] + "/daily?day=2026-02-30")
    assert error.value.code == 400
    with pytest.raises(HTTPError) as error:
        urlopen(service["url"] + "/daily?day=2026-10-25&repository=unknown")
    assert error.value.code == 400


def test_report_html_json_head_and_asset_boundaries():
    with display(ReportApplication()) as url:
        with urlopen(url) as response:
            body = response.read()
            length = int(response.headers["Content-Length"])
            assert len(body) == length
            assert b"plotly-4.1.1.min.js" in body
            assert b'<span>Total hours</span><strong>02:30</strong>' in body
            assert b'<h1 class="panel-title" id="daily-title">Daily Tasks</h1>' in body
            assert b'id="tasks-title"' not in body and b'<table' not in body
            assert b'<p id="current-task-status">No task currently running</p>' in body
            assert body.index(b'id="reporting-title"') < body.index(b'id="current-task-title"') < body.index(b'id="daily-title"')
            assert b"&lt;script&gt;" in body
            assert b'<script>alert("unsafe")</script>' not in body
            assert response.headers["X-Content-Type-Options"] == "nosniff"
        with urlopen(Request(url, method="HEAD")) as response:
            assert response.read() == b""
            assert int(response.headers["Content-Length"]) == length
        with urlopen(url + "/api/report") as response:
            assert json.load(response)["total_hours"] == 2.5
        for path, status in (("/missing", 404), ("/static/../../conf/database.env", 404), ("/?start=a&start=b", 400)):
            with pytest.raises(HTTPError) as error:
                urlopen(url + path)
            assert error.value.code == status
        with pytest.raises(HTTPError) as error:
            urlopen(Request(url + "/api/report", data=b"{", method="POST"))
        assert error.value.code == 501


@pytest.mark.parametrize("hours, duration", [
    (0, "00:00"),
    (59.999999 / 3600, "00:00"),
    (1 / 60, "00:01"),
    (13.53, "13:31"),
    (13 + 31 / 60, "13:31"),
    (1 - 1 / 3600, "00:59"),
    (36.5, "36:30"),
])
def test_report_total_uses_hours_and_completed_minutes(hours, duration):
    app = ReportApplication()
    app.total_hours = hours
    with display(app) as url:
        with urlopen(url) as response:
            html = response.read().decode()
    assert f'<span>Total hours</span><strong>{duration}</strong>' in html


@pytest.mark.parametrize("seconds, duration", [
    (0, "0 seconds"),
    (.1, "1 second"),
    (2.1, "3 seconds"),
    (60, "1 minute"),
    (60.1, "1 minute 1 second"),
    (131.1, "2 minutes 12 seconds"),
    (3599, "59 minutes 59 seconds"),
    (3599.1, "1 hour"),
    (3600, "1 hour"),
    (3600.1, "1 hour 1 minute"),
    (4 * 3600 + 22 * 60 + .1, "4 hours 23 minutes"),
    (5 * 3600 - .1, "5 hours"),
    (36 * 3600, "36 hours"),
])
def test_current_task_uses_short_repository_and_rounded_human_duration(seconds, duration):
    app = ReportApplication()
    app.current_task = dict(task_id=17, repository="github.com/example/bmdynip", active_seconds=seconds)
    with display(app) as url:
        with urlopen(url) as response:
            html = response.read().decode()
    assert f'<p id="current-task-status">Task #17 (bmdynip) running for {duration}</p>' in html


def test_current_task_repository_is_escaped():
    app = ReportApplication()
    app.current_task = dict(task_id=17, repository='github.com/example/<img onerror="unsafe">', active_seconds=3)
    with display(app) as url:
        with urlopen(url) as response:
            html = response.read().decode()
    assert 'Task #17 (&lt;img onerror=&#34;unsafe&#34;&gt;) running for 3 seconds' in html
    assert '<img onerror="unsafe">' not in html


def test_health_and_report_dependency_failures_are_not_success():
    class Unavailable(ReportApplication):
        def health(self):
            return dict(status="error", components={"http": "ok", "zmq": "error", "db-server": "error"})

        def report(self, **filters):
            raise ServiceUnavailable("private database detail")

    with display(Unavailable()) as url:
        for path in ("/health", "/"):
            with pytest.raises(HTTPError) as error:
                urlopen(url + path)
            assert error.value.code == 503
            assert b"private database detail" not in error.value.read()


def test_aggregate_health_uses_application_connections_and_reports_failure(monkeypatch):
    app = Application(SimpleNamespace(database=lambda: {}, local_endpoint="tcp://127.0.0.1:19701", timeout_ms=100))
    app.worker = SimpleNamespace(check=lambda: None)

    class NativeHealth:
        def __init__(self, *args, **kwargs):
            pass

        def call(self, method, payload):
            return {}

    def failed_database(**options):
        raise pymysql.OperationalError(2003, "private database detail")

    monkeypatch.setattr("devlog.activity.Application.ZMQClient", NativeHealth)
    monkeypatch.setattr("devlog.interface.TaskStore.DbMgr", failed_database)
    with display(app) as url:
        with pytest.raises(HTTPError) as error:
            urlopen(url + "/health")
        assert error.value.code == 503
        assert json.load(error.value) == {"status": "error", "components": {
            "http": "ok", "zmq": "ok", "db-server": "error",
        }}


@pytest.mark.database
def test_current_task_is_global_excludes_pauses_and_clears_when_paused(service, tasks):
    repository, other = "github.com/example/bmdynip", "github.com/example/other"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    tasks.start(other, now=now - timedelta(days=1))
    tasks.pause(other, now=now - timedelta(days=1) + timedelta(seconds=3))
    start = now - timedelta(hours=6)
    task_id = tasks.start(repository, now=start)["task_id"]
    tasks.pause(repository, now=start + timedelta(hours=4, minutes=22, seconds=20))
    tasks.start(repository, now=now - timedelta(seconds=5))
    # Both the selected repository and historical dates exclude the running task.
    query = "?" + urlencode(dict(repository=other, start="2020-01-01", end="2020-01-01"))
    with urlopen(service["url"] + query) as response:
        html = response.read().decode()
        assert f'Task #{task_id} (bmdynip) running for 4 hours 23 minutes' in html
    with urlopen(service["url"] + "/api/report" + query) as response:
        report = json.load(response)
        assert report["total_hours"] == 0
        assert report["current_task"]["task_id"] == task_id
        assert report["current_task"]["repository"] == repository
        assert 4 * 3600 + 22 * 60 + 25 <= report["current_task"]["active_seconds"] < 4 * 3600 + 23 * 60
    tasks.pause(repository)
    with urlopen(service["url"] + query) as response:
        assert '<p id="current-task-status">No task currently running</p>' in response.read().decode()


@pytest.mark.database
def test_real_service_reports_commands_and_survives_restart(service, checkout, tasks):
    root, _ = checkout
    result = dl(root, service, "start")
    assert result.returncode == 0, result.stderr
    before = tasks.prepare_commit("github.com/example/project")["task_id"]
    service["process"].terminate()
    assert service["process"].wait(timeout=10) == 0
    service["start"]()
    assert dl(root, service, "start").returncode == 0
    assert tasks.prepare_commit("github.com/example/project")["task_id"] == before
    with urlopen(service["url"] + "/api/report") as response:
        report = json.load(response)
        assert report["repositories"] == ["github.com/example/project"]
        assert len(report["days"]) == 7
        assert report["total_hours"] > 0
    with pytest.raises(HTTPError) as error:
        urlopen(service["url"] + "/?start=2020-01-01&end=2026-01-01")
    assert error.value.code == 400
    client = ZMQClient(service["endpoint"], timeout_ms=1000)
    with pytest.raises(Exception, match="unknown_method"):
        client.call("invented", {"repository": "github.com/example/project"})


@pytest.mark.database
def test_history_drilldown_and_pause_form_recalculate_report(service, tasks):
    repository = "github.com/example/overnight"
    task_id = tasks.start(repository, now=datetime(2026, 10, 25, 1))["task_id"]
    tasks.complete(repository, task_id, "a" * 40, '<script>alert("unsafe")</script>',
                   now=datetime(2026, 10, 25, 13))
    interval = tasks.task_detail(task_id)["intervals"][0]["interval_id"]
    query = "?start=2026-10-24&end=2026-10-25&day=2026-10-25&lang=en"
    with urlopen(service["url"] + "/tasks" + query) as response:
        html = response.read().decode()
        assert f"/tasks/{task_id}?" in html
        assert "&lt;script&gt;" in html
        assert "<span>Total time</span><strong>9 hours</strong>" in html
        assert "<td>09:00</td>" in html
        assert "<time>21:00</time>" in html
    with urlopen(service["url"] + f"/tasks/{task_id}" + query) as response:
        html = response.read().decode()
        assert 'id="timing-editor"' in html and '/static/timing.js' in html
        assert 'name="pause_start"' not in html and 'name="pause_end"' not in html
        assert "America/Toronto" in html and "12.00" in html
        assert "<time>2026-10-24 21:00:00</time>" in html
        assert "<time>2026-10-25 09:00:00</time>" in html
        assert "Elapsed time: 12:00:00" in html
        assert 'id="timing-data"' in html
        assert 'vis-timeline@8.5.6/standalone/umd/vis-timeline-graph2d.min.js' in html
        assert 'vis-timeline@8.5.6/styles/vis-timeline-graph2d.min.css' in html
        assert 'id="timing-help"' not in html and 'id="timing-loaded"' not in html
        assert "Timeline and precise fields use UTC" not in html
        assert html.index('id="timing-form"') < html.index('id="timing-track"')
        assert 'type="datetime-local"' in html and '<label for="timing-start">Start</label>' in html
        for control in ("timing-zoom-in", "timing-zoom-out", "timing-focus", "timing-show-all"):
            assert f'id="{control}"' not in html
    data = urlencode(dict(interval_id=interval, pause_start="2026-10-24 22:00",
                          pause_end="2026-10-25 08:00")).encode()
    request = Request(service["url"] + f"/tasks/{task_id}/pause" + query, data=data,
                      headers={"Origin": service["url"]})
    with urlopen(request) as response:
        assert response.status == 200 and "saved=1" in response.geturl()
        html = response.read().decode()
        assert "Pause saved" in html
        assert "Elapsed time: 10:00:00" in html
    with urlopen(service["url"] + "/api/report?start=2026-10-24&end=2026-10-25") as response:
        assert [day["hours"] for day in json.load(response)["days"]] == [1, 1]
    with pytest.raises(HTTPError) as error:
        urlopen(request)
    assert error.value.code == 409
    with pytest.raises(HTTPError) as error:
        urlopen(service["url"] + "/tasks/999999999")
    assert error.value.code == 404


@pytest.mark.database
@pytest.mark.parametrize("data,headers,query,status", [
    (b"interval_id=1&pause_start=x&pause_end=", {}, "", 403),
    (b"interval_id=1&pause_start=x&pause_end=", {"Origin": "http://elsewhere.invalid"}, "", 403),
    (b"interval_id=1&pause_start=x&pause_end=", {"Sec-Fetch-Site": "cross-site"}, "", 403),
    (b"{}", {"Content-Type": "application/json"}, "", 400),
    (b"x" * 8193, {}, "", 400),
    (b"interval_id=1&pause_start=x&pause_start=y&pause_end=", {}, "", 400),
    (b"interval_id=1&pause_start=x&pause_end=&extra=y", {}, "", 400),
    (b"interval_id=1&pause_start=x&pause_end=", {}, "?extra=y", 400),
])
def test_invalid_pause_requests_do_not_modify_data(service, tasks, data, headers, query, status):
    task_id = tasks.start("github.com/example/a", now=datetime(2026, 10, 24, 10))["task_id"]
    tasks.pause("github.com/example/a", now=datetime(2026, 10, 24, 12))
    before = tasks.task_detail(task_id)
    # An empty headers mapping in the first case intentionally omits Origin.
    supplied = {"Origin": service["url"], **headers}
    if status == 403 and not headers:
        supplied = {}
    request = Request(service["url"] + f"/tasks/{task_id}/pause" + query, data=data, headers=supplied)
    with pytest.raises(HTTPError) as error:
        urlopen(request)
    assert error.value.code == status
    assert tasks.task_detail(task_id) == before
