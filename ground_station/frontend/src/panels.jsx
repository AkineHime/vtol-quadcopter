import { useEffect, useRef, useState } from "react";
import { CONDITION, PHOTO, STATUS, colorOf, fmtNum, fmtTime, photoState } from "./theme.js";
import { api, camera } from "./live.js";
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

export function SidePanel({ panel, info, trees, pattern, setPattern, selectedId, onSelect, filter, setFilter, setPanel }) {
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
          {Object.entries(STATUS).map(([k, s]) => (
            <CountRow key={k} color={s.color} label={s.label} n={trees.filter((t) => t.status === k).length}
              onClick={() => show("status", k)} />
          ))}
        </Group>

        <Group title="Condition">
          {Object.entries(CONDITION).map(([k, s]) => (
            <CountRow key={k} color={s.color} label={s.label} n={trees.filter((t) => t.condition === k).length}
              onClick={() => show("condition", k)} />
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
        <p>{filter.field === "condition" ? `${CONDITION[filter.value].label} · ` : ""}{shown.length} of {trees.length}</p>
      </header>
      <label className="search">
        <Icon name="search" size={16} />
        <input placeholder="Search" value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.target.value })} />
      </label>
      <Segmented value={statusFilter} onChange={(v) => setFilter({ field: v ? "status" : null, value: v, q: filter.q })}
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
      <span className="dot" style={{ background: colorOf(t, "condition") }} />
      <span className="cell-label"><b>{t.id}</b><span className="secondary"> Row {t.row}, Col {t.col}</span></span>
      <span className="cell-value" style={{ color: t.status === "unscouted" ? undefined : STATUS[t.status].color }}>
        {STATUS[t.status].label}
      </span>
    </button>
  );
}

// ---------- floating: telemetry ----------
export function TelemetryCard({ tel, live }) {
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
      </div>
      {metric("Altitude", fmtNum(tel.alt), "m")}
      {metric("Ground speed", fmtNum(tel.groundspeed), "m/s")}
      {metric("Airspeed", fmtNum(tel.airspeed), "m/s")}
      {metric("Heading", fmtNum(tel.heading, 0), "°")}
      {metric("Battery", tel.battery != null ? String(tel.battery) : fmtNum(tel.voltage), tel.battery != null ? "%" : "V")}
      {metric("Waypoint", tel.wp != null ? String(tel.wp) : "—")}
    </div>
  );
}

// ---------- floating: legend ----------
export function Legend({ colorBy, setColorBy }) {
  const table = colorBy === "condition" ? CONDITION : colorBy === "photos" ? PHOTO : STATUS;
  return (
    <div className="material legend">
      <Segmented small value={colorBy} onChange={setColorBy}
        options={[["status", "Status"], ["condition", "Condition"], ["photos", "Photos"]]} />
      <div className="legend-keys">
        {Object.values(table).map((s) => (
          <div key={s.label} className="legend-key"><span className="dot" style={{ background: s.color }} />{s.label}</div>
        ))}
      </div>
    </div>
  );
}

// ---------- floating: inspector ----------
const KIND = { seed: "Imported", status: "Status changed", visit: "Visited", detection: "Detection", note: "Note" };

export function TreeCard({ id, tree, pattern, onClose, compact }) {
  const [hist, setHist] = useState([]);
  const [note, setNote] = useState("");
  const [cond, setCond] = useState(tree.condition);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => { setCond(tree.condition); setErr(null); }, [id, tree.condition]);
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
        <span className="tag" style={{ "--c": CONDITION[tree.condition].color }}>{CONDITION[tree.condition].label}</span>
        {ps !== "skip" && <span className="tag" style={{ "--c": PHOTO[ps].color }}>{PHOTO[ps].label}</span>}
      </div>

      {photo && (
        <a className="hero" href={`/media/${photo.image}`} target="_blank" rel="noreferrer">
          <img src={`/media/${photo.image}`} alt={`Latest photo of ${tree.id}`} />
          <span>{fmtTime(photo.ts)}</span>
        </a>
      )}

      <div className="group-body">
        {row("Height", `${fmtNum(tree.height)} m`)}
        {row("Confidence", tree.confidence != null ? `${Math.round(tree.confidence * 100)}%` : "—")}
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
          <select value={cond} onChange={(e) => setCond(e.target.value)} aria-label="Condition">
            {Object.entries(CONDITION).map(([k, c]) => <option key={k} value={k}>{c.label}</option>)}
          </select>
          <button className="btn" disabled={busy} onClick={() => send({ kind: "visit", condition: cond })}>Log</button>
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
              {[h.status && STATUS[h.status]?.label, h.condition && CONDITION[h.condition]?.label,
                h.confidence != null && `${Math.round(h.confidence * 100)}%`, h.note, `via ${h.source}`]
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
  useEffect(() => {
    camera.video = ref.current;
    camera.onShutter = () => setShutter((n) => n + 1);
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
      {!live && (
        <div className="cam-empty">
          <Icon name="camera" size={26} stroke={1.5} />
          <p>Open on the phone and tap Start</p>
          {(urls.length ? urls : ["https://<laptop-ip>:8443/camera"]).map((u) => <code key={u}>{u}</code>)}
        </div>
      )}
    </div>
  );
}

