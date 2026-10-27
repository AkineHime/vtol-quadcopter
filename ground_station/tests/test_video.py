"""Step 4: WebRTC signalling relay, phone camera page, HTTPS cert, and a real
end-to-end stream between two headless Chromium pages over the HTTPS server."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from cryptography import x509
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.certs import ensure_cert, local_ips
from backend.signaling import Signaling

GS = Path(__file__).resolve().parent.parent


@pytest.fixture()
def client():
    with TestClient(create_app(signaling=Signaling())) as c:
        yield c


def test_camera_page_served(client):
    r = client.get("/camera")
    assert r.status_code == 200
    html = r.text
    assert "getUserMedia" in html and 'facingMode: { ideal: "environment" }' in html
    assert "playsinline" in html and "muted" in html          # iOS Safari inline autoplay


def test_relay(client):
    with client.websocket_connect("/ws/signal?role=viewer") as viewer:
        assert viewer.receive_json() == {"type": "camera-off"}
        with client.websocket_connect("/ws/signal?role=camera") as cam:
            assert viewer.receive_json() == {"type": "camera-on"}
            hello = cam.receive_json()
            assert hello["type"] == "viewer"
            vid = hello["id"]
            cam.send_json({"type": "offer", "to": vid, "sdp": {"type": "offer", "sdp": "v=0"}})
            assert viewer.receive_json() == {"type": "offer", "sdp": {"type": "offer", "sdp": "v=0"}, "from": "camera"}
            viewer.send_json({"type": "answer", "sdp": {"type": "answer", "sdp": "v=0"}})
            assert cam.receive_json() == {"type": "answer", "sdp": {"type": "answer", "sdp": "v=0"}, "from": vid}
            viewer.send_json({"type": "ice", "candidate": {"candidate": "c"}})
            assert cam.receive_json()["from"] == vid
            with client.websocket_connect("/ws/signal?role=viewer") as v2:   # second viewer
                assert v2.receive_json() == {"type": "camera-on"}
                vid2 = cam.receive_json()["id"]
                assert vid2 != vid
            assert cam.receive_json() == {"type": "bye", "id": vid2}
        assert viewer.receive_json() == {"type": "camera-off"}


def test_cert(tmp_path):
    cert, key, ips = ensure_cert(tmp_path)
    c = x509.load_pem_x509_certificate(cert.read_bytes())
    san = c.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert set(local_ips()) <= {str(i) for i in san.get_values_for_type(x509.IPAddress)}
    assert "localhost" in san.get_values_for_type(x509.DNSName)
    mtime = cert.stat().st_mtime_ns
    ensure_cert(tmp_path)
    assert cert.stat().st_mtime_ns == mtime, "cert is reused while the IPs are unchanged"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_end_to_end_stream(tmp_path):
    """Phone page (fake camera) -> HTTPS server -> dashboard viewer receives frames."""
    pw = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    env = {**os.environ, "GS_PORT": str(port), "GS_DB": str(tmp_path / "e2e.db"),
           "GS_CERTS": str(tmp_path / "certs"), "MAVLINK_URL": "none"}
    srv = subprocess.Popen([sys.executable, "-u", "run.py"], cwd=GS, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"https://127.0.0.1:{port}"
    viewer_js = (GS / "frontend" / "src" / "videoViewer.js").read_text()
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
            ctx = browser.new_context(ignore_https_errors=True, permissions=["camera"])
            phone = ctx.new_page()
            phone.goto(f"{base}/camera")
            phone.click("#btn")
            phone.wait_for_function("document.getElementById('preview').videoWidth > 0", timeout=10000)

            dash = ctx.new_page()
            dash.goto(f"{base}/api/layout")                    # same origin, any page will do
            dash.add_script_tag(type="module", content=viewer_js + """
                const v = document.createElement('video'); v.muted = true; v.autoplay = true;
                document.body.appendChild(v); window.__status = [];
                startViewer(s => { v.srcObject = s; if (s) v.play(); }, s => window.__status.push(s));
                window.__video = v;""")
            dash.wait_for_function("window.__video && window.__video.videoWidth > 0", timeout=15000)
            assert "live" in dash.evaluate("window.__status")
            phone.wait_for_function("document.getElementById('badge').textContent.startsWith('live')", timeout=5000)

            phone.click("#btn")                                 # phone stops -> dashboard sees camera-off
            dash.wait_for_function("window.__status.at(-1) === 'off'", timeout=5000)
            browser.close()
    finally:
        srv.terminate()
        out = srv.communicate(timeout=10)[0].decode()
    assert "Phone camera  https://" in out
