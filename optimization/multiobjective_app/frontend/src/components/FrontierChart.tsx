import {
  CartesianGrid,
  ReferenceDot,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { FrontierResult, Solution } from "../types";
import { CO2_GRADIENT, co2Color, fmtCo2, fmtCost, fmtCostShort, fmtDays, fmtPct } from "../format";

interface Props {
  frontier: FrontierResult;
  selected: Solution | null;
  onSelect: (s: Solution) => void;
}

interface Datum {
  cost: number;
  duration: number;
  solution: Solution;
}

const SURFACE = "#fcfcfb";
const LINE = "#c3c2b7";
const INK = "#0b0b0b";
const MUTED = "#8a8984";

/** lo〜hi を含む、1・2・2.5・5 × 10^n 刻みのきりのよい目盛り（4〜7 本程度） */
function niceTicks(lo: number, hi: number): number[] {
  const span = hi - lo || Math.abs(hi) || 1;
  const raw = span / 5;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? 10 * pow;
  const start = Math.floor(lo / step) * step;
  const end = Math.ceil(hi / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= end + step / 2; v += step) ticks.push(Number(v.toPrecision(12)));
  return ticks;
}

/** 点の上に乗せたときの説明 */
function PointTooltip({ active, payload }: { active?: boolean; payload?: { payload: Datum }[] }) {
  if (!active || !payload?.length) return null;
  const s = payload[0].payload.solution;
  return (
    <div className="tooltip">
      <div className="tooltip-title">ε = {s.epsilon.toFixed(3)}</div>
      <div>総コスト <b>{fmtCost(s.cost)}</b></div>
      <div>平均所要日数 <b>{fmtDays(s.duration)}</b></div>
      <div>CO2 排出量 <b>{fmtCo2(s.emissions)}</b></div>
      <div>道路 {fmtPct(s.share_road)} ／ 鉄道 {fmtPct(s.share_rail)}</div>
      <div className="muted">クリックでこの解を選択</div>
    </div>
  );
}

export default function FrontierChart({ frontier, selected, onSelect }: Props) {
  const { bounds, points, grid } = frontier;
  const co2s = grid.map((s) => s.emissions);
  const co2Min = Math.min(...co2s);
  const co2Max = Math.max(...co2s);

  const toDatum = (s: Solution): Datum => ({ cost: s.cost, duration: s.duration, solution: s });
  const pointData = points.map(toDatum);
  const lineData = grid.map(toDatum);

  // 軸の範囲と目盛りは、ユートピア値・ナディア値を含むきりのよい値にそろえる
  const xTicks = niceTicks(bounds.utopia_cost, bounds.nadir_cost);
  const yTicks = niceTicks(bounds.utopia_duration, bounds.nadir_duration);
  const xDomain = [xTicks[0], xTicks[xTicks.length - 1]];
  const yDomain = [yTicks[0], yTicks[yTicks.length - 1]];

  return (
    <div>
      <div className="chart-legend">
        <span className="legend-item">
          <span className="swatch-ring" /> 選択中の解
        </span>
        <span className="legend-item">
          <span className="swatch-dashed" /> ユートピア点・ナディア点
        </span>
        <span className="legend-item">
          点の色 = CO2 排出量
          <span className="gradient" style={{ background: CO2_GRADIENT }} />
          <span className="muted">
            {fmtCo2(co2Min)} 〜 {fmtCo2(co2Max)}
          </span>
        </span>
      </div>
      {/* 非表示の説明（tooltip）が前の位置に残り、画面幅を縮めたときに横スクロールが出るのを防ぐ */}
      <div className="chart-box">
      <ResponsiveContainer width="100%" height={340}>
        <ScatterChart margin={{ top: 16, right: 24, bottom: 28, left: 12 }}>
          <CartesianGrid stroke="#e8e7e2" strokeDasharray="0" />
          <XAxis
            type="number"
            dataKey="cost"
            domain={xDomain}
            ticks={xTicks}
            tickFormatter={fmtCostShort}
            stroke={MUTED}
            tick={{ fontSize: 12 }}
            label={{ value: "総コスト", position: "insideBottom", offset: -16, fill: MUTED, fontSize: 12 }}
          />
          <YAxis
            type="number"
            dataKey="duration"
            domain={yDomain}
            ticks={yTicks}
            tickFormatter={(v: number) => v.toFixed(1)}
            stroke={MUTED}
            tick={{ fontSize: 12 }}
            width={48}
            label={{ value: "平均所要日数", angle: -90, position: "insideLeft", offset: 8, fill: MUTED, fontSize: 12 }}
          />
          <Tooltip content={<PointTooltip />} cursor={false} isAnimationActive={false} />
          {/* 0.01 刻みの解をつないだパレートフロント */}
          <Scatter
            data={lineData}
            line={{ stroke: LINE, strokeWidth: 2 }}
            shape={() => <g />}
            isAnimationActive={false}
            tooltipType="none"
          />
          {/* 計算した n 点（CO2 で色分け、周りに背景色の縁取り） */}
          <Scatter
            data={pointData}
            isAnimationActive={false}
            cursor="pointer"
            onClick={(d: unknown) => {
              const datum = (d as { payload?: Datum }).payload;
              if (datum) onSelect(datum.solution);
            }}
            shape={(p: unknown) => {
              const { cx, cy, payload } = p as { cx: number; cy: number; payload: Datum };
              return (
                <g>
                  <circle cx={cx} cy={cy} r={14} fill="transparent" />
                  <circle
                    cx={cx}
                    cy={cy}
                    r={6}
                    fill={co2Color(payload.solution.emissions, co2Min, co2Max)}
                    stroke={SURFACE}
                    strokeWidth={2}
                  />
                </g>
              );
            }}
          />
          <ReferenceDot
            x={bounds.utopia_cost}
            y={bounds.utopia_duration}
            r={6}
            fill={SURFACE}
            stroke={MUTED}
            strokeDasharray="3 2"
            label={{ value: "ユートピア点", position: "right", fill: MUTED, fontSize: 12 }}
          />
          <ReferenceDot
            x={bounds.nadir_cost}
            y={bounds.nadir_duration}
            r={6}
            fill={SURFACE}
            stroke={MUTED}
            strokeDasharray="3 2"
            label={{ value: "ナディア点", position: "left", fill: MUTED, fontSize: 12 }}
          />
          {selected && (
            <ReferenceDot x={selected.cost} y={selected.duration} r={10} fill="none" stroke={INK} strokeWidth={2} />
          )}
        </ScatterChart>
      </ResponsiveContainer>
      </div>
    </div>
  );
}
