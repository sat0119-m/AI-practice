import { useMemo } from "react";
import type React from "react";
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { Leg, Network, Solution } from "../types";
import { RAIL_COLOR, ROAD_COLOR, fmtTon } from "../format";

interface Props {
  network: Network;
  solution: Solution | null;
  /** What-if シナリオで停止した港（灰色で表示する） */
  closedPorts?: string[];
  /** 道路・鉄道の平均速度（マイル/時）。流れるアニメーションの速さに使う */
  speeds?: { road: number; rail: number };
}

const PORT_COLOR = "#2a78d6";
const DC_COLOR = "#52514e";
const TERMINAL_COLOR = "#6250d6";
const CLOSED_COLOR = "#a8a8a8";

/** 線の太さ（輸送量に比例。最大の区間で 12px） */
const lineWidth = (flow: number, maxFlow: number) => 2 + (flow / maxFlow) * 10;

/** 凡例：輸送モードの線と、運ぶ向きに流れる白い点（地図と同じアニメーション） */
function FlowSwatch({ mode }: { mode: "road" | "rail" }) {
  return (
    <svg width="46" height="12" aria-hidden="true">
      <line x1="2" y1="6" x2="44" y2="6" stroke={mode === "rail" ? RAIL_COLOR : ROAD_COLOR} strokeWidth="7" strokeLinecap="round" />
      <line
        x1="2"
        y1="6"
        x2="44"
        y2="6"
        stroke="#fff"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeDasharray="2 14"
        className={`flow-dash ${mode}`}
      />
    </svg>
  );
}

/** 凡例：線の太さの見本 */
function WidthSwatch({ width }: { width: number }) {
  return (
    <svg width="34" height="14" aria-hidden="true">
      <line x1="3" y1="7" x2="31" y2="7" stroke="#8a8984" strokeWidth={width} strokeLinecap="round" />
    </svg>
  );
}

/** 地図に描く区間と、その区間を通る輸送量の合計 */
interface DrawnLeg {
  leg: Leg;
  flow: number;
  details: string[];
}

export default function MapView({ network, solution, closedPorts = [], speeds = { road: 60, rail: 35 } }: Props) {
  // 最初に表示する範囲（港・配送センター・鉄道ターミナルがすべて入るようにする）
  const allPoints = useMemo(
    () =>
      [...network.ports, ...network.distribution_centers, ...network.rail_terminals].map(
        (n) => [n.lat, n.lon] as [number, number],
      ),
    [network],
  );

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
    <div
      className="map-wrap"
      style={
        {
          "--road-dur": `${60 / speeds.road}s`,
          "--rail-dur": `${60 / speeds.rail}s`,
        } as React.CSSProperties
      }
    >
      <MapContainer
        bounds={allPoints}
        boundsOptions={{ padding: [16, 16] }}
        zoomSnap={0.25}
        scrollWheelZoom
        className="map"
      >
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
              weight: lineWidth(d.flow, maxFlow),
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
        {/* 輸送の向き：経路の上に白い破線を重ね、出発地 → 到着地の向きに流す（速さは道路 > 鉄道） */}
        {drawn.map((d) => (
          <Polyline
            key={`flow|${d.leg.from}|${d.leg.to}|${d.leg.mode}`}
            positions={d.leg.path}
            interactive={false}
            className={`flow-dash ${d.leg.mode}`}
            pathOptions={{
              color: "#ffffff",
              weight: Math.max(1.5, lineWidth(d.flow, maxFlow) * 0.35),
              opacity: 0.9,
              dashArray: "2 14",
              lineCap: "round",
            }}
          />
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
        {network.ports.map((p) => {
          const closed = closedPorts.includes(p.ID);
          return (
            <CircleMarker
              key={p.ID}
              center={[p.lat, p.lon]}
              radius={8}
              pathOptions={{
                color: closed ? "#555" : "#fff",
                weight: 2,
                dashArray: closed ? "3 3" : undefined,
                fillColor: closed ? CLOSED_COLOR : PORT_COLOR,
                fillOpacity: 1,
              }}
            >
              <Tooltip>
                {p.name} 港{closed && "（停止中：貨物はほかの港へ振り替え）"}
              </Tooltip>
            </CircleMarker>
          );
        })}
      </MapContainer>
      <div className="map-legend">
        <div className="lg-group">
          <span className="lg-title">輸送モードと速さ</span>
          <span className="lg-item">
            <FlowSwatch mode="road" /> 道路 {speeds.road} mph
          </span>
          <span className="lg-item">
            <FlowSwatch mode="rail" /> 鉄道 {speeds.rail} mph
          </span>
          <span className="lg-note">白い点が運ぶ向きに流れ、速いほど速く動く</span>
        </div>
        {drawn.length > 0 && (
          <div className="lg-group">
            <span className="lg-title">線の太さ = 輸送量</span>
            {[0.1, 0.5, 1].map((r) => (
              <span className="lg-item" key={r}>
                <WidthSwatch width={lineWidth(r * maxFlow, maxFlow)} /> {fmtTon(r * maxFlow)}
              </span>
            ))}
          </div>
        )}
        <div className="lg-group">
          <span className="lg-item">
            <span className="dot-swatch big" style={{ background: PORT_COLOR }} /> 港
          </span>
          {closedPorts.length > 0 && (
            <span className="lg-item">
              <span className="dot-swatch big" style={{ background: CLOSED_COLOR }} /> 停止した港
            </span>
          )}
          <span className="lg-item">
            <span className="dot-swatch" style={{ background: DC_COLOR }} /> 配送センター
          </span>
          <span className="lg-item">
            <span className="dot-swatch" style={{ background: TERMINAL_COLOR }} /> 鉄道ターミナル
          </span>
        </div>
      </div>
    </div>
  );
}
