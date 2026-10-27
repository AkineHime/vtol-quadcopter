"""Paths and settings. Everything can be overridden with environment variables."""
from __future__ import annotations

import os
from pathlib import Path

GS_DIR = Path(__file__).resolve().parent.parent          # ground_station/
REPO = GS_DIR.parent
DEMO = REPO / "flight_software" / "demo"

TREES_CSV = Path(os.environ.get("TREES_CSV", DEMO / "trees.csv"))
LAYOUT_JSON = Path(os.environ.get("LAYOUT_JSON", DEMO / "layout.json"))
DB_PATH = Path(os.environ.get("GS_DB", GS_DIR / "data" / "ground_station.db"))
CERT_DIR = Path(os.environ.get("GS_CERTS", GS_DIR / "certs"))
MEDIA_DIR = Path(os.environ.get("GS_MEDIA", GS_DIR / "media"))
FRONTEND_DIST = GS_DIR / "frontend" / "dist"
STATIC_DIR = Path(__file__).resolve().parent / "static"

MAVLINK_URL = os.environ.get("MAVLINK_URL", "tcp:127.0.0.1:5762")
HOST = os.environ.get("GS_HOST", "0.0.0.0")
PORT = int(os.environ.get("GS_PORT", "8443"))
CAPTURE_RADIUS = os.environ.get("GS_CAPTURE_RADIUS")   # m; default: layout.json crown_radius_m
