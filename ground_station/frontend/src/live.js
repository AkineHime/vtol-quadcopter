// REST helpers and the live WebSocket (telemetry + tree updates).
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
