// REST helpers, the live WebSocket (telemetry + tree updates), and frame grabs
// from the drone camera for automatic tree photos.
import { CARD_MODEL, readCard } from "./cardReader.js";
export async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export function connectLive(onMessage, onLink) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  let ws = null, stopped = false, retry = null;
  const open = () => {
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => onLink(true);
    ws.onmessage = (e) => onMessage(JSON.parse(e.data));
    ws.onclose = () => {
      onLink(false);
      if (!stopped) retry = setTimeout(open, 2000);
    };
  };
  open();
  return () => { stopped = true; clearTimeout(retry); ws && ws.close(); };
}

// The camera card registers its <video> (phone browser, WebRTC) or <img>
// (MJPEG from the IP Webcam app / ESP32-CAM, same-origin via /api/camera/stream);
// a capture request grabs one frame from it.
export const camera = { el: null, onShutter: null };

export async function captureTree(treeId, captureId) {
  const v = camera.el;
  const w = v && (v.videoWidth || v.naturalWidth), h = v && (v.videoHeight || v.naturalHeight);
  if (!v || !w || (v.tagName === "VIDEO" && !v.srcObject)) return false;   // no live feed here
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  c.getContext("2d").drawImage(v, 0, 0);
  const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.9));
  if (!blob) return false;
  // stand-in classifier: read a colour card in view (green = tender, ...);
  // no card in view -> logged as a plain photo
  const card = readCard(c);
  const q = card ? `&label=${card.label}&confidence=${card.confidence}&model=${CARD_MODEL}` : "";
  const res = await fetch(`/api/trees/${treeId}/photo?capture_id=${captureId}${q}`, {
    method: "POST", headers: { "Content-Type": "image/jpeg" }, body: blob,
  });
  if (res.ok && camera.onShutter) camera.onShutter(treeId, card);
  return res.ok;
}
