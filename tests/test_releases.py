from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

import pytest

from conftest import dl, git
from devlog import cli
from devlog.activity.TaskHistory import TaskHistory
from devlog.activity.Tracking import Tracking
from devlog.entity.TrackingError import TrackingError
from devlog.interface.DbMgr import DbMgr
from devlog.interface.LocalRepository import LocalRepository
from devlog.interface.TaskDb import TaskDb
from devlog.zmq.ZMQServer import ZMQServer


REPOSITORY = "github.com/example/project"
RELEASE = dict(repository=REPOSITORY, tag_name="v0.15.4", codename="neptune",
               commit_sha="a" * 40, released_at="2026-10-25T14:13:00+00:00")


def test_local_release_tags_use_tag_time_and_standard_codename(checkout, monkeypatch):
    root, _ = checkout
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-10-25T10:13:00-04:00")
    git(root, "tag", "-a", "v0.15.4", "-m", "Release 0.15.4: neptune")
    git(root, "tag", "-a", "0.15.5-rc.1+build.2", "-m", "Release 0.15.5-rc.1+build.2: Next release")
    git(root, "tag", "-a", "v0.15.6", "-m", "An unrelated annotation")
    git(root, "tag", "-a", "v0.15.7", "-m", "Release 0.15.7: néptune\u2028next")
    git(root, "tag", "v0.1.0")
    git(root, "tag", "not-a-release")
    git(root, "tag", "v0.2.0", "HEAD:initial")  # A blob is not a release commit.
    local = LocalRepository(root)
    releases = {release["tag_name"]: release for release in local.release_tags()}
    assert set(releases) == {"v0.15.4", "0.15.5-rc.1+build.2", "v0.15.6", "v0.15.7", "v0.1.0"}
    assert releases["v0.15.4"] == {key: value for key, value in RELEASE.items() if key != "repository"} | {
        "commit_sha": git(root, "rev-parse", "HEAD").stdout.strip(),
    }
    assert releases["0.15.5-rc.1+build.2"]["codename"] == "Next release"
    assert releases["v0.15.6"]["codename"] is None
    assert releases["v0.15.7"]["codename"] == "néptune\u2028next"
    assert releases["v0.1.0"]["codename"] is None
    commit_time = git(root, "show", "-s", "--format=%cI", "HEAD").stdout.strip()
    assert releases["v0.1.0"]["released_at"] == datetime.fromisoformat(commit_time).astimezone(timezone.utc).isoformat()
    assert local.release_tags(exclude=set(releases)) == []


def test_release_sync_dry_run_does_not_contact_service(checkout, monkeypatch, capsys):
    root, _ = checkout
    git(root, "tag", "-a", "v0.15.4", "-m", "Release 0.15.4: neptune")
    monkeypatch.chdir(root)
    assert cli.main(["--server", "invalid", "releases", "sync", "--dry-run"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1
    assert rows[0]["tag_name"] == "v0.15.4"
    assert rows[0]["codename"] == "neptune"


@pytest.mark.parametrize("create_tag,status,expected_count", [(True, 0, 1), (True, 7, 0), (False, 0, 0)])
def test_publish_records_only_new_tags_after_success(checkout, monkeypatch, capfd, create_tag, status, expected_count):
    root, _ = checkout
    git(root, "tag", "-a", "v0.15.3", "-m", "Release 0.15.3: old")
    script = root / "new_release.sh"
    script.write_text("#!/bin/bash\n"
                      + ("git tag -a v0.15.4 -m 'Release 0.15.4: neptune'\n" if create_tag else "")
                      + f"exit {status}\n")
    monkeypatch.chdir(root)
    requests = []

    @contextmanager
    def handler():
        def respond(request):
            requests.append(request)
            return {"status": "ok", "result": {"release_id": 1, "inserted": True}}
        yield respond

    with ZMQServer("tcp://127.0.0.1:*", handler) as server:
        assert cli.main(["--server", server.endpoint, "publish", "--", "script argument"]) == status
    assert len(requests) == expected_count
    if requests:
        assert requests[0].method == "release"
        assert requests[0].payload["repository"] == REPOSITORY
        assert requests[0].payload["tag_name"] == "v0.15.4"
        assert requests[0].payload["codename"] == "neptune"
        assert "1 added, 1 checked" in capfd.readouterr().out


def test_published_release_recording_failure_has_sync_recovery(checkout, monkeypatch, capfd):
    root, _ = checkout
    (root / "new_release.sh").write_text("git tag -a v0.15.4 -m 'Release 0.15.4: neptune'\n")
    monkeypatch.chdir(root)

    @contextmanager
    def handler():
        yield lambda request: {"status": "error", "error": {
            "code": "request_timeout", "message_key": "error.request_timeout",
        }}

    with ZMQServer("tcp://127.0.0.1:*", handler) as server:
        assert cli.main(["--server", server.endpoint, "publish"]) == 1
    assert "Run dl releases sync to recover; do not publish again." in capfd.readouterr().err
    assert git(root, "rev-parse", "v0.15.4^{commit}").returncode == 0


@pytest.mark.parametrize("updates", [
    {"tag_name": "--invalid"}, {"tag_name": "nightly"}, {"tag_name": "v1.2.3\n"},
    {"tag_name": "v1.2.3-" + "x" * 255}, {"tag_name": 42},
    {"codename": ""}, {"codename": "  "}, {"codename": "bad\nname"},
    {"codename": "é" * 513}, {"codename": True},
    {"commit_sha": "abc"}, {"commit_sha": 42},
    {"released_at": "2026-10-25T14:13:00"}, {"released_at": "invalid"},
    {"released_at": "0999-01-01T00:00:00+00:00"}, {"released_at": None},
    {"repository": ""}, {"repository": "bad\nrepository"}, {"extra": 1},
])
def test_release_payload_is_validated_before_any_write(updates):
    with pytest.raises(TrackingError, match="invalid_request"):
        Tracking(None).execute("release", RELEASE | updates)


def test_release_timestamp_offset_normalizes_to_utc():
    calls = []
    tasks = SimpleNamespace(record_release=lambda *values: calls.append(values))
    Tracking(tasks).execute("release", RELEASE | {"released_at": "2026-10-25T10:13:00-04:00"})
    assert calls == [(REPOSITORY, "v0.15.4", "neptune", "a" * 40, datetime(2026, 10, 25, 14, 13))]


@pytest.mark.parametrize("field", RELEASE)
def test_release_payload_requires_all_fields(field):
    with pytest.raises(TrackingError, match="invalid_request"):
        Tracking(None).execute("release", {key: value for key, value in RELEASE.items() if key != field})


@pytest.mark.database
def test_release_storage_is_idempotent_and_conflicts_preserve_original(tasks):
    tracking = Tracking(tasks)
    first = tracking.execute("release", RELEASE)
    before = tasks.db.query("SELECT * FROM releases")
    assert first["inserted"] is True
    assert tracking.execute("release", RELEASE) == {"release_id": first["release_id"], "inserted": False}
    for updates in ({"codename": "changed"}, {"commit_sha": "b" * 40},
                    {"released_at": "2026-10-25T14:14:00+00:00"}):
        with pytest.raises(TrackingError, match="release_conflict"):
            tracking.execute("release", RELEASE | updates)
    assert tasks.db.query("SELECT * FROM releases") == before
    other = tracking.execute("release", RELEASE | {"repository": "github.com/example/other"})
    assert other["inserted"] is True
    assert len(tasks.db.query("SELECT * FROM releases")) == 2
    assert tasks.status()["task_id"] is None


@pytest.mark.database
def test_release_schema_upgrade_is_additive_and_repeatable(tasks):
    task = tasks.start(REPOSITORY)["task_id"]
    original = tasks.task_detail(task)
    tasks.db.execute("DROP TABLE releases")  # Simulate the pre-feature schema in this disposable database.
    tasks.initialize()
    Tracking(tasks).execute("release", RELEASE)
    tasks.initialize()
    assert tasks.task_detail(task) == original
    assert len(tasks.db.query("SELECT * FROM releases")) == 1


@pytest.mark.database
def test_concurrent_release_retries_create_one_record(db_options):
    def record(_):
        with DbMgr(**db_options) as manager:
            return Tracking(TaskDb(manager)).execute("release", RELEASE)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(record, range(4)))
    assert sum(result["inserted"] for result in results) == 1
    assert len({result["release_id"] for result in results}) == 1


@pytest.mark.database
def test_release_write_failure_rolls_back_repository_creation(tasks, monkeypatch):
    insert = tasks.db.insert

    def fail_release(sql, params=()):
        if "INSERT INTO releases" in sql:
            raise RuntimeError("injected failure")
        return insert(sql, params)

    monkeypatch.setattr(tasks.db, "insert", fail_release)
    with pytest.raises(RuntimeError, match="injected"):
        Tracking(tasks).execute("release", RELEASE)
    assert tasks.repositories() == []
    assert tasks.db.query("SELECT * FROM releases") == []


@pytest.mark.database
def test_releases_use_local_day_boundaries_and_utc_order_without_affecting_totals(tasks, monkeypatch):
    tracking = Tracking(tasks)
    for tag, timestamp, repository in (
        ("v1.0.0", "2026-11-01T03:59:59+00:00", REPOSITORY),  # Previous local day.
        ("v1.0.1", "2026-11-01T04:00:00+00:00", REPOSITORY),
        ("v1.0.2", "2026-11-01T05:50:00+00:00", REPOSITORY),  # 01:50 EDT.
        ("v1.0.3", "2026-11-01T06:10:00+00:00", REPOSITORY),  # 01:10 EST, later.
        ("v1.0.4", "2026-11-02T05:00:00+00:00", REPOSITORY),  # Following local day.
        ("v1.0.0", "2026-11-01T15:00:00+00:00", "github.com/example/release-only"),
    ):
        tracking.execute("release", RELEASE | dict(tag_name=tag, released_at=timestamp, repository=repository))
    task_id = tasks.start(REPOSITORY, now=datetime(2026, 11, 1, 5, 40))["task_id"]
    tasks.complete(REPOSITORY, task_id, "b" * 40, "Work", now=datetime(2026, 11, 1, 6, 20))
    history = TaskHistory(tasks, ZoneInfo("America/Toronto"))
    # A report must not execute Git or any other subprocess.
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: pytest.fail("Report executed a subprocess"))
    report = history.list(day="2026-11-01", repository=REPOSITORY)
    assert [item.get("tag_name", "task") for item in report["entries"]] == ["v1.0.3", "v1.0.2", "task", "v1.0.1"]
    assert report["entries"][0]["released_at"] == "2026-11-01 01:10:00"
    assert report["entries"][1]["released_at"] == "2026-11-01 01:50:00"
    assert report["total_hours"] == pytest.approx(40 / 60)
    daily = history.daily(day="2026-11-01", repository="github.com/example/release-only")
    assert daily["repositories"] == [REPOSITORY, "github.com/example/release-only"]
    assert daily["total_hours"] == 0
    assert daily["tasks"] == []
    assert len(daily["entries"]) == 1
    assert daily["entries"][0]["repository"] == "github.com/example/release-only"


@pytest.mark.database
def test_real_cli_catchup_then_publish_preserves_task_timer(service, checkout, tasks):
    root, _ = checkout
    git(root, "tag", "-a", "v0.15.3", "-m", "Release 0.15.3: old")
    first = dl(root, service, "releases", "sync")
    assert first.returncode == 0, first.stderr
    assert "1 added, 1 checked" in first.stdout
    assert tasks.status()["task_id"] is None
    again = dl(root, service, "releases", "sync")
    assert again.returncode == 0, again.stderr
    assert "0 added, 1 checked" in again.stdout
    task_id = tasks.start(REPOSITORY)["task_id"]
    before = tasks.task_detail(task_id)
    (root / "new_release.sh").write_text("git tag -a v0.15.4 -m 'Release 0.15.4: neptune'\n")
    published = dl(root, service, "publish")
    assert published.returncode == 0, published.stderr
    assert "1 added, 1 checked" in published.stdout
    assert tasks.task_detail(task_id) == before
    assert [row["tag_name"] for row in tasks.db.query("SELECT tag_name FROM releases ORDER BY release_id")] == ["v0.15.3", "v0.15.4"]


@pytest.mark.database
def test_release_rows_are_escaped_and_work_on_release_only_days(service, tasks):
    tracking = Tracking(tasks)
    tracking.execute("release", RELEASE)
    tracking.execute("release", RELEASE | {"tag_name": "v0.15.5", "codename": '<img src=x onerror="unsafe">',
                                           "released_at": "2026-10-25T15:00:00+00:00"})
    query = urlencode(dict(day="2026-10-25", repository=REPOSITORY))
    for path in ("/tasks?", "/daily?"):
        with urlopen(service["url"] + path + query) as response:
            html = response.read().decode()
        assert html.count('class="release-row"') == 2
        assert 'Release v0.15.4 (neptune)' in html
        assert 'Release v0.15.5 (&lt;img src=x onerror=&#34;unsafe&#34;&gt;)' in html
        assert '<img src=x' not in html
        assert '<time>10:13</time>' in html
        assert '<strong>00:00</strong>' in html
        assert '<p class="empty">' not in html
        assert 'class="task-link"' not in html
    with urlopen(service["url"] + "/daily?day=2026-10-26") as response:
        assert 'class="release-row"' not in response.read().decode()


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
def test_release_row_desktop_and_mobile(service, tasks):
    playwright = pytest.importorskip("playwright.sync_api")
    Tracking(tasks).execute("release", RELEASE)
    task_id = tasks.start(REPOSITORY, now=datetime(2026, 10, 25, 14))["task_id"]
    tasks.complete(REPOSITORY, task_id, "b" * 40, "Finish feature", now=datetime(2026, 10, 25, 14, 12))
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        for width in (1440, 390):
            page.set_viewport_size(dict(width=width, height=900))
            page.goto(service["url"] + "/tasks?" + urlencode(dict(day="2026-10-25", repository=REPOSITORY)))
            row = page.locator(".release-row")
            assert row.inner_text().strip().startswith("10:13")
            assert row.locator("strong").inner_text() == "Release v0.15.4 (neptune)"
            assert row.locator("td").first.inner_text() == ""
            assert row.locator("td").last.inner_text() == ""
            assert row.evaluate("node => getComputedStyle(node).backgroundColor") == "rgb(53, 35, 21)"
            assert page.locator(".task-total strong").inner_text() == "00:12"
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            # Keep the release styling when a striped row is hovered.
            row.hover()
            assert row.evaluate("node => getComputedStyle(node).backgroundColor") == "rgb(53, 35, 21)"
            page.screenshot(path=f"/tmp/devlog-release-{width}.png", full_page=True)
        browser.close()
