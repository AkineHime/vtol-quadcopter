"""Start the ground station:  python run.py

Serves the dashboard, API, WebSockets and the phone camera page over HTTPS
on port 8443 (GS_PORT) and reads telemetry from MAVLINK_URL. The same app is
also served over plain HTTP on http://localhost:8080 (GS_HTTP_PORT, this
machine only; 0 disables it): browsers treat localhost as a secure origin,
so the dashboard works there without the certificate warning. Phones still
need the HTTPS address for the camera."""
from __future__ import annotations

import asyncio
import socket

import uvicorn

from backend import config
from backend.app import create_app
from backend.certs import ensure_cert
from backend.signaling import Signaling
from backend.telemetry import Telemetry


def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def main() -> None:
    cert, key, ips = ensure_cert(config.CERT_DIR)
    app = create_app(telemetry=Telemetry(config.MAVLINK_URL), signaling=Signaling())
    lan = [ip for ip in ips if not ip.startswith("127.")] or ["<laptop-ip>"]
    print(f"\n  Dashboard     https://localhost:{config.PORT}")
    if config.HTTP_PORT:
        print(f"                http://localhost:{config.HTTP_PORT}  (this computer only)")
    for ip in lan:
        print(f"  Phone camera  https://{ip}:{config.PORT}/camera")
        print(f"  Phone setup   https://{ip}:{config.PORT}/phone   (or scan the QR code on the dashboard)")
    print(f"  No warnings:  certutil -user -addstore Root \"{config.CERT_DIR / 'ca.pem'}\"   (once; see README)")
    print(f"  Telemetry     {config.MAVLINK_URL}")
    if not config.FRONTEND_DIST.exists():
        print("  (frontend not built yet: cd frontend && npm install && npm run build)")
    print()
    servers = [uvicorn.Server(uvicorn.Config(app, host=config.HOST, port=config.PORT, ssl_certfile=str(cert),
                                             ssl_keyfile=str(key), log_level="warning"))]
    if config.HTTP_PORT and not port_free(config.HTTP_PORT):
        print(f"  (port {config.HTTP_PORT} is busy: no http://localhost mirror this time)")
    elif config.HTTP_PORT:    # same app object; only the first server runs its startup/shutdown
        servers.append(uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=config.HTTP_PORT,
                                                     log_level="warning", lifespan="off")))

    async def serve():
        await asyncio.gather(*(s.serve() for s in servers))
    asyncio.run(serve())


if __name__ == "__main__":
    main()
