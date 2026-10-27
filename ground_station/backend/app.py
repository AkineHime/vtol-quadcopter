"""FastAPI ground-station backend: REST API, live WebSocket, static pages."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import camera, config, db, flights, planner, ripeness
from .capture import Capture

MAX_PHOTO_BYTES = 8 * 1024 * 1024
JPEG_MAGIC = bytes([0xFF, 0xD8])


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


class CameraIn(BaseModel):
    mode: Literal["webrtc", "mjpeg"]
    url: str | None = Field(None, max_length=200)     # mjpeg: the phone app's / ESP32-CAM's address


class WindIn(BaseModel):
    speed: float | None = Field(None, ge=0, le=40)       # m/s mean; null clears it
    gust: float | None = Field(None, ge=0, le=50)


class EventIn(BaseModel):
    kind: Literal["status", "visit", "detection", "note"]
    status: Literal["unscouted", "target", "confirmed", "harvested", "cleared"] | None = None   # cleared = old name
    maturity: Literal["unknown", "young", "tender", "mature", "over-mature"] | None = None
    health: Literal["healthy", "frond-damage", "pest"] | None = None
    condition: Literal["healthy", "ripe", "frond", "ripe+frond"] | None = None   # survey vocabulary, older clients
    confidence: float | None = Field(None, ge=0, le=1)
    image: str | None = None
    note: str | None = Field(None, max_length=2000)
    source: str = "dashboard"
    model: str | None = Field(None, max_length=60)
    label: str | None = Field(None, max_length=40)


def trees_with_scores(con) -> list[dict]:
    """Trees plus the ripeness prediction (computed, not stored)."""
    sc = ripeness.score_all(con)
    return [dict(t, ripe_score=sc[t["id"]][0], ripe_reason=sc[t["id"]][1]) for t in db.list_trees(con)]


def tree_with_score(con, tree_id: str) -> dict | None:
    t = db.get_tree(con, tree_id)
    if t:
        s, why = ripeness.score(t, db.history(con, tree_id))
        t.update(ripe_score=s, ripe_reason=why)
    return t


def sim_mission() -> dict | None:
    """The mission last planned for the simulator (flight_software/demo/plan.json), shown
    next to the database plan: what the sim flies vs what the database asks for now."""
    if not config.SIM_PLAN.exists():
        return None
    p = json.loads(config.SIM_PLAN.read_text())
    h = p["home"]
    route = []
    for m in p["mission"]:
        if m["n"] is None:
            continue
        lat, lon = db.meters_to_latlon(m["n"], m["e"], h["lat"], h["lon"])
        route.append({"seq": m["seq"], "label": m["label"], "lat": lat, "lon": lon, "tree": m.get("tree")})
    return {"route": route, "targets": sorted({m["tree"] for m in p["mission"] if m.get("tree")}),
            "items": len(p["mission"]), "mtime": config.SIM_PLAN.stat().st_mtime}


async def watch_external_writes(con, hub: Hub, capture: Capture, state: dict) -> None:
    """The planner / ML pipeline may write the SQLite file directly. PRAGMA
    data_version only changes on commits from *other* connections, so when it
    moves we push a fresh tree list (and a re-plan) to every dashboard. Also
    pushes the simulator's mission when flight_software/demo/plan.json changes."""
    last = con.execute("PRAGMA data_version").fetchone()[0]
    while True:
        await asyncio.sleep(1.0)
        v = con.execute("PRAGMA data_version").fetchone()[0]
        if v != last:
            last = v
            capture.refresh()
            await hub.send_all({"type": "trees", "trees": trees_with_scores(con)})
            await state["replan"]()
        m = config.SIM_PLAN.stat().st_mtime if config.SIM_PLAN.exists() else None
        if m != state.get("sim_mtime"):
            state["sim_mtime"] = m
            await hub.send_all({"type": "mission", "mission": sim_mission()})


def create_app(telemetry=None, signaling=None) -> FastAPI:
    con = db.connect()
    db.init_db(con)
    hub = Hub()
    capture = Capture(con, float(config.CAPTURE_RADIUS) if config.CAPTURE_RADIUS else None)
    tasks = []
    state = {"plan": planner.plan(con)}

    async def replan() -> None:
        state["plan"] = planner.plan(con)
        await hub.send_all({"type": "plan", "plan": planner.public(state["plan"])})
    state["replan"] = replan
    recorder = flights.Recorder(con, snapshot=lambda: (planner.public(state["plan"]), sim_mission()))

    async def on_telemetry(msg: dict) -> None:
        await hub.send_all(msg)
        ended = recorder.feed(msg)
        if ended:                                    # post-flight report is ready
            await hub.send_all({"type": "flight_ended", "flight": next(
                (f for f in flights.list_flights(con) if f["id"] == ended), None)})
        req = capture.check(msg)
        if req:
            await hub.send_all(req)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        hub.loop = asyncio.get_running_loop()
        tasks.append(asyncio.create_task(watch_external_writes(con, hub, capture, state)))
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
        return trees_with_scores(con)

    @app.get("/api/trees/{tree_id}")
    def get_tree(tree_id: str):
        t = tree_with_score(con, tree_id)
        if not t:
            raise HTTPException(404, f"no tree {tree_id}")
        return {"tree": t, "history": db.history(con, tree_id)}

    @app.get("/api/plan")
    def get_plan():
        """Next mission planned from the database: targets + predicted-ripe palms
        within the battery rule (backend/planner.py)."""
        return planner.public(state["plan"])

    @app.get("/api/plan.waypoints")
    def get_plan_waypoints():
        return PlainTextResponse(planner.waypoints(state["plan"]), headers={
            "Content-Disposition": "attachment; filename=next_mission.waypoints"})

    @app.get("/api/mission")
    def get_mission():
        """The mission last planned for the simulator, for comparison with /api/plan."""
        return sim_mission()

    @app.post("/api/trees/{tree_id}/image")
    async def post_image(tree_id: str, request: Request):
        """Store a JPEG for a palm (e.g. the ML pipeline's best frame); returns the
        media path to reference from a detection event."""
        if not db.get_tree(con, tree_id):
            raise HTTPException(404, f"no tree {tree_id}")
        body = await request.body()
        if not body.startswith(JPEG_MAGIC) or len(body) > MAX_PHOTO_BYTES:
            raise HTTPException(422, "expected a JPEG under 8 MB")
        folder = config.MEDIA_DIR / tree_id
        folder.mkdir(parents=True, exist_ok=True)
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".jpg"
        (folder / name).write_bytes(body)
        return {"image": f"{tree_id}/{name}"}

    @app.post("/api/trees/{tree_id}/events")
    async def post_event(tree_id: str, ev: EventIn):
        try:
            t = db.add_event(con, tree_id, **ev.model_dump())
        except KeyError:
            raise HTTPException(404, f"no tree {tree_id}")
        except ValueError as e:
            raise HTTPException(422, str(e))
        capture.refresh()
        t = tree_with_score(con, tree_id)
        await hub.send_all({"type": "tree", "tree": t})
        await replan()
        return t

    @app.post("/api/trees/{tree_id}/photo")
    async def post_photo(tree_id: str, capture_id: str, request: Request, label: str | None = None,
                         confidence: float | None = None, model: str | None = None):
        """A dashboard answers a capture request with one JPEG frame (raw body).
        With `label` (the colour-card reader's or another classifier's result,
        e.g. pre-mature) the photo is logged as a detection, else as a visit."""
        if label is not None and (len(label) > 40 or confidence is None or not 0 <= confidence <= 1):
            raise HTTPException(422, "label needs a confidence between 0 and 1")
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
        if label:
            db.add_event(con, tree_id, "detection", image=f"{tree_id}/{name}", label=label, confidence=confidence,
                         model=(model or "")[:60] or None, note="Photo taken overhead", source="camera")
        else:
            db.add_event(con, tree_id, "visit", image=f"{tree_id}/{name}", note="Photo taken overhead", source="camera")
        capture.refresh()
        t = tree_with_score(con, tree_id)
        await hub.send_all({"type": "tree", "tree": t})
        await replan()
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

    @app.get("/api/photos")
    def get_photos(tree: str | None = None, maturity: str | None = None, limit: int = 120):
        """Photos across the farm, newest first, with what was seen in each (gallery)."""
        q = ("SELECT e.id, e.tree_id, e.ts, e.kind, e.maturity, e.label, e.confidence, e.model, e.image, e.source,"
             " t.row, t.col FROM tree_events e JOIN trees t ON t.id = e.tree_id WHERE e.image IS NOT NULL")
        args: list = []
        if tree:
            q += " AND e.tree_id = ?"
            args.append(tree)
        if maturity:
            q += " AND (e.maturity = ? OR (? = 'tender' AND e.label = 'pre-mature'))"
            args += [maturity, maturity]
        q += " ORDER BY e.ts DESC, e.id DESC LIMIT ?"
        args.append(max(1, min(limit, 500)))
        return [dict(r) for r in con.execute(q, args)]

    @app.get("/api/flights")
    def get_flights():
        """Recorded flights, newest first, each with its post-flight summary."""
        return flights.list_flights(con)

    @app.get("/api/flights/{flight_id}")
    def get_flight(flight_id: int):
        """One flight for replay: track, events, the plan/mission at takeoff, summary."""
        f = flights.get_flight(con, flight_id)
        if not f:
            raise HTTPException(404, f"no flight {flight_id}")
        return f

    @app.get("/api/camera")
    def get_camera():
        return camera.get(con)

    @app.post("/api/camera")
    async def post_camera(c: CameraIn):
        """Choose the camera: the phone browser (WebRTC) or an MJPEG stream on the
        LAN (Android IP Webcam app, ESP32-CAM). Shared by all dashboards."""
        try:
            v = camera.set_(con, c.mode, c.url)
        except ValueError as e:
            raise HTTPException(422, str(e))
        await hub.send_all({"type": "camera", "camera": v})
        return v

    @app.get("/api/camera/stream")
    async def camera_stream():
        """Relay the MJPEG stream (same origin, so the dashboard can read frames)."""
        import httpx
        cam = camera.get(con)
        if cam["mode"] != "mjpeg" or not cam["url"]:
            raise HTTPException(404, "no MJPEG camera set")
        client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=15.0))
        try:
            up = await client.send(client.build_request("GET", cam["url"]), stream=True)
        except httpx.HTTPError as e:
            await client.aclose()
            raise HTTPException(502, f"camera not reachable at {cam['url']}: {type(e).__name__}")
        if up.status_code != 200:
            await up.aclose()
            await client.aclose()
            raise HTTPException(502, f"camera answered {up.status_code}")

        async def relay():
            try:
                async for chunk in up.aiter_raw():
                    yield chunk
            except httpx.HTTPError:
                pass
            finally:
                await up.aclose()
                await client.aclose()
        return StreamingResponse(relay(), media_type=up.headers.get("content-type", "multipart/x-mixed-replace"),
                                 headers={"Cache-Control": "no-store"})

    @app.get("/api/wind")
    def get_wind():
        return db.get_wind(con)

    @app.post("/api/wind")
    async def post_wind(w: WindIn):
        """Operator-entered wind for the go/no-go card (all dashboards see it)."""
        try:
            v = db.set_wind(con, w.speed, w.gust)
        except ValueError as e:
            raise HTTPException(422, str(e))
        await hub.send_all({"type": "wind", "wind": v})
        return v

    @app.get("/api/telemetry")
    def get_telemetry():
        return telemetry.snapshot() if telemetry else {"connected": False}

    @app.get("/api/camera-urls")
    def camera_urls():
        """Where to point the phone, shown in the dashboard's video card."""
        from .certs import local_ips
        # Wi-Fi/LAN addresses first: 172.16-31.x is usually a virtual adapter (WSL, Hyper-V) a phone can't reach
        rank = lambda ip: (0 if ip.startswith("192.168.") else 1 if ip.startswith("10.") else 2, ip)
        ips = sorted((ip for ip in local_ips() if not ip.startswith("127.")), key=rank)
        return [f"https://{ip}:{config.PORT}/camera" for ip in ips]

    @app.websocket("/ws")
    async def ws_live(ws: WebSocket):
        await ws.accept()
        hub.clients.add(ws)
        await ws.send_text(json.dumps({"type": "pattern", "pattern": db.get_pattern(con)}))
        await ws.send_text(json.dumps({"type": "plan", "plan": planner.public(state["plan"])}))
        await ws.send_text(json.dumps({"type": "mission", "mission": sim_mission()}))
        await ws.send_text(json.dumps({"type": "wind", "wind": db.get_wind(con)}))
        await ws.send_text(json.dumps({"type": "camera", "camera": camera.get(con)}))
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

    @app.get("/phone")
    def phone_page():
        """Phone setup: trust the ground station's certificate, then open the camera."""
        return FileResponse(config.STATIC_DIR / "phone.html")

    @app.get("/ca.crt")
    def ca_cert():
        """The ground station's local CA (backend/certs.py), for phones and laptops to trust once."""
        from .certs import ca_der
        return Response(ca_der(config.CERT_DIR), media_type="application/x-x509-ca-cert",
                        headers={"Content-Disposition": 'attachment; filename="coconut-ground-station-ca.crt"'})

    @app.get("/api/qr")
    def qr(text: str):
        """QR code (SVG) of a short text, e.g. the phone setup link shown on the dashboard."""
        import io
        import segno
        if len(text) > 200:
            raise HTTPException(422, "text too long")
        buf = io.BytesIO()
        segno.make(text, error="m").save(buf, kind="svg", scale=6, border=2, dark="#111", light="#fff")
        return Response(buf.getvalue(), media_type="image/svg+xml")

    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=config.MEDIA_DIR), name="media")
    if config.FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=config.FRONTEND_DIST, html=True), name="ui")
    return app
