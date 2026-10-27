import { useEffect, useMemo } from "react";
import L from "leaflet";
import { MapContainer, Marker, Polygon, Polyline, Rectangle, ScaleControl, Tooltip, ZoomControl, useMap } from "react-leaflet";
import { colorOf } from "./theme.js";

// A palm seen from above: a ring of fronds around a crown.
const palmSvg = (color, selected) => `
<svg viewBox="-16 -16 32 32" width="30" height="30" xmlns="http://www.w3.org/2000/svg">
  ${selected ? '<circle r="15" fill="none" stroke="#ffffff" stroke-width="2"/>' : ""}
  <g fill="${color}" fill-opacity="0.92" stroke="#0b1912" stroke-width="0.8">
    ${[0, 45, 90, 135, 180, 225, 270, 315].map((a) =>
      `<ellipse cx="0" cy="-7" rx="3" ry="6.5" transform="rotate(${a})"/>`).join("")}
  </g>
  <circle r="3.2" fill="#0b1912"/><circle r="1.8" fill="${color}"/>
</svg>`;

const iconCache = new Map();
function palmIcon(color, selected) {
  const key = color + selected;
  if (!iconCache.has(key)) {
    iconCache.set(key, L.divIcon({ className: "palm", html: palmSvg(color, selected), iconSize: [30, 30], iconAnchor: [15, 15] }));
  }
  return iconCache.get(key);
}

const droneIcon = (heading, connected) => L.divIcon({
  className: "drone",
  iconSize: [44, 44],
  iconAnchor: [22, 22],
  html: `<svg viewBox="-22 -22 44 44" width="44" height="44" style="transform: rotate(${heading || 0}deg)">
    <circle r="20" fill="${connected ? "rgba(212,137,79,0.18)" : "rgba(140,140,140,0.18)"}"/>
    <path d="M0,-17 L11,13 L0,6 L-11,13 Z" fill="${connected ? "#d4894f" : "#8a948e"}" stroke="#fff4ea" stroke-width="2" stroke-linejoin="round"/>
  </svg>`,
});

const dockIcon = L.divIcon({ className: "dock-label", html: "DOCK", iconSize: [44, 16], iconAnchor: [22, -10] });

function FitField({ bounds }) {
  const map = useMap();
  useEffect(() => { if (bounds) map.fitBounds(bounds, { paddingTopLeft: [40, 120], paddingBottomRight: [410, 30] }); }, [bounds, map]);
  return null;
}

function FlyTo({ target }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo(target.latlng, Math.max(map.getZoom(), 19.5), { duration: 0.6 });
  }, [target, map]);
  return null;
}

export default function FarmMap({ info, trees, colorBy, selectedId, onSelect, telemetry, trail, focus }) {
  const bounds = useMemo(() => info && L.latLngBounds([...info.field, info.dock]), [info]);

  // one faint guide line per planting row, like a drawn plan
  const rowLines = useMemo(() => {
    const rows = new Map();
    trees.forEach((t) => { if (!rows.has(t.row)) rows.set(t.row, []); rows.get(t.row).push(t); });
    return [...rows.values()].map((r) => {
      r.sort((a, b) => a.col - b.col);
      return [[r[0].lat, r[0].lon], [r[r.length - 1].lat, r[r.length - 1].lon]];
    });
  }, [trees]);

  const dockPad = useMemo(() => {
    if (!info) return null;
    const [lat, lon] = info.dock, d = 2 / 111320, dl = d / Math.cos((lat * Math.PI) / 180);
    return [[lat - d, lon - dl], [lat + d, lon + dl]];
  }, [info]);

  const hasDrone = telemetry && telemetry.lat != null;

  return (
    <MapContainer className="map" center={[10.6611, 77.0048]} zoom={19} minZoom={16} maxZoom={22}
      zoomSnap={0.25} zoomControl={false} attributionControl={false}>
      <FitField bounds={bounds} />
      <FlyTo target={focus} />
      <ZoomControl position="bottomleft" />
      <ScaleControl position="bottomleft" imperial={false} />
      {info && (
        <>
          <Polygon positions={info.field} pathOptions={{ color: "#3b5e48", weight: 1.5, fillColor: "#183324", fillOpacity: 1, dashArray: "6 6" }} />
          {rowLines.map((p, i) => (
            <Polyline key={i} positions={p} pathOptions={{ color: "#244533", weight: 1 }} interactive={false} />
          ))}
          <Polyline positions={[info.dock, [info.field[0][0], info.dock[1]]]} pathOptions={{ color: "#3b5e48", weight: 1, dashArray: "2 6" }} interactive={false} />
          <Rectangle bounds={dockPad} pathOptions={{ color: "#d4894f", weight: 2, fillColor: "#d4894f", fillOpacity: 0.25 }} />
          <Marker position={info.dock} icon={dockIcon} interactive={false} />
        </>
      )}
      {trees.map((t) => (
        <Marker key={t.id} position={[t.lat, t.lon]} icon={palmIcon(colorOf(t, colorBy), t.id === selectedId)}
          zIndexOffset={t.id === selectedId ? 1000 : 0} eventHandlers={{ click: () => onSelect(t.id) }}>
          <Tooltip direction="top" offset={[0, -12]} className="tip">{t.id}</Tooltip>
        </Marker>
      ))}
      {trail.length > 1 && (
        <Polyline positions={trail} pathOptions={{ color: "#d4894f", weight: 2.5, opacity: 0.85 }} interactive={false} />
      )}
      {hasDrone && (
        <Marker position={[telemetry.lat, telemetry.lon]} icon={droneIcon(telemetry.heading, telemetry.connected)}
          zIndexOffset={2000} interactive={false} />
      )}
    </MapContainer>
  );
}
