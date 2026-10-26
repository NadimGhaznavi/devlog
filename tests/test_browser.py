"""Optional real-browser acceptance check; Playwright is test tooling only."""

import base64
from datetime import datetime, timedelta
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest


def use_cached_plotly(page):
    asset = os.environ.get("DEVLOG_TEST_PLOTLY_ASSET")
    if asset:
        page.route("https://cdn.plot.ly/plotly-4.1.1.min.js",
                   lambda route: route.fulfill(path=asset, content_type="text/javascript"))


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
def test_drilldown_insert_overnight_pause_and_chart_fallback(service, tasks):
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
        page.get_by_text("Insert a pause", exact=True).click()
        assert page.get_by_label("Pause began", exact=True).get_attribute("placeholder") == "2026-10-24 21:00"
        assert page.get_by_label("Work resumed (optional)", exact=True).get_attribute("placeholder") == "2026-10-25 09:00"
        page.get_by_label("Pause began", exact=True).fill("2026-10-24 22:00")
        page.get_by_label("Work resumed (optional)", exact=True).fill("2026-10-24 21:00")
        page.get_by_role("button", name="Save pause").click()
        assert page.get_by_role("alert").is_visible()
        assert page.get_by_label("Pause began", exact=True).input_value() == "2026-10-24 22:00"
        page.get_by_label("Work resumed (optional)", exact=True).fill("2026-10-25 08:00")
        page.get_by_role("button", name="Save pause").click()
        assert page.get_by_role("status").inner_text().startswith("Pause saved")
        assert page.locator(".total strong").inner_text() == "2.00"
        assert page.locator(".interval").count() == 3
        assert page.locator(".interval.pause").count() == 1
        assert page.locator(".elapsed").all_text_contents() == [
            "Elapsed time: 01:00:00", "Elapsed time: 10:00:00", "Elapsed time: 01:00:00"]
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
        assert page.locator(".total strong").inner_text() == "4.00"
        assert page.evaluate("document.getElementById('daily-chart').data.map(trace => trace.y)") == [[2, 0], [1, 1]]
        # The table drill-down and forms work even when the CDN cannot be reached.
        page.route("https://cdn.plot.ly/plotly-4.1.1.min.js", lambda route: route.abort())
        page.reload()
        assert page.locator("#chart-error").is_visible()
        page.get_by_role("link", name="2026-10-25", exact=True).click()
        page.locator(".task-link").click()
        assert page.locator(".total strong").inner_text() == "2.00"
        assert errors == []
        browser.close()
