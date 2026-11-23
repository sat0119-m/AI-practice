import type { Inputs, Network } from "../types";
import { fmtTon } from "../format";
import {
  DEFAULT_SCENARIO,
  DEMAND_SCALES,
  FUEL_SCALES,
  RAIL_DELAYS,
  isDefaultScenario,
  type Scenario,
} from "../scenario";

interface Props {
  network: Network;
  /** シナリオを当てたあとの入力（振り替え後の供給量などを表示する） */
  effective: Inputs;
  scenario: Scenario;
  onChange: (s: Scenario) => void;
  error: string | null;
}

/** 値を選ぶボタンの列（選んでいるものを強調する） */
function Choice<T extends number>(props: {
  label: string;
  values: T[];
  value: T;
  format: (v: T) => string;
  onChange: (v: T) => void;
}) {
  return (
    <div className="choice">
      <span className="choice-label">{props.label}</span>
      <div className="choice-buttons" role="group" aria-label={props.label}>
        {props.values.map((v) => (
          <button
            key={v}
            type="button"
            className={v === props.value ? "active" : ""}
            aria-pressed={v === props.value}
            onClick={() => props.onChange(v)}
          >
            {props.format(v)}
          </button>
        ))}
      </div>
    </div>
  );
}

/** What-if 分析: ボタンで入力を切り替える（「計算」を押すと、このシナリオで計算し直す） */
export default function ScenarioPanel({ network, effective, scenario: s, onChange, error }: Props) {
  const set = (patch: Partial<Scenario>) => onChange({ ...s, ...patch });
  // 停止する港は ports の順に並べる（選んだ順で「変更あり」と判定されたり、表示順が変わったりしないように）
  const togglePort = (id: string) => {
    const next = s.closedPorts.includes(id) ? s.closedPorts.filter((p) => p !== id) : [...s.closedPorts, id];
    set({ closedPorts: network.ports.map((p) => p.ID).filter((p) => next.includes(p)) });
  };
  const supplyText = (id: string) => {
    const v = effective.incoming_flow[id];
    return Number.isFinite(v) ? fmtTon(v) : "—";
  };

  return (
    <section className="card scenario">
      <div className="card-head">
        <h2>What-if シナリオ</h2>
        {/* 押したあとにフォーカスが消えないよう、ボタンは常に置き、戻す必要がないときは無効にする */}
        <button
          type="button"
          className="link"
          disabled={isDefaultScenario(s)}
          onClick={() => onChange(DEFAULT_SCENARIO)}
        >
          元に戻す
        </button>
      </div>
      <p className="muted small">条件を変えると、そのシナリオのパレートフロントを自動で計算し直します。</p>

      <div className="choice">
        <span className="choice-label">港の停止（ストライキ）</span>
        <div className="port-toggles">
          {network.ports.map((p) => {
            const closed = s.closedPorts.includes(p.ID);
            return (
              <label key={p.ID} className={`port-toggle ${closed ? "closed" : ""}`}>
                <input
                  type="checkbox"
                  checked={closed}
                  onChange={() => togglePort(p.ID)}
                  aria-label={`${p.name} 港を停止する`}
                />
                <span>{p.name}</span>
                <small>{closed ? "停止" : supplyText(p.ID)}</small>
              </label>
            );
          })}
        </div>
        {s.closedPorts.length > 0 && (
          <small className="muted">停止した港の貨物は、ほかの港へ供給量の比率で振り替えます。</small>
        )}
      </div>

      <Choice
        label="需要の増減（供給量も同じ倍率）"
        values={DEMAND_SCALES}
        value={s.demandScale}
        format={(v) => `×${v}`}
        onChange={(v) => set({ demandScale: v })}
      />
      <Choice
        label="燃料の高騰（道路の単価）"
        values={FUEL_SCALES}
        value={s.fuelScale}
        format={(v) => `×${v}`}
        onChange={(v) => set({ fuelScale: v })}
      />
      <Choice
        label="鉄道の遅延（ターミナルでの滞留）"
        values={RAIL_DELAYS}
        value={s.railDelayDays}
        format={(v) => (v === 0 ? "なし" : `+${v}日`)}
        onChange={(v) => set({ railDelayDays: v })}
      />

      {/* 読み上げは「計算」ボタンの近くの一覧（role="alert"）で行うので、ここは表示だけ */}
      {error && <p className="error-text small">{error}</p>}
    </section>
  );
}
