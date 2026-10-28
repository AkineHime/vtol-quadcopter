"""MJPEG camera source (backend/camera.py): settings, address checks, stream relay."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from backend import camera
from backend.app import create_app

JPEG = b"\xff\xd8\xff\xe0fake-frame\xff\xd9"


class FakeIPWebcam(BaseHTTPRequestHandler):
    """Like the Android IP Webcam app: /video is multipart/x-mixed-replace JPEG frames."""
    def do_GET(self):
        if self.path != "/video":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        for _ in range(3):
            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(JPEG) + JPEG + b"\r\n")
        self.wfile.flush()

    def log_message(self, *a):
        pass


@pytest.fixture
def fake_cam():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeIPWebcam)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def test_normalise():
    assert camera.normalise("192.168.1.20:8080") == "http://192.168.1.20:8080/video"        # IP Webcam default path
    assert camera.normalise("http://192.168.4.1:81/stream") == "http://192.168.4.1:81/stream"  # ESP32-CAM
    assert camera.normalise("http://phone.local:8080/video") == "http://phone.local:8080/video"
    for bad in ("http://8.8.8.8/video", "ftp://192.168.1.2/x", "http://example.com/video", "http://0.0.0.0:8080"):
        with pytest.raises(ValueError):
            camera.normalise(bad)


def test_camera_setting_and_relay(fake_cam):
    with TestClient(create_app()) as client:
        assert client.post("/api/camera", json={"mode": "mjpeg", "url": "http://8.8.8.8:8080"}).status_code == 422
        c = client.post("/api/camera", json={"mode": "mjpeg", "url": f"127.0.0.1:{fake_cam}"}).json()
        assert c == {"mode": "mjpeg", "url": f"http://127.0.0.1:{fake_cam}/video"}
        assert client.get("/api/camera").json() == c
        with client.stream("GET", "/api/camera/stream") as r:
            assert r.status_code == 200 and r.headers["content-type"].startswith("multipart/x-mixed-replace")
            body = b"".join(r.iter_bytes())
        assert body.count(JPEG) == 3 and b"--frame" in body
        client.post("/api/camera", json={"mode": "mjpeg", "url": f"127.0.0.1:{fake_cam}/nothing"})
        assert client.get("/api/camera/stream").status_code == 502                       # camera answered 404
        client.post("/api/camera", json={"mode": "webrtc"})
        assert client.get("/api/camera/stream").status_code == 404
