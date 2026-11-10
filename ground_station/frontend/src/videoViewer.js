// WebRTC viewer: receives the phone camera via the /ws/signal relay.
// No React here so it can be tested on its own. Returns a stop() function.
export function startViewer(onStream, onStatus) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  let ws = null, pc = null, stopped = false, retry = null;

  const closePeer = () => { if (pc) { pc.close(); pc = null; } onStream(null); };

  function connect() {
    ws = new WebSocket(`${proto}://${location.host}/ws/signal?role=viewer`);
    ws.onmessage = async (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "camera-on") onStatus("waiting");
      else if (msg.type === "camera-off") { closePeer(); onStatus("off"); }
      else if (msg.type === "offer") {
        closePeer();
        pc = new RTCPeerConnection({ iceServers: [] });
        pc.ontrack = (e) => onStream(e.streams[0] || new MediaStream([e.track]));
        pc.onicecandidate = (e) => e.candidate && ws.send(JSON.stringify({ type: "ice", candidate: e.candidate }));
        pc.onconnectionstatechange = () => {
          const s = pc && pc.connectionState;
          if (s === "connected") onStatus("live");
          else if (s === "failed" || s === "disconnected") onStatus("waiting");
        };
        await pc.setRemoteDescription(msg.sdp);
        await pc.setLocalDescription(await pc.createAnswer());
        ws.send(JSON.stringify({ type: "answer", sdp: pc.localDescription }));
      } else if (msg.type === "ice" && pc && msg.candidate) {
        try { await pc.addIceCandidate(msg.candidate); } catch (e) { /* stale candidate */ }
      }
    };
    ws.onclose = () => {
      closePeer();
      onStatus("off");
      if (!stopped) retry = setTimeout(connect, 2000);
    };
  }

  connect();
  return () => { stopped = true; clearTimeout(retry); if (ws) ws.close(); closePeer(); };
}
