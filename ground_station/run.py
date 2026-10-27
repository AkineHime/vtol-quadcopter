"""Start the ground station:  python run.py

Serves the dashboard, API, WebSockets and the phone camera page over HTTPS
on port 8443 (GS_PORT) and reads telemetry from MAVLINK_URL."""
from __future__ import annotations

import uvicorn

from backend import config
from backend.app import create_app
from backend.certs import ensure_cert
from backend.signaling import Signaling
from backend.telemetry import Telemetry


def main() -> None:
    cert, key, ips = ensure_cert(config.CERT_DIR)
    app = create_app(telemetry=Telemetry(config.MAVLINK_URL), signaling=Signaling())
    lan = [ip for ip in ips if not ip.startswith("127.")] or ["<laptop-ip>"]
    print(f"\n  Dashboard     https://localhost:{config.PORT}")
    for ip in lan:
        print(f"  Phone camera  https://{ip}:{config.PORT}/camera")
    print(f"  Telemetry     {config.MAVLINK_URL}")
    if not config.FRONTEND_DIST.exists():
        print("  (frontend not built yet: cd frontend && npm install && npm run build)")
    print()
    uvicorn.run(app, host=config.HOST, port=config.PORT, ssl_certfile=str(cert),
                ssl_keyfile=str(key), log_level="warning")


if __name__ == "__main__":
    main()
