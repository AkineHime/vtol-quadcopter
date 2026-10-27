# Ground station: dashboard + per-tree database

Live map of the 1 ha plantation for the coconut VTOL. One Python process
serves everything over HTTPS on port **8443**:

- a **SQLite database** of the 169 palms with a full per-tree history,
- a **REST API** and a **WebSocket** pushing drone telemetry and tree changes,
- the **dashboard** (React + Vite + react-leaflet): a drawn farm plan with
  every palm as a clickable icon, a tree detail card, the drone as a moving
  arrow with a trail, and a live video panel,
- the **phone camera page** (`/camera`): a phone streams its rear camera to
  the dashboard over browser WebRTC. No app install, Android and iPhone.

Telemetry comes from the autopilot over MAVLink (`pymavlink`), by default
`tcp:127.0.0.1:5762`: the SITL's second port, so the route planner keeps 5760.

Nothing needs the internet: no map tiles, no web fonts, no STUN/TURN servers.

> **Note.** `documents/dashboard/DASHBOARD_SPEC.md` and `reference_ui.jpg`
> were not in the repository when this was built, so the schema, API and
> layout below were designed from the build brief, the farm data and the
> roadmap docs. See *Decisions made without the spec* at the end.

```
ground_station/
  run.py               start the server
  backend/
    config.py          paths + env settings
    db.py              schema, seeding, events  (the DB contract)
    app.py             FastAPI: REST, /ws, static pages
    telemetry.py       MAVLink reader thread
    signaling.py       WebRTC signalling relay (/ws/signal)
    certs.py           self-signed HTTPS cert
    static/camera.html phone camera page
  frontend/            React + Vite dashboard (build -> frontend/dist)
  tests/               pytest suite (+ fake_vehicle.py)
  data/ certs/ media/  created at runtime, git-ignored
```

## Install

Python 3.10+ and Node 18+. On Windows use PowerShell; on Linux/WSL a shell.

```bash
cd ground_station
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/WSL: source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium   # only for the browser tests

cd frontend
npm install
npm run build                           # -> frontend/dist, served by run.py
cd ..
```

## Run

```bash
python run.py
```

It prints:

```
  Dashboard     https://localhost:8443
  Phone camera  https://192.168.1.23:8443/camera
  Telemetry     tcp:127.0.0.1:5762
```

1. Open **https://localhost:8443** on the laptop. The certificate is
   self-signed, so accept the warning once (Chrome/Edge: *Advanced → Proceed*).
2. On the phone, on the **same Wi-Fi**, open the *Phone camera* URL, accept
   the certificate warning, tap **Start** and allow the camera.
   - **Android (Chrome):** *Advanced → Proceed to 192.168.x.x (unsafe)*.
   - **iPhone (Safari):** *Show Details → visit this website → Visit Website*.
   The dashboard's video card switches to **LIVE**. The phone keeps its screen
   awake while streaming.
3. If the phone can't load the page, allow Python through the firewall on
   private networks (Windows asks the first time `run.py` starts).

The certificate is created in `certs/` on first run and regenerated
automatically when the laptop's IP addresses change.

Settings (environment variables):

| Variable | Default | |
|---|---|---|
| `MAVLINK_URL` | `tcp:127.0.0.1:5762` | any pymavlink URL, e.g. `udpin:0.0.0.0:14550`; `none` disables |
| `GS_PORT` | `8443` | HTTPS port |
| `GS_HOST` | `0.0.0.0` | bind address |
| `GS_DB` | `data/ground_station.db` | SQLite file |
| `GS_CERTS` / `GS_MEDIA` | `certs/` / `media/` | cert folder / tree images |
| `TREES_CSV` / `LAYOUT_JSON` | `flight_software/demo/…` | seed data |

### With the simulator (Gazebo + ArduPilot SITL in WSL)

Run the simulator in WSL and the ground station **on Windows**. WSL2
forwards `127.0.0.1:5762` to Windows (this is how QGroundControl connects
too), and only the Windows side has an address your phone can reach.

```bash
# WSL terminal
bash flight_software/gazebo/run_demo.sh
```

```powershell
# Windows PowerShell, in ground_station\
.venv\Scripts\activate
python run.py
```

The dashboard shows "No drone link" until SITL is up, then connects by
itself: the mode, altitude and speeds appear and the arrow follows the
aircraft through the scout sweep and the VTOL stops, leaving a copper trail.
The route planner keeps using port 5760; the dashboard only reads.

Running the ground station inside WSL also works for the laptop browser,
but a phone can only reach it if WSL uses mirrored networking.

### Without the simulator

```bash
python tests/fake_vehicle.py     # terminal 1: fake aircraft circling the field on tcp:5762
python run.py                    # terminal 2
```

### Frontend development

`python run.py` in one terminal, `cd frontend && npm run dev` in another, then
open the Vite URL (http://localhost:5173). API and WebSocket calls are proxied
to the backend. The phone camera page always comes from `https://<ip>:8443/camera`.

## Test

```bash
cd ground_station
npm --prefix frontend run build    # the dashboard test drives the built UI
python -m pytest -v
```

| File | Covers |
|---|---|
| `test_db.py` | schema keeps the `trees.csv` columns, 169 trees seeded exactly, idempotent seed, events update tree + history, bad values rejected |
| `test_api.py` | REST endpoints, validation, WebSocket push on change, and push when another process writes the DB |
| `test_telemetry.py` | MAVLink reader against a fake vehicle: mode/armed/position/battery/waypoint, GCS heartbeat, 5 Hz throttle, waits for SITL, detects link loss |
| `test_video.py` | signalling relay protocol, camera page, certificate, and a real WebRTC stream between two headless Chromium pages over HTTPS |
| `test_dashboard.py` | the built dashboard in headless Chromium: 169 palm icons, no tiles, moving drone + trail, tree card actions, live video |

Set `GS_SCREENSHOT=shot.png` to save a screenshot from the dashboard test.

## Database (contract with the route planner and ML pipeline)

File: `ground_station/data/ground_station.db` (SQLite, WAL mode, so other
processes can read while the server runs). Created and seeded on first start,
or with `python -m backend.db`.

**`trees`**: one row per palm. The first eight columns are exactly
`trees.csv`.

| column | type | |
|---|---|---|
| `id` | TEXT PK | `P0612` = row 06, column 12 |
| `row`, `col` | INTEGER | grid index, row 0 = south |
| `n`, `e` | REAL | metres north / east of the dock |
| `height` | REAL | m |
| `condition` | TEXT | `healthy` · `ripe` · `frond` · `ripe+frond` |
| `status` | TEXT | `unscouted` · `target` · `cleared` |
| `lat`, `lon` | REAL | from `layout.json` home, same conversion as `upload_mission.py` |
| `confidence` | REAL | 0–1, latest detection |
| `last_visit` | TEXT | ISO-8601 UTC |
| `notes` | TEXT | |
| `updated_at` | TEXT | ISO-8601 UTC |

**`tree_events`**: append-only history.

| column | type | |
|---|---|---|
| `id` | INTEGER PK | |
| `tree_id` | TEXT → `trees.id` | |
| `ts` | TEXT | ISO-8601 UTC |
| `kind` | TEXT | `seed` · `status` · `visit` · `detection` · `note` |
| `status`, `condition`, `confidence` | | values set by this event (NULL if unchanged) |
| `image` | TEXT | path under `ground_station/media/`, shown in the history |
| `note` | TEXT | |
| `source` | TEXT | `dashboard` · `planner` · `ml` · `seed` |

**`meta`**: `key='layout'` holds `layout.json`.

How teammates should write: preferably through the API, which also updates
the tree row and pushes to the dashboard instantly:

```bash
curl -k -X POST https://localhost:8443/api/trees/P0612/events \
  -H 'Content-Type: application/json' \
  -d '{"kind":"detection","condition":"ripe","confidence":0.92,"image":"P0612/2026-10-27.jpg","source":"ml"}'
```

Writing straight to SQLite also works (the dashboard refreshes within a
second). Insert a `tree_events` row and update the matching `trees` row in
the same transaction, or call `backend.db.add_event()` from Python.

## API

| | |
|---|---|
| `GET /api/layout` | `layout.json` + field corners and dock as lat/lon |
| `GET /api/trees` | all trees |
| `GET /api/trees/{id}` | `{tree, history}` (newest first) |
| `POST /api/trees/{id}/events` | `{kind, status?, condition?, confidence?, image?, note?, source?}` → updated tree; `kind` is `status`/`visit`/`detection`/`note` |
| `GET /api/telemetry` | latest telemetry |
| `GET /api/camera-urls` | the phone URLs for this laptop |
| `GET /camera` | phone camera page |
| `GET /media/…` | tree images |
| `WS /ws` | server → dashboard: `{"type":"telemetry", connected, mode, armed, lat, lon, alt, heading, groundspeed, airspeed, climb, battery, voltage, wp, text}` (≤ 5 Hz), `{"type":"tree", tree}`, `{"type":"trees", trees}` |
| `WS /ws/signal?role=camera\|viewer` | WebRTC signalling (offer/answer/ICE relay; protocol in `backend/signaling.py`) |

## Decisions made without the spec

The spec file was missing, so these were chosen here. Check them against the
spec and change what differs:

1. **Schema**: `trees` keeps the CSV columns verbatim and adds `lat`, `lon`,
   `confidence`, `last_visit`, `notes`, `updated_at`; history lives in
   `tree_events`. Vocabularies come from `make_plantation.py`, enforced with
   CHECK constraints.
2. **Tree actions**: set status (unscouted/target/cleared), log a visit with a
   condition, add a note. The dashboard cannot command the aircraft.
3. **Colouring**: toggle between status and condition in the legend.
4. **Map**: lat/lon from `layout.json` home, field outline, faint row lines,
   dock pad; north up.
5. **Video**: phone-to-browser WebRTC, peer-to-peer on the LAN, no STUN; the
   server only relays signalling. One phone at a time (a new phone replaces
   the old one), any number of dashboards.
6. **Single port**: dashboard, API and camera page all on HTTPS 8443.
7. **Telemetry trail**: last 3000 points (about 10 minutes at 5 Hz), not stored.

Tested here with headless Chromium only (fake camera, fake vehicle). The
iPhone and Android camera pages and the live SITL link still need a run on
real devices.
