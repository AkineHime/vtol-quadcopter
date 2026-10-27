// REST helpers, the live WebSocket (telemetry + tree updates), and frame grabs
// from the drone camera for automatic tree photos.
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

// The video panel registers its <video>; a capture request grabs one frame.
export const camera = { video: null, onShutter: null };

export async function captureTree(treeId, captureId) {
  const v = camera.video;
  if (!v || !v.srcObject || !v.videoWidth) return false;       // no live feed here
  const c = document.createElement("canvas");
  c.width = v.videoWidth;
  c.height = v.videoHeight;
  c.getContext("2d").drawImage(v, 0, 0);
  const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.9));
  if (!blob) return false;
  const res = await fetch(`/api/trees/${treeId}/photo?capture_id=${captureId}`, {
    method: "POST", headers: { "Content-Type": "image/jpeg" }, body: blob,
  });
  if (res.ok && camera.onShutter) camera.onShutter(treeId);
  return res.ok;
}
