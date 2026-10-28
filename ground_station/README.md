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
  changes, exportable as a QGroundControl `.waypoints` file (**Mission**). The simulator's
  last mission is drawn faintly next to it for comparison.
- **prediction export to Excel** (**Excel** button, `GET /api/prediction.xlsx`):
  Summary (counts as live formulas, with an editable predicted-tender
  threshold), Prediction (every palm, most likely tender first: probability,
  why, maturity, health, status, mission stop), Next mission (stops in flying
  order) and How it works (the rules). `backend/export_xlsx.py`.
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
  detects health yet. A reading needs white paper in view (>= 15% of the frame)
  and confidence >= 0.6; otherwise the photo is kept as a plain visit. Light
  vs deep green is told apart by saturation, so it holds in dim or bright light.
  **Printable cards:** `documents/dashboard/colour_cards.pdf` (instructions + four
  A5 cards; regenerate with `python tools/colour_cards.py`, needs `reportlab`).

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
2. **Connect an Android phone as the camera (recommended).** No browser
   streaming and no certificates on the phone:
   - Install **IP Webcam** (free, by Pavel Khlebovich) from the Play Store on
     the phone, put the phone on the **same Wi-Fi** as the laptop, open the app
     and tap **Start server**. It shows an address like `http://192.168.1.20:8080`.
   - In the dashboard's camera card, tab **Android app**, type that address and
     tap **Connect**. The card goes **Live**.
   - The ground station relays the phone's MJPEG stream (`/api/camera/stream`),
     so the colour-card reader can read frames. The drone's **ESP32-CAM**
     streams the same way (`http://<esp32-ip>:81/stream`), so the same setting
     works for the real aircraft.
   - Only cameras on the local network (private IP addresses) are accepted.
   - Some cameras (the ESP32-CAM) serve one viewer at a time: keep a single
     dashboard showing the camera.

   **Or use the phone's browser** (any phone; tab *Phone browser* in the camera
   card). Scan the QR code (click it to enlarge), or open the *Phone setup* URL
   that `run.py` prints, `https://<laptop-wifi-ip>:8443/phone`. That page has
   two steps:
   - **Trust the ground station** (once; optional): *Download certificate* and
     install it: Android *Settings → Security → Encryption & credentials →
     Install a certificate → CA certificate*; iPhone (Safari) *Settings →
     Profile Downloaded → Install*, then *General → About → Certificate Trust
     Settings* → turn it on. Skipped? Then tap through the warning instead
     (Android *Advanced → Proceed*, iPhone *Show Details → visit this website*).
   - **Open camera**, tap **Start**, allow the camera. The dashboard's camera
     card switches to **Live**; the phone keeps its screen awake while streaming.
3. If the phone can't load the page, allow Python through the firewall on
   **private** networks (Windows asks the first time `run.py` starts), and make
   sure the phone isn't on a guest network that isolates devices. The phone
   needs the laptop's Wi-Fi address (192.168.x.x or 10.x.x.x), not a
   172.x.x.x one, which is usually the WSL/Hyper-V virtual adapter.

### Flights: replay, report, photos

- **Every flight is recorded** automatically from arming to disarming
  (`backend/flights.py`): the track at 2 Hz, the plan and mission as they were
  at takeoff, and a summary. A flight that loses the link for 30 s, or is left
  open by a restart, is closed as `lost`.
- **Post-flight report** opens on landing, or from *Flights* in the rail →
  *Report*. It shows:
  - flight time and distance against the plan;
  - stops reached, with the missed stops named;
  - battery from start to end;
  - photos and classifications;
  - maximum wind and altitude, and telemetry gaps;
  - time in each phase (VTOL / transition / fixed-wing);
  - the palms where tender nuts were found and new targets were flagged.

  *Print / save PDF* gives a clean page.
- **Replay** (*Flights* → *Replay*): the recorded flight plays back on the
  map with its plan and mission as they were at takeoff.
  - Play or pause at 1×, 4×, 16× or 64×, and drag the scrubber.
  - A coloured band under the scrubber shows the flight phase over time.
  - Marks on the band are detections and new targets; click one to jump to it.
  - *Exit replay* returns to live.
- **Photos** (rail): every photo across the farm, newest first, filtered by
  maturity. The tree card has the same gallery for one palm; click a photo for
  the full-size viewer (← → keys).

### Layout

- **Background:** a blurred pixel-art relief of the land around the farm
  (`frontend/src/relief.js`): a fine 750 m patch over a coarse 6 km one, so it
  fills the view at every zoom.
- **Zoom:** live layers (trail, routes, stops, the drone) hold still while a
  zoom animates and catch up when it ends, so nothing flickers or jumps.
- **Tablets** (720–1199 px wide):
  - the sidebar becomes a drawer that slides in from the rail (tap the rail
    icon again, or the map, to close it);
  - buttons and rows get bigger for touch;
  - the telemetry bar keeps the essentials;
  - in portrait, the legend moves to the right.

### Alerts and go / no-go

**Go / no-go** (top of the sidebar) checks, before and during a flight:

| Check | GO | CAUTION | NO-GO |
|---|---|---|---|
| Wind (mean) | ≤ 5 m/s | 5–6 m/s | > 6 m/s |
| Gusts (if entered) | ≤ 7 m/s | 7–9 m/s | > 9 m/s |
| Battery plan | within 80% | palms left out | over 80% |
| Battery charge (on the ground) | ≥ 90% | 70–90% | < 70% |
| Drone link | telemetry | | none |
| GPS | 3D fix, ≥ 8 satellites | < 8 satellites | no 3D fix |

- **Wind sources:** the value typed into the card (anemometer or forecast;
  shared by all dashboards) is used on the ground. Once airborne, the
  autopilot's own wind estimate (MAVLink `WIND`) takes over.
- **Where the wind limits come from:** the sim study. 5 m/s with 2 m/s gusts
  flew fine. At 8 m/s with 3 m/s gusts JSBSim stayed controllable but imaged
  only 79% of the palms, and Gazebo crashed. The gust limits are provisional
  until real flights.

**Alerts** appear at the top of the map; click one to jump to its palm. A
beep plays for warnings, unless the bell in the toolbar is muted.

| Alert | When | Stays |
|---|---|---|
| Target found / Tender nuts at P… | a palm becomes a target, or a tender detection arrives (ML, colour card, visit) | 9 s |
| Battery limit reached | predicted palms no longer fit the 80% rule | 9 s |
| Battery over limit | in flight, the projected battery at landing drops below 20% | until it recovers |
| Drone link lost | telemetry stops | until restored |
| No-go | the go/no-go check turns red | 9 s |

The rules are pure functions in `frontend/src/checks.js`, tested in Node by
`tests/test_checks.py`.

### No security warning

`run.py` signs its HTTPS certificate with the ground station's own small
certificate authority, created once in `certs/ca.pem` (10 years). Trust that CA
once per device and the warning is gone for good, also after the laptop's IP
changes (the server certificate is re-issued automatically):

- **Windows (Chrome, Edge):** in a terminal, `certutil -user -addstore Root
  ground_station\certs\ca.pem`, confirm the dialog, restart the browser.
  To undo: `certutil -user -delstore Root "Coconut VTOL ground station local CA"`.
- **Firefox:** *Settings → Privacy & Security → Certificates → View
  Certificates → Authorities → Import* `certs/ca.pem`, tick "identify websites".
- **Phones:** step 2 above.
- Or skip HTTPS on the laptop: **http://localhost:8080** works without any
  certificate (this computer only).

Keep `certs/ca-key.pem` private: anyone with it could make certificates your
devices trust. It never leaves the laptop and is git-ignored. Delete the
`certs/` folder to start over with a new CA (then trust the new one).

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
| `test_flights.py` | flight recorder: start on arm, track, end on disarm / link loss, crash recovery, summary (distance, stops reached and missed, photos, tender found, battery, phases), flights API |
| `test_camera.py` | camera address checks (private network only, IP Webcam default path), the MJPEG relay against a fake IP Webcam, errors |
| `test_checks.py` | go/no-go thresholds, wind source, landing projection and every alert rule (Node) |
| `test_card_reader.py` | the colour-card reader on synthetic frames (Node): green/light green/yellow/brown → stage; tiny, far-off, mixed-colour cards, blank paper, no paper and a brown desk give no reading; young card in dim light |
| `test_export.py` | Excel export: four sheets, one row per palm sorted by probability, Yes/No formula tied to the threshold, mission stops match the plan |
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
| `GET /api/prediction.xlsx` | the ripeness prediction for every palm plus the next mission, as an Excel workbook |
| `GET /api/mission` | the simulator's last planned mission (`flight_software/demo/plan.json`): `{route, targets, items}` |
| `POST /api/trees/{id}/photo?capture_id=…&label=…&confidence=…&model=…` | the capture answer can carry a classifier result (the colour-card reader's): then it is logged as a `detection` |
| `POST /api/trees/{id}/image` | raw JPEG body → `{"image": path}` to reference from an event (used by the ML pipeline) |
| `GET /api/camera-urls` | the phone URLs for this laptop |
| `GET /camera` | phone camera page |
| `GET /phone` | phone setup page: trust the certificate, then open the camera (the dashboard shows it as a QR code) |
| `GET /ca.crt` | the ground station's local CA certificate (DER), to install on phones and laptops |
| `GET /api/qr?text=…` | QR code (SVG) of a short text |
| `GET /api/camera` · `POST /api/camera` | camera source `{mode: "webrtc" \| "mjpeg", url}` (mjpeg: an IP Webcam / ESP32-CAM address on the LAN); pushed as `{"type":"camera"}` |
| `GET /api/camera/stream` | the MJPEG camera relayed (same origin) |
| `GET /api/flights` · `GET /api/flights/{id}` | recorded flights with their summary; one flight with its track, events, plan and mission (replay); `{"type":"flight_ended"}` is pushed on landing |
| `GET /api/photos?tree=&maturity=&limit=` | photos across the farm, newest first (gallery) |
| `GET /api/wind` · `POST /api/wind` | operator-entered wind `{speed, gust}` (m/s; `speed: null` clears); pushed as `{"type":"wind"}` |
| `GET /media/…` | tree images |
| `WS /ws` | server → dashboard: `{"type":"telemetry", connected, mode, armed, phase, lat, lon, alt, heading, groundspeed, airspeed, climb, battery, voltage, wp, wp_total, wind_speed, wind_dir, gps_fix, gps_sats, text}` (≤ 5 Hz; `phase` = `vtol`/`transition`/`fixed-wing`/`ground` from the motor outputs), `{"type":"tree", tree}`, `{"type":"trees", trees}`, `{"type":"pattern", pattern}`, `{"type":"capture", tree_id, capture_id}`, `{"type":"plan", plan}` (after every change), `{"type":"mission", mission}` |
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

*Why the sweep comes before the stops.* The sweep is the cheap scout: 7.3 Wh
(about 16% of the pack) photographs all 169 palms from cruise. That keeps the
evidence the ripeness rules feed on fresh (a stale sighting decays, so without
regular sweeps predictions drift towards "unknown"), and it is how new tender
bunches and health problems get noticed at all; the stops only go where the
database already points. A hover stop costs about 1.2 Wh, so close-ups of every
palm would take roughly 200 Wh, five to six full batteries. The stops then
spend the rest of the budget on the palms that matter.

**Battery in the simulator.** The JSBSim bridge sends ArduPilot the pack voltage
and current from its battery model (SIM_JSON `battery.voltage`/`battery.current`)
and `coconut_jsbsim.param` sets `BATT_CAPACITY 4000`, so the dashboard's battery
percentage drains in flight; before this it stayed at 100%.

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
