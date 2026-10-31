"""All-time, single-project history through MariaDB, HTTP and the browser."""

from datetime import datetime, timezone
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pytest

from devlog.activity.TaskHistory import TaskHistory
from test_http import TaskListApplication, display


class ProjectApplication(TaskListApplication):
    repositories = ["github.com/example/Alpha", 'github.com/example/<img onerror="unsafe">']

    def project_task_list(self, *, repository=""):
        repository = repository or self.repositories[0]
        return dict(self.task_list(), repositories=self.repositories, repository=repository)


def test_projects_http_selector_navigation_dates_escaping_and_head():
    with display(ProjectApplication()) as url:
        with urlopen(url + "/projects?lang=en") as response:
            html = response.read().decode()
        assert '<h1 id="tasks-heading">Repository (Alpha) Tasks</h1>' in html
        assert html.index('>Tasks</a>') < html.index('aria-current="page">Projects</a>')
        assert 'href="/projects?repository=github.com%2Fexample%2FAlpha&amp;lang=en" aria-current="page"' in html
        assert '<option value="github.com/example/Alpha" selected>Alpha</option>' in html
        assert '<option value="">' not in html and ' multiple' not in html
        assert 'name="day"' not in html and 'name="start"' not in html and 'name="end"' not in html
        assert html.index('id="project"') < html.index('id="tasks-heading"')
        assert '<time>27 Oct 2026 09:15</time>' in html
        assert '<span>Total time</span><strong>02:32</strong>' in html
        assert '&lt;img onerror=&#34;unsafe&#34;&gt;' in html
        assert '&lt;script&gt;alert(&#34;unsafe&#34;)&lt;/script&gt;' in html
        assert '<img onerror=' not in html and '<script>alert(' not in html
        assert '/tasks/123?repository=github.com%2Fexample%2FAlpha&amp;lang=en' in html
        query = urlencode(dict(repository=ProjectApplication.repositories[1], lang="en"))
        with urlopen(url + "/projects?" + query) as response:
            html = response.read().decode()
        assert 'selected>&lt;img onerror=&#34;unsafe&#34;&gt;</option>' in html
        with urlopen(Request(url + "/projects", method="HEAD")) as response:
            assert response.status == 200 and response.read() == b""
        with urlopen(url + "/tasks?repository=Alpha&day=2026-10-27&start=2026-10-26&end=2026-10-27") as response:
            html = response.read().decode()
        assert 'href="/projects?repository=Alpha&amp;lang=en">Projects</a>' in html
        for query in ("day=2026-10-27", "start=2020-01-01", "end=2026-10-27", "repository=a&repository=b"):
            with pytest.raises(HTTPError) as error:
                urlopen(url + "/projects?" + query)
            assert error.value.code == 400


@pytest.mark.database
def test_project_history_includes_all_years_full_intervals_and_only_one_project(tasks):
    alpha, beta = "github.com/example/Alpha", "github.com/example/Beta"
    old = tasks.start(alpha, now=datetime(2023, 1, 1, 23))["task_id"]
    tasks.pause(alpha, now=datetime(2023, 1, 2, 1))
    tasks.start(alpha, now=datetime(2023, 1, 3, 1))
    tasks.complete(alpha, old, "a" * 40, "Old multi-day work", now=datetime(2023, 1, 3, 2))
    other = tasks.start(beta, now=datetime(2026, 10, 1, 10))["task_id"]
    tasks.complete(beta, other, "b" * 40, "Other project", now=datetime(2026, 10, 1, 20))
    paused = tasks.start(alpha, now=datetime(2026, 10, 2, 10))["task_id"]
    tasks.pause(alpha, now=datetime(2026, 10, 2, 10))
    tasks.complete(alpha, paused, "c" * 40, "Zero-duration task", now=datetime(2026, 10, 2, 10))
    # The two UTC times have the same local clock time during DST fall-back.
    tasks.record_release(alpha, "v0.1.0", "First release", "a" * 40, datetime(2026, 11, 1, 5, 30))
    running = tasks.start(alpha, now=datetime(2026, 11, 1, 6, 30))["task_id"]
    tasks.record_release(beta, "v9.0.0", None, "b" * 40, datetime(2026, 11, 1, 6, 45))
    history = TaskHistory(tasks, ZoneInfo("America/Toronto"))
    report = history.project(now=datetime(2026, 11, 1, 7, 30, tzinfo=timezone.utc))
    assert report["repository"] == alpha and report["repositories"] == [alpha, beta]
    assert [task["task_id"] for task in report["tasks"]] == [running, paused, old]
    assert [task["hours"] for task in report["tasks"]] == [1, 0, 3]
    assert report["total_hours"] == 4
    assert [entry["entry_type"] for entry in report["entries"]] == ["task", "release", "task", "task"]
    assert report["entries"][0]["started_at"] == report["entries"][1]["released_at"] == "2026-11-01 01:30:00"
    assert len(report["releases"]) == 1 and report["releases"][0]["tag_name"] == "v0.1.0"
    report = history.project(repository=beta)
    assert report["total_hours"] == 10
    assert [task["task_id"] for task in report["tasks"]] == [other]
    with pytest.raises(ValueError, match="Unknown repository"):
        history.project(repository="*")


@pytest.mark.database
def test_projects_empty_database_and_release_only_project(service, tasks):
    with urlopen(service["url"] + "/projects") as response:
        html = response.read().decode()
    assert '<h1 id="tasks-heading">Projects</h1>' in html
    assert '<strong>00:00</strong>' in html and 'class="empty"' in html
    assert 'disabled></select>' in html and '<option' not in html
    repository = "github.com/example/ReleasesOnly"
    tasks.record_release(repository, "v0.1.0", None, "c" * 40, datetime(2020, 1, 1, 15))
    with urlopen(service["url"] + "/projects") as response:
        html = response.read().decode()
    assert 'selected>ReleasesOnly</option>' in html
    assert '<time>01 Jan 2020 10:00</time>' in html
    assert 'class="release-row"' in html and '<strong>Release v0.1.0</strong>' in html
    assert '<strong>00:00</strong>' in html
    for repository in ("unknown", "*"):
        with pytest.raises(HTTPError) as error:
            urlopen(service["url"] + "/projects?" + urlencode(dict(repository=repository)))
        assert error.value.code == 400


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
def test_projects_browser_selection_task_links_and_responsive_layout(service, tasks):
    playwright = pytest.importorskip("playwright.sync_api")
    for repository, start, end, message in (
        ("Alpha", datetime(2023, 1, 1, 23), datetime(2023, 1, 3, 1), "Old work across dates"),
        ("Beta", datetime(2026, 10, 1, 10), datetime(2026, 10, 1, 12), "Other project work"),
    ):
        repository = "github.com/example/" + repository
        task_id = tasks.start(repository, now=start)["task_id"]
        tasks.complete(repository, task_id, "a" * 40, message, now=end)
    tasks.record_release("github.com/example/Alpha", "v0.1.0", "First release", "a" * 40, datetime(2023, 1, 3, 2))
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(service["url"] + "/projects")
        assert page.locator("#project").input_value() == "github.com/example/Alpha"
        assert page.locator("#project option").count() == 2
        assert page.locator("#project").get_attribute("multiple") is None
        assert page.locator(".task-total strong").inner_text() == "26:00"
        assert page.locator(".release-row").count() == 1
        assert "01 Jan 2023 18:00" in page.locator(".tasks-table").inner_text()
        assert "Other project work" not in page.locator(".tasks-table").inner_text()
        screenshots = Path(os.environ.get("DEVLOG_SCREENSHOT_DIR", "/tmp/devlog-projects-screenshots"))
        screenshots.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshots / "projects-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("#project").focus()
        assert page.locator("#project").evaluate("el => getComputedStyle(el).outlineStyle") != "none"
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path=str(screenshots / "projects-mobile.png"), full_page=True)
        with page.expect_navigation():
            page.select_option("#project", "github.com/example/Beta")
        assert page.locator("#tasks-heading").inner_text() == "Repository (Beta) Tasks"
        assert page.locator(".task-total strong").inner_text() == "02:00"
        assert "Other project work" in page.locator(".tasks-table").inner_text()
        assert "Old work across dates" not in page.locator(".tasks-table").inner_text()
        page.locator(".task-link").click()
        assert page.locator("h1").inner_text() == "Task #2"
        page.get_by_role("link", name="Projects", exact=True).click()
        assert page.locator("#project").input_value() == "github.com/example/Beta"
        fallback = browser.new_page(java_script_enabled=False)
        fallback.goto(service["url"] + "/projects")
        fallback.select_option("#project", "github.com/example/Beta")
        fallback.get_by_role("button", name="Show Report").click()
        assert fallback.locator("#tasks-heading").inner_text() == "Repository (Beta) Tasks"
        browser.close()
