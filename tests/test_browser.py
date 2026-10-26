"""Optional real-browser acceptance check; Playwright is test tooling only."""

import base64
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest


def use_cached_plotly(page):
    asset = os.environ.get("DEVLOG_TEST_PLOTLY_ASSET")
    if asset:
        page.route("https://cdn.plot.ly/plotly-4.1.1.min.js",
                   lambda route: route.fulfill(path=asset, content_type="text/javascript"))


def drag_timing_boundary(page, index, edge, target):
    page.get_by_role("button", name="Focus task", exact=True).click()
    handles = page.locator(".timing-handle")
    left, right = handles.first, handles.last
    left_box, right_box = left.bounding_box(), right.bounding_box()
    left_value, right_value = float(left.get_attribute("aria-valuenow")), float(right.get_attribute("aria-valuenow"))
    scale = (right_box["x"] - left_box["x"]) / (right_value - left_value)
    handle = page.locator(f'.timing-handle[data-index="{index}"][data-edge="{edge}"]')
    box = handle.bounding_box()
    current = float(handle.get_attribute("aria-valuenow"))
    destination = target.replace(tzinfo=timezone.utc).timestamp() * 1000
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + (destination - current) * scale, y, steps=10)
    page.mouse.up()


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
        assert page.locator(".total strong").inner_text() == "3.00"
        assert page.evaluate("document.getElementById('daily-chart').data.map(trace => trace.y)") == [[0, 0, 0, 0, 0, 2, 0], [0, 0, 0, 0, 0, 1, 0]]
        assert page.evaluate("document.getElementById('daily-chart').layout.barmode") == "stack"
        assert page.locator("#daily-chart .annotation-text").all_text_contents() == ["0.00"] * 5 + ["3.00", "0.00"]
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

        # Hiding a lower project must move the separator with the remaining bar.
        page.locator("#daily-chart .legendtoggle").nth(0).click()
        page.wait_for_function("document.getElementById('daily-chart').layout.shapes[0].y0 === .25")
        page.wait_for_function("document.getElementById('daily-chart').layout.annotations[5].text === '1.00'")
        page.locator("#daily-chart .legendtoggle").nth(0).click()
        page.wait_for_function("document.getElementById('daily-chart').layout.shapes[0].y0 === 2.25")
        page.wait_for_function("document.getElementById('daily-chart').layout.annotations[5].text === '3.00'")
        page.locator("#daily-chart .legendtoggle").nth(1).click()
        page.wait_for_function("document.getElementById('daily-chart').layout.shapes.length === 0")
        page.wait_for_function("document.getElementById('daily-chart').layout.annotations[5].text === '2.00'")
        page.locator("#daily-chart .legendtoggle").nth(1).click()
        page.wait_for_function("document.getElementById('daily-chart').layout.shapes.length === 1")

        # Every section collapses to its heading and supports keyboard toggling.
        panels = page.locator("main > details.panel")
        assert panels.count() == 4
        contents = [".filters", "#current-task-status", "#daily-chart", ".table-wrap"]
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
        page.get_by_role("button", name="Show report").click()
        page.wait_for_selector("#daily-chart .plot-container")
        assert page.locator(".total strong").inner_text() == "1.00"
        assert page.evaluate("document.getElementById('daily-chart').data[0].y") == [0, 0, 0, 0, 0, 1, 0]
        assert page.locator("#daily-chart .annotation-text").all_text_contents() == ["0.00"] * 5 + ["1.00", "0.00"]
        assert page.evaluate("document.getElementById('daily-chart').data[0].marker.color") == colors[1]
        assert page.evaluate("document.getElementById('daily-chart').layout.shapes[0].y0") == .25
        line = page.locator("#daily-chart .shapelayer path").bounding_box()
        page.mouse.click(line["x"] + line["width"] / 2, line["y"])
        page.wait_for_url("**/tasks?**")
        assert parse_qs(urlsplit(page.url).query)["repository"] == ["github.com/nadimghaznavi/beta"]
        assert errors == []
        browser.close()


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
def test_completed_editor_four_handles_cancel_conflict_touch_and_readonly_fallback(service, tasks):
    playwright = pytest.importorskip("playwright.sync_api")
    previous_repo, repository = "github.com/example/previous", "github.com/example/edited"
    previous = tasks.start(previous_repo, now=datetime(2026, 10, 24, 10))["task_id"]
    tasks.complete(previous_repo, previous, "b" * 40, "Previous work", now=datetime(2026, 10, 24, 11))
    task_id = tasks.start(repository, now=datetime(2026, 10, 24, 12))["task_id"]
    tasks.pause(repository, now=datetime(2026, 10, 24, 14))
    tasks.start(repository, now=datetime(2026, 10, 24, 15))
    tasks.complete(repository, task_id, "a" * 40, "Historical work", now=datetime(2026, 10, 24, 17))
    before = tasks.task_detail(task_id)
    previous_before = tasks.task_detail(previous)
    errors = []
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        url = service["url"] + f"/tasks/{task_id}?start=2026-10-24&end=2026-10-25&lang=en"
        page.goto(url)
        assert page.locator("#timing-editor").is_visible()
        assert page.locator(".timing-handle").count() == 4
        assert float(page.locator(".timing-handle").last.get_attribute("aria-valuemax")) == datetime(
            2026, 10, 24, 17, tzinfo=timezone.utc).timestamp() * 1000
        assert page.locator(".timing-span.fixed strong").inner_text() == f"Task #{previous}"
        assert page.get_by_text("Insert a pause", exact=True).count() == 0
        loaded = page.locator("#timing-loaded").inner_text()
        handle = page.locator('.timing-handle[data-index="0"][data-edge="start"]')
        initial = int(handle.get_attribute("aria-valuenow"))
        handle.press("Shift+ArrowRight")
        assert int(handle.get_attribute("aria-valuenow")) == initial + 1000
        handle.press("ArrowRight")
        assert int(handle.get_attribute("aria-valuenow")) == initial + 61000
        page.get_by_role("button", name="Cancel", exact=True).click()
        assert page.locator("#timing-loaded").inner_text() == loaded
        assert page.locator("#timing-total").inner_text() == "Elapsed time: 04:00:00"
        drag_timing_boundary(page, 1, "end", datetime(2026, 10, 24, 18))
        assert page.locator("#timing-save").is_disabled()
        assert page.locator("#timing-completed").is_visible()
        drag_timing_boundary(page, 0, "start", datetime(2026, 10, 24, 10))
        assert float(handle.get_attribute("aria-valuenow")) == datetime(2026, 10, 24, 11, tzinfo=timezone.utc).timestamp() * 1000
        page.get_by_role("button", name="Cancel", exact=True).click()
        stale = browser.new_page(viewport={"width": 1200, "height": 1000})
        stale.goto(url)
        for index, edge, hour, minute in [(0, "start", 12, 30), (0, "end", 13, 30),
                                          (1, "start", 15, 30), (1, "end", 16, 30)]:
            drag_timing_boundary(page, index, edge, datetime(2026, 10, 24, hour, minute))
        assert page.locator("#timing-total").inner_text() == "Elapsed time: 02:00:00"
        assert tasks.task_detail(task_id) == before  # Dragging has made no writes.
        blocks = page.locator(".timing-span.active")
        assert abs(blocks.nth(0).bounding_box()["width"] - blocks.nth(1).bounding_box()["width"]) < 1
        assert page.locator("#timing-loaded").inner_text() == loaded
        page.get_by_role("button", name="Save timing", exact=True).click()
        page.wait_for_url("**saved=timing")
        assert "start=2026-10-24" in page.url and "lang=en" in page.url
        assert page.locator(".total strong").inner_text() == "2.00"
        assert page.get_by_text("Timing saved.", exact=False).is_visible()
        after = tasks.task_detail(task_id)
        assert {k: v for k, v in after.items() if k != "intervals"} == {
            k: v for k, v in before.items() if k != "intervals"}
        assert tasks.task_detail(previous) == previous_before
        stale.locator(".timing-handle").first.press("ArrowRight")
        stale.get_by_role("button", name="Save timing", exact=True).click()
        stale.locator("#timing-error").wait_for(state="visible")
        assert "Reload" in stale.locator("#timing-error").inner_text()
        assert stale.locator("#timing-save").is_disabled()
        assert tasks.task_detail(task_id) == after
        page.get_by_role("button", name="Focus task", exact=True).click()
        screenshots = os.environ.get("DEVLOG_SCREENSHOT_DIR")
        if screenshots:
            Path(screenshots).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(screenshots) / "timing-desktop.png"), full_page=True)
        mobile = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        mobile_page = mobile.new_page()
        mobile_page.on("pageerror", lambda error: errors.append(str(error)))
        mobile_page.goto(url)
        mobile_page.get_by_role("button", name="Focus task", exact=True).click()
        assert mobile_page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        left, right = mobile_page.locator(".timing-handle").first, mobile_page.locator(".timing-handle").last
        left_box, right_box = left.bounding_box(), right.bounding_box()
        # Touch-drag the final work boundary back by half an hour.
        scale = (right_box["x"] - left_box["x"]) / (float(right.get_attribute("aria-valuenow")) - float(left.get_attribute("aria-valuenow")))
        mobile_page.locator("#timing-track").scroll_into_view_if_needed()
        right_box = right.bounding_box()
        x, y = right_box["x"] + 14, right_box["y"] + 60
        session = mobile.new_cdp_session(mobile_page)
        session.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]})
        for step in range(1, 11):
            session.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [
                {"x": x - 1800000 * scale * step / 10, "y": y}]})
        session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        assert mobile_page.locator("#timing-total").inner_text() == "Elapsed time: 01:30:00"
        mobile_page.get_by_role("button", name="Cancel", exact=True).click()
        mobile_page.get_by_role("button", name="Focus task", exact=True).click()
        if screenshots:
            mobile_page.screenshot(path=str(Path(screenshots) / "timing-mobile.png"), full_page=True)
        readonly = browser.new_context(java_script_enabled=False)
        readonly_page = readonly.new_page()
        readonly_page.goto(url)
        assert readonly_page.locator("#timing-editor").is_hidden()
        assert readonly_page.locator(".interval").first.is_visible()
        assert readonly_page.get_by_text("Enable JavaScript", exact=False).is_visible()
        assert readonly_page.locator("form.pause-form").count() == 0
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
        page = browser.new_page(viewport={"width": 1200, "height": 900}, ignore_https_errors=True)
        use_cached_plotly(page)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(service["url"] + "/?start=2026-10-24&end=2026-10-25")
        page.wait_for_selector("#daily-chart .plot-container")
        assert page.locator(".total strong").inner_text() == "14.00"
        bar = page.locator("#daily-chart .barlayer .point").last.bounding_box()
        page.mouse.click(bar["x"] + bar["width"] / 2, bar["y"] + bar["height"] / 2)
        page.wait_for_url("**/tasks?**")
        assert "day=2026-10-25" in page.url
        assert "repository=" in page.url
        back_to_report = page.get_by_role("link", name="Back to report").get_attribute("href")
        assert parse_qs(urlsplit(back_to_report).query) == {
            "start": ["2026-10-24"], "end": ["2026-10-25"], "lang": ["en"]}
        page.locator(".task-link").click()
        page.wait_for_url(f"**/tasks/{task_id}?**")
        assert page.locator(".total strong").inner_text() == "12.00"
        assert page.locator(".task-metadata time").all_text_contents() == [
            "2026-10-24 21:00:00", "2026-10-25 09:00:00"]
        assert page.locator(".interval time").all_text_contents() == [
            "2026-10-24 21:00:00", "2026-10-25 09:00:00"]
        assert page.locator(".elapsed").all_text_contents() == ["Elapsed time: 12:00:00"]
        drag_timing_boundary(page, 0, "end", datetime(2026, 10, 25, 2))
        assert page.locator("#timing-total").inner_text() == "Elapsed time: 01:00:00"
        page.get_by_role("button", name="Save timing").click()
        page.wait_for_url("**saved=timing")
        assert page.get_by_text("Timing saved.", exact=False).is_visible()
        assert page.locator(".total strong").inner_text() == "1.00"
        assert page.locator(".interval").count() == 2
        assert page.locator(".interval.pause").count() == 1
        assert page.locator(".elapsed").all_text_contents() == [
            "Elapsed time: 01:00:00", "Elapsed time: 11:00:00"]
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
        assert page.locator(".total strong").inner_text() == "3.00"
        assert page.evaluate("document.getElementById('daily-chart').data.map(trace => trace.y)") == [[2, 0], [1, 0]]
        # The table drill-down and editor work even when the CDN cannot be reached.
        page.route("https://cdn.plot.ly/plotly-4.1.1.min.js", lambda route: route.abort())
        page.reload()
        assert page.locator("#chart-error").is_visible()
        page.get_by_role("link", name="2026-10-25", exact=True).click()
        page.locator(".task-link").click()
        assert page.locator(".total strong").inner_text() == "1.00"
        assert page.locator("#timing-editor").is_visible()
        assert errors == []
        browser.close()
