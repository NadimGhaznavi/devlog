"""Optional real-browser acceptance check; Playwright is test tooling only."""

import base64
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest


def use_cached_plotly(page):
    use_cached_timeline(page)
    asset = os.environ.get("DEVLOG_TEST_PLOTLY_ASSET")
    if asset:
        page.route("https://cdn.plot.ly/plotly-4.1.1.min.js",
                   lambda route: route.fulfill(path=asset, content_type="text/javascript"))


def use_cached_timeline(page):
    for extension, path, content_type in (
        ("js", "standalone/umd/vis-timeline-graph2d.min.js", "text/javascript"),
        ("css", "styles/vis-timeline-graph2d.min.css", "text/css"),
    ):
        asset = os.environ.get("DEVLOG_TEST_TIMELINE_" + extension.upper())
        if asset:
            page.route("https://unpkg.com/vis-timeline@8.5.6/" + path,
                       lambda route, request, asset=asset, content_type=content_type:
                       route.fulfill(path=asset, content_type=content_type))


def observe_timeline_hooks(page):
    """Observe the app's vis callbacks without changing the library or app source."""
    def instrument(route):
        response = route.fetch()
        route.fulfill(response=response, body="""
            const NativeTimeline = vis.Timeline;
            window.timelineHooks = [];
            vis.Timeline = function(container, items, options) {
                for (const name of ['onMove', 'onUpdate']) {
                    const handler = options[name];
                    options[name] = (item, callback) => {
                        const event = {name, calls: 0, accepted: null};
                        window.timelineHooks.push(event);
                        handler(item, result => {
                            event.calls++;
                            event.accepted = result !== null;
                            callback(result);
                        });
                    };
                }
                window.timelineItems = items;
                window.testTimeline = new NativeTimeline(container, items, options);
                return window.testTimeline;
            };
        """ + response.text())
    page.route("**/static/timing.js", instrument)


def save_precise_timing(page, *, start=None, end=None):
    if start is not None:
        page.get_by_label("Start", exact=True).fill(start.replace("T", " ") + (":00" if len(start) == 16 else ""))
    if end is not None:
        page.get_by_label("End", exact=True).fill(end.replace("T", " ") + (":00" if len(end) == 16 else ""))
    page.get_by_role("button", name="Save timing", exact=True).click()
    page.wait_for_function("""document.getElementById('timing-status').textContent.startsWith('Timing saved.')
        || !document.getElementById('timing-error').hidden""")
    assert page.locator("#timing-status").inner_text().startswith("Timing saved."), page.locator("#timing-error").inner_text()


def drag_work_range(page, index, delta_seconds, edge=None, touch=False, wait=True):
    work = page.locator(".vis-item.vis-range.timing-work").nth(index)
    work.click()
    # Keep the selection click outside the library's double-click gesture window.
    page.wait_for_timeout(400)
    start = datetime.fromisoformat(page.locator("#timing-start").input_value())
    end = datetime.fromisoformat(page.locator("#timing-end").input_value())
    work_box = work.bounding_box()
    scale = work_box["width"] / (end - start).total_seconds()
    target = work.locator(".vis-drag-" + edge) if edge else work
    target.scroll_into_view_if_needed()
    box = target.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    if touch:
        session = page.context.new_cdp_session(page)
        session.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
        for step in range(1, 11):
            session.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [
                {"x": x + delta_seconds * scale * step / 10, "y": y}]})
        session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    else:
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + delta_seconds * scale, y, steps=10)
        page.mouse.up()
    if wait:
        page.wait_for_function("document.getElementById('timing-track').getAttribute('aria-busy') === 'false'")


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
def test_plotly_report_filters_and_mobile_layout(service, tasks):
    playwright = pytest.importorskip("playwright.sync_api")
    tasks.start("github.com/nadimghaznavi/alpha", now=datetime(2026, 10, 24, 10))
    tasks.pause("github.com/nadimghaznavi/alpha", now=datetime(2026, 10, 24, 12))
    first_beta = tasks.start("github.com/nadimghaznavi/beta", now=datetime(2026, 10, 24, 13))["task_id"]
    tasks.complete("github.com/nadimghaznavi/beta", first_beta, "a" * 40, "First task",
                   now=datetime(2026, 10, 24, 13, 15))
    tasks.start("github.com/nadimghaznavi/beta", now=datetime(2026, 10, 24, 13, 15))
    tasks.pause("github.com/nadimghaznavi/beta", now=datetime(2026, 10, 24, 14))
    errors = []
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900}, ignore_https_errors=True)
        use_cached_plotly(page)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(service["url"] + "/?start=2026-10-19&end=2026-10-25")
        page.wait_for_selector("#daily-chart .plot-container")
        assert page.evaluate("Plotly.version") == "4.1.1"
        assert page.locator(".total strong").inner_text() == "03:00"
        assert page.evaluate("document.getElementById('daily-chart').data.map(trace => trace.y)") == [[0, 0, 0, 0, 0, 2, 0], [0, 0, 0, 0, 0, 1, 0]]
        assert page.evaluate("document.getElementById('daily-chart').layout.barmode") == "stack"
        assert page.locator("#daily-chart .annotation-text").all_text_contents() == ["00:00"] * 5 + ["03:00", "00:00"]
        assert page.locator("#daily-title").inner_text() == "Daily Tasks"
        assert page.locator("#daily-chart").bounding_box()["height"] == 680
        label = page.locator("#daily-chart .annotation-text").nth(5)
        total_font = page.locator(".total strong").evaluate("""node => {
            const style = getComputedStyle(node);
            return {family: style.fontFamily, weight: style.fontWeight, size: parseFloat(style.fontSize), color: style.color};
        }""")
        label_font = label.evaluate("""node => {
            const style = getComputedStyle(node);
            return {family: style.fontFamily, weight: style.fontWeight, size: parseFloat(style.fontSize), color: style.fill};
        }""")
        assert label_font["family"] == total_font["family"]
        assert label_font["weight"] == total_font["weight"]
        assert label_font["color"] == total_font["color"]
        assert 0 < label_font["size"] < total_font["size"]
        bar = page.locator("#daily-chart .barlayer .point").nth(5).bounding_box()
        label_box = label.bounding_box()
        assert label_box["y"] + label_box["height"] < bar["y"]
        colors = page.evaluate("document.getElementById('daily-chart').data.map(trace => trace.marker.color)")
        assert colors == ["#E63946", "#00BCD4"]
        borders = page.evaluate("document.getElementById('daily-chart').data.map(trace => trace.marker.line)")
        assert [border["width"] for border in borders] == [[0, 0, 0, 0, 0, 4, 0], [0, 0, 0, 0, 0, 4, 0]]
        for fill, border in zip(colors, borders):
            assert all(int(border["color"][channel:channel + 2], 16) <= int(fill[channel:channel + 2], 16)
                       for channel in (1, 3, 5))
            assert border["color"] != fill
        assert page.locator("#daily-chart .barlayer .point path").first.evaluate(
            "node => getComputedStyle(node).strokeWidth") == "0px"
        assert page.locator("#daily-chart .barlayer .point path").nth(5).evaluate(
            "node => getComputedStyle(node).strokeWidth") == "4px"
        separator = page.evaluate("document.getElementById('daily-chart').layout.shapes[0]")
        assert separator["y0"] == separator["y1"] == 2.25
        assert separator["x0"] == 4.6 and separator["x1"] == 5.4
        assert separator["line"] == {"color": borders[1]["color"], "width": 2}
        assert page.locator("#daily-chart .shapelayer path").count() == 1
        assert page.locator("#daily-chart .shapelayer path").evaluate(
            "node => getComputedStyle(node).strokeWidth") == "2px"
        assert page.locator("#daily-chart .legendtext").all_text_contents() == ["alpha", "beta"]
        page.locator("#daily-chart .barlayer .point").nth(5).scroll_into_view_if_needed()
        bar = page.locator("#daily-chart .barlayer .point").nth(5).bounding_box()
        page.mouse.move(bar["x"] + bar["width"] / 2, bar["y"] + bar["height"] / 2)
        page.wait_for_selector("#daily-chart .hovertext")
        assert page.locator("#daily-chart .hovertext").all_text_contents() == ["alpha: 02:00"]

        # Hiding a lower project must move the separator with the remaining bar.
        page.locator("#daily-chart .legendtoggle").nth(0).click()
        page.wait_for_function("document.getElementById('daily-chart').layout.shapes[0].y0 === .25")
        page.wait_for_function("document.querySelectorAll('#daily-chart .annotation-text')[5].textContent === '01:00'")
        page.locator("#daily-chart .legendtoggle").nth(0).click()
        page.wait_for_function("document.getElementById('daily-chart').layout.shapes[0].y0 === 2.25")
        page.wait_for_function("document.querySelectorAll('#daily-chart .annotation-text')[5].textContent === '03:00'")
        page.locator("#daily-chart .legendtoggle").nth(1).click()
        page.wait_for_function("document.getElementById('daily-chart').layout.shapes.length === 0")
        page.wait_for_function("document.querySelectorAll('#daily-chart .annotation-text')[5].textContent === '02:00'")
        page.locator("#daily-chart .legendtoggle").nth(1).click()
        page.wait_for_function("document.getElementById('daily-chart').layout.shapes.length === 1")

        # Every section collapses to its heading and supports keyboard toggling.
        panels = page.locator("main > details.panel")
        assert panels.count() == 3
        contents = [".filters", "#current-task-status", "#daily-chart"]
        for panel, content in zip(panels.all(), contents):
            summary = panel.locator("summary")
            summary.click()
            assert panel.get_attribute("open") is None
            assert summary.is_visible()
            assert not panel.locator(content).is_visible()
            if content == "#daily-chart":
                assert not panel.locator(".total").is_visible()
            summary.focus()
            summary.press("Enter")
            assert panel.get_attribute("open") is not None
            assert panel.locator(content).is_visible()

        def assert_legend_below_date():
            title = page.locator("#daily-chart .xtitle").bounding_box()
            legend = page.locator("#daily-chart .legend").bounding_box()
            assert legend["y"] > title["y"] + title["height"]

        screenshot = os.environ.get("DEVLOG_SCREENSHOT_DIR")
        if screenshot:
            Path(screenshot).mkdir(parents=True, exist_ok=True)
        assert_legend_below_date()
        if screenshot:
            page.screenshot(path=str(Path(screenshot) / "devlog-desktop.png"), full_page=True)
        daily_summary = page.locator(".report > summary")
        daily_summary.click()
        page.set_viewport_size({"width": 390, "height": 844})
        daily_summary.click()
        page.wait_for_timeout(300)
        assert_legend_below_date()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        chart_box = page.locator("#daily-chart").bounding_box()
        plot_box = page.locator("#daily-chart .svg-container").bounding_box()
        assert abs(chart_box["width"] - plot_box["width"]) < 1
        label_boxes = [node.bounding_box() for node in page.locator("#daily-chart .annotation-text").all()]
        assert all(left["x"] + left["width"] < right["x"] for left, right in zip(label_boxes, label_boxes[1:]))
        if screenshot:
            page.screenshot(path=str(Path(screenshot) / "devlog-mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1200, "height": 900})
        page.get_by_role("combobox", name="Reporting", exact=True).select_option("github.com/nadimghaznavi/beta")
        page.get_by_role("button", name="Show Report").click()
        page.wait_for_selector("#daily-chart .plot-container")
        assert page.locator(".total strong").inner_text() == "01:00"
        assert page.evaluate("document.getElementById('daily-chart').data[0].y") == [0, 0, 0, 0, 0, 1, 0]
        assert page.locator("#daily-chart .annotation-text").all_text_contents() == ["00:00"] * 5 + ["01:00", "00:00"]
        assert page.evaluate("document.getElementById('daily-chart').data[0].marker.color") == colors[1]
        assert page.evaluate("document.getElementById('daily-chart').layout.shapes[0].y0") == .25
        page.locator("#daily-chart .shapelayer path").scroll_into_view_if_needed()
        line = page.locator("#daily-chart .shapelayer path").bounding_box()
        page.mouse.click(line["x"] + line["width"] / 2, line["y"])
        page.wait_for_url("**/tasks?**")
        assert parse_qs(urlsplit(page.url).query)["repository"] == ["github.com/nadimghaznavi/beta"]
        assert errors == []
        browser.close()


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
def test_chart_durations_round_to_minutes_and_empty_day_link_supports_keyboard(service, tasks):
    playwright = pytest.importorskip("playwright.sync_api")
    durations = [timedelta(hours=.51), timedelta(hours=6.21), timedelta(minutes=59, seconds=29),
                 timedelta(minutes=59, seconds=30), timedelta(seconds=29), timedelta(seconds=30)]
    labels = ["00:31", "06:13", "00:59", "01:00", "00:00", "00:01", "00:00"]
    repository = "github.com/nadimghaznavi/rounded"
    for index, duration in enumerate(durations):
        start = datetime(2026, 10, 19 + index, 10)
        task_id = tasks.start(repository, now=start)["task_id"]
        tasks.complete(repository, task_id, f"{index:040x}", "Work", now=start + duration)
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 1100}, ignore_https_errors=True)
        use_cached_plotly(page)
        page.goto(service["url"] + "/?start=2026-10-19&end=2026-10-25&lang=en")
        page.wait_for_selector("#daily-chart .plot-container")
        assert page.locator("#daily-chart .annotation-text").all_text_contents() == labels
        for index, label in enumerate(labels[:-1]):
            page.evaluate("""index => Plotly.Fx.hover(document.getElementById('daily-chart'),
                [{curveNumber: 0, pointNumber: index}])""", index)
            playwright.expect(page.locator("#daily-chart .hovertext")).to_have_text(["rounded: " + label])
        page.evaluate("Plotly.Fx.unhover(document.getElementById('daily-chart'))")
        link = page.get_by_role("link", name="Daily Task Report - 2026-10-25", exact=True)
        link.focus()
        link.press("Enter")
        page.wait_for_url("**/daily?**")
        assert parse_qs(urlsplit(page.url).query) == {"day": ["2026-10-25"], "lang": ["en"]}
        assert page.locator(".empty").is_visible()
        browser.close()


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
def test_daily_date_navigation_all_projects_and_mobile_table(service, tasks):
    playwright = pytest.importorskip("playwright.sync_api")
    for repository, start, end in (("alpha", 10, 12), ("beta", 13, 14)):
        repository = "github.com/example/" + repository
        task_id = tasks.start(repository, now=datetime(2026, 10, 24, start))["task_id"]
        tasks.complete(repository, task_id, "a" * 40, "Work on " + repository.rsplit("/", 1)[-1],
                       now=datetime(2026, 10, 24, end))
    for repository, start, elapsed in (
        ("tiny", datetime(2026, 10, 24, 14), timedelta(seconds=10)),
        ("otherday", datetime(2026, 10, 25, 10), timedelta(hours=1)),
    ):
        repository = "github.com/example/" + repository
        task_id = tasks.start(repository, now=start)["task_id"]
        tasks.complete(repository, task_id, "a" * 40, "Short work", now=start + elapsed)
    errors = []
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900}, ignore_https_errors=True)
        use_cached_plotly(page)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(service["url"] + "/?repository=github.com/example/alpha&start=2026-10-24&end=2026-10-24")
        page.wait_for_selector("#daily-chart .plot-container")
        chart_colors = page.evaluate("JSON.parse(document.getElementById('chart-data').textContent).projectColors")
        page.get_by_role("link", name="Daily Task Report - 2026-10-24", exact=True).click()
        page.wait_for_url("**/daily?**")
        assert parse_qs(urlsplit(page.url).query) == {"day": ["2026-10-24"], "lang": ["en"]}
        assert page.get_by_role("link", name="Daily", exact=True).get_attribute("aria-current") == "page"
        assert page.locator("#tasks-heading").inner_text() == "Daily Task Report - 24 Oct 2026"
        assert page.locator(".task-total strong").inner_text() == "03:00"
        assert page.locator(".tasks-table th").all_text_contents() == [
            "Task #", "Project", "Start Time", "Description", "Duration"]
        assert page.locator(".tasks-table tbody tr td:nth-child(2)").all_text_contents() == ["tiny", "beta", "alpha"]
        assert page.locator(".tasks-table tbody tr td:last-child").all_text_contents() == ["00:00", "01:00", "02:00"]
        swatches = page.locator(".project-swatch")
        assert swatches.count() == 3
        assert swatches.evaluate_all("nodes => nodes.map(node => node.style.getPropertyValue('--project-color'))") == [
            chart_colors["github.com/example/" + name] for name in ("tiny", "beta", "alpha")]
        assert all(node.get_attribute("aria-hidden") == "true" for node in swatches.all())
        project = page.get_by_role("combobox", name="Project", exact=True)
        assert project.locator("option").all_text_contents() == ["*", "alpha", "beta", "tiny"]
        assert project.input_value() == ""
        date_box = page.get_by_label("Date", exact=True).bounding_box()
        project_box = project.bounding_box()
        button_box = page.get_by_role("button", name="Show Report", exact=True).bounding_box()
        assert date_box["x"] < project_box["x"] < button_box["x"]
        project.select_option("github.com/example/tiny")
        page.get_by_role("button", name="Show Report", exact=True).click()
        assert page.locator(".tasks-table tbody tr td:nth-child(2)").all_text_contents() == ["tiny"]
        assert page.locator(".task-total strong").inner_text() == "00:00"
        assert swatches.first.evaluate("node => node.style.getPropertyValue('--project-color')") == chart_colors["github.com/example/tiny"]
        assert project.input_value() == "github.com/example/tiny"
        assert project.locator("option").all_text_contents() == ["*", "alpha", "beta", "tiny"]
        screenshot = os.environ.get("DEVLOG_SCREENSHOT_DIR")
        if screenshot:
            Path(screenshot).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(screenshot) / "daily-desktop.png"), full_page=True)
        project.select_option("github.com/example/beta")
        page.get_by_role("button", name="Show Report", exact=True).click()
        assert page.locator(".task-total strong").inner_text() == "01:00"
        assert swatches.first.evaluate("node => node.style.getPropertyValue('--project-color')") == chart_colors["github.com/example/beta"]
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        table_wrap = page.locator(".table-wrap")
        assert table_wrap.evaluate("element => element.scrollWidth > element.clientWidth")
        table_wrap.focus()
        table_wrap.press("ArrowRight")
        page.wait_for_function("document.querySelector('.table-wrap').scrollLeft > 0")
        if screenshot:
            page.screenshot(path=str(Path(screenshot) / "daily-mobile.png"), full_page=True)
        page.locator(".task-link").first.click()
        assert page.locator(".total strong").inner_text() == "01:00"
        page.get_by_role("link", name="Daily", exact=True).click()
        assert page.get_by_label("Date", exact=True).input_value() == "2026-10-24"
        project.select_option("github.com/example/tiny")
        page.get_by_label("Date", exact=True).fill("2026-10-25")
        page.get_by_role("button", name="Show Report", exact=True).click()
        assert project.input_value() == ""
        assert project.locator("option").all_text_contents() == ["*", "otherday"]
        assert page.locator(".task-total strong").inner_text() == "01:00"
        assert page.locator(".tasks-table tbody tr td:nth-child(2)").all_text_contents() == ["otherday"]
        page.get_by_label("Date", exact=True).fill("2026-10-26")
        page.get_by_role("button", name="Show Report", exact=True).click()
        assert parse_qs(urlsplit(page.url).query) == {"day": ["2026-10-26"], "lang": ["en"]}
        assert project.locator("option").all_text_contents() == ["*"]
        assert page.locator(".tasks-table tbody tr").count() == 0
        assert page.locator(".empty").is_visible()
        assert page.locator(".task-total strong").inner_text() == "00:00"
        assert errors == []
        browser.close()


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
def test_completed_task_dividers_have_visible_pixels(service, tasks):
    playwright = pytest.importorskip("playwright.sync_api")
    lower, blue = "github.com/example/alpha", "github.com/example/beta"
    cursor = datetime(2026, 10, 24, 10)
    first = tasks.start(lower, now=cursor)["task_id"]
    cursor += timedelta(minutes=47)
    tasks.complete(lower, first, "f" * 40, "Lower project", now=cursor)
    # Include a six-second completed task whose boundaries overlap at this scale.
    durations = (760, 6, 851, 406, 128, 202)
    for index, seconds in enumerate(durations):
        task = tasks.start(blue, now=cursor)["task_id"]
        cursor += timedelta(seconds=seconds)
        if index < len(durations) - 1:
            tasks.complete(blue, task, f"{index:040x}", "Completed task", now=cursor)
        else:
            tasks.pause(blue, now=cursor)
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 1000})
        use_cached_plotly(page)
        page.goto(service["url"] + "/?start=2026-10-18&end=2026-10-24")
        page.wait_for_selector("#daily-chart .plot-container")
        lines = page.locator("#daily-chart .shapelayer path")
        assert lines.count() == 5
        bounds = [line.bounding_box() for line in lines.all()]
        # Read screenshot pixels, so a line element alone cannot pass this check.
        pixels = page.evaluate("""async ({png, bounds}) => {
            const image = new Image();
            image.src = 'data:image/png;base64,' + png;
            await image.decode();
            const canvas = document.createElement('canvas');
            canvas.width = image.width;
            canvas.height = image.height;
            const context = canvas.getContext('2d');
            context.drawImage(image, 0, 0);
            return bounds.map(box => {
                const x = Math.round(box.x + box.width / 2);
                const y = Math.round(box.y);
                return [-2, -1, 0, 1, 2].map(offset => [...context.getImageData(x, y + offset, 1, 1).data]);
            });
        }""", dict(png=base64.b64encode(page.screenshot()).decode(), bounds=bounds))
        border = page.evaluate("document.getElementById('daily-chart').data[1].marker.line.color")
        rgb = [int(border[channel:channel + 2], 16) for channel in (1, 3, 5)]
        for samples in pixels:
            assert samples.count([*rgb, 255]) >= 2

        def luminance(channels):
            values = [channel / 255 for channel in channels]
            linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
                      for value in values]
            return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))

        assert (luminance([0, 188, 212]) + .05) / (luminance(rgb) + .05) >= 1.8
        browser.close()


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
def test_drilldown_trim_forgotten_running_time_and_chart_fallback(service, tasks):
    playwright = pytest.importorskip("playwright.sync_api")
    other = "github.com/example/other"
    other_task = tasks.start(other, now=datetime(2026, 10, 24, 14))["task_id"]
    tasks.complete(other, other_task, "f" * 40, "Earlier task", now=datetime(2026, 10, 24, 16))
    repository = "github.com/example/overnight"
    task_id = tasks.start(repository, now=datetime(2026, 10, 25, 1))["task_id"]
    tasks.complete(repository, task_id, "e" * 40, "Overnight correction", now=datetime(2026, 10, 25, 13))
    errors = []
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900}, ignore_https_errors=True, timezone_id="America/Toronto")
        use_cached_plotly(page)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(service["url"] + "/?start=2026-10-24&end=2026-10-25")
        page.wait_for_selector("#daily-chart .plot-container")
        assert page.locator(".total strong").inner_text() == "14:00"
        bar = page.locator("#daily-chart .barlayer .point").last.bounding_box()
        page.mouse.click(bar["x"] + bar["width"] / 2, bar["y"] + bar["height"] / 2)
        page.wait_for_url("**/tasks?**")
        assert "day=2026-10-25" in page.url
        assert "repository=" in page.url
        back_to_report = page.get_by_role("link", name="Back to report").get_attribute("href")
        assert parse_qs(urlsplit(back_to_report).query) == {
            "start": ["2026-10-24"], "end": ["2026-10-25"], "lang": ["en"]}
        assert page.get_by_role("heading", level=1).inner_text() == "Repository (overnight) Tasks - 25 Oct 2026"
        assert page.locator(".task-total span").inner_text() == "Total time"
        assert page.locator(".task-total strong").inner_text() == "09:00"
        assert page.locator(".tasks-table th").all_text_contents() == ["Task #", "Start Time", "Description", "Duration"]
        assert page.locator(".tasks-table tbody tr").first.locator("td").all_text_contents() == [
            str(task_id), "21:00", "Overnight correction", "09:00"]
        screenshot = os.environ.get("DEVLOG_SCREENSHOT_DIR")
        if screenshot:
            Path(screenshot).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(screenshot) / "tasks-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        table_wrap = page.locator(".table-wrap")
        assert table_wrap.evaluate("element => element.scrollWidth > element.clientWidth")
        table_wrap.focus()
        table_wrap.press("ArrowRight")
        page.wait_for_function("document.querySelector('.table-wrap').scrollLeft > 0")
        page.locator(".tasks-table th").last.scroll_into_view_if_needed()
        if screenshot:
            page.screenshot(path=str(Path(screenshot) / "tasks-mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1200, "height": 900})
        page.locator(".task-link").click()
        page.wait_for_url(f"**/tasks/{task_id}?**")
        assert page.locator(".total strong").inner_text() == "12:00"
        assert page.locator(".task-metadata time").all_text_contents() == [
            "2026-10-24 21:00:00", "2026-10-25 09:00:00"]
        assert page.locator(".interval time").all_text_contents() == [
            "2026-10-24 21:00:00", "2026-10-25 09:00:00"]
        assert page.locator(".elapsed").all_text_contents() == ["Elapsed time: 12:00:00"]
        save_precise_timing(page, end="2026-10-24T22:00")
        assert page.locator("#timing-total").inner_text() == "01:00:00"
        assert page.get_by_text("Timing saved.", exact=False).is_visible()
        assert page.locator(".total strong").inner_text() == "01:00"
        assert page.locator(".interval").count() == 1
        assert page.locator(".interval.pause").count() == 0
        assert page.locator(".elapsed").all_text_contents() == ["Elapsed time: 01:00:00"]
        assert page.locator(".task-metadata").inner_text().count("e" * 40) == 1
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        screenshot = os.environ.get("DEVLOG_SCREENSHOT_DIR")
        if screenshot:
            Path(screenshot).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(screenshot) / "devlog-pause-mobile.png"), full_page=True)
        page.get_by_role("link", name="Back to report").click()
        page.wait_for_selector("#daily-chart .plot-container")
        assert page.get_by_role("combobox", name="Reporting", exact=True).input_value() == ""
        assert page.get_by_label("From", exact=True).input_value() == "2026-10-24"
        assert page.get_by_label("Through", exact=True).input_value() == "2026-10-25"
        assert page.locator(".total strong").inner_text() == "03:00"
        assert page.evaluate("document.getElementById('daily-chart').data.map(trace => trace.y)") == [[2, 0], [1, 0]]
        # The table drill-down and editor work even when the CDN cannot be reached.
        page.route("https://cdn.plot.ly/plotly-4.1.1.min.js", lambda route: route.abort())
        page.reload()
        assert page.locator("#chart-error").is_visible()
        page.locator("#chart-error a").click()
        page.locator(".task-link").click()
        assert page.locator(".total strong").inner_text() == "01:00"
        playwright.expect(page.locator("#timing-editor")).to_be_visible()
        assert errors == []
        browser.close()


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
def test_vis_timeline_resize_move_precise_cancel_and_reload(service, tasks):
    playwright = pytest.importorskip("playwright.sync_api")
    previous_repo, repository = "github.com/example/previous", "github.com/example/edited"
    previous = tasks.start(previous_repo, now=datetime(2026, 10, 24, 10))["task_id"]
    tasks.complete(previous_repo, previous, "b" * 40, "Previous", now=datetime(2026, 10, 24, 11))
    task_id = tasks.start(repository, now=datetime(2026, 10, 24, 12))["task_id"]
    tasks.pause(repository, now=datetime(2026, 10, 24, 14))
    tasks.start(repository, now=datetime(2026, 10, 24, 15))
    tasks.complete(repository, task_id, "a" * 40, '<img src=x onerror="alert(1)">', now=datetime(2026, 10, 24, 17))
    before, previous_before = tasks.task_detail(task_id), tasks.task_detail(previous)
    url = service["url"] + f"/tasks/{task_id}?start=2026-10-24&end=2026-10-25&lang=en"
    errors, writes = [], []
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 1100}, timezone_id="Pacific/Auckland")
        use_cached_timeline(page)
        observe_timeline_hooks(page)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: writes.append(request) if request.method == "POST" else None)
        page.goto(url)
        playwright.expect(page.locator("#timing-editor")).to_be_visible()
        assert page.locator("#timing-start").input_value() == "2026-10-25 01:00:00"
        assert page.locator(".task-metadata time").all_text_contents() == [
            "2026-10-25 01:00:00", "2026-10-25 06:00:00"]
        assert page.locator("#timing-save").is_disabled()
        assert page.locator("#timing-total").inner_text() == "02:00:00"
        assert page.locator("#timing-fields").bounding_box()["y"] < page.locator("#timing-track").bounding_box()["y"]
        assert page.locator(".timing-form-fields tr").count() == 4
        assert page.locator(".timing-form-fields tr").first.locator("td").first.locator("select").count() == 1
        assert page.locator("label[for='timing-part']").count() == 0
        assert page.get_by_text("Snapshot at", exact=False).count() == 0
        assert page.get_by_text("Select a work range", exact=False).count() == 0
        assert page.evaluate("testTimeline.options.moment(new Date('2026-10-24T12:00:00Z')).format('YYYY-MM-DD HH:mm:ss')") == "2026-10-25 01:00:00"
        assert page.locator(".vis-item.vis-range.timing-work").count() == 1
        assert page.evaluate("timelineItems.get().filter(item => item.type === 'range').length") == 1
        for control in ("Zoom in", "Zoom out", "Focus task", "Show all"):
            assert page.get_by_role("button", name=control, exact=True).count() == 0
        # The task is fitted on load; wheel and background drags cannot change the view.
        window = page.evaluate("() => { const w = testTimeline.getWindow(); return [+w.start, +w.end]; }")
        assert window[0] <= datetime(2026, 10, 24, 12, tzinfo=timezone.utc).timestamp() * 1000
        assert window[1] >= datetime(2026, 10, 24, 14, tzinfo=timezone.utc).timestamp() * 1000
        assert window[1] - window[0] <= 7 * 3600 * 1000
        track = page.locator("#timing-track")
        track.scroll_into_view_if_needed()
        box = track.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 5)
        page.mouse.wheel(0, -500)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] / 3, box["y"] + 5, steps=10)
        page.mouse.up()
        page.wait_for_timeout(300)
        assert page.evaluate("() => { const w = testTimeline.getWindow(); return [+w.start, +w.end]; }") == window
        assert page.locator(".commit-message img").count() == 0
        assert page.get_by_text("Insert a pause", exact=True).count() == 0
        page.locator("#timing-start").fill("2026-10-25 01:30:00")
        page.get_by_role("button", name="Cancel", exact=True).click()
        assert page.locator("#timing-start").input_value() == "2026-10-25 01:00:00"
        assert writes == [] and tasks.task_detail(task_id) == before
        # Double-click uses onUpdate; cancelling leaves the range and storage intact.
        page.locator(".vis-item.vis-range.timing-work").first.dblclick()
        assert page.locator("#timing-start").evaluate("node => node === document.activeElement")
        page.get_by_role("button", name="Cancel", exact=True).click()
        assert writes == []
        # The actual vis resize and move handlers persist exactly once per gesture.
        drag_work_range(page, 0, 1800, edge="left")
        assert len(writes) == 1
        row = tasks.task_detail(task_id)["intervals"][0]
        assert datetime(2026, 10, 24, 12) < row["started_at"] < datetime(2026, 10, 24, 13)
        assert row["ended_at"] == datetime(2026, 10, 24, 14)
        resized_duration = row["ended_at"] - row["started_at"]
        drag_work_range(page, 0, 900)
        assert len(writes) == 2
        row = tasks.task_detail(task_id)["intervals"][0]
        assert datetime(2026, 10, 24, 14) < row["ended_at"] < datetime(2026, 10, 24, 15)
        assert row["ended_at"] - row["started_at"] == resized_duration
        save_precise_timing(page, start="2026-10-25T01:30", end="2026-10-25T02:30")
        first_id = page.evaluate("timelineItems.get().find(item => item.type === 'range').id")
        page.get_by_label("Active time", exact=True).select_option(index=1)
        assert page.evaluate("timelineItems.get().find(item => item.type === 'range').id") != first_id
        assert page.locator(".vis-item.vis-range.timing-work").count() == 1
        assert page.locator("ol.timeline .interval").count() == 1
        assert page.locator("ol.timeline time").first.text_content() == "2026-10-25 04:00:00"
        save_precise_timing(page, start="2026-10-25T04:30", end="2026-10-25T05:30")
        assert len(writes) == 4
        assert page.evaluate("timelineHooks") == [
            {"name": "onUpdate", "calls": 1, "accepted": False},
            {"name": "onMove", "calls": 1, "accepted": True},
            {"name": "onMove", "calls": 1, "accepted": True},
        ]
        assert page.locator(".total strong").inner_text() == "02:00"
        assert page.locator("#timing-total").inner_text() == "01:00:00"
        assert tasks.task_detail(previous) == previous_before
        after = tasks.task_detail(task_id)
        assert {k: v for k, v in after.items() if k != "intervals"} == {
            k: v for k, v in before.items() if k != "intervals"}
        assert "start=2026-10-24" in page.url and "lang=en" in page.url
        page.reload()
        assert page.locator(".total strong").inner_text() == "02:00"
        assert page.locator("#timing-start").input_value() == "2026-10-25 01:30:00"
        playwright.expect(page.locator("#timing-track .vis-timeline")).to_be_visible()
        for width in (1200, 390):
            page.set_viewport_size({"width": width, "height": 1100})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            screenshots = os.environ.get("DEVLOG_SCREENSHOT_DIR")
            if screenshots:
                Path(screenshots).mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(Path(screenshots) / f"vis-timeline-{width}.png"), full_page=True)
        assert errors == []
        browser.close()


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
@pytest.mark.parametrize("seconds", [5, 59])
def test_vis_short_task_mobile_touch_and_precise_edit(service, tasks, seconds):
    playwright = pytest.importorskip("playwright.sync_api")
    repository = "github.com/example/short"
    start = datetime(2026, 10, 24, 12)
    task_id = tasks.start(repository, now=start)["task_id"]
    tasks.complete(repository, task_id, "a" * 40, "Short", now=start + timedelta(seconds=seconds))
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        context = browser.new_context(timezone_id="UTC", viewport={"width": 390, "height": 1000}, is_mobile=True, has_touch=True)
        page = context.new_page()
        use_cached_timeline(page)
        page.goto(service["url"] + f"/tasks/{task_id}")
        drag_work_range(page, 0, -seconds / 5, edge="left", touch=True)
        after_touch = tasks.task_detail(task_id)["intervals"][0]
        assert after_touch["started_at"] < start
        assert after_touch["ended_at"] == start + timedelta(seconds=seconds)
        # Both boundaries remain precisely reachable for sub-minute tasks at any scale.
        save_precise_timing(page, start="2026-10-24T11:30")
        assert tasks.task_detail(task_id)["intervals"][0]["started_at"] == datetime(2026, 10, 24, 11, 30)
        page.reload()
        assert page.locator("#timing-start").input_value() == "2026-10-24 11:30:00"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
def test_vis_rejection_stale_edit_and_lost_acknowledgement(service, tasks):
    playwright = pytest.importorskip("playwright.sync_api")
    repository = "github.com/example/recovery"
    task_id = tasks.start(repository, now=datetime(2026, 10, 24, 12))["task_id"]
    tasks.complete(repository, task_id, "a" * 40, "Recovery", now=datetime(2026, 10, 24, 17))
    url = service["url"] + f"/tasks/{task_id}"
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(timezone_id="UTC")
        stale = browser.new_page(timezone_id="UTC")
        for view in (page, stale):
            use_cached_timeline(view)
            view.goto(url)
        # Server rejection preserves the last accepted range and leaves form values unsaved.
        page.locator("#timing-end").fill("2026-10-24 18:00:00")
        page.get_by_role("button", name="Save timing", exact=True).click()
        page.locator("#timing-error").wait_for(state="visible")
        assert "completion" in page.locator("#timing-error").inner_text()
        assert tasks.task_detail(task_id)["intervals"][0]["ended_at"] == datetime(2026, 10, 24, 17)
        save_precise_timing(page, end="2026-10-24T16:00")
        stale.locator("#timing-start").fill("2026-10-24 13:00:00")
        stale.get_by_role("button", name="Save timing", exact=True).click()
        stale.wait_for_function("document.getElementById('timing-status').textContent.startsWith('Recorded timing refreshed.')")
        assert stale.locator("#timing-error").is_visible()
        assert stale.locator("#timing-end").input_value() == "2026-10-24 16:00:00"
        # Drop a successful POST response: recovery reads storage and does not repeat the write.
        writes = []
        def lose_ack(route):
            if route.request.method == "POST":
                writes.append(route.request)
                response = route.fetch()
                assert response.status == 200
                route.abort("failed")
            else:
                route.continue_()
        page.route("**/tasks/*/timing*", lose_ack)
        page.locator("#timing-end").fill("2026-10-24 15:00:00")
        page.get_by_role("button", name="Save timing", exact=True).click()
        page.wait_for_function("document.getElementById('timing-status').textContent.startsWith('Recorded timing refreshed.')")
        assert len(writes) == 1
        assert page.locator("#timing-error").is_visible()
        assert page.locator("#timing-end").input_value() == "2026-10-24 15:00:00"
        assert page.locator(".total strong").inner_text() == "03:00"
        page.unroute("**/tasks/*/timing*", lose_ack)
        save_precise_timing(page, end="2026-10-24T14:00")
        # An unreadable recovery snapshot blocks editing and offers an explicit reload.
        page.route("**/tasks/*/timing*", lambda route: route.abort("failed"))
        page.locator("#timing-start").fill("2026-10-24 12:30:00")
        page.get_by_role("button", name="Save timing", exact=True).click()
        page.locator("#timing-reload").wait_for(state="visible")
        assert page.locator("#timing-start").is_disabled()
        assert tasks.task_detail(task_id)["intervals"][0]["started_at"] == datetime(2026, 10, 24, 12)
        browser.close()


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
@pytest.mark.parametrize("unavailable", ["js", "css", "no-script"])
def test_vis_asset_failure_and_readonly_intervals(service, tasks, unavailable):
    playwright = pytest.importorskip("playwright.sync_api")
    repository = "github.com/example/fallback"
    task_id = tasks.start(repository, now=datetime(2026, 10, 24, 12))["task_id"]
    tasks.complete(repository, task_id, "a" * 40, "Read-only", now=datetime(2026, 10, 24, 17))
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(java_script_enabled=unavailable != "no-script")
        use_cached_timeline(page)
        page.route("https://unpkg.com/**/*." + unavailable, lambda route: route.abort())
        page.goto(service["url"] + f"/tasks/{task_id}")
        assert page.locator("#timing-editor").is_hidden()
        assert page.locator(".interval").first.is_visible()
        assert page.locator("#timing-no-script").is_visible()
        if unavailable != "no-script":
            assert "unpkg.com" in page.locator("#timing-no-script").inner_text()
        assert page.locator("form.pause-form").count() == 0
        browser.close()


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
@pytest.mark.parametrize("failure", ["server", "timeout"])
def test_vis_failed_drag_settles_once_and_refetches_before_editing(service, tasks, failure):
    playwright = pytest.importorskip("playwright.sync_api")
    repository = "github.com/example/failed-drag"
    task_id = tasks.start(repository, now=datetime(2026, 10, 24, 12))["task_id"]
    tasks.complete(repository, task_id, "a" * 40, "Failed drag", now=datetime(2026, 10, 24, 14))
    before = tasks.task_detail(task_id)
    writes = []
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(timezone_id="UTC")
        use_cached_timeline(page)
        observe_timeline_hooks(page)
        page.goto(service["url"] + f"/tasks/{task_id}")
        def fail_write(route):
            if route.request.method == "POST":
                writes.append(route.request)
                if failure == "server":
                    route.fulfill(status=503, json={"error": "Unavailable"})
                # Otherwise leave the request pending until AbortSignal.timeout fires.
            else:
                route.continue_()
        page.route("**/tasks/*/timing*", fail_write)
        drag_work_range(page, 0, -1800, edge="right", wait=False)
        if failure == "timeout":
            page.wait_for_function("timelineHooks.length === 1")
            assert page.evaluate("timelineHooks[0].calls") == 0
            assert page.locator("#timing-start").is_disabled()
            assert page.locator(".total strong").inner_text() == "02:00"
        page.wait_for_function("document.getElementById('timing-status').textContent.startsWith('Recorded timing refreshed.')",
                               timeout=20000)
        assert len(writes) == 1
        assert page.evaluate("timelineHooks") == [{"name": "onMove", "calls": 1, "accepted": False}]
        assert page.locator("#timing-error").is_visible()
        assert page.locator("#timing-end").input_value() == "2026-10-24 14:00:00"
        assert not page.locator("#timing-start").is_disabled()
        assert tasks.task_detail(task_id) == before
        browser.close()


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
@pytest.mark.parametrize("start,end,invalid,valid,expected", [
    (datetime(2025, 3, 9, 5, 30), datetime(2025, 3, 9, 8),
     "2025-03-09 02:30:00", "2025-03-09 03:30:00", datetime(2025, 3, 9, 7, 30)),
    (datetime(2025, 11, 2, 4, 30), datetime(2025, 11, 2, 8),
     "2025-11-02 01:15:00", "2025-11-02 01:15:00-05:00", datetime(2025, 11, 2, 6, 15)),
])
def test_vis_local_time_dst_validation(service, tasks, start, end, invalid, valid, expected):
    playwright = pytest.importorskip("playwright.sync_api")
    repository = "github.com/example/local-dst"
    task_id = tasks.start(repository, now=start)["task_id"]
    tasks.complete(repository, task_id, "a" * 40, "Local DST", now=end)
    writes = []
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(timezone_id="America/Toronto")
        use_cached_timeline(page)
        page.on("request", lambda request: writes.append(request) if request.method == "POST" else None)
        page.goto(service["url"] + f"/tasks/{task_id}")
        page.get_by_label("Start", exact=True).fill(invalid)
        assert page.locator("#timing-total").inner_text() == "—"
        page.get_by_role("button", name="Save timing", exact=True).click()
        assert "Enter a valid local time" in page.locator("#timing-error").inner_text()
        assert writes == []
        save_precise_timing(page, start=valid)
        assert len(writes) == 1
        assert tasks.task_detail(task_id)["intervals"][0]["started_at"] == expected
        browser.close()


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
def test_vis_local_calendar_and_unchanged_timestamp_precision(service, tasks):
    playwright = pytest.importorskip("playwright.sync_api")
    repository = "github.com/example/local-calendar"
    # The second occurrence of 01:15 must retain its original offset and precision.
    start = datetime(2025, 11, 2, 6, 15, 0, 123456)
    task_id = tasks.start(repository, now=start)["task_id"]
    tasks.complete(repository, task_id, "a" * 40, "Local precision", now=datetime(2025, 11, 2, 8))
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(timezone_id="America/Toronto")
        use_cached_timeline(page)
        page.goto(service["url"] + f"/tasks/{task_id}")
        assert page.get_by_label("Start", exact=True).input_value() == "2025-11-02 01:15:00"
        assert page.locator("#timing-save").is_disabled()
        picker = page.get_by_label("Choose end date and time", exact=True)
        picker.fill("2025-11-02T02:30")
        assert page.get_by_label("End", exact=True).input_value() == "2025-11-02 02:30:00"
        assert page.locator("#timing-total").inner_text() == "01:14:59"
        page.get_by_role("button", name="Save timing", exact=True).click()
        page.wait_for_function("document.getElementById('timing-status').textContent.startsWith('Timing saved.')")
        row = tasks.task_detail(task_id)["intervals"][0]
        assert row["started_at"] == start
        assert row["ended_at"] == datetime(2025, 11, 2, 7, 30)
        page.reload()
        assert page.locator("#timing-save").is_disabled()
        assert page.get_by_label("End", exact=True).input_value() == "2025-11-02 02:30:00"
        browser.close()
