import { useEffect, useRef, useState } from "react";
import { HEALTH, LABEL_STAGE, LENSES, MATURITY, PHOTO, STATUS, colorOf, fmtNum, fmtPct, fmtTime, heat, photoState } from "./theme.js";
import { api, camera } from "./live.js";
import { goNoGo, LIMITS, remaining } from "./checks.js";
import { startViewer } from "./videoViewer.js";

// ---------- icons (SF Symbols-like strokes) ----------
const PATHS = {
  map: <><path d="M9 4 3.5 6v14L9 18l6 2 5.5-2V4L15 6 9 4Z" /><path d="M9 4v14M15 6v14" /></>,
  list: <><path d="M9 6h11M9 12h11M9 18h11" /><circle cx="4.5" cy="6" r="1" /><circle cx="4.5" cy="12" r="1" /><circle cx="4.5" cy="18" r="1" /></>,
  video: <><rect x="3" y="6" width="12.5" height="12" rx="3" /><path d="m15.5 10.5 5-3v9l-5-3" /></>,
  location: <path d="M20.5 3.5 3.5 10.6l7.1 2.8 2.8 7.1 7.1-17Z" />,
  close: <path d="M7 7l10 10M17 7 7 17" />,
  search: <><circle cx="10.5" cy="10.5" r="6" /><path d="m15 15 5 5" /></>,
  chevron: <path d="m9 6 6 6-6 6" />,
  camera: <><path d="M4 8.5A2.5 2.5 0 0 1 6.5 6h1.8l1.4-2h4.6l1.4 2h1.8A2.5 2.5 0 0 1 20 8.5v8a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 16.5v-8Z" /><circle cx="12" cy="12.5" r="3.5" /></>,
  download: <><path d="M12 4v11M7.5 10.5 12 15l4.5-4.5" /><path d="M5 19h14" /></>,
  fit: <><path d="M4 9V5h4M20 9V5h-4M4 15v4h4M20 15v4h-4" /></>,
  bell: <><path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15L6 16Z" /><path d="M10 20.5a2 2 0 0 0 4 0" /></>,
  bellOff: <><path d="M6 16V11a6 6 0 0 1 9.5-4.9M18 11v5l1.5 2H8" /><path d="M10 20.5a2 2 0 0 0 4 0" /><path d="m4 4 16 16" /></>,
};
export const Icon = ({ name, size = 20, stroke = 1.7 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{PATHS[name]}</svg>
);

function Segmented({ options, value, onChange, small }) {
  return (
    <div className={"segmented" + (small ? " small" : "")} role="tablist">
      {options.map(([v, label]) => (
        <button key={String(v)} role="tab" aria-selected={value === v} className={value === v ? "on" : ""}
          onClick={() => value !== v && onChange(v)}>{label}</button>
      ))}
    </div>
  );
}

// ---------- rail ----------
export function Rail({ panel, setPanel, video, setVideo, onLocate, canLocate }) {
  const btn = (name, active, onClick, title, disabled) => (
    <button className={"rail-btn" + (active ? " on" : "")} onClick={onClick} title={title} aria-label={title} disabled={disabled}>
      <Icon name={name} />
    </button>
  );
  return (
    <nav className="rail">
      <div className="logo" aria-hidden="true"><span /></div>
      {btn("map", panel === "overview", () => setPanel("overview"), "Overview")}
      {btn("list", panel === "trees", () => setPanel("trees"), "Trees")}
      <div className="rail-gap" />
      {btn("video", video, () => setVideo(!video), video ? "Hide camera" : "Show camera")}
      {btn("location", false, onLocate, "Centre on drone", !canLocate)}
    </nav>
  );
}

// ---------- sidebar ----------
function Group({ title, trailing, children }) {
  return (
    <section className="group">
      {title && <div className="group-title"><span>{title}</span>{trailing}</div>}
      <div className="group-body">{children}</div>
    </section>
  );
}

function CountRow({ color, label, n, onClick }) {
  return (
    <button className="cell" onClick={onClick}>
      <span className="dot" style={{ background: color }} />
      <span className="cell-label">{label}</span>
      <span className="cell-value">{n}</span>
      <span className="chev"><Icon name="chevron" size={14} stroke={2} /></span>
    </button>
  );
}

// stacked bar of counts (a status overview strip)
function StackBar({ parts }) {
  const total = parts.reduce((a, p) => a + p.n, 0) || 1;
  return (
    <div className="stackbar">
      {parts.filter((p) => p.n).map((p) => (
        <span key={p.label} title={`${p.label}: ${p.n}`} style={{ flexGrow: p.n / total, background: p.color }} />
      ))}
    </div>
  );
}

// next mission planned from the database (backend/planner.py)
function MissionPlan({ plan, mission, onSelect, setColorBy }) {
  const [all, setAll] = useState(false);
  if (!plan) return null;
  const stops = all ? plan.stops : plan.stops.slice(0, 5);
  const used = Math.min(100, plan.battery_pct);
  const simOnly = mission ? mission.targets.filter((t) => !plan.stops.some((s) => s.tree === t)) : [];
  return (
    <Group title="Next mission" trailing={<span className="secondary">from database</span>}>
      <div className="cell static column plan-head">
        <div className="plan-figs">
          <div><b className="num">{plan.stops.length}</b><span>stops</span></div>
          <div><b className="num">{(plan.distance_m / 1000).toFixed(2)}</b><span>km</span></div>
          <div><b className="num">{plan.energy_wh}</b><span>Wh</span></div>
        </div>
        <div className="energy" title={`Battery used: ${plan.battery_pct}% (limit ${plan.budget_pct}%)`}>
          <span className="energy-fill" style={{ width: `${used}%` }} />
          <span className="energy-limit" style={{ left: `${plan.budget_pct}%` }} />
        </div>
        <div className="plan-sub secondary">
          {plan.n_targets} target · {plan.n_predicted} predicted · {plan.battery_pct}% battery
          {plan.dropped.length > 0 && <> · <span className="warn">{plan.dropped.length} over the battery limit</span></>}
        </div>
      </div>
      {stops.map((s) => (
        <button key={s.tree} className="cell stop-row" onClick={() => onSelect(s.tree, true)} title={s.reason}>
          <span className={"stop-badge " + s.kind}>{s.order}</span>
          <span className="cell-label"><b>{s.tree}</b><span className="secondary"> {s.kind === "target" ? "target" : s.reason}</span></span>
          <span className="score"><span style={{ width: `${s.score * 100}%` }} /></span>
        </button>
      ))}
      <div className="cell static plan-actions">
        {plan.stops.length > 5 && <button className="link" onClick={() => setAll(!all)}>{all ? "Fewer" : `All ${plan.stops.length}`}</button>}
        <button className="link" onClick={() => setColorBy("prediction")}>Show prediction</button>
        <a className="btn btn-sm" href="/api/plan.waypoints" download="next_mission.waypoints">
          <Icon name="download" size={15} stroke={2} />Export
        </a>
      </div>
      {mission && (
        <div className="cell static secondary sim-note">
          Simulator mission: {mission.targets.length} stops
          {simOnly.length > 0 && <> · {simOnly.length} no longer in the plan</>}
        </div>
      )}
    </Group>
  );
}

export function SidePanel({ panel, info, trees, pattern, setPattern, selectedId, onSelect, filter, setFilter, setPanel,
  plan, mission, setColorBy, goCard }) {
  const lay = info?.layout;
  const show = (field, value) => { setFilter({ field, value, q: "" }); setPanel("trees"); };

  if (panel === "overview") {
    const inPattern = trees.filter((t) => photoState(t, pattern) !== "skip");
    const done = inPattern.filter((t) => photoState(t, pattern) === "done").length;
    const pct = inPattern.length ? (100 * done) / inPattern.length : 0;
    const targets = trees.filter((t) => t.status === "target");
    return (
      <aside className="sidebar">
        <header className="large-title">
          <h1>Plantation</h1>
          {lay && <p>{trees.length} palms · {lay.grid} × {lay.grid} · {lay.spacing} m spacing</p>}
        </header>

        {goCard}

        <MissionPlan plan={plan} mission={mission} onSelect={onSelect} setColorBy={setColorBy} />

        <Group title="Photo round">
          <div className="cell static">
            <span className="cell-label">Every</span>
            <Segmented small value={pattern.every || 1} onChange={setPattern}
              options={[[1, "All"], [2, "2nd"], [4, "4th"], [8, "8th"]]} />
          </div>
          <div className="cell static column">
            <div className="progress-head">
              <span><b>{done}</b> of {inPattern.length} photographed</span>
              <span className="secondary">{Math.round(pct)}%</span>
            </div>
            <div className="progress"><span style={{ width: `${pct}%` }} /></div>
          </div>
        </Group>

        <Group title="Status">
          <div className="cell static"><StackBar parts={Object.entries(STATUS).map(([k, s]) => (
            { label: s.label, color: s.color, n: trees.filter((t) => t.status === k).length }))} /></div>
          {Object.entries(STATUS).map(([k, s]) => (
            <CountRow key={k} color={s.color} label={s.label} n={trees.filter((t) => t.status === k).length}
              onClick={() => show("status", k)} />
          ))}
        </Group>

        <Group title="Maturity">
          <div className="cell static"><StackBar parts={Object.entries(MATURITY).map(([k, s]) => (
            { label: s.label, color: s.color, n: trees.filter((t) => t.maturity === k).length }))} /></div>
          {Object.entries(MATURITY).map(([k, s]) => (
            <CountRow key={k} color={s.color} label={s.label} n={trees.filter((t) => t.maturity === k).length}
              onClick={() => show("maturity", k)} />
          ))}
        </Group>

        <Group title="Health">
          {Object.entries(HEALTH).map(([k, s]) => (
            <CountRow key={k} color={s.color} label={s.label} n={trees.filter((t) => t.health === k).length}
              onClick={() => show("health", k)} />
          ))}
        </Group>

        <Group title="Targets" trailing={<span className="secondary">{targets.length}</span>}>
          {targets.length === 0 && <div className="cell static secondary">No palms flagged</div>}
          {targets.map((t) => <TreeCell key={t.id} t={t} active={t.id === selectedId} onSelect={onSelect} />)}
        </Group>
      </aside>
    );
  }

  const q = filter.q.trim().toUpperCase();
  const shown = trees.filter((t) => (!filter.field || t[filter.field] === filter.value) && (!q || t.id.includes(q)));
  const statusFilter = filter.field === "status" ? filter.value : filter.field ? "other" : null;
  return (
    <aside className="sidebar">
      <header className="large-title">
        <h1>Trees</h1>
        <p>{filter.field === "maturity" ? `${MATURITY[filter.value].label} · ` : filter.field === "health" ? `${HEALTH[filter.value].label} · ` : ""}{shown.length} of {trees.length}</p>
      </header>
      <label className="search">
        <Icon name="search" size={16} />
        <input placeholder="Search" value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.target.value })} />
      </label>
      <Segmented small value={statusFilter} onChange={(v) => setFilter({ field: v ? "status" : null, value: v, q: filter.q })}
        options={[[null, "All"], ...Object.entries(STATUS).map(([k, s]) => [k, s.label])]} />
      <div className="group-body scroll">
        {shown.map((t) => <TreeCell key={t.id} t={t} active={t.id === selectedId} onSelect={onSelect} />)}
      </div>
    </aside>
  );
}

function TreeCell({ t, active, onSelect }) {
  return (
    <button className={"cell" + (active ? " active" : "")} onClick={() => onSelect(t.id, true)}>
      <span className="dot" style={{ background: colorOf(t, "harvest") }} />
      <span className="cell-label"><b>{t.id}</b><span className="secondary"> Row {t.row}, Col {t.col}</span></span>
      <span className="cell-value" style={{ color: t.status === "unscouted" ? undefined : STATUS[t.status].color }}>
        {STATUS[t.status].label}
      </span>
    </button>
  );
}

// ---------- floating: telemetry ----------
const PHASE = { vtol: "VTOL", transition: "Transition", "fixed-wing": "Fixed-wing", ground: "On ground", glide: "Gliding" };

function Spark({ values }) {
  if (values.length < 2) return <svg className="spark" viewBox="0 0 100 28" />;
  const lo = Math.min(...values), hi = Math.max(...values, lo + 1);
  const pts = values.map((v, i) => `${(100 * i) / (values.length - 1)},${26 - (24 * (v - lo)) / (hi - lo)}`).join(" ");
  return (
    <svg className="spark" viewBox="0 0 100 28" preserveAspectRatio="none">
      <polyline points={`0,28 ${pts} 100,28`} className="spark-fill" />
      <polyline points={pts} className="spark-line" />
    </svg>
  );
}

export function TelemetryCard({ tel, live, altHist = [] }) {
  const c = tel.connected;
  const metric = (label, value, unit) => (
    <div className="metric">
      <div className="metric-v">{value}{value !== "—" && unit && <span className="unit">{unit}</span>}</div>
      <div className="metric-l">{label}</div>
    </div>
  );
  return (
    <div className="material hud">
      <div className="hud-head">
        <span className={"status-dot" + (c ? " ok" : "")} />
        <div>
          <div className="hud-title">{c ? tel.mode || "Connected" : live ? "No Drone" : "Offline"}</div>
          <div className="hud-sub">{c ? (tel.armed ? "Armed" : "Disarmed") : live ? "Waiting for MAVLink" : "Reconnecting"}</div>
        </div>
        {c && tel.phase && <span className={"phase " + tel.phase}>{PHASE[tel.phase] || tel.phase}</span>}
      </div>
      <div className="metric spark-metric"><Spark values={altHist} /><div className="metric-l">Altitude trend</div></div>
      {metric("Altitude", fmtNum(tel.alt), "m")}
      {metric("Ground speed", fmtNum(tel.groundspeed), "m/s")}
      {metric("Airspeed", fmtNum(tel.airspeed), "m/s")}
      {metric("Heading", fmtNum(tel.heading, 0), "°")}
      {metric("Battery", tel.battery != null ? String(tel.battery) : fmtNum(tel.voltage), tel.battery != null ? "%" : "V")}
      {metric("Waypoint", tel.wp != null ? (tel.wp_total ? `${tel.wp}/${tel.wp_total}` : String(tel.wp)) : "—")}
    </div>
  );
}

// ---------- floating: legend ----------
export function MapBar({ layers, setLayers, onFit, muted, setMuted }) {
  const pill = (k, label) => (
    <button key={k} className={"pill" + (layers[k] ? " on" : "")} aria-pressed={layers[k]}
      onClick={() => setLayers({ ...layers, [k]: !layers[k] })}>{label}</button>
  );
  return (
    <div className="material mapbar">
      {pill("plan", "Plan")}{pill("sim", "Sim route")}{pill("trail", "Trail")}{pill("chips", "Labels")}
      <span className="bar-sep" />
      <button className="icon-btn" onClick={onFit} title="Fit field" aria-label="Fit field"><Icon name="fit" size={16} stroke={2} /></button>
      <button className={"icon-btn" + (muted ? "" : " on")} onClick={() => setMuted(!muted)}
        title={muted ? "Alert sounds off" : "Alert sounds on"} aria-label={muted ? "Turn alert sounds on" : "Turn alert sounds off"}>
        <Icon name={muted ? "bellOff" : "bell"} size={16} stroke={2} /></button>
    </div>
  );
}

const RINGS = Object.values(STATUS).filter((s) => s.ring);

export function Legend({ colorBy, setColorBy }) {
  const table = colorBy === "health" ? HEALTH : colorBy === "photos" ? PHOTO : colorBy === "prediction" ? null : MATURITY;
  const rings = colorBy === "harvest" || colorBy === "prediction";
  return (
    <div className="material legend">
      <Segmented small value={colorBy} onChange={setColorBy} options={LENSES} />
      <div className="legend-keys">
        {table ? Object.values(table).map((s) => (
          <div key={s.label} className="legend-key"><span className="dot" style={{ background: s.color }} />{s.label}</div>
        )) : (
          <div className="legend-heat">
            <span className="heat-bar" style={{ background: `linear-gradient(90deg, ${[0, 0.35, 0.5, 0.75, 1].map(heat).join(",")})` }} />
            <div className="heat-ticks secondary"><span>0%</span><span>tender chance</span><span>100%</span></div>
          </div>
        )}
        {rings && (
          <div className="legend-rings">
            {RINGS.map((s) => <span key={s.label} className="legend-key"><span className="ring-swatch" style={{ "--r": s.ring }} />{s.label}</span>)}
            <span className="legend-key"><span className="notch-swatch" />Health issue</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------- floating: inspector ----------
const KIND = { seed: "Imported", status: "Status changed", visit: "Visited", detection: "Detection", note: "Note" };

export function TreeCard({ id, tree, pattern, onClose, compact, plan }) {
  const [hist, setHist] = useState([]);
  const [note, setNote] = useState("");
  const [stage, setStage] = useState(tree.maturity);
  const [hea, setHea] = useState(tree.health);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => { setStage(tree.maturity); setHea(tree.health); setErr(null); }, [id, tree.maturity, tree.health]);
  useEffect(() => {
    let alive = true;
    api(`/api/trees/${id}`).then((r) => alive && setHist(r.history)).catch(() => {});
    return () => { alive = false; };
  }, [id, tree.updated_at, tree.status, tree.condition, tree.notes, tree.last_photo]);

  const send = async (ev) => {
    setBusy(true); setErr(null);
    try { await api(`/api/trees/${id}/events`, ev); } catch (e) { setErr(e.message); }
    setBusy(false);
  };
  const addNote = () => { if (note.trim()) { send({ kind: "note", note: note.trim() }); setNote(""); } };
  const photo = hist.find((h) => h.image);
  const stop = plan?.stops?.find((x) => x.tree === id);
  const ps = photoState(tree, pattern);
  const row = (label, value, mono) => (
    <div className="cell static"><span className="cell-label secondary">{label}</span><span className={"cell-value" + (mono ? " mono" : "")}>{value}</span></div>
  );

  return (
    <div className={"material inspector" + (compact ? " compact" : "")} key={id}>
      <header className="insp-head">
        <div>
          <h2>{tree.id}</h2>
          <p>Row {tree.row}, Column {tree.col}</p>
        </div>
        <button className="close" onClick={onClose} aria-label="Close"><Icon name="close" size={14} stroke={2.4} /></button>
      </header>

      <div className="tags">
        <span className="tag" style={{ "--c": STATUS[tree.status].color }}>{STATUS[tree.status].label}</span>
        <span className="tag" style={{ "--c": (MATURITY[tree.maturity] || MATURITY.unknown).color }}>{(MATURITY[tree.maturity] || MATURITY.unknown).label}</span>
        {tree.health !== "healthy" && <span className="tag" style={{ "--c": HEALTH[tree.health]?.color }}>{HEALTH[tree.health]?.label}</span>}
        {ps !== "skip" && <span className="tag" style={{ "--c": PHOTO[ps].color }}>{PHOTO[ps].label}</span>}
        {stop && <span className="tag" style={{ "--c": "#ffcf99" }}>Stop {stop.order} of next mission</span>}
      </div>

      <div className="ripe-meter">
        <div className="ripe-top"><span>Tender-nut prediction</span><b>{fmtPct(tree.ripe_score)}</b></div>
        <div className="score big"><span style={{ width: `${(tree.ripe_score ?? 0) * 100}%` }} /></div>
        <div className="secondary ripe-why">{tree.ripe_reason || "—"}</div>
      </div>

      {photo && (
        <a className="hero" href={`/media/${photo.image}`} target="_blank" rel="noreferrer">
          <img src={`/media/${photo.image}`} alt={`Latest photo of ${tree.id}`} />
          <span>{fmtTime(photo.ts)}</span>
        </a>
      )}

      <div className="group-body">
        {row("Height", `${fmtNum(tree.height)} m`)}
        {row("Last detection", tree.label ? `${MATURITY[LABEL_STAGE[tree.label]]?.label || tree.label} · ${fmtPct(tree.confidence)}` : "—")}
        {row("Last visit", fmtTime(tree.last_visit))}
        {row("From dock", `${tree.n.toFixed(1)} m N · ${Math.abs(tree.e).toFixed(1)} m ${tree.e < 0 ? "W" : "E"}`)}
        {row("Coordinates", `${tree.lat.toFixed(6)}, ${tree.lon.toFixed(6)}`, true)}
      </div>

      <Group title="Status">
        <div className="cell static pad">
          <Segmented value={tree.status} onChange={(k) => !busy && send({ kind: "status", status: k })}
            options={Object.entries(STATUS).map(([k, s]) => [k, s.label])} />
        </div>
      </Group>

      <Group title="Log visit">
        <div className="cell static pad gap">
          <select value={stage} onChange={(e) => setStage(e.target.value)} aria-label="Maturity">
            {Object.entries(MATURITY).map(([k, c]) => <option key={k} value={k}>{c.label}</option>)}
          </select>
          <select value={hea} onChange={(e) => setHea(e.target.value)} aria-label="Health">
            {Object.entries(HEALTH).map(([k, c]) => <option key={k} value={k}>{c.label}</option>)}
          </select>
          <button className="btn" disabled={busy} onClick={() => send({ kind: "visit", maturity: stage, health: hea })}>Log</button>
        </div>
      </Group>

      <Group title="Notes">
        {tree.notes && <div className="cell static notes">{tree.notes}</div>}
        <div className="cell static pad gap">
          <input value={note} placeholder="Add a note" maxLength={2000} onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addNote()} />
          <button className="btn" disabled={busy || !note.trim()} onClick={addNote}>Add</button>
        </div>
      </Group>
      {err && <p className="error">{err}</p>}

      <Group title="History" trailing={<span className="secondary">{hist.length}</span>}>
        {hist.map((h) => (
          <div key={h.id} className="cell static event">
            <div className="event-top"><b>{KIND[h.kind] || h.kind}</b><span className="secondary">{fmtTime(h.ts)}</span></div>
            <div className="event-body secondary">
              {[h.status && STATUS[h.status]?.label, h.maturity && MATURITY[h.maturity]?.label,
                h.health && h.health !== "healthy" && HEALTH[h.health]?.label,
                h.label && !h.maturity && (MATURITY[LABEL_STAGE[h.label]]?.label || h.label),
                h.confidence != null && `${Math.round(h.confidence * 100)}%`, h.model, h.note, `via ${h.source}`]
                .filter(Boolean).join(" · ")}
            </div>
            {h.image && h !== photo && <img className="event-img" src={`/media/${h.image}`} alt="" />}
          </div>
        ))}
      </Group>
    </div>
  );
}

// ---------- floating: camera ----------
export function VideoCard() {
  const ref = useRef(null);
  const [status, setStatus] = useState("off");
  const [urls, setUrls] = useState([]);
  const [shutter, setShutter] = useState(0);
  const [reading, setReading] = useState(null);
  useEffect(() => {
    camera.video = ref.current;
    camera.onShutter = (treeId, card) => { setShutter((n) => n + 1); setReading({ treeId, card }); };
    api("/api/camera-urls").then(setUrls).catch(() => {});
    const stop = startViewer((stream) => {
      const v = ref.current;
      if (!v) return;
      v.srcObject = stream;
      if (stream) v.play().catch(() => {});
    }, setStatus);
    return () => { stop(); camera.video = null; camera.onShutter = null; };
  }, []);
  const live = status === "live";
  return (
    <div className={"material camera-card" + (live ? " live" : "")}>
      <video ref={ref} autoPlay playsInline muted />
      {shutter > 0 && <div key={shutter} className="shutter" />}
      <div className="cam-label">
        <span className={"rec" + (live ? " on" : "")} />{live ? "Live" : status === "waiting" ? "Connecting" : "Camera"}
      </div>
      {live && reading && (
        <div className="cam-reading" key={shutter}>
          <b>{reading.treeId}</b>
          {reading.card
            ? <><i style={{ background: MATURITY[reading.card.stage].color }} />{MATURITY[reading.card.stage].label} · {fmtPct(reading.card.confidence)}</>
            : <span className="secondary">no card in view: photo only</span>}
        </div>
      )}
      {!live && (
        <div className="cam-empty">
          {urls.length > 0 ? (
            <>
              <img className="qr" alt="QR code: phone setup" src={`/api/qr?text=${encodeURIComponent(urls[0].replace(/\/camera$/, "/phone"))}`} />
              <div className="cam-help">
                <b>Connect a phone camera</b>
                <p>Same Wi-Fi as this laptop. Scan, then follow the two steps.</p>
                <code>{urls[0].replace(/\/camera$/, "/phone")}</code>
              </div>
            </>
          ) : (
            <>
              <Icon name="camera" size={26} stroke={1.5} />
              <p>No network: connect the laptop to Wi-Fi to add a phone camera</p>
            </>
          )}
        </div>
      )}
    </div>
  );
}


// ---------- floating: mission progress ----------
// The stops of the mission being flown (the simulator's / uploaded plan) as
// done / current / next, with time and energy to landing (checks.remaining).
export function MissionStrip({ mission, plan, tel, onSelect }) {
  const r = remaining(mission, tel);
  if (!r) return null;
  const { flying, wp, stops, left, current, secs, wh, landingPct } = r;
  const sameAsPlan = plan && plan.stops.length === stops.length && plan.stops.every((p) => stops.some((s) => s.tree === p.tree));
  return (
    <div className="material strip">
      <div className="strip-head">
        <b>{flying ? "Mission in flight" : "Loaded mission"}</b>
        <span className="secondary">{stops.length - left.length}/{stops.length} stops
          {sameAsPlan ? " · matches the plan" : plan ? " · differs from the plan" : ""}</span>
      </div>
      <div className="strip-stops">
        {stops.map((s) => {
          const st = !flying ? "next" : s.seq < wp ? "done" : s === current ? "current" : "next";
          return (
            <button key={s.tree} className={"strip-stop " + st} title={s.tree} onClick={() => onSelect(s.tree, true)}>
              <span />
            </button>
          );
        })}
      </div>
      <div className="strip-figs">
        <span>{current ? <>next <b>{current.tree}</b></> : "landing"}</span>
        <span>≈ <b>{Math.floor(secs / 60)}:{String(Math.round(secs % 60)).padStart(2, "0")}</b> to landing</span>
        <span>≈ <b>{wh.toFixed(1)} Wh</b> still needed</span>
        {landingPct != null && <span className={landingPct < 20 ? "warn" : ""}>≈ <b>{Math.max(0, Math.round(landingPct))}%</b> at landing</span>}
      </div>
    </div>
  );
}

// ---------- go / no-go (sidebar) ----------
const GO_LABEL = { go: "GO", caution: "CAUTION", "no-go": "NO-GO" };

export function GoCard({ tel, wind, plan }) {
  const g = goNoGo({ tel, wind, plan });
  const [speed, setSpeed] = useState("");
  const [gust, setGust] = useState("");
  const [err, setErr] = useState(null);
  const save = async (clear) => {
    setErr(null);
    try {
      await api("/api/wind", clear ? { speed: null } : { speed: Number(speed), gust: gust === "" ? null : Number(gust) });
      if (clear) { setSpeed(""); setGust(""); }
    } catch (e) { setErr("Mean 0-40 m/s; gust at least the mean"); }
  };
  return (
    <Group title="Go / no-go" trailing={<span className={"go-pill " + g.overall}>{GO_LABEL[g.overall]}</span>}>
      {g.checks.map((c) => (
        <div key={c.key} className="cell static go-row">
          <span className={"go-dot " + c.state} />
          <span className="cell-label">{c.label}</span>
          <span className="cell-value go-detail" title={c.detail}>{c.detail}</span>
        </div>
      ))}
      <div className="cell static column wind-entry">
        <div className="wind-inputs">
          <label>Wind <input type="number" min="0" max="40" step="0.5" placeholder="mean" value={speed}
            onChange={(e) => setSpeed(e.target.value)} aria-label="Mean wind, m/s" /></label>
          <label>gust <input type="number" min="0" max="50" step="0.5" placeholder="—" value={gust}
            onChange={(e) => setGust(e.target.value)} aria-label="Gusts, m/s" /></label>
          <span className="secondary">m/s</span>
          <button className="btn btn-sm" disabled={speed === ""} onClick={() => save(false)}>Set</button>
          {wind && <button className="link" onClick={() => save(true)}>Clear</button>}
        </div>
        <div className="secondary wind-note">
          Limits from the sim study: go ≤ {LIMITS.windGo} m/s, no-go &gt; {LIMITS.windNoGo} m/s mean.
          {wind ? ` Entered ${new Date(wind.ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}.` : " In flight the autopilot's wind estimate is used."}
        </div>
        {err && <div className="error">{err}</div>}
      </div>
    </Group>
  );
}

// ---------- floating: alerts ----------
export function Toasts({ alerts, onDismiss, onSelect }) {
  if (!alerts.length) return null;
  return (
    <div className="toasts" role="status" aria-live="polite">
      {alerts.map((a) => (
        <div key={a.key} className={"material toast " + a.level}>
          <span className="toast-bar" />
          <div className="toast-text" onClick={() => a.tree && onSelect(a.tree, true)} style={{ cursor: a.tree ? "pointer" : undefined }}>
            <b>{a.title}</b>
            {a.body && <span>{a.body}</span>}
          </div>
          <button className="close" onClick={() => onDismiss(a.key)} aria-label="Dismiss"><Icon name="close" size={12} stroke={2.4} /></button>
        </div>
      ))}
    </div>
  );
}
