import { useEffect, useRef, useState } from "react";
import { CONDITION, STATUS, colorOf, fmtNum, fmtTime } from "./theme.js";
import { api } from "./live.js";
import { startViewer } from "./videoViewer.js";

// ---------- icons ----------
const I = {
  overview: <path d="M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z" />,
  trees: <path d="M12 21v-8M12 13c-1-4-5-5-8-4 2-3 6-3 8 0 2-3 6-3 8 0-3-1-7 0-8 4zM12 9c0-3 2-5 5-6-1 2-2 4-5 6zm0 0c0-3-2-5-5-6 1 2 2 4 5 6z" />,
  camera: <path d="M3 7h12v10H3zM15 10l6-3v10l-6-3z" />,
  locate: <><circle cx="12" cy="12" r="4" /><path d="M12 2v4M12 18v4M2 12h4M18 12h4" /></>,
  close: <path d="M6 6l12 12M18 6L6 18" />,
};
const Icon = ({ name, size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
    strokeLinecap="round" strokeLinejoin="round">{I[name]}</svg>
);

export function Rail({ panel, setPanel, video, setVideo, onLocate, canLocate }) {
  const btn = (name, active, onClick, title, disabled) => (
    <button className={"rail-btn" + (active ? " active" : "")} onClick={onClick} title={title} disabled={disabled}>
      <Icon name={name} />
    </button>
  );
  return (
    <nav className="rail">
      <div className="logo" title="Coconut VTOL ground station">
        <svg viewBox="-16 -16 32 32" width="26" height="26">
          {[0, 60, 120, 180, 240, 300].map((a) => <ellipse key={a} cx="0" cy="-7" rx="2.6" ry="6" transform={`rotate(${a})`} fill="#1a0f06" />)}
        </svg>
      </div>
      {btn("overview", panel === "overview", () => setPanel("overview"), "Overview")}
      {btn("trees", panel === "trees", () => setPanel("trees"), "Trees")}
      <div className="rail-sep" />
      {btn("camera", video, () => setVideo(!video), video ? "Hide camera" : "Show camera")}
      {btn("locate", false, onLocate, "Centre on drone", !canLocate)}
    </nav>
  );
}

// ---------- side panel ----------
function Breakdown({ title, table, trees, field, onPick }) {
  const total = trees.length || 1;
  return (
    <section className="block">
      <h3>{title}</h3>
      {Object.entries(table).map(([key, { label, color }]) => {
        const n = trees.filter((t) => t[field] === key).length;
        return (
          <button key={key} className="bar-row" onClick={() => onPick(field, key)}>
            <span className="dot" style={{ background: color }} />
            <span className="bar-label">{label}</span>
            <span className="bar-track"><span style={{ width: `${(100 * n) / total}%`, background: color }} /></span>
            <span className="bar-num">{n}</span>
          </button>
        );
      })}
    </section>
  );
}

export function SidePanel({ panel, info, trees, selectedId, onSelect, filter, setFilter, setPanel }) {
  const lay = info?.layout;
  const pick = (field, value) => { setFilter({ field, value, q: "" }); setPanel("trees"); };

  if (panel === "overview") {
    const targets = trees.filter((t) => t.status === "target");
    return (
      <aside className="panel">
        <header className="panel-head">
          <div className="eyebrow">Plantation</div>
          <h2>Coconut block · 1 ha</h2>
          {lay && <p className="sub">{trees.length} palms · {lay.grid} × {lay.grid} grid · {lay.spacing} m spacing</p>}
        </header>
        <Breakdown title="Status" table={STATUS} trees={trees} field="status" onPick={pick} />
        <Breakdown title="Condition" table={CONDITION} trees={trees} field="condition" onPick={pick} />
        <section className="block">
          <h3>Targets <span className="count">{targets.length}</span></h3>
          {targets.length === 0 && <p className="muted">No palms flagged yet.</p>}
          <div className="list">
            {targets.map((t) => <TreeRow key={t.id} t={t} active={t.id === selectedId} onSelect={onSelect} />)}
          </div>
        </section>
      </aside>
    );
  }

  const q = filter.q.trim().toUpperCase();
  const shown = trees.filter((t) => (!filter.field || t[filter.field] === filter.value) && (!q || t.id.includes(q)));
  return (
    <aside className="panel">
      <header className="panel-head">
        <div className="eyebrow">Trees</div>
        <h2>{shown.length} of {trees.length}</h2>
      </header>
      <input className="search" placeholder="Search tree ID, e.g. P0612" value={filter.q}
        onChange={(e) => setFilter({ ...filter, q: e.target.value })} />
      <div className="chips">
        <button className={"chip" + (!filter.field ? " on" : "")} onClick={() => setFilter({ field: null, value: null, q: filter.q })}>All</button>
        {Object.entries(STATUS).map(([k, s]) => (
          <button key={k} className={"chip" + (filter.field === "status" && filter.value === k ? " on" : "")}
            onClick={() => setFilter({ field: "status", value: k, q: filter.q })}>{s.label}</button>
        ))}
        {filter.field === "condition" && <button className="chip on">{CONDITION[filter.value].label}</button>}
      </div>
      <div className="list grow">
        {shown.map((t) => <TreeRow key={t.id} t={t} active={t.id === selectedId} onSelect={onSelect} />)}
      </div>
    </aside>
  );
}

function TreeRow({ t, active, onSelect }) {
  return (
    <button className={"tree-row" + (active ? " active" : "")} onClick={() => onSelect(t.id, true)}>
      <span className="dot" style={{ background: colorOf(t, "condition") }} title={CONDITION[t.condition]?.label} />
      <span className="tree-id">{t.id}</span>
      <span className="muted small">R{t.row} · C{t.col}</span>
      <span className={"pill " + t.status}>{STATUS[t.status]?.label}</span>
    </button>
  );
}

// ---------- floating cards ----------
export function TelemetryCard({ tel, live }) {
  const c = tel.connected;
  const stat = (label, value) => <div className="stat"><div className="stat-v">{value}</div><div className="stat-l">{label}</div></div>;
  return (
    <div className="card telemetry">
      <div className="tel-head">
        <span className={"link " + (c ? "ok" : "bad")} />
        <div>
          <div className="tel-title">{c ? tel.mode || "Connected" : live ? "No drone link" : "Ground station offline"}</div>
          <div className="muted small">{c ? (tel.armed ? "Armed" : "Disarmed") : tel.url || "waiting for MAVLink"}</div>
        </div>
      </div>
      {stat("Altitude", fmtNum(tel.alt, 1, " m"))}
      {stat("Ground speed", fmtNum(tel.groundspeed, 1, " m/s"))}
      {stat("Airspeed", fmtNum(tel.airspeed, 1, " m/s"))}
      {stat("Heading", fmtNum(tel.heading, 0, "°"))}
      {stat("Battery", tel.battery != null ? `${tel.battery}%` : fmtNum(tel.voltage, 1, " V"))}
      {stat("Waypoint", tel.wp ?? "—")}
      {tel.text && <div className="tel-text" title={tel.text}>{tel.text}</div>}
    </div>
  );
}

export function Legend({ colorBy, setColorBy }) {
  const table = colorBy === "condition" ? CONDITION : STATUS;
  return (
    <div className="card legend">
      <div className="seg">
        {["status", "condition"].map((k) => (
          <button key={k} className={colorBy === k ? "on" : ""} onClick={() => setColorBy(k)}>
            {k === "status" ? "Status" : "Condition"}
          </button>
        ))}
      </div>
      {Object.values(table).map((s) => (
        <div key={s.label} className="legend-row"><span className="dot" style={{ background: s.color }} />{s.label}</div>
      ))}
      <div className="legend-row"><span className="drone-key" />Drone + trail</div>
    </div>
  );
}

const KIND = { seed: "Imported", status: "Status", visit: "Visit", detection: "Detection", note: "Note" };

export function TreeCard({ id, tree, onClose, compact }) {
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
  }, [id, tree.updated_at, tree.status, tree.condition, tree.notes]);

  const send = async (ev) => {
    setBusy(true); setErr(null);
    try { await api(`/api/trees/${id}/events`, ev); } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  return (
    <div className={"card tree-card" + (compact ? " compact" : "")}>
      <header className="tc-head">
        <div>
          <div className="eyebrow">Palm</div>
          <h2>{tree.id}</h2>
          <div className="muted small">Row {tree.row} · Column {tree.col}</div>
        </div>
        <button className="icon-btn" onClick={onClose} title="Close"><Icon name="close" size={18} /></button>
      </header>

      <div className="tc-pills">
        <span className={"pill big " + tree.status}>{STATUS[tree.status]?.label}</span>
        <span className="pill big" style={{ color: CONDITION[tree.condition]?.color, borderColor: CONDITION[tree.condition]?.color }}>
          {CONDITION[tree.condition]?.label}
        </span>
      </div>

      <dl className="facts">
        <div><dt>Height</dt><dd>{fmtNum(tree.height, 1, " m")}</dd></div>
        <div><dt>Confidence</dt><dd>{tree.confidence != null ? `${Math.round(tree.confidence * 100)}%` : "—"}</dd></div>
        <div><dt>Last visit</dt><dd>{fmtTime(tree.last_visit)}</dd></div>
        <div><dt>From dock</dt><dd>{tree.n.toFixed(1)} m N, {Math.abs(tree.e).toFixed(1)} m {tree.e < 0 ? "W" : "E"}</dd></div>
        <div className="wide"><dt>Lat / Lon</dt><dd className="mono">{tree.lat.toFixed(6)}, {tree.lon.toFixed(6)}</dd></div>
      </dl>

      <section className="tc-sec">
        <h3>Set status</h3>
        <div className="seg full">
          {Object.entries(STATUS).map(([k, s]) => (
            <button key={k} className={tree.status === k ? "on" : ""} disabled={busy || tree.status === k}
              onClick={() => send({ kind: "status", status: k })}>{s.label}</button>
          ))}
        </div>
      </section>

      <section className="tc-sec">
        <h3>Log a visit</h3>
        <div className="row">
          <select value={cond} onChange={(e) => setCond(e.target.value)}>
            {Object.entries(CONDITION).map(([k, c]) => <option key={k} value={k}>{c.label}</option>)}
          </select>
          <button className="btn" disabled={busy} onClick={() => send({ kind: "visit", condition: cond })}>Log visit</button>
        </div>
      </section>

      <section className="tc-sec">
        <h3>Notes</h3>
        {tree.notes && <p className="notes">{tree.notes}</p>}
        <div className="row">
          <input value={note} placeholder="Add a note…" maxLength={2000} onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && note.trim()) { send({ kind: "note", note: note.trim() }); setNote(""); } }} />
          <button className="btn" disabled={busy || !note.trim()}
            onClick={() => { send({ kind: "note", note: note.trim() }); setNote(""); }}>Add</button>
        </div>
      </section>
      {err && <p className="error">{err}</p>}

      <section className="tc-sec">
        <h3>History <span className="count">{hist.length}</span></h3>
        <ol className="history">
          {hist.map((h) => (
            <li key={h.id}>
              <div className="h-top"><b>{KIND[h.kind] || h.kind}</b><span className="muted small">{fmtTime(h.ts)}</span></div>
              <div className="small">
                {h.status && <span className={"pill " + h.status}>{STATUS[h.status]?.label}</span>}
                {h.condition && <span className="h-cond" style={{ color: CONDITION[h.condition]?.color }}>{CONDITION[h.condition]?.label}</span>}
                {h.confidence != null && <span className="muted"> {Math.round(h.confidence * 100)}%</span>}
                {h.note && <span className="h-note">{h.note}</span>}
              </div>
              {h.image && <a href={`/media/${h.image}`} target="_blank" rel="noreferrer"><img className="h-img" src={`/media/${h.image}`} alt="" /></a>}
              <div className="muted tiny">via {h.source}</div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

export function VideoCard() {
  const ref = useRef(null);
  const [status, setStatus] = useState("off");
  const [urls, setUrls] = useState([]);
  useEffect(() => {
    api("/api/camera-urls").then(setUrls).catch(() => {});
    return startViewer((stream) => {
      const v = ref.current;
      if (!v) return;
      v.srcObject = stream;
      if (stream) v.play().catch(() => {});
    }, setStatus);
  }, []);
  return (
    <div className="card video-card">
      <div className="vc-head">
        <span>Drone camera</span>
        <span className={"vc-badge " + status}>{status === "live" ? "LIVE" : status === "waiting" ? "Connecting" : "Offline"}</span>
      </div>
      <div className="vc-frame">
        <video ref={ref} autoPlay playsInline muted />
        {status !== "live" && (
          <div className="vc-empty">
            <Icon name="camera" size={28} />
            <p>On the phone open</p>
            {(urls.length ? urls : ["https://<laptop-ip>:8443/camera"]).map((u) => <code key={u}>{u}</code>)}
            <p className="muted small">and tap Start</p>
          </div>
        )}
      </div>
    </div>
  );
}
