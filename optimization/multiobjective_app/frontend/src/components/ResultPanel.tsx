import type { Bounds, Primary, Solution } from "../types";
import { COST_DEFINITION, RAIL_COLOR, ROAD_COLOR, fmtCo2, fmtCost, fmtDays, fmtPct } from "../format";

interface Props {
  solution: Solution;
  bounds: Bounds;
  primary: Primary;
}

/** 選択中の解の評価指標（総輸送コスト・平均所要日数・CO2・輸送モードの割合） */
export default function ResultPanel({ solution: s, bounds, primary }: Props) {
  // ユートピア値からどれだけ離れているか（0% = ユートピア値、100% = ナディア値）
  const rel = (v: number, lo: number, hi: number) => (hi > lo ? (100 * (v - lo)) / (hi - lo) : 0);

  return (
    <div className="result">
      <div className="stats">
        <div className="stat">
          <div className="stat-label" title={COST_DEFINITION}>
            総輸送コスト
            <span className="info" aria-label={COST_DEFINITION}>?</span>
            {primary === "cost" ? <span className="tag primary-tag">主目的</span> : <span className="tag">副目的・上限 ε</span>}
          </div>
          <div className="stat-value">{fmtCost(s.cost)}</div>
          <div className="stat-sub">ユートピア値から {fmtPct(rel(s.cost, bounds.utopia_cost, bounds.nadir_cost))}</div>
        </div>
        <div className="stat">
          <div className="stat-label">
            平均所要日数
            {primary === "duration" ? <span className="tag primary-tag">主目的</span> : <span className="tag">副目的・上限 ε</span>}
          </div>
          <div className="stat-value">{fmtDays(s.duration)}</div>
          <div className="stat-sub">
            ユートピア値から {fmtPct(rel(s.duration, bounds.utopia_duration, bounds.nadir_duration))}
          </div>
        </div>
        <div className="stat">
          <div className="stat-label">CO2 排出量</div>
          <div className="stat-value">{fmtCo2(s.emissions)}</div>
          <div className="stat-sub">評価指標（目的関数には含めない）</div>
        </div>
      </div>
      <div className="share">
        <div className="share-label">輸送モードの割合（輸送量ベース）</div>
        <div className="share-bar" role="img" aria-label={`道路 ${fmtPct(s.share_road)}、鉄道 ${fmtPct(s.share_rail)}`}>
          {s.share_road > 0 && <div style={{ width: `${s.share_road}%`, background: ROAD_COLOR }} />}
          {s.share_rail > 0 && <div style={{ width: `${s.share_rail}%`, background: RAIL_COLOR }} />}
        </div>
        <div className="share-legend">
          <span>
            <span className="dot-swatch" style={{ background: ROAD_COLOR }} /> 道路のみ {fmtPct(s.share_road)}
          </span>
          <span>
            <span className="dot-swatch" style={{ background: RAIL_COLOR }} /> 鉄道＋道路 {fmtPct(s.share_rail)}
          </span>
        </div>
      </div>
    </div>
  );
}
