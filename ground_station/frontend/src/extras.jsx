// Flight replay, post-flight report, photo gallery and the enlarged QR code.
import { useEffect, useMemo, useState } from "react";
import { LABEL_STAGE, MATURITY, fmtPct, fmtTime } from "./theme.js";
import { api } from "./live.js";

const PHASE_COLOR = { vtol: "#64d2ff", transition: "#ffd60a", "fixed-wing": "#30d158", ground: "#8e8e93", glide: "#bf5af2" };
const fmtDur = (s) => (s == null ? "—" : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`);
const stageOf = (e) => e.maturity || LABEL_STAGE[e.label];

// ---------- modal shell ----------
export function Modal({ onClose, children, wide }) {
  useEffect(() => {
    const k = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="modal-back" onClick={onClose}>
      <div className={"modal" + (wide ? " wide" : "")} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <button className="close modal-close" onClick={onClose} aria-label="Close">×</button>
        {children}
      </div>
    </div>
  );
}

// ---------- QR code, large ----------
export function QrModal({ url, onClose }) {
  return (
    <Modal onClose={onClose}>
      <div className="qr-big">
        <img src={`/api/qr?text=${encodeURIComponent(url)}`} alt="QR code" />
        <code>{url}</code>
        <p className="secondary">Scan with the phone on the same Wi-Fi.</p>
      </div>
    </Modal>
  );
}

// ---------- photo lightbox ----------
export function Lightbox({ photos, index, onClose, onOpenTree }) {
  const [i, setI] = useState(index);
  useEffect(() => {
    const k = (e) => {
      if (e.key === "ArrowRight") setI((x) => Math.min(photos.length - 1, x + 1));
      if (e.key === "ArrowLeft") setI((x) => Math.max(0, x - 1));
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [photos.length]);
  const p = photos[i];
  if (!p) return null;
  const st = stageOf(p);
  return (
    <Modal onClose={onClose} wide>
      <div className="lightbox">
        <img src={`/media/${p.image}`} alt={`${p.tree_id} ${fmtTime(p.ts)}`} />
        <div className="lb-bar">
          <button className="icon-btn" disabled={i === 0} onClick={() => setI(i - 1)} aria-label="Previous">‹</button>
          <div className="lb-cap">
            <b>{p.tree_id}</b>
            <span>{fmtTime(p.ts)}</span>
            {st && <span className="tag" style={{ "--c": MATURITY[st]?.color }}>{MATURITY[st]?.label}{p.confidence != null ? ` · ${fmtPct(p.confidence)}` : ""}</span>}
            <span className="secondary">{p.model || p.source}</span>
          </div>
          <span className="secondary">{i + 1} / {photos.length}</span>
          <button className="icon-btn" disabled={i === photos.length - 1} onClick={() => setI(i + 1)} aria-label="Next">›</button>
          {onOpenTree && <button className="btn btn-sm" onClick={() => { onOpenTree(p.tree_id); onClose(); }}>Open palm</button>}
        </div>
      </div>
    </Modal>
  );
}

// thumbnails grid used by the tree card and the photos panel
export function Thumbs({ photos, onOpen, showTree }) {
  return (
    <div className="thumbs">
      {photos.map((p, k) => {
        const st = stageOf(p);
        return (
          <button key={p.id} className="thumb" onClick={() => onOpen(k)} title={`${p.tree_id} · ${fmtTime(p.ts)}`}>
            <img src={`/media/${p.image}`} alt="" loading="lazy" />
            {st && <i style={{ background: MATURITY[st]?.color }} />}
            {showTree && <span>{p.tree_id}</span>}
          </button>
        );
      })}
    </div>
  );
}

// ---------- sidebar: all photos ----------
export function PhotosPanel({ onSelect }) {
  const [filter, setFilter] = useState("");
  const [photos, setPhotos] = useState([]);
  const [open, setOpen] = useState(null);
  useEffect(() => {
    api(`/api/photos${filter ? `?maturity=${filter}` : ""}`).then(setPhotos).catch(() => {});
  }, [filter]);
  return (
    <aside className="sidebar">
      <header className="large-title"><h1>Photos</h1><p>{photos.length} shown · newest first</p></header>
      <div className="chips">
        {[["", "All"], ["tender", "Tender"], ["mature", "Mature"], ["over-mature", "Over-mature"], ["young", "Young"]].map(([k, l]) => (
          <button key={k} className={"pill" + (filter === k ? " on" : "")} onClick={() => setFilter(k)}>{l}</button>
        ))}
      </div>
      {photos.length === 0 && <p className="secondary empty">No photos yet: they come from photo rounds, the phone camera and the ML pipeline.</p>}
      <Thumbs photos={photos} onOpen={setOpen} showTree />
      {open != null && <Lightbox photos={photos} index={open} onClose={() => setOpen(null)} onOpenTree={(id) => onSelect(id, true)} />}
    </aside>
  );
}

// ---------- sidebar: recorded flights ----------
export function FlightsPanel({ flights, onReplay, onReport, activeId }) {
  return (
    <aside className="sidebar">
      <header className="large-title"><h1>Flights</h1><p>{flights.length} recorded · arm to disarm</p></header>
      {flights.length === 0 && <p className="secondary empty">No flights yet. Every flight is recorded automatically from takeoff to landing.</p>}
      <div className="group-body">
        {flights.map((f) => {
          const s = f.stats || {};
          return (
            <div key={f.id} className={"cell static flight-row" + (f.id === activeId ? " active" : "")}>
              <div className="flight-main">
                <b>Flight {f.id}</b>
                <span className="secondary">{fmtTime(f.started_at)} · {fmtDur(s.duration_s)} · {s.distance_m != null ? `${(s.distance_m / 1000).toFixed(2)} km` : "—"}</span>
                <span className="secondary">{f.ended_at ? `${s.stops_reached ?? 0}/${s.stops_planned ?? 0} stops · ${s.photos ?? 0} photos` : "in flight…"}
                  {f.result === "lost" && <span className="warn"> · link lost</span>}</span>
              </div>
              <div className="flight-actions">
                <button className="btn btn-sm" onClick={() => onReplay(f.id)}>Replay</button>
                {f.ended_at && <button className="link" onClick={() => onReport(f.id)}>Report</button>}
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
}

// position etc. at time t, linearly interpolated between recorded points
export function sampleAt(points, t) {
  if (!points.length) return null;
  let i = points.findIndex((p) => p.t > t);
  if (i === -1) return { ...points[points.length - 1] };
  if (i === 0) return { ...points[0] };
  const a = points[i - 1], b = points[i], w = (t - a.t) / (b.t - a.t || 1);
  const lerp = (x, y) => (x == null || y == null ? x ?? y : x + (y - x) * w);
  const dh = ((((b.heading ?? 0) - (a.heading ?? 0)) % 360) + 540) % 360 - 180;
  return { ...a, t, lat: lerp(a.lat, b.lat), lon: lerp(a.lon, b.lon), alt: lerp(a.alt, b.alt),
    groundspeed: lerp(a.groundspeed, b.groundspeed), heading: ((a.heading ?? 0) + dh * w + 360) % 360 };
}

// ---------- bottom: replay controls ----------
const SPEEDS = [1, 4, 16, 64];
export function ReplayBar({ flight, t, setT, playing, setPlaying, speed, setSpeed, onExit, onReport, onSelect }) {
  const total = flight.points.length ? flight.points[flight.points.length - 1].t : 0;
  const t0 = useMemo(() => new Date(flight.started_at).getTime(), [flight.started_at]);
  const marks = flight.events.filter((e) => e.kind === "detection" || e.status === "target")
    .map((e) => ({ ...e, at: (new Date(e.ts).getTime() - t0) / 1000 })).filter((e) => e.at >= 0 && e.at <= total);
  const segs = [];
  flight.points.forEach((p, i) => {
    const last = segs[segs.length - 1];
    if (last && last.phase === p.phase) last.to = p.t;
    else segs.push({ phase: p.phase, from: i ? flight.points[i - 1].t : 0, to: p.t });
  });
  return (
    <div className="material strip replay">
      <div className="strip-head">
        <b>Replay · flight {flight.id}</b>
        <span className="secondary">{fmtTime(flight.started_at)}</span>
      </div>
      <div className="replay-track">
        <div className="phase-band">
          {segs.map((s, k) => <span key={k} style={{ left: `${(100 * s.from) / total}%`, width: `${(100 * (s.to - s.from)) / total}%`, background: PHASE_COLOR[s.phase] || "#555" }} />)}
          {marks.map((m) => <button key={m.id} className="mark" style={{ left: `${(100 * m.at) / total}%` }}
            title={`${m.tree_id}: ${m.label || m.status}`} onClick={() => { setT(m.at); onSelect(m.tree_id, true); }} />)}
        </div>
        <input type="range" min="0" max={total} step="0.5" value={t} onChange={(e) => setT(Number(e.target.value))} aria-label="Replay time" />
      </div>
      <div className="replay-ctl">
        <button className="btn btn-sm" onClick={() => { if (t >= total) setT(0); setPlaying(!playing); }}>{playing ? "Pause" : "Play"}</button>
        <div className="segmented small">
          {SPEEDS.map((s) => <button key={s} className={speed === s ? "on" : ""} onClick={() => setSpeed(s)}>{s}×</button>)}
        </div>
        <span className="replay-time"><b>{fmtDur(t)}</b> / {fmtDur(total)}</span>
        <span className="spacer" />
        <button className="link" onClick={onReport}>Report</button>
        <button className="link" onClick={onExit}>Exit replay</button>
      </div>
    </div>
  );
}

// ---------- post-flight report ----------
export function ReportModal({ flight, onClose, onReplay, onSelect }) {
  const s = flight.stats || {};
  const plan = flight.plan || {};
  const phaseTotal = Object.values(s.phase_s || {}).reduce((a, b) => a + b, 0) || 1;
  const fig = (label, value, sub) => (
    <div className="rep-fig"><span>{label}</span><b>{value}</b>{sub && <i>{sub}</i>}</div>
  );
  const pct = (a, b) => (a != null && b ? `${Math.round((100 * a) / b)}% of plan` : null);
  return (
    <Modal onClose={onClose} wide>
      <div className="report">
        <header>
          <h2>Flight {flight.id} report</h2>
          <p className="secondary">{fmtTime(flight.started_at)} → {fmtTime(flight.ended_at)} ·
            {flight.result === "lost" ? " ended: link lost" : " landed"}</p>
        </header>
        <div className="rep-grid">
          {fig("Flight time", fmtDur(s.duration_s))}
          {fig("Distance", `${((s.distance_m || 0) / 1000).toFixed(2)} km`, plan.distance_m ? `planned ${(plan.distance_m / 1000).toFixed(2)} km` : null)}
          {fig("Stops", `${s.stops_reached ?? 0} / ${s.stops_planned ?? 0}`, s.stops_missed?.length ? `missed ${s.stops_missed.join(", ")}` : "all reached")}
          {fig("Battery", s.battery_start != null ? `${Math.round(s.battery_start)}% → ${Math.round(s.battery_end)}%` : "—",
            plan.energy_wh ? `plan ${plan.energy_wh} Wh (${plan.battery_pct}%)` : null)}
          {fig("Photos", s.photos ?? 0, `${s.detections ?? 0} with a classification`)}
          {fig("Max wind", s.max_wind ? `${s.max_wind} m/s` : "—", s.max_wind > 6 ? "above the 6 m/s limit" : null)}
          {fig("Max altitude", `${s.max_alt_m ?? 0} m`)}
          {fig("Link gaps", s.link_gaps ?? 0, s.link_gaps ? "telemetry gaps over 3 s" : "none")}
        </div>
        <h3>Time by phase</h3>
        <div className="rep-phases">
          {Object.entries(s.phase_s || {}).map(([k, v]) => (
            <span key={k} style={{ flexGrow: v / phaseTotal, background: PHASE_COLOR[k] || "#555" }} title={`${k}: ${fmtDur(v)}`} />
          ))}
        </div>
        <div className="rep-phase-keys">
          {Object.entries(s.phase_s || {}).map(([k, v]) => <span key={k}><i style={{ background: PHASE_COLOR[k] || "#555" }} />{k} {fmtDur(v)}</span>)}
        </div>
        <h3>Found on this flight</h3>
        <div className="rep-found">
          <div><b>Tender nuts</b>{(s.tender_found || []).length ? s.tender_found.map((id) => <button key={id} className="pill" onClick={() => { onSelect(id, true); onClose(); }}>{id}</button>) : <span className="secondary"> none</span>}</div>
          <div><b>New targets</b>{(s.targets_flagged || []).length ? s.targets_flagged.map((id) => <button key={id} className="pill" onClick={() => { onSelect(id, true); onClose(); }}>{id}</button>) : <span className="secondary"> none</span>}</div>
        </div>
        <div className="rep-actions">
          <button className="btn btn-sm" onClick={() => { onReplay(flight.id); onClose(); }}>Replay flight</button>
          <button className="link" onClick={() => window.print()}>Print / save PDF</button>
        </div>
      </div>
    </Modal>
  );
}
