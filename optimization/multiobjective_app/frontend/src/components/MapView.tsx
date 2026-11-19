import { useMemo } from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { Leg, Network, Solution } from "../types";
import { RAIL_COLOR, ROAD_COLOR, fmtTon } from "../format";

interface Props {
  network: Network;
  solution: Solution | null;
}

const PORT_COLOR = "#2a78d6";
const DC_COLOR = "#52514e";
const TERMINAL_COLOR = "#6250d6";

/** 地図に描く区間と、その区間を通る輸送量の合計 */
interface DrawnLeg {
  leg: Leg;
  flow: number;
  details: string[];
}

export default function MapView({ network, solution }: Props) {
  const names = useMemo(() => {
    const m = new Map<string, string>();
    network.ports.forEach((p) => m.set(p.ID, p.name));
    network.distribution_centers.forEach((d) => m.set(d.ID, `${d.ID} ${d.name}`));
    network.rail_terminals.forEach((r) => m.set(r.ID, `${r.name}（鉄道ターミナル）`));
    return m;
  }, [network]);

  // 輸送フローを区間ごとに集計する
  // 道路のみ: 港 → 配送センター（道路）
  // 鉄道＋道路: 港 → 最寄り鉄道ターミナル（鉄道）＋ 鉄道ターミナル → 配送センター（道路）
  const drawn = useMemo(() => {
    if (!solution) return [];
    const legByKey = new Map(network.legs.map((l) => [`${l.from}|${l.to}|${l.mode}`, l]));
    const dcById = new Map(network.distribution_centers.map((d) => [d.ID, d]));
    const acc = new Map<string, DrawnLeg>();
    const add = (key: string, flow: number, detail: string) => {
      const leg = legByKey.get(key);
      if (!leg) return;
      const item = acc.get(key) ?? { leg, flow: 0, details: [] };
      item.flow += flow;
      item.details.push(detail);
      acc.set(key, item);
    };
    for (const f of solution.flows) {
      const label = `${names.get(f.port)} → ${names.get(f.dc)}: ${fmtTon(f.flow)}`;
      if (f.mode === "road_only") {
        add(`${f.port}|${f.dc}|road`, f.flow, label);
      } else {
        const rt = dcById.get(f.dc)!.rail_terminal;
        add(`${f.port}|${rt}|rail`, f.flow, label);
        add(`${rt}|${f.dc}|road`, f.flow, label);
      }
    }
    return [...acc.values()].sort((a, b) => a.flow - b.flow);
  }, [network, solution, names]);

  const maxFlow = Math.max(1, ...drawn.map((d) => d.flow));

  return (
    <div className="map-wrap">
      <MapContainer center={[39, -100]} zoom={4} scrollWheelZoom className="map">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {drawn.map((d) => (
          <Polyline
            key={`${d.leg.from}|${d.leg.to}|${d.leg.mode}`}
            positions={d.leg.path}
            pathOptions={{
              color: d.leg.mode === "rail" ? RAIL_COLOR : ROAD_COLOR,
              weight: 2 + (d.flow / maxFlow) * 10,
              opacity: 0.75,
            }}
          >
            <Tooltip sticky>
              <b>
                {d.leg.mode === "rail" ? "鉄道" : "道路"}: {names.get(d.leg.from)} → {names.get(d.leg.to)}
              </b>
              <br />
              区間の輸送量 {fmtTon(d.flow)}（{d.leg.distance_mi.toFixed(0)} マイル）
              {d.details.map((t) => (
                <div key={t} className="muted">
                  {t}
                </div>
              ))}
            </Tooltip>
          </Polyline>
        ))}
        {network.rail_terminals.map((r) => (
          <CircleMarker
            key={r.ID}
            center={[r.lat, r.lon]}
            radius={5}
            pathOptions={{ color: "#fff", weight: 2, fillColor: TERMINAL_COLOR, fillOpacity: 1 }}
          >
            <Tooltip>{r.name}（鉄道ターミナル）</Tooltip>
          </CircleMarker>
        ))}
        {network.distribution_centers.map((d) => (
          <CircleMarker
            key={d.ID}
            center={[d.lat, d.lon]}
            radius={5}
            pathOptions={{ color: "#fff", weight: 2, fillColor: DC_COLOR, fillOpacity: 1 }}
          >
            <Tooltip>
              {d.ID} {d.name}（配送センター）
              <br />
              需要 {fmtTon(d.demand)}・最寄りターミナル {names.get(d.rail_terminal)}
            </Tooltip>
          </CircleMarker>
        ))}
        {network.ports.map((p) => (
          <CircleMarker
            key={p.ID}
            center={[p.lat, p.lon]}
            radius={8}
            pathOptions={{ color: "#fff", weight: 2, fillColor: PORT_COLOR, fillOpacity: 1 }}
          >
            <Tooltip>{p.name} 港</Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
      <div className="map-legend">
        <div>
          <span className="line-swatch" style={{ background: ROAD_COLOR }} /> 道路
        </div>
        <div>
          <span className="line-swatch" style={{ background: RAIL_COLOR }} /> 鉄道
        </div>
        <div className="muted">線の太さ = 輸送量</div>
        <div>
          <span className="dot-swatch big" style={{ background: PORT_COLOR }} /> 港
        </div>
        <div>
          <span className="dot-swatch" style={{ background: DC_COLOR }} /> 配送センター
        </div>
        <div>
          <span className="dot-swatch" style={{ background: TERMINAL_COLOR }} /> 鉄道ターミナル
        </div>
      </div>
    </div>
  );
}
