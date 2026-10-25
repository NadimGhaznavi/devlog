"""Optional real-browser acceptance check; Playwright is test tooling only."""

from datetime import datetime
import os
from pathlib import Path

import pytest


@pytest.mark.database
@pytest.mark.skipif(os.environ.get("DEVLOG_TEST_BROWSER") != "1", reason="Set DEVLOG_TEST_BROWSER=1 and install Playwright/Chromium")
def test_plotly_report_filters_and_mobile_layout(service, tasks):
    playwright = pytest.importorskip("playwright.sync_api")
    tasks.start("github.com/nadimghaznavi/alpha", now=datetime(2026, 10, 24, 10))
    tasks.pause("github.com/nadimghaznavi/alpha", now=datetime(2026, 10, 24, 12))
    tasks.start("github.com/nadimghaznavi/beta", now=datetime(2026, 10, 24, 13))
    tasks.pause("github.com/nadimghaznavi/beta", now=datetime(2026, 10, 24, 14))
    errors = []
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900}, ignore_https_errors=True)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(service["url"] + "/?start=2026-10-23&end=2026-10-25")
        page.wait_for_selector("#daily-chart .plot-container")
        assert page.evaluate("Plotly.version") == "4.1.1"
        assert page.locator(".total strong").inner_text() == "3.00"
        assert page.evaluate("document.getElementById('daily-chart').data.map(trace => trace.y)") == [[0, 2, 0], [0, 1, 0]]
        assert page.evaluate("document.getElementById('daily-chart').layout.barmode") == "stack"
        colors = page.evaluate("document.getElementById('daily-chart').data.map(trace => trace.marker.color)")
        assert colors == ["rgb(230, 57, 70)", "rgb(243, 84, 37)"]
        assert page.locator("#daily-chart .legendtext").all_text_contents() == ["alpha", "beta"]

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
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(300)
        assert_legend_below_date()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        if screenshot:
            page.screenshot(path=str(Path(screenshot) / "devlog-mobile.png"), full_page=True)
        page.set_viewport_size({"width": 1200, "height": 900})
        page.get_by_label("Repository", exact=True).select_option("github.com/nadimghaznavi/beta")
        page.get_by_role("button", name="Show report").click()
        page.wait_for_selector("#daily-chart .plot-container")
        assert page.locator(".total strong").inner_text() == "1.00"
        assert page.evaluate("document.getElementById('daily-chart').data[0].y") == [0, 1, 0]
        assert page.evaluate("document.getElementById('daily-chart').data[0].marker.color") == colors[1]
        assert errors == []
        browser.close()
