import { useCallback, useEffect, useMemo, useState } from "react";
import FarmMap from "./FarmMap.jsx";
import { Legend, Rail, SidePanel, TelemetryCard, TreeCard, VideoCard } from "./panels.jsx";
import { api, connectLive } from "./live.js";

const TRAIL_MAX = 3000;   // points; at 5 Hz that is the last 10 minutes of flight

export default function App() {
  const [info, setInfo] = useState(null);
  const [treeMap, setTreeMap] = useState({});
  const [tel, setTel] = useState({ connected: false });
  const [trail, setTrail] = useState([]);
  const [live, setLive] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [focus, setFocus] = useState(null);
  const [panel, setPanel] = useState("overview");
  const [filter, setFilter] = useState({ field: null, value: null, q: "" });
  const [colorBy, setColorBy] = useState("status");
  const [video, setVideo] = useState(true);

  const loadTrees = useCallback(
    (list) => setTreeMap(Object.fromEntries(list.map((t) => [t.id, t]))), []);

  useEffect(() => {
    api("/api/layout").then(setInfo).catch(() => {});
    api("/api/trees").then(loadTrees).catch(() => {});
    return connectLive((msg) => {
      if (msg.type === "telemetry") {
        setTel(msg);
        if (msg.connected && msg.lat != null) {
          setTrail((tr) => {
            const last = tr[tr.length - 1];
            if (last && last[0] === msg.lat && last[1] === msg.lon) return tr;
            const next = [...tr, [msg.lat, msg.lon]];
            return next.length > TRAIL_MAX ? next.slice(-TRAIL_MAX) : next;
          });
        }
      } else if (msg.type === "tree") {
        setTreeMap((m) => ({ ...m, [msg.tree.id]: msg.tree }));
      } else if (msg.type === "trees") {
        loadTrees(msg.trees);
      }
    }, (up) => {
      setLive(up);
      if (up) api("/api/trees").then(loadTrees).catch(() => {});   // resync after a reconnect
    });
  }, [loadTrees]);

  const trees = useMemo(() => Object.values(treeMap).sort((a, b) => a.row - b.row || a.col - b.col), [treeMap]);
  const selected = selectedId && treeMap[selectedId];

  const select = (id, fly) => {
    setSelectedId(id);
    if (fly && treeMap[id]) setFocus({ latlng: [treeMap[id].lat, treeMap[id].lon] });
  };
  const locate = () => tel.lat != null && setFocus({ latlng: [tel.lat, tel.lon] });

  return (
    <div className="app">
      <Rail panel={panel} setPanel={setPanel} video={video} setVideo={setVideo}
        onLocate={locate} canLocate={tel.lat != null} />
      <SidePanel panel={panel} setPanel={setPanel} info={info} trees={trees} selectedId={selectedId}
        onSelect={select} filter={filter} setFilter={setFilter} />
      <main className="stage">
        <FarmMap info={info} trees={trees} colorBy={colorBy} selectedId={selectedId} onSelect={(id) => select(id)}
          telemetry={tel} trail={trail} focus={focus} />
        <TelemetryCard tel={tel} live={live} />
        <Legend colorBy={colorBy} setColorBy={setColorBy} />
        {selected && <TreeCard id={selectedId} tree={selected} compact={video} onClose={() => setSelectedId(null)} />}
        {video && <VideoCard />}
      </main>
    </div>
  );
}
