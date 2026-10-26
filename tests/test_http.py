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

    def report(self, **filters):
        return dict(repositories=['<script>alert("unsafe")</script>'], repository="", start="2026-10-24",
                    end="2026-10-24", timezone="America/Toronto", total_hours=2.5, current_task=self.current_task,
                    days=[dict(date="2026-10-24", hours=2.5,
                               projects={'<script>alert("unsafe")</script>': 2.5})])

    def health(self):
        return dict(status="ok", components={"http": "ok", "zmq": "ok", "db-server": "ok"})


def test_report_html_json_head_and_asset_boundaries():
    with display(ReportApplication()) as url:
        with urlopen(url) as response:
            body = response.read()
            length = int(response.headers["Content-Length"])
            assert len(body) == length
            assert b"plotly-4.1.1.min.js" in body
            assert b"2.50" in body
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
        assert "9.00" in html
    with urlopen(service["url"] + f"/tasks/{task_id}" + query) as response:
        html = response.read().decode()
        assert 'id="timing-editor"' in html and '/static/timing.js' in html
        assert 'name="pause_start"' not in html and 'name="pause_end"' not in html
        assert "America/Toronto" in html and "12.00" in html
        assert "<time>2026-10-24 21:00:00</time>" in html
        assert "<time>2026-10-25 09:00:00</time>" in html
        assert "Elapsed time: 12:00:00" in html
        assert 'id="timing-data"' in html
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
