import { useEffect, useMemo } from "react";
import L from "leaflet";
import { MapContainer, Marker, Polygon, Polyline, ScaleControl, Tooltip, ZoomControl, useMap } from "react-leaflet";
import { colorOf, photoState } from "./theme.js";

// A palm canopy seen from above: a plain disc. Dimmed when it's outside the
// photo pattern; a one-shot ring when it has just been photographed.
const iconCache = new Map();
function palmIcon(color, { selected, dim, flash }) {
  const key = `${color}|${selected}|${dim}|${flash}`;
  if (!iconCache.has(key)) {
    const size = dim ? 10 : selected ? 22 : 16;
    iconCache.set(key, L.divIcon({
      className: "palm" + (selected ? " selected" : "") + (dim ? " dim" : "") + (flash ? " flash" : ""),
      html: `<span style="--c:${color};width:${size}px;height:${size}px"></span>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    }));
  }
  return iconCache.get(key);
}

const droneIcon = (heading, connected) => L.divIcon({
  className: "drone" + (connected ? "" : " stale"),
  iconSize: [40, 40],
  iconAnchor: [20, 20],
  html: `<div class="drone-disc"><svg viewBox="-12 -12 24 24" width="22" height="22" style="transform:rotate(${heading || 0}deg)">
    <path d="M0,-9 L7,8 L0,4 L-7,8 Z" fill="currentColor" stroke-linejoin="round"/></svg></div>`,
});

const dockIcon = L.divIcon({
  className: "dock", iconSize: [64, 40], iconAnchor: [32, 9],
  html: '<span class="dock-pad"></span><span class="dock-label">Dock</span>',
});

function FitField({ bounds }) {
  const map = useMap();
  useEffect(() => {
    if (bounds) map.fitBounds(bounds, { paddingTopLeft: [40, 110], paddingBottomRight: [390, 30] });
  }, [bounds, map]);
  return null;
}

function FlyTo({ target }) {
  const map = useMap();
  useEffect(() => {
    if (target) map.flyTo(target.latlng, Math.max(map.getZoom(), 19.5), { duration: 0.6 });
  }, [target, map]);
  return null;
}

export default function FarmMap({ info, trees, colorBy, pattern, selectedId, onSelect, telemetry, trail, focus, flashId }) {
  const bounds = useMemo(() => info && L.latLngBounds([...info.field, info.dock]), [info]);
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
          <Polygon positions={info.field} interactive={false}
            pathOptions={{ color: "rgba(255,255,255,0.10)", weight: 1, fillColor: "#16211b", fillOpacity: 1 }} />
          <Polyline positions={[info.dock, [info.field[0][0], info.dock[1]]]} interactive={false}
            pathOptions={{ color: "rgba(255,255,255,0.14)", weight: 1, dashArray: "1 5", lineCap: "round" }} />
          <Marker position={info.dock} icon={dockIcon} interactive={false} />
        </>
      )}
      {trees.map((t) => {
        const selected = t.id === selectedId;
        const dim = colorBy === "photos" && photoState(t, pattern) === "skip";
        return (
          <Marker key={t.id} position={[t.lat, t.lon]} zIndexOffset={selected ? 1000 : 0}
            icon={palmIcon(colorOf(t, colorBy, pattern), { selected, dim, flash: t.id === flashId })}
            eventHandlers={{ click: () => onSelect(t.id) }}>
            <Tooltip direction="top" offset={[0, -10]} className="tip">{t.id}</Tooltip>
          </Marker>
        );
      })}
      {trail.length > 1 && (
        <Polyline positions={trail} interactive={false}
          pathOptions={{ color: "#e3a06a", weight: 3, opacity: 0.9, lineCap: "round", lineJoin: "round" }} />
      )}
      {hasDrone && (
        <Marker position={[telemetry.lat, telemetry.lon]} icon={droneIcon(telemetry.heading, telemetry.connected)}
          zIndexOffset={2000} interactive={false} />
      )}
    </MapContainer>
  );
}
