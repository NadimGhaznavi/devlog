from contextlib import contextmanager
import json
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

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

    def report(self, **filters):
        return dict(repositories=['<script>alert("unsafe")</script>'], repository="", start="2026-10-24",
                    end="2026-10-24", timezone="America/Toronto", total_hours=2.5,
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
