#!/usr/bin/env python3
"""Capture screenshots of the web UI for documentation."""

from playwright.sync_api import sync_playwright
from pathlib import Path
import time

SCREENSHOT_DIR = Path(__file__).parent.parent / "docs" / "screenshots"
BASE_URL = "http://127.0.0.1:8080"


def capture_screenshots():
    """Capture screenshots of all main pages."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        pages_to_capture = [
            ("", "dashboard.png", "Dashboard"),
            ("/map", "map.png", "Map"),
            ("/nodes", "nodes.png", "Nodes"),
            ("/messages", "messages.png", "Messages"),
        ]

        for path, filename, name in pages_to_capture:
            url = f"{BASE_URL}{path}"
            print(f"Capturing {name}...")
            page.goto(url)
            # Wait for page to fully load
            page.wait_for_load_state("networkidle")
            time.sleep(0.5)  # Extra time for any animations
            page.screenshot(path=SCREENSHOT_DIR / filename, full_page=False)
            print(f"  Saved {filename}")

        # Capture a node detail page if nodes exist
        print("Capturing Node Detail...")
        page.goto(f"{BASE_URL}/nodes")
        page.wait_for_load_state("networkidle")

        # Click on the first node link if available
        first_node_link = page.locator("table tbody tr td a").first
        if first_node_link.count() > 0:
            first_node_link.click()
            page.wait_for_load_state("networkidle")
            time.sleep(0.5)
            page.screenshot(path=SCREENSHOT_DIR / "node-detail.png", full_page=False)
            print("  Saved node-detail.png")
        else:
            print("  No nodes found, skipping node detail")

        browser.close()
        print(f"\nScreenshots saved to {SCREENSHOT_DIR}")


if __name__ == "__main__":
    capture_screenshots()
