"""FastAPI ground-station backend: REST API, live WebSocket, static pages."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, db
from .capture import Capture

MAX_PHOTO_BYTES = 8 * 1024 * 1024


class Hub:
    """Fan-out of JSON messages to every connected dashboard WebSocket."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    async def send_all(self, msg: dict) -> None:
        text = json.dumps(msg)
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except Exception:
                self.clients.discard(ws)



class PatternIn(BaseModel):
    every: Literal[1, 2, 4, 8]


class EventIn(BaseModel):
    kind: Literal["status", "visit", "detection", "note"]
    status: Literal["unscouted", "target", "cleared"] | None = None
    condition: Literal["healthy", "ripe", "frond", "ripe+frond"] | None = None
    confidence: float | None = Field(None, ge=0, le=1)
    image: str | None = None
    note: str | None = Field(None, max_length=2000)
    source: str = "dashboard"


async def watch_external_writes(con, hub: Hub, capture: Capture) -> None:
    """The planner / ML pipeline may write the SQLite file directly. PRAGMA
    data_version only changes on commits from *other* connections, so when it
    moves we push a fresh tree list to every dashboard."""
    last = con.execute("PRAGMA data_version").fetchone()[0]
    while True:
        await asyncio.sleep(1.0)
        v = con.execute("PRAGMA data_version").fetchone()[0]
        if v != last:
            last = v
            capture.refresh()
            await hub.send_all({"type": "trees", "trees": db.list_trees(con)})


def create_app(telemetry=None, signaling=None) -> FastAPI:
    con = db.connect()
    db.init_db(con)
    hub = Hub()
    capture = Capture(con, float(config.CAPTURE_RADIUS) if config.CAPTURE_RADIUS else None)
    tasks = []

    async def on_telemetry(msg: dict) -> None:
        await hub.send_all(msg)
        req = capture.check(msg)
        if req:
            await hub.send_all(req)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        hub.loop = asyncio.get_running_loop()
        tasks.append(asyncio.create_task(watch_external_writes(con, hub, capture)))
        if telemetry:     # the reader thread hands each message to the event loop
            telemetry.start(lambda m: asyncio.run_coroutine_threadsafe(on_telemetry(m), hub.loop))
        yield
        for t in tasks:
            t.cancel()
        if telemetry:
            telemetry.stop()

    app = FastAPI(title="Coconut VTOL ground station", lifespan=lifespan)
    app.state.con, app.state.hub, app.state.capture = con, hub, capture

    @app.get("/api/layout")
    def get_layout():
        lay = db.layout(con)
        h = lay["home"]
        n0, e0, size = lay["field_n0"], lay["field_e0"], lay["field_m"]
        corners = [db.meters_to_latlon(n, e, h["lat"], h["lon"])
                   for n, e in ((n0, e0), (n0, e0 + size), (n0 + size, e0 + size), (n0 + size, e0))]
        dock = db.meters_to_latlon(lay["dock"]["n"], lay["dock"]["e"], h["lat"], h["lon"])
        return {"layout": lay, "field": corners, "dock": dock}

    @app.get("/api/trees")
    def get_trees():
        return db.list_trees(con)

    @app.get("/api/trees/{tree_id}")
    def get_tree(tree_id: str):
        t = db.get_tree(con, tree_id)
        if not t:
            raise HTTPException(404, f"no tree {tree_id}")
        return {"tree": t, "history": db.history(con, tree_id)}

    @app.post("/api/trees/{tree_id}/events")
    async def post_event(tree_id: str, ev: EventIn):
        try:
            t = db.add_event(con, tree_id, **ev.model_dump())
        except KeyError:
            raise HTTPException(404, f"no tree {tree_id}")
        except ValueError as e:
            raise HTTPException(422, str(e))
        capture.refresh()
        await hub.send_all({"type": "tree", "tree": t})
        return t

    @app.post("/api/trees/{tree_id}/photo")
    async def post_photo(tree_id: str, capture_id: str, request: Request):
        """A dashboard answers a capture request with one JPEG frame (raw body)."""
        if not db.get_tree(con, tree_id):
            raise HTTPException(404, f"no tree {tree_id}")
        body = await request.body()
        if not body.startswith(b"\xff\xd8") or len(body) > MAX_PHOTO_BYTES:
            raise HTTPException(422, "expected a JPEG under 8 MB")
        if not capture.claim(capture_id, tree_id):
            raise HTTPException(409, "capture already answered or expired")
        folder = config.MEDIA_DIR / tree_id
        folder.mkdir(parents=True, exist_ok=True)
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".jpg"
        (folder / name).write_bytes(body)
        t = db.add_event(con, tree_id, "visit", image=f"{tree_id}/{name}",
                         note="Photo taken overhead", source="camera")
        capture.refresh()
        await hub.send_all({"type": "tree", "tree": t})
        return t

    @app.get("/api/pattern")
    def get_pattern():
        return db.get_pattern(con)

    @app.post("/api/pattern")
    async def post_pattern(p: PatternIn):
        """Choose every Nth palm to photograph; restarts the photo round."""
        pat = db.set_pattern(con, p.every)
        capture.refresh()
        await hub.send_all({"type": "pattern", "pattern": pat})
        return pat

    @app.get("/api/telemetry")
    def get_telemetry():
        return telemetry.snapshot() if telemetry else {"connected": False}

    @app.get("/api/camera-urls")
    def camera_urls():
        """Where to point the phone, shown in the dashboard's video card."""
        from .certs import local_ips
        return [f"https://{ip}:{config.PORT}/camera" for ip in local_ips() if not ip.startswith("127.")]

    @app.websocket("/ws")
    async def ws_live(ws: WebSocket):
        await ws.accept()
        hub.clients.add(ws)
        await ws.send_text(json.dumps({"type": "pattern", "pattern": db.get_pattern(con)}))
        if telemetry:
            await ws.send_text(json.dumps({"type": "telemetry", **telemetry.snapshot()}))
        try:
            while True:
                await ws.receive_text()          # dashboard doesn't send; keep alive
        except WebSocketDisconnect:
            pass
        finally:
            hub.clients.discard(ws)

    if signaling:
        signaling.mount(app)

    @app.get("/camera")
    def camera_page():
        return FileResponse(config.STATIC_DIR / "camera.html")

    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=config.MEDIA_DIR), name="media")
    if config.FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="ui")
    return app
