import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import FarmMap from "./FarmMap.jsx";
import { Legend, MapBar, MissionStrip, Rail, SidePanel, TelemetryCard, TreeCard, VideoCard } from "./panels.jsx";
import { api, captureTree, connectLive } from "./live.js";

const TRAIL_MAX = 3000;   // points; at 5 Hz that is the last 10 minutes of flight
const HIST_MAX = 150;     // altitude samples for the HUD sparkline (~30 s)

export default function App() {
  const [info, setInfo] = useState(null);
  const [treeMap, setTreeMap] = useState({});
  const [pattern, setPatternState] = useState({ every: 1, since: "" });
  const [tel, setTel] = useState({ connected: false });
  const [altHist, setAltHist] = useState([]);
  const [trail, setTrail] = useState([]);
  const [live, setLive] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [focus, setFocus] = useState(null);
  const [flashId, setFlashId] = useState(null);
  const [panel, setPanel] = useState("overview");
  const [filter, setFilter] = useState({ field: null, value: null, q: "" });
  const [colorBy, setColorBy] = useState("harvest");
  const [video, setVideo] = useState(true);
  const [plan, setPlan] = useState(null);
  const [mission, setMission] = useState(null);
  const [layers, setLayers] = useState({ plan: true, sim: true, trail: true, chips: true });
  const [fitKey, setFitKey] = useState(0);
  const photoSeen = useRef({});          // tree id -> last_photo already shown
  const homeRef = useRef(null);          // dock lat/lon, to drop bogus fixes from the trail

  const loadTrees = useCallback((list) => {
    list.forEach((t) => { photoSeen.current[t.id] = t.last_photo; });
    setTreeMap(Object.fromEntries(list.map((t) => [t.id, t])));
  }, []);

  useEffect(() => {
    let flashTimer = null;
    api("/api/layout").then((i) => { homeRef.current = i.layout.home; setInfo(i); }).catch(() => {});
    api("/api/trees").then(loadTrees).catch(() => {});
    const stop = connectLive((msg) => {
      if (msg.type === "telemetry") {
        setTel(msg);
        if (msg.connected && msg.alt != null) {
          setAltHist((h) => (h.length >= HIST_MAX ? [...h.slice(1), msg.alt] : [...h, msg.alt]));
        }
        // SITL reports its default location for a moment before it moves to the
        // farm: keep only fixes within ~2 km of the dock so the trail starts clean
        const home = homeRef.current;
        const near = home && Math.abs(msg.lat - home.lat) < 0.02 && Math.abs(msg.lon - home.lon) < 0.02;
        if (msg.connected && msg.lat != null && near) {
          setTrail((tr) => {
            const last = tr[tr.length - 1];
            if (last && last[0] === msg.lat && last[1] === msg.lon) return tr;
            const next = [...tr, [msg.lat, msg.lon, msg.alt || 0]];
            return next.length > TRAIL_MAX ? next.slice(-TRAIL_MAX) : next;
          });
        }
      } else if (msg.type === "tree") {
        const { id, last_photo } = msg.tree;
        if (last_photo && last_photo !== photoSeen.current[id]) {
          photoSeen.current[id] = last_photo;
          setFlashId(id);                                  // ring pulse on the palm just photographed
          clearTimeout(flashTimer);
          flashTimer = setTimeout(() => setFlashId(null), 1600);
        }
        setTreeMap((m) => ({ ...m, [id]: msg.tree }));
      } else if (msg.type === "trees") {
        loadTrees(msg.trees);
      } else if (msg.type === "pattern") {
        setPatternState(msg.pattern);
      } else if (msg.type === "plan") {
        setPlan(msg.plan);
      } else if (msg.type === "mission") {
        setMission(msg.mission);
      } else if (msg.type === "capture") {
        captureTree(msg.tree_id, msg.capture_id).catch(() => {});
      }
    }, (up) => {
      setLive(up);
      if (up) api("/api/trees").then(loadTrees).catch(() => {});   // resync after a reconnect
    });
    return () => { stop(); clearTimeout(flashTimer); };
  }, [loadTrees]);

  const trees = useMemo(() => Object.values(treeMap).sort((a, b) => a.row - b.row || a.col - b.col), [treeMap]);
  const trail2d = useMemo(() => trail.map((p) => [p[0], p[1]]), [trail]);
  const selected = selectedId && treeMap[selectedId];

  const select = (id, fly) => {
    setSelectedId(id);
    if (fly && treeMap[id]) setFocus({ latlng: [treeMap[id].lat, treeMap[id].lon] });
  };
  const locate = () => tel.lat != null && setFocus({ latlng: [tel.lat, tel.lon] });
  const setPattern = (every) => {
    setColorBy("photos");
    api("/api/pattern", { every }).then(setPatternState).catch(() => {});
  };

  return (
    <div className="app">
      <Rail panel={panel} setPanel={setPanel} video={video} setVideo={setVideo}
        onLocate={locate} canLocate={tel.lat != null} />
      <SidePanel panel={panel} setPanel={setPanel} info={info} trees={trees} pattern={pattern} setPattern={setPattern}
        selectedId={selectedId} onSelect={select} filter={filter} setFilter={setFilter} plan={plan} mission={mission}
        setColorBy={setColorBy} />
      <main className="stage">
        <FarmMap info={info} trees={trees} colorBy={colorBy} pattern={pattern} selectedId={selectedId}
          onSelect={(id) => select(id)} telemetry={tel} trail={trail2d} focus={focus} flashId={flashId}
          plan={plan} mission={mission} layers={layers} fitKey={fitKey} />
        <TelemetryCard tel={tel} live={live} altHist={altHist} />
        <MapBar layers={layers} setLayers={setLayers} onFit={() => setFitKey((k) => k + 1)} />
        <Legend colorBy={colorBy} setColorBy={setColorBy} />
        <MissionStrip mission={mission} plan={plan} tel={tel} onSelect={select} />
        {selected && <TreeCard id={selectedId} tree={selected} pattern={pattern} compact={video} plan={plan}
          onClose={() => setSelectedId(null)} />}
        {video && <VideoCard />}
      </main>
    </div>
  );
}
