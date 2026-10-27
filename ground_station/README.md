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
- **photo rounds**: photograph every palm, or every 2nd, 4th or 8th. Palms in
  the pattern are highlighted; when the drone passes over one, the dashboard
  saves a still from the live feed to that palm's history and it turns green.
- **next mission planned from the database**: flagged targets plus palms the
  ripeness model predicts are tender, within the 80% battery rule, drawn as a
  dashed route with numbered stops, re-planned live whenever the database
  changes, exportable as a QGroundControl `.waypoints` file. The simulator's
  last mission is drawn faintly next to it for comparison.
- **ripeness prediction**: a per-palm probability of tender nuts from
  bunch-cycle rules (`backend/ripeness.py`), shown on the map and in the tree
  card, with the reason.
- **ML results**: `ml/detect_pipeline.py --post` sends detections (model,
  label, confidence, best frame) into the palm histories.
- **palm classification**: each palm has a *maturity* (not seen yet · young ·
  **tender** = harvest target · mature · over-mature), a *health* (healthy ·
  frond damage · pest) and a *harvest status* (unscouted → target → confirmed →
  harvested). On the map one glyph shows them together: fill = maturity, ring =
  status, red notch = health issue. Lenses switch the fill to Prediction (heat),
  Health or Photos. Hovering a palm shows a peek card; row/column numbers run
  along the field edges; a strip shows the flying mission's stop progress.
- **phone colour-card reader** (stand-in classifier): during a photo round,
  each automatic photo is checked for a coloured card on white paper — green =
  tender, light green = young, yellow = mature, brown = over-mature — and logged
  as a detection (`model` `colour-card-v1`). Only colour is read: nothing
  detects health yet.

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
    capture.py         when to photograph a palm (drone over a pattern palm)
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

1. Open **https://localhost:8443** on the laptop (accept the self-signed
   certificate once: Chrome/Edge *Advanced → Proceed*), or **http://localhost:8080**,
   which needs no certificate (plain HTTP, this computer only; `GS_HTTP_PORT`, 0 = off).
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
| `GS_CAPTURE_RADIUS` | `crown_radius_m` (4 m) | how close (horizontally) the drone must be to photograph a palm |

### Photo rounds

In the sidebar, *Photo round → Every*: **All**, **2nd**, **4th** or **8th**
palm, counted row by row from P0000 (every 2nd = 85 palms, 4th = 43,
8th = 22). On the map (legend set to *Photos*), palms in the pattern are copper,
the rest are dimmed, and photographed ones turn green with a short ring pulse.
The sidebar shows the progress.

How a photo is taken: when telemetry puts the drone within the crown radius
of a copper palm, the server asks the open dashboards for a frame. The first
dashboard with live video grabs one from the phone feed (the camera card
flashes like a shutter) and uploads it; it lands in
`media/<tree id>/<timestamp>.jpg` and as a *Visited* event in the palm's
history. While the drone stays overhead it retries every 5 s, so keep the
dashboard open with the video live. Picking a pattern again starts a new
round: earlier photos stay in the history but no longer count.

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
| `test_card_reader.py` | the colour-card reader on synthetic frames (Node): green/light green/yellow/brown → stage, tiny card and blank paper ignored |
| `test_plan.py` | ripeness rules (fresh/stale sightings, harvest cycle, health, survey, visits), migration to maturity/health/harvested, photo with a card reading, planner battery cap + targets first + stop order + WPL export, confirmed palms dropped, plan/export/image endpoints, ML label/model fields, live re-plan |
| `test_photo.py` | pattern membership (85/43/22), capture only over pattern palms within the radius, retry window, one answer per request, photo upload saved + history + `last_photo`, new round resets |
| `test_api.py` | REST endpoints, validation, WebSocket push on change, and push when another process writes the DB |
| `test_telemetry.py` | MAVLink reader against a fake vehicle: mode/armed/position/battery/waypoint, GCS heartbeat, 5 Hz throttle, waits for SITL, detects link loss |
| `test_video.py` | signalling relay protocol, camera page, certificate, and a real WebRTC stream between two headless Chromium pages over HTTPS |
| `test_dashboard.py` | the built dashboard in headless Chromium: 169 palm icons, no tiles, every-2nd pattern, moving drone + trail, live video, palms photographed automatically turn green, inspector photo + actions |

Set `GS_SCREENSHOT=/some/prefix` to save screenshots from the dashboard test.

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
| `condition` | TEXT | the survey's `healthy` · `ripe` · `frond` · `ripe+frond`, kept read-only for `trees.csv` (use `maturity`/`health`) |
| `status` | TEXT | `unscouted` · `target` · `confirmed` · `harvested` (confirmed: a confirm stop saw tender nuts; the old name `cleared` is still accepted on input) |
| `maturity` | TEXT | `unknown` · `young` · `tender` · `mature` · `over-mature` (tender = harvest target); seeded from the survey's `ripe` |
| `health` | TEXT | `healthy` · `frond-damage` · `pest`; seeded from the survey's `frond` |
| `lat`, `lon` | REAL | from `layout.json` home, same conversion as `upload_mission.py` |
| `confidence` | REAL | 0–1, latest detection |
| `label` | TEXT | latest detection label (`pre-mature` = tender, `mature`, `over-mature`) |
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
| `model`, `label` | TEXT | detector name and its label, for `detection` events; a label naming a stage (`pre-mature` → tender, `mature`, `over-mature`, `young`) also sets the tree's maturity |
| `maturity`, `health` | TEXT | values set by this event |
| `image` | TEXT | path under `ground_station/media/`, shown in the history |
| `note` | TEXT | |
| `source` | TEXT | `dashboard` · `camera` · `planner` · `ml` · `seed` |

**`meta`**: `key='layout'` holds `layout.json`; `key='photo_pattern'` holds
`{"every": 1|2|4|8, "since": ts}`.

The API also returns `last_photo` for each tree: the time of its latest event
with an image. It is computed from `tree_events`, not stored.

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
| `POST /api/trees/{id}/photo?capture_id=…` | raw JPEG body answering a capture request (409 if already answered) |
| `GET /api/pattern` · `POST /api/pattern` | `{"every": 1\|2\|4\|8}`; posting starts a new photo round |
| `GET /api/telemetry` | latest telemetry |
| `GET /api/plan` | next mission from the database: `{stops: [{tree, order, kind: target\|predicted, score, reason, lat, lon}], route: [{seq, label, lat, lon, alt, tree}], dropped, n_targets, n_predicted, distance_m, energy_wh, battery_pct, budget_pct, max_stops}` |
| `GET /api/plan.waypoints` | the same mission as a QGroundControl WPL 110 file |
| `GET /api/mission` | the simulator's last planned mission (`flight_software/demo/plan.json`): `{route, targets, items}` |
| `POST /api/trees/{id}/photo?capture_id=…&label=…&confidence=…&model=…` | the capture answer can carry a classifier result (the colour-card reader's): then it is logged as a `detection` |
| `POST /api/trees/{id}/image` | raw JPEG body → `{"image": path}` to reference from an event (used by the ML pipeline) |
| `GET /api/camera-urls` | the phone URLs for this laptop |
| `GET /camera` | phone camera page |
| `GET /media/…` | tree images |
| `WS /ws` | server → dashboard: `{"type":"telemetry", connected, mode, armed, phase, lat, lon, alt, heading, groundspeed, airspeed, climb, battery, voltage, wp, wp_total, text}` (≤ 5 Hz; `phase` = `vtol`/`transition`/`fixed-wing`/`ground` from the motor outputs), `{"type":"tree", tree}`, `{"type":"trees", trees}`, `{"type":"pattern", pattern}`, `{"type":"capture", tree_id, capture_id}`, `{"type":"plan", plan}` (after every change), `{"type":"mission", mission}` |
| `GET /api/trees` | each tree also carries `ripe_score` (0–1) and `ripe_reason`, computed, not stored |
| `WS /ws/signal?role=camera\|viewer` | WebRTC signalling (offer/answer/ICE relay; protocol in `backend/signaling.py`) |

## Next mission, prediction and ML

**Planner** (`backend/planner.py`). Picks, in order: every `target` palm, then
`unscouted` palms with `ripe_score >= 0.5`, best first, adding hover stops while
the mission stays within 80% of the 44.4 Wh battery. Confirmed palms go to the
harvest crew and cleared ones were just harvested, so neither is revisited. The
route itself is `flight_software/route_planner.py`, the same planner the
simulator flies: racetrack sweep from the dock, U-turn into the stops, stops
flowing back to the dock. Energy model from the JSBSim runs: 7.3 Wh sweep +
0.9 Wh back-transition/return/landing + 1.2 Wh per stop. Re-planning takes a few
milliseconds, so it runs after every change and is pushed to all dashboards.
Checked in JSBSim (2026-10-27): the seeded farm's 22-stop plan, estimated at
34.6 Wh (78%), flew 2.76 km in 555 s on 32.4 Wh (73%), imaged all 22 targets and
landed on the dock, so the estimate is about 7% conservative.

**Ripeness prediction** (`backend/ripeness.py`). A palm opens a new bunch about
monthly and a bunch is tender for about a month, so: a fresh tender detection
scores its confidence and fades after the tender window; a harvest (status
`cleared`) makes the palm due again one bunch interval later; mature or
over-mature sightings mean a younger bunch is probably tender; the survey's
"ripe" counts as a tender sighting; frond damage x0.7. These are rules, not a
fitted model: every constant is named in the file, ready to fit once flights
build up history in `tree_events`.

**ML pipeline** (`ml/detect_pipeline.py`):
```bash
python ml/detect_pipeline.py RUN --frames manifest.csv --post https://<laptop>:8443 --insecure
```
Per palm with detections it uploads the best frame, posts a `detection` event
(model, label, confidence), and sets `target` when >= 2 frames saw tender nuts.
The palm then joins the next mission. From WSL, use the Windows host IP
(`ip route | awk '/default/ {print $3}'`) rather than localhost.

## Decisions made without the spec

The spec file was missing, so these were chosen here. Check them against the
spec and change what differs:

1. **Schema**: `trees` keeps the CSV columns verbatim and adds `lat`, `lon`,
   `confidence`, `last_visit`, `notes`, `updated_at`; history lives in
   `tree_events`. Vocabularies come from `make_plantation.py`, enforced with
   CHECK constraints.
2. **Tree actions**: set status (unscouted/target/cleared), log a visit with a
   condition, add a note. The dashboard cannot command the aircraft.
3. **Colouring**: the legend switches between status, condition and photos (default: photos).
4. **Map**: lat/lon from `layout.json` home, field outline, faint row lines,
   dock pad; north up.
5. **Video**: phone-to-browser WebRTC, peer-to-peer on the LAN, no STUN; the
   server only relays signalling. One phone at a time (a new phone replaces
   the old one), any number of dashboards.
6. **Single port**: dashboard, API and camera page all on HTTPS 8443.
7. **Telemetry trail**: last 3000 points (about 10 minutes at 5 Hz), not stored.
8. **Photos**: taken from the dashboard's copy of the live feed (WebRTC
   quality, up to 1280×720), so a dashboard must be open with video live.

Tested here with headless Chromium only (fake camera, fake vehicle). The
iPhone and Android camera pages and the live SITL link still need a run on
real devices.
