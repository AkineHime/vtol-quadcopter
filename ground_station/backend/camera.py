"""Camera source: an MJPEG stream on the local network, proxied to the dashboard.

Two kinds of camera speak the same protocol, an HTTP MJPEG stream:
  - an Android phone running the "IP Webcam" app: http://<phone-ip>:8080/video
  - the drone's ESP32-CAM (CameraWebServer):      http://<esp32-ip>:81/stream
so the same code serves the phone now and the real aircraft later. The browser
can't read pixels from a stream on another origin (needed for the colour-card
reader), so the dashboard plays /api/camera/stream, which this module relays.

The URL is stored in the meta table ('camera') so every open dashboard uses the
same one. Only private-network addresses are accepted: the server fetches the
URL itself, and must not be pointed at the internet.
"""
from __future__ import annotations

import ipaddress
import json
from urllib.parse import urlparse, urlunparse

DEFAULT_PATH = "/video"       # IP Webcam's MJPEG stream


def normalise(url: str) -> str:
    """'192.168.1.20:8080' -> 'http://192.168.1.20:8080/video'; raises ValueError
    for anything that is not http(s) to a private-network host."""
    url = url.strip()
    if "://" not in url:
        url = "http://" + url
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("expected http://<phone-ip>:<port>/…")
    host = u.hostname
    try:
        ip = ipaddress.ip_address(host)
        if not (ip.is_private or ip.is_loopback) or ip.is_unspecified:
            raise ValueError("only cameras on the local network (private addresses) are allowed")
    except ValueError as e:
        if "only cameras" in str(e):
            raise
        if not (host == "localhost" or host.endswith(".local")):
            raise ValueError("use the camera's IP address (or a .local name)") from None
    path = u.path if u.path not in ("", "/") else DEFAULT_PATH
    return urlunparse((u.scheme, u.netloc, path, "", u.query, ""))


def get(con) -> dict:
    row = con.execute("SELECT value FROM meta WHERE key='camera'").fetchone()
    return json.loads(row[0]) if row else {"mode": "webrtc", "url": None}


def set_(con, mode: str, url: str | None) -> dict:
    if mode not in ("webrtc", "mjpeg"):
        raise ValueError("mode must be webrtc or mjpeg")
    c = {"mode": mode, "url": normalise(url) if mode == "mjpeg" else None}
    con.execute("INSERT OR REPLACE INTO meta VALUES ('camera', ?)", (json.dumps(c),))
    return c
