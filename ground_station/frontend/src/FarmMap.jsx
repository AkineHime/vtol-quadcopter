import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import { MapContainer, Marker, Polygon, Polyline, ScaleControl, Tooltip, ZoomControl, useMap } from "react-leaflet";
import { colorOf, fmtPct, HEALTH, MATURITY, photoState, PREDICT_MIN, STATUS } from "./theme.js";

// A palm canopy seen from above, as one layered glyph: the disc's fill is the
// lens colour (maturity by default), a ring shows the harvest status, a red
// notch a health problem. Dimmed outside the photo pattern; a one-shot ring
// when just photographed; a soft halo when predicted tender (Prediction lens).
const iconCache = new Map();
function palmIcon(color, { selected, dim, flash, predicted, ring, notch, faded }) {
  const key = `${color}|${selected}|${dim}|${flash}|${predicted}|${ring}|${notch}|${faded}`;
  if (!iconCache.has(key)) {
    const size = dim ? 10 : selected ? 22 : 16;
    const ringCss = ring ? `;box-shadow:0 0 0 2px #0f1612,0 0 0 4px ${ring}` : "";
    iconCache.set(key, L.divIcon({
      className: "palm" + (selected ? " selected" : "") + (dim ? " dim" : "") + (flash ? " flash" : "")
        + (predicted ? " predicted" : "") + (faded ? " faded" : ""),
      html: `<span style="--c:${color};width:${size}px;height:${size}px${ringCss}"></span>`
        + (notch ? `<i class="notch" style="background:${notch}"></i>` : ""),
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    }));
  }
  return iconCache.get(key);
}

// hover peek: the palm at a glance without opening the card
function Peek({ t }) {
  const m = MATURITY[t.maturity] || MATURITY.unknown;
  return (
    <div className="peek">
      <div className="peek-head"><b>{t.id}</b><span className="peek-status" style={{ "--c": STATUS[t.status]?.color }}>{STATUS[t.status]?.label}</span></div>
      <div className="peek-row"><i style={{ background: m.color }} />{m.label}{t.confidence != null && t.label ? ` · ${fmtPct(t.confidence)}` : ""}</div>
      <div className="peek-row"><i style={{ background: (HEALTH[t.health] || HEALTH.healthy).color }} />{(HEALTH[t.health] || HEALTH.healthy).label}</div>
      <div className="peek-bar"><span style={{ width: `${(t.ripe_score ?? 0) * 100}%` }} /></div>
      <div className="peek-row dim">Tender chance {fmtPct(t.ripe_score)}</div>
    </div>
  );
}

// row / column numbers along the field edges (P0612 = row 06, column 12)
const marginIcon = (text, cls) => cachedIcon(`margin|${cls}|${text}`, () => L.divIcon({
  className: "margin-label " + cls, iconSize: [0, 0], html: `<span>${text}</span>`,
}));

// numbered stop of the planned mission + a status chip (id, kind, score)
// (chips for targets and the selected palm; the others show theirs on hover)
// Icons are cached by their content: react-leaflet replaces a marker's DOM
// whenever it gets a new icon object, and the map re-renders on every
// telemetry message (5 Hz), so fresh icons made the pins blink.
function cachedIcon(key, make) {
  if (!iconCache.has(key)) iconCache.set(key, make());
  return iconCache.get(key);
}

const stopIcon = (s, show, open) => cachedIcon(`stop|${s.tree}|${s.order}|${s.kind}|${s.score}|${show}|${open}`, () => L.divIcon({
  className: "stop-pin " + s.kind,
  iconSize: [0, 0],
  html: `<span class="stop-n">${s.order ?? ""}</span>` + (show
    ? `<span class="chip${open ? "" : " soft"}"><b>${s.tree}</b><i>${s.kind === "target" ? "Target" : "Predicted"} · ${Math.round(s.score * 100)}%</i></span>`
    : ""),
}));

const routeChip = (plan) => cachedIcon(`route|${plan.distance_m}|${plan.energy_wh}|${plan.battery_pct}`, () => L.divIcon({
  className: "route-chip", iconSize: [0, 0],
  html: `<span>Next mission</span><b>${(plan.distance_m / 1000).toFixed(2)} km · ${plan.energy_wh} Wh · ${plan.battery_pct}%</b>`,
}));

const dockIcon = L.divIcon({
  className: "dock", iconSize: [64, 40], iconAnchor: [32, 9],
  html: '<span class="dock-pad"></span><span class="dock-label">Dock</span>',
});

function FitField({ bounds, fitKey }) {
  const map = useMap();
  useEffect(() => {
    if (!bounds) return;
    map.invalidateSize();
    map.fitBounds(bounds, { paddingTopLeft: [40, 100], paddingBottomRight: [380, 40], animate: fitKey > 0 });
  }, [bounds, fitKey, map]);
  return null;
}

function FlyTo({ target }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo(target.latlng, Math.max(map.getZoom(), 19.5), { duration: 0.6 });
  }, [target, map]);
  return null;
}

// The drone glides between 5 Hz telemetry fixes instead of jumping: an
// imperative Leaflet marker eased toward the latest fix every animation frame.
function Drone({ telemetry }) {
  const map = useMap();
  const ref = useRef(null);
  useEffect(() => {
    const m = L.marker([0, 0], {
      interactive: false, zIndexOffset: 2000,
      icon: L.divIcon({
        className: "drone", iconSize: [40, 40], iconAnchor: [20, 20],
        html: `<div class="drone-disc"><svg viewBox="-12 -12 24 24" width="22" height="22">
          <path d="M0,-9 L7,8 L0,4 L-7,8 Z" fill="currentColor" stroke-linejoin="round"/></svg></div>`,
      }),
    });
    const st = { m, cur: null, goal: null, hdg: 0, goalHdg: 0, raf: 0, added: false };
    const tick = () => {
      if (st.goal) {
        if (!st.cur) st.cur = st.goal.slice();
        st.cur[0] += (st.goal[0] - st.cur[0]) * 0.18;
        st.cur[1] += (st.goal[1] - st.cur[1]) * 0.18;
        st.hdg += (((st.goalHdg - st.hdg + 540) % 360) - 180) * 0.18;
        m.setLatLng(st.cur);
        if (!st.added) { m.addTo(map); st.added = true; }
        const svg = m.getElement()?.querySelector("svg");
        if (svg) svg.style.transform = `rotate(${st.hdg}deg)`;
      }
      st.raf = requestAnimationFrame(tick);
    };
    st.raf = requestAnimationFrame(tick);
    ref.current = st;
    return () => { cancelAnimationFrame(st.raf); m.remove(); };
  }, [map]);
  useEffect(() => {
    const st = ref.current;
    if (!st || telemetry?.lat == null) return;
    st.goal = [telemetry.lat, telemetry.lon];
    st.goalHdg = telemetry.heading || 0;
    st.m.getElement()?.classList.toggle("stale", !telemetry.connected);
  }, [telemetry]);
  return null;
}

export default function FarmMap({ info, trees, colorBy, pattern, selectedId, onSelect, telemetry, trail, focus,
  flashId, plan, mission, layers, fitKey }) {
  const planned = useMemo(() => plan?.route?.map((p) => [p.lat, p.lon]) || [], [plan]);
  // frame the field, the dock and the whole planned route (lanes run past the
  // field edges), so the drone stays in view; refit only when that extent
  // changes, not on every database edit
  const extent = info ? [...info.field, info.dock, ...planned] : [];
  const extentKey = extent.length ? [Math.min(...extent.map((p) => p[0])), Math.max(...extent.map((p) => p[0])),
    Math.min(...extent.map((p) => p[1])), Math.max(...extent.map((p) => p[1]))].map((v) => v.toFixed(5)).join() : "";
  const bounds = useMemo(() => (extent.length ? L.latLngBounds(extent) : null), [extentKey]);
  const simRoute = useMemo(() => mission?.route?.map((p) => [p.lat, p.lon]) || [], [mission]);
  const stops = plan?.stops || [];
  // the route chip sits at the far end of the first lane, out of the way of the palms
  const chipAt = planned.length > 2 ? planned[1] : null;
  const margins = useMemo(() => {
    if (!trees.length) return [];
    const dLat = 5.5 / 111320, dLon = 5.5 / (111320 * Math.cos((trees[0].lat * Math.PI) / 180));
    return [
      ...trees.filter((t) => t.col === 0).map((t) => ({ key: "r" + t.row, pos: [t.lat, t.lon - dLon], text: String(t.row).padStart(2, "0"), cls: "row" })),
      ...trees.filter((t) => t.row === 0).map((t) => ({ key: "c" + t.col, pos: [t.lat - dLat, t.lon], text: String(t.col).padStart(2, "0"), cls: "col" })),
    ];
  }, [trees.length > 0]);    // the grid never moves

  return (
    <MapContainer className="map" center={[10.6611, 77.0048]} zoom={19} minZoom={16} maxZoom={22}
      zoomSnap={0.25} zoomControl={false} attributionControl={false}>
      <FitField bounds={bounds} fitKey={fitKey} />
      <FlyTo target={focus} />
      <ZoomControl position="bottomleft" />
      <ScaleControl position="bottomleft" imperial={false} />
      {info && (
        <>
          <Polygon positions={info.field} interactive={false}
            pathOptions={{ color: "rgba(255,255,255,0.12)", weight: 1, fillColor: "#131c17", fillOpacity: 1, className: "field" }} />
          <Polyline positions={[info.dock, [info.field[0][0], info.dock[1]]]} interactive={false}
            pathOptions={{ color: "rgba(255,255,255,0.14)", weight: 1, dashArray: "1 5", lineCap: "round" }} />
          <Marker position={info.dock} icon={dockIcon} interactive={false} />
        </>
      )}
      {layers.sim && simRoute.length > 1 && (
        <Polyline positions={simRoute} interactive={false}
          pathOptions={{ color: "rgba(255,255,255,0.32)", weight: 1.5, dashArray: "2 6", lineCap: "round", className: "route-sim" }} />
      )}
      {layers.plan && planned.length > 1 && (
        <>
          <Polyline positions={planned} interactive={false}
            pathOptions={{ color: "#ffcf99", weight: 6, opacity: 0.12, lineCap: "round", lineJoin: "round" }} />
          <Polyline positions={planned} interactive={false}
            pathOptions={{ color: "#ffcf99", weight: 2, dashArray: "6 8", lineCap: "round", lineJoin: "round", className: "route-plan" }} />
        </>
      )}
      {margins.map((m) => <Marker key={m.key} position={m.pos} icon={marginIcon(m.text, m.cls)} interactive={false} />)}
      {trees.map((t) => {
        const selected = t.id === selectedId;
        const photos = colorBy === "photos";
        const dim = photos && photoState(t, pattern) === "skip";
        const predicted = colorBy === "prediction" && t.status === "unscouted" && (t.ripe_score ?? 0) >= PREDICT_MIN;
        const ring = photos ? null : STATUS[t.status]?.ring;
        const notch = photos || colorBy === "health" || t.health === "healthy" ? null : HEALTH[t.health]?.color;
        return (
          <Marker key={t.id} position={[t.lat, t.lon]} zIndexOffset={selected ? 1000 : 0}
            icon={palmIcon(colorOf(t, colorBy, pattern), { selected, dim, flash: t.id === flashId, predicted, ring, notch,
              faded: !photos && t.status === "harvested" })}
            eventHandlers={{ click: () => onSelect(t.id) }}>
            <Tooltip direction="top" offset={[0, -12]} className="tip peek-tip"><Peek t={t} /></Tooltip>
          </Marker>
        );
      })}
      {layers.plan && stops.map((s) => (
        <Marker key={"stop-" + s.tree} position={[s.lat, s.lon]} zIndexOffset={1500}
          icon={stopIcon(s, layers.chips, s.kind === "target" || s.tree === selectedId)}
          eventHandlers={{ click: () => onSelect(s.tree) }} />
      ))}
      {layers.plan && chipAt && plan && <Marker position={chipAt} icon={routeChip(plan)} interactive={false} zIndexOffset={1800} />}
      {layers.trail && trail.length > 1 && (
        <Polyline positions={trail} interactive={false}
          pathOptions={{ color: "#e3a06a", weight: 3, opacity: 0.9, lineCap: "round", lineJoin: "round" }} />
      )}
      <Drone telemetry={telemetry} />
    </MapContainer>
  );
}
