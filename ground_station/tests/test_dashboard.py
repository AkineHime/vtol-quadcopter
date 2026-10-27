"""Step 5: the built dashboard in headless Chromium, end to end:
HTTPS server + fake vehicle circling the field + fake phone camera."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from fake_vehicle import FakeVehicle, circle

GS = Path(__file__).resolve().parent.parent
SHOT = os.environ.get("GS_SCREENSHOT")          # optional: save a screenshot here


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.mark.skipif(not (GS / "frontend" / "dist" / "index.html").exists(),
                    reason="frontend not built (cd frontend && npm run build)")
def test_dashboard(tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    vehicle = FakeVehicle(path=circle).start()
    port = _free_port()
    env = {**os.environ, "GS_PORT": str(port), "GS_DB": str(tmp_path / "ui.db"),
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

            # farm plan: 169 clickable palm icons, field outline, no map tiles
            dash.wait_for_function("document.querySelectorAll('.palm').length === 169", timeout=10000)
            assert dash.locator(".leaflet-tile").count() == 0

            # drone arrow appears and moves, trail grows
            dash.wait_for_selector(".drone", timeout=10000)
            assert dash.locator(".tel-title").inner_text() == "AUTO"
            p1 = dash.locator(".drone").bounding_box()
            time.sleep(1.5)
            p2 = dash.locator(".drone").bounding_box()
            assert abs(p1["x"] - p2["x"]) + abs(p1["y"] - p2["y"]) > 3, "drone marker should move"
            assert dash.locator("path.leaflet-interactive[stroke='#d4894f']").count() >= 1   # trail

            # click a tree -> detail card; set status -> UI + history update live
            dash.locator(".palm").nth(6 * 13 + 12).click(force=True)       # P0612
            dash.wait_for_selector(".tree-card")
            assert dash.locator(".tc-head h2").inner_text() == "P0612"
            dash.locator(".tree-card .seg button", has_text="Target").click()
            dash.wait_for_function("document.querySelector('.tc-pills .pill').textContent === 'Target'")
            dash.wait_for_function("document.querySelector('.history li b').textContent === 'Status'")
            dash.locator(".tree-card .row input").fill("east bunch looks ready")
            dash.locator(".tree-card .row button", has_text="Add").click()
            dash.wait_for_function("document.querySelector('.notes')?.textContent.includes('east bunch')")
            # overview panel picked it up as a target
            assert "P0612" in dash.locator(".panel").inner_text()

            # phone camera -> video card goes LIVE with real frames
            phone = ctx.new_page()
            phone.goto(f"{base}/camera")
            phone.click("#btn")
            dash.wait_for_function("document.querySelector('.vc-frame video').videoWidth > 0", timeout=15000)
            assert dash.locator(".vc-badge").inner_text() == "LIVE"

            dash.bring_to_front()
            time.sleep(1.0)
            if SHOT:
                dash.screenshot(path=SHOT)
            assert not errors, errors
            browser.close()
    finally:
        vehicle.stop.set()
        srv.terminate()
        srv.communicate(timeout=10)
