# Ground-station dashboard + tree database: specification

**Owner:** frontend/database teammate.
**Status:** built in `ground_station/` (2026-10-27). **The built design is the
contract**: `ground_station/README.md` documents the database, API and WebSocket
messages. Where it differs from this original spec, the code wins (decided
2026-10-27):

| This spec said | Built (current contract) |
|---|---|
| `n_m`, `e_m`, `height_m` | `n`, `e`, `height`: the `trees.csv` names, kept verbatim |
| `observations` + `status_history` tables | one append-only `tree_events` table: `kind` = status, visit, detection or note, with `model`, `label`, `confidence`, `image`, `source` |
| status unscouted/target/confirmed/cleared; `condition` healthy/ripe/frond/ripe+frond | status unscouted/target/confirmed/**harvested**; separate `maturity` (unknown/young/tender/mature/over-mature) and `health` (healthy/frond-damage/pest); `condition` kept read-only from the survey |
| `missions` table, `/api/missions`, `/api/stats` | not built. The dashboard computes counts itself, and `/api/mission` shows the simulator's last mission |
| `GET /api/farm`, `PATCH /api/trees/{id}`, `POST .../observations` | `GET /api/layout`, `POST /api/trees/{id}/events`, `POST /api/trees/{id}/image` |
| WS `tree_update`, `rtc` on `/ws` | WS `tree`/`trees`/`plan`/`mission`; WebRTC signalling on its own `/ws/signal` |
| (not in spec) | photo rounds; the next-mission plan from the database with ripeness prediction (`/api/plan`, `.waypoints` export); layered palm glyphs with lenses; a phone colour-card reader standing in for the classifier |

The design intent below still holds. The schema and API sections (§3–§4) are
kept for history only.

**Reference design:** `reference_ui.jpg` in this folder. The 2026-10-27
redesign also drew on dark glass control-room dashboards, on-map status chips,
and frosted pill toolbars.

This is the ground-station app for the CoconutQuadplane. It has three parts:
- a **map of the farm**, with every palm as a clickable icon that opens its
  full record;
- the **drone's live position and route** on that map;
- a **live video feed** from the drone. For now a phone camera stands in for
  it, because there is no physical aircraft yet.

Behind it sits the **per-tree database** that the rest of the system reads
and writes (requirements FR4 and FR6 in the report).

Decisions already made (from the project docs and the team):

| Topic | Decision |
|---|---|
| Database | **SQLite**, one file |
| Backend | **Python, FastAPI**. REST for data, **WebSocket** for live telemetry and WebRTC signalling. MAVLink via `pymavlink`, which is already used in `flight_software/` |
| Frontend | **React + Vite + Leaflet** (`react-leaflet`) |
| Map base layer | **Drawn farm plan.** No satellite tiles; it must work offline |
| Farm | **The simulated 1 ha farm**: 169 palms from `flight_software/demo/trees.csv` and `layout.json` |
| Video | **Browser WebRTC.** The phone opens a page served by the laptop and streams its rear camera; no app install. Must work on Android and iPhone |

Keep the code **minimal and working**. Build it part by part, and test each
part before starting the next (see §8).

---

## 1. Folder layout (new top-level folder)

```
ground_station/
  backend/
    app.py            FastAPI app: REST, WebSocket, static files
    db.py             SQLite schema + queries
    seed.py           load trees.csv + layout.json into the DB
    telemetry.py      pymavlink reader -> latest state + broadcast
    signaling.py      WebRTC offer/answer/ICE relay over WebSocket
    requirements.txt  fastapi, uvicorn[standard], pymavlink
    data/farm.db      created by seed.py (git-ignored)
    media/            tree photos / snapshots (git-ignored)
  frontend/           Vite + React + react-leaflet
    src/...
  certs/              self-signed cert for HTTPS (git-ignored)
  README.md           how to run, how to test
```

The backend must not import anything from `flight_software/` except
`pymavlink`. Read the CSV and JSON files by path, so the two parts stay
independent.

## 2. Coordinates

The sim uses **local metres**: `n` = north and `e` = east of the dock. The
dock sits at `layout.json → home` (lat 10.6609, lon 77.0048). The map shows
real lat/lon, so convert exactly as `flight_software/upload_mission.py`
does:

```
lat = home.lat + n / 111320
lon = home.lon + e / (111320 * cos(radians(home.lat)))
```

Field geometry, all in `layout.json`:
- the field is a 100 × 100 m square;
- its south-west corner is at (n = `field_n0` 15, e = `field_e0` −50);
- palms are on a 7.5 m grid, 13 × 13;
- crown radius is 4 m;
- the dock is at (0, 0) and faces south.

## 3. Database (SQLite)

```sql
CREATE TABLE trees (
  id            TEXT PRIMARY KEY,      -- "P0000" .. "P0168"
  row           INTEGER NOT NULL,
  col           INTEGER NOT NULL,
  n_m           REAL NOT NULL,         -- local north of dock, metres
  e_m           REAL NOT NULL,         -- local east of dock, metres
  lat           REAL NOT NULL,
  lon           REAL NOT NULL,
  height_m      REAL,
  condition     TEXT,                  -- latest known: healthy | ripe | frond | ripe+frond | unknown
  status        TEXT NOT NULL DEFAULT 'unscouted',
                                       -- unscouted | target | confirmed | cleared
  confidence    REAL,                  -- latest detection confidence 0..1
  last_visit    TEXT,                  -- ISO-8601 UTC
  notes         TEXT
);

CREATE TABLE missions (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at    TEXT NOT NULL,
  ended_at      TEXT,
  strategy      TEXT,                  -- fw_sweep | hybrid | hover | vtol_sweep
  result        TEXT,                  -- ok | aborted | crashed
  energy_wh     REAL,
  summary_json  TEXT                   -- raw summary.json from a sim run, if any
);

CREATE TABLE observations (            -- one row per photo/detection of a tree
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  tree_id       TEXT NOT NULL REFERENCES trees(id),
  mission_id    INTEGER REFERENCES missions(id),
  captured_at   TEXT NOT NULL,
  source        TEXT NOT NULL,         -- scout | confirm | manual
  model         TEXT,                  -- e.g. "ripeness-yolo11n", "disease-v1"; NULL for a plain photo
  label         TEXT,                  -- e.g. ripe | not_ripe | bud_rot | ...
  confidence    REAL,
  image_path    TEXT                   -- relative to backend/media/
);

CREATE TABLE status_history (          -- audit trail for every status change
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  tree_id       TEXT NOT NULL REFERENCES trees(id),
  changed_at    TEXT NOT NULL,
  old_status    TEXT,
  new_status    TEXT NOT NULL,
  by            TEXT NOT NULL          -- dashboard | planner | pipeline
);
```

- **`seed.py`:** creates the tables, then inserts the 169 trees from
  `trees.csv` (columns `id,row,col,n,e,height,condition,status`), computing
  lat/lon. It must be idempotent: running it twice leaves 169 rows. It also
  takes a `--demo-observations` flag: for the ripe palms in the CSV, insert
  1–3 fake observations with plausible confidences, so the UI has history to
  show before the real pipeline exists.
- **This schema is a contract.** The route planner and the detection pipeline
  (built by other teammates) will read `trees.status` and write
  `observations`. Don't rename columns without telling the team.

## 4. Backend API

REST (JSON):

| Method | Path | Returns / does |
|---|---|---|
| GET | `/api/farm` | `layout.json` plus the field polygon and dock in lat/lon |
| GET | `/api/trees` | All trees (the `trees` row fields). Optional `?status=target` |
| GET | `/api/trees/{id}` | One tree, plus its last 20 observations and status history |
| PATCH | `/api/trees/{id}` | `{status?, notes?}`. Writes `status_history` with `by="dashboard"` |
| POST | `/api/trees/{id}/observations` | Add an observation (the pipeline uses this) |
| GET | `/api/missions` | Mission list, newest first |
| GET | `/api/stats` | Counts per status and condition; last mission; field coverage |
| GET | `/media/{path}` | Static images |

WebSocket `/ws`. Every message is JSON with a `type` field:

| type | direction | payload |
|---|---|---|
| `telemetry` | server → clients, 5 Hz | `{lat, lon, alt_m, heading_deg, groundspeed, airspeed, mode, armed, battery_pct, battery_v, phase, wp_seq, wp_total}` |
| `tree_update` | server → clients | a full tree row, sent whenever a tree changes, from any source |
| `rtc` | phone ↔ server ↔ dashboard | `{role: "camera" or "viewer", kind: "offer", "answer" or "ice", data}`. The server only relays |

`telemetry.py`:
- connects with `pymavlink` to `MAVLINK_URL`; default `tcp:127.0.0.1:5762`,
  a free SITL port while the sim runs;
- reads HEARTBEAT, GLOBAL_POSITION_INT, VFR_HUD, SYS_STATUS / BATTERY_STATUS
  and MISSION_CURRENT;
- broadcasts the latest state at 5 Hz.

If no vehicle is connected, the backend must keep running and send
`{"type":"telemetry","connected":false}`.

## 5. Live video: phone as the drone camera (WebRTC)

1. The phone and the laptop are on the **same Wi-Fi**.
2. The backend serves **`https://<laptop-ip>:8443/camera`**. This is a tiny
   page with one "Start camera" button. It calls
   `getUserMedia({video:{facingMode:"environment", width:1280, height:720}})`
   and sends the stream to the dashboard over WebRTC, using `/ws` for
   signalling.
3. The dashboard's video panel is the WebRTC viewer.
   - No TURN server on a LAN; STUN can be omitted.
   - One camera, one or more viewers. Supporting a single viewer is fine
     for v1.
4. **HTTPS is required:** browsers only allow camera access on secure
   origins.
   - Generate a self-signed cert into `ground_station/certs/`; `mkcert` is
     easiest, or `openssl`.
   - Run uvicorn with it on `0.0.0.0:8443`.
   - The README must say to accept the certificate warning once on the
     phone.
5. The panel shows:
   - a "LIVE" badge with latency/fps from `getStats()`;
   - "No feed" when the camera is gone;
   - a **Snapshot** button that saves the current frame. On the server it
     goes to `media/`; if a tree is selected, it becomes an `observations`
     row with `source="manual"` for that tree.
6. Later, the real drone's camera only has to replace step 2. Keep the
   sender page isolated so it can be swapped out.

## 6. Frontend: layout and behaviour

Match the **reference image** (`reference_ui.jpg`): a dark green, premium
look; a thin icon rail on the left; a content panel; the large map filling
the rest; floating rounded cards with soft shadows; a copper accent colour.

**Design tokens** (taken from the reference; adjust slightly by eye):

| Token | Value |
|---|---|
| `--bg` | `#18211d` |
| `--panel` | `#1f2b26` |
| `--panel-2` | `#26342e` |
| `--border` | `#33433b` |
| `--text` | `#e9eeeb` |
| `--muted` | `#9aa9a1` |
| `--accent` (copper) | `#d9875c` |
| `--accent-2` | `#e7a882` |
| `--ok` | `#6fbf73` |
| `--ripe` | `#e8b04a` |
| `--frond` | `#c46a4a` |
| `--unscouted` | `#7d8b84` |

Typography: **Inter**, weights 400/500/600, 14 px base. Corner radius:
12–16 px on cards, 8 px on buttons.

**Layout, desktop first (≥ 1280 px wide):**

1. **Icon rail** (left, 64 px): Farm (map), Trees (list), Missions, Live,
   Settings. The active item is highlighted in copper.
2. **Side panel** (320 px), the equivalent of "Discover" in the reference:
   - **Mission card:** connection state, flight mode, phase, battery %,
     waypoint `seq/total`, elapsed time.
   - **Farm summary:** counts per status (unscouted / target / confirmed /
     cleared) and per condition, shown as small chips.
   - **"Needs attention" list:** trees with status `target`, sorted by
     confidence, in the style of the reference's "Near You" list. Clicking
     one centres the map and opens that tree's card.
3. **Map** (the rest of the screen):
   - **Drawn farm plan on a dark background**, with no tile layer:
     - field boundary polygon (subtle outline, slightly lighter fill);
     - faint row lines;
     - the dock as a small labelled square.
   - **Tree icons:** a dot or palm glyph per tree, coloured by
     `condition`/`status` with the tokens above. Cleared trees are dimmed;
     targets get a pulsing copper ring. The icon grows on hover, and a
     tooltip shows the ID.
   - **Drone:** an arrow icon rotated to the heading, with a fading trail
     of the last 2 minutes and a dashed line for the planned route. The
     route comes later; leave the hook.
   - **Top bar:** a search box (by tree ID, e.g. "P0305") and connection
     and notification icons, as in the reference.
   - **Bottom-right controls:** zoom +/−, "fit field", and a layer toggle
     (show/hide trees, route, trail, labels).
   - **Legend:** a small card bottom-left.
4. **Tree detail card:** opens on click, floating over the map, in the
   style of the "Kinkaku-ji" card in the reference.
   - **Header:** tree ID, row/col, status pill.
   - **Photo:** the latest observation image if there is one, otherwise a
     placeholder. Thumbnails of earlier images below.
   - **Fields:** height, condition, latest label and confidence, last visit
     (relative time), lat/lon, notes (editable).
   - **History:** observations, newest first, and status changes.
   - **Actions:**
     - **Mark confirmed** and **Mark cleared**: these PATCH the status.
     - **Add to next mission**: sets the status to `target`.
     - **Snapshot from live feed**: enabled when video is live.
5. **Live video panel:**
   - a draggable picture-in-picture over the map, about 360 × 200;
   - an expand button makes it fill the right half of the screen;
   - also available as the "Live" page from the rail.

Every change, from this UI or arriving via `tree_update`, updates the map
icon and any open card **without a page reload**.

## 7. Not in scope (v1)

- Login and user accounts.
- Cloud hosting.
- Satellite tiles.
- Mobile layout for the dashboard. The phone only runs the camera page.
- Mission editing from the UI.
- Running ML in the browser.

## 8. Build order and tests (do each step, test it, then continue)

| Step | Build | Test that must pass before the next step |
|---|---|---|
| 1 | `db.py`, `seed.py` | Run seed twice → `SELECT COUNT(*) FROM trees` = 169. P0000 is at lat ≈ 10.66108, lon ≈ 77.00439. Counts per condition match the CSV: 126 healthy, 23 ripe, 14 frond, 6 ripe+frond |
| 2 | REST API | `pytest` with FastAPI's TestClient covers: list, get one, PATCH status (which writes `status_history`), POST observation, 404 on an unknown ID |
| 3 | Frontend map | Vite dev server shows the field, 169 coloured icons and the dock; clicking any icon opens its card with the correct data |
| 4 | Edit actions | "Mark cleared" changes the icon live; the `status_history` row exists; a second browser tab updates via `tree_update` |
| 5 | Telemetry | With no vehicle, the UI shows "disconnected" and nothing crashes. With the sim running (`bash flight_software/gazebo/run_demo.sh`, then `MAVLINK_URL=tcp:127.0.0.1:5762`), the drone icon moves along the sweep and the mission card updates |
| 6 | Video | Phone on the same Wi-Fi opens `https://<laptop-ip>:8443/camera` and taps Start, and the dashboard shows the feed in under 3 s. Verify on one Android and one iPhone if available. Snapshot creates a file and an `observations` row for the selected tree |
| 7 | Polish | Side by side with `reference_ui.jpg`: same palette, spacing and card style. No console errors |

## 9. How it fits the rest of the project

- **Route planner** (`flight_software/route_planner.py`): today it reads tree
  status from `trees.csv`. Later it will read targets from this DB
  (`status='target'`) and write `cleared` after a confirm pass.
- **Detection pipeline** (ML teammate): posts results to
  `POST /api/trees/{id}/observations`. Each result carries `model`,
  `label`, `confidence` and an image.
- **Simulation:** `flight_software/sim_runner.py` runs produce
  `summary.json`. A small import script can add them to `missions`. That's
  optional for v1.
