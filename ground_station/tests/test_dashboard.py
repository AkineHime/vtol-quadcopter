"""The built dashboard in headless Chromium, end to end: HTTPS server + fake
vehicle circling the field + fake phone camera. Covers the farm plan, drone
arrow + trail, the tree inspector, live video, the every-Nth photo pattern
and automatic photos when the drone passes over a palm."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from fake_vehicle import FakeVehicle, circle

GS = Path(__file__).resolve().parent.parent
SHOT = os.environ.get("GS_SCREENSHOT")          # optional: save screenshots with this prefix
GREEN = "#30d158"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _palm_colors(page):
    return page.evaluate("[...document.querySelectorAll('.palm span')].map(s => s.style.getPropertyValue('--c'))")


@pytest.mark.skipif(not (GS / "frontend" / "dist" / "index.html").exists(),
                    reason="frontend not built (cd frontend && npm run build)")
def test_dashboard(tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    vehicle = FakeVehicle(path=circle).start()
    port = _free_port()
    media = tmp_path / "media"
    env = {**os.environ, "GS_PORT": str(port), "GS_DB": str(tmp_path / "ui.db"), "GS_MEDIA": str(media),
           "GS_CERTS": str(tmp_path / "certs"), "MAVLINK_URL": f"tcp:127.0.0.1:{vehicle.port}"}
    srv = subprocess.Popen([sys.executable, "-u", "run.py"], cwd=GS, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"https://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), 0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        with pw.sync_playwright() as p:
            browser = p.chromium.launch(args=["--use-fake-device-for-media-stream",
                                              "--use-fake-ui-for-media-stream"])
            ctx = browser.new_context(ignore_https_errors=True, permissions=["camera"],
                                      viewport={"width": 1600, "height": 900})
            errors = []
            dash = ctx.new_page()
            dash.on("pageerror", lambda e: errors.append(str(e)))
            dash.goto(base)

            # farm plan: 169 clickable palm icons, no map tiles
            dash.wait_for_function("document.querySelectorAll('.palm').length === 169", timeout=10000)
            assert dash.locator(".leaflet-tile").count() == 0
            if SHOT:
                time.sleep(0.5)
                dash.screenshot(path=f"{SHOT}-initial.png")

            # photo pattern: every 2nd palm -> 85 highlighted, 84 dimmed
            dash.locator(".sidebar .segmented button", has_text="2nd").click()
            dash.wait_for_function("document.querySelectorAll('.palm.dim').length === 84")
            assert "0 of 85 photographed" in dash.locator(".sidebar").inner_text()

            # drone arrow appears and moves, trail grows
            dash.wait_for_selector(".drone", timeout=10000)
            assert dash.locator(".hud-title").inner_text() == "AUTO"
            p1 = dash.locator(".drone").bounding_box()
            time.sleep(1.5)
            p2 = dash.locator(".drone").bounding_box()
            assert abs(p1["x"] - p2["x"]) + abs(p1["y"] - p2["y"]) > 3, "drone marker should move"
            assert dash.locator(".leaflet-overlay-pane path[stroke='#e3a06a']").count() >= 1   # trail

            # phone camera -> video goes live
            phone = ctx.new_page()
            phone.goto(f"{base}/camera")
            phone.click("#btn")
            dash.bring_to_front()
            dash.wait_for_function("document.querySelector('.camera-card video').videoWidth > 0", timeout=15000)
            assert dash.locator(".cam-label").inner_text().strip() == "Live"

            # drone passes over pattern palms -> photo taken, palm turns green
            dash.wait_for_function(f"[...document.querySelectorAll('.palm span')].some(s => s.style.getPropertyValue('--c') === '{GREEN}')",
                                   timeout=40000)
            photos = list(media.rglob("*.jpg"))
            assert photos and photos[0].read_bytes()[:2] == b"\xff\xd8"
            done = [c for c in _palm_colors(dash) if c == GREEN]
            assert 1 <= len(done) <= 85
            assert f"{len(done)} of 85 photographed" in dash.locator(".sidebar").inner_text()

            # inspector on a photographed palm shows the photo
            shot_id = photos[0].parent.name
            dash.locator(".sidebar .rail-btn, .rail .rail-btn").nth(1).click()          # Trees list
            dash.locator(".search input").fill(shot_id)
            dash.locator(".sidebar .cell", has_text=shot_id).click()
            dash.wait_for_selector(".inspector .hero img")
            assert dash.locator(".insp-head h2").inner_text() == shot_id
            assert "Photographed" in dash.locator(".tags").inner_text()

            # status + note actions update live
            dash.locator(".inspector .segmented button", has_text="Target").click()
            dash.wait_for_function("document.querySelector('.tags .tag').textContent === 'Target'")
            dash.wait_for_function("document.querySelector('.event-top b').textContent === 'Status changed'")
            dash.locator(".inspector input").fill("east bunch looks ready")
            dash.locator(".inspector .btn", has_text="Add").click()
            dash.wait_for_function("document.querySelector('.notes')?.textContent.includes('east bunch')")

            time.sleep(0.8)
            if SHOT:
                dash.screenshot(path=f"{SHOT}-inspector.png")
                dash.locator(".insp-head .close").click()
                dash.locator(".rail .rail-btn").nth(0).click()
                time.sleep(0.6)
                dash.screenshot(path=f"{SHOT}-overview.png")
            assert not errors, errors
            browser.close()
    finally:
        vehicle.stop.set()
        srv.terminate()
        srv.communicate(timeout=10)
