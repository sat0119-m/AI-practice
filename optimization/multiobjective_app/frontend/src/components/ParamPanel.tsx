import { useEffect, useState, type ReactNode } from "react";
import type { Inputs, Network, Params, Primary } from "../types";
import { fmtTon } from "../format";
import { N_POINTS_MAX, N_POINTS_MIN, type Validation } from "../validate";

interface Props {
  network: Network;
  inputs: Inputs;
  onChange: (inputs: Inputs) => void;
  primary: Primary;
  onPrimaryChange: (p: Primary) => void;
  nPointsText: string;
  onNPointsChange: (text: string) => void;
  validation: Validation;
  onReset: () => void;
  onCompute: () => void;
  computing: boolean;
  /** 入力が前回の計算から変わったか（ボタンを「再計算」にする） */
  stale?: boolean;
  /** 「ε制約法の設定」の下に差し込む欄（What-if シナリオ） */
  scenarioSlot?: ReactNode;
}

// パラメータ入力欄の定義（グループ・ラベル・単位・刻み）
const PARAM_GROUPS: { title: string; fields: { key: keyof Params; label: string; unit: string; step: number }[] }[] = [
  {
    title: "コスト",
    fields: [
      { key: "cost_mile_road", label: "道路", unit: "$/トン・マイル", step: 0.01 },
      { key: "cost_mile_rail", label: "鉄道", unit: "$/トン・マイル", step: 0.01 },
      { key: "min_cost_road", label: "道路の最低コスト", unit: "$/トン", step: 1 },
      { key: "min_cost_rail", label: "鉄道の最低コスト", unit: "$/トン", step: 1 },
    ],
  },
  {
    title: "所要時間",
    fields: [
      { key: "speed_road", label: "道路の平均速度", unit: "マイル/時", step: 1 },
      { key: "speed_rail", label: "鉄道の平均速度", unit: "マイル/時", step: 1 },
      { key: "hours_day", label: "1日の稼働時間", unit: "時間（24 以下）", step: 1 },
      { key: "duration_rail_terminal", label: "鉄道ターミナルでの滞留", unit: "日", step: 0.1 },
    ],
  },
  {
    title: "CO2 排出係数",
    fields: [
      { key: "emission_road_lb", label: "道路", unit: "ポンド/トン・マイル", step: 0.01 },
      { key: "emission_rail_lb", label: "鉄道", unit: "ポンド/トン・マイル", step: 0.01 },
    ],
  },
];

/**
 * 入力エラーがあるときに自動で開く折りたたみ。
 * open を props で直接渡すと、エラーが消えた瞬間に勝手に閉じるため、開閉は自分で持ち、エラーで開くだけにする。
 */
function AutoOpenDetails(props: { forceOpen: boolean; className?: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (props.forceOpen) setOpen(true);
  }, [props.forceOpen]);
  return (
    <details className={props.className} open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      {props.children}
    </details>
  );
}

const num = (s: string) => (s.trim() === "" ? NaN : Number(s));
const shown = (v: number) => (Number.isFinite(v) ? v : "");

export default function ParamPanel(props: Props) {
  const { network, inputs, onChange, primary, onPrimaryChange, validation } = props;
  const errors = validation.fields;
  const totalDemand = Object.values(inputs.demand).reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0);
  const totalSupply = Object.values(inputs.incoming_flow).reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0);
  const shortage = totalSupply < totalDemand;
  const demandErrors = Object.keys(errors).some((k) => k.startsWith("demand:"));
  const supplyErrors = Object.keys(errors).some((k) => k.startsWith("supply:"));
  const hasDetailErrors = Object.keys(errors).length > 0 || shortage;

  const setParam = (key: keyof Params, value: number) =>
    onChange({ ...inputs, params: { ...inputs.params, [key]: value } });

  return (
    <aside className="panel">
      <section className="card">
        <h2>ε制約法の設定</h2>
        <fieldset className="segmented" aria-label="主目的">
          <label className={primary === "duration" ? "active" : ""}>
            <input
              type="radio"
              name="primary"
              checked={primary === "duration"}
              onChange={() => onPrimaryChange("duration")}
            />
            <span>
              <b>
                <span className="role primary-role">主目的</span>平均所要日数を最小化
              </b>
              <small>
                <span className="role secondary-role">副目的</span>総輸送コストに上限 ε
              </small>
            </span>
          </label>
          <label className={primary === "cost" ? "active" : ""}>
            <input type="radio" name="primary" checked={primary === "cost"} onChange={() => onPrimaryChange("cost")} />
            <span>
              <b>
                <span className="role primary-role">主目的</span>総輸送コストを最小化
              </b>
              <small>
                <span className="role secondary-role">副目的</span>平均所要日数に上限 ε
              </small>
            </span>
          </label>
        </fieldset>
        {validation.messages.length > 0 && (
          <ul className="validation" role="alert">
            {validation.messages.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        )}
        <div className="actions">
          <button
            className={`primary ${props.stale && !props.computing ? "needs-recompute" : ""}`}
            onClick={props.onCompute}
            disabled={props.computing || validation.messages.length > 0}
          >
            {props.computing ? "計算中…" : props.stale ? "再計算" : "計算"}
          </button>
          <button onClick={props.onReset} disabled={props.computing}>
            初期値に戻す
          </button>
        </div>
      </section>

      {props.scenarioSlot}

      {/* デモで触らない細かい入力は「詳細設定」にまとめ、最初は閉じておく（入力エラーがあるときは開く） */}
      <AutoOpenDetails className="card advanced" forceOpen={hasDetailErrors}>
        <summary>
          <span>詳細設定</span>
          <small className="muted">グラフ・パラメータ・需要・供給量</small>
        </summary>
        <section className="sub-section first">
          <h2>グラフ</h2>
          <label className={`field ${errors.nPoints ? "invalid" : ""}`}>
            <span>パレートフロントの点の数</span>
            <input
              type="number"
              min={N_POINTS_MIN}
              max={N_POINTS_MAX}
              step={1}
              value={props.nPointsText}
              onChange={(e) => props.onNPointsChange(e.target.value)}
            />
            <small className="unit">
              {N_POINTS_MIN}〜{N_POINTS_MAX}
            </small>
          </label>
        </section>
      {PARAM_GROUPS.map((group) => (
        <section className="sub-section" key={group.title}>
          <h2>{group.title}</h2>
          {group.fields.map((f) => (
            <label className={`field ${errors[f.key] ? "invalid" : ""}`} key={f.key}>
              <span>{f.label}</span>
              <input
                type="number"
                min={0}
                step={f.step}
                value={shown(inputs.params[f.key])}
                onChange={(e) => setParam(f.key, num(e.target.value))}
              />
              <small className="unit">{f.unit}</small>
              {errors[f.key] && <small className="field-error">{errors[f.key]}</small>}
            </label>
          ))}
        </section>
      ))}

      <section className="sub-section">
        <h2>需要と供給量</h2>
        <p className={`totals ${shortage ? "error-text" : ""}`}>
          需要の合計 {fmtTon(totalDemand)} ／ 供給量の合計 {fmtTon(totalSupply)}
          {shortage && (
            <>
              <br />
              供給量が足りないため計算できません
            </>
          )}
        </p>
        <AutoOpenDetails forceOpen={supplyErrors}>
          <summary>港の供給量（{network.ports.length} 港）</summary>
          <table className="input-table">
            <tbody>
              {network.ports.map((p) => (
                <tr key={p.ID} className={errors[`supply:${p.ID}`] ? "invalid" : ""}>
                  <td>{p.name}</td>
                  <td>
                    <input
                      type="number"
                      min={0}
                      step={100}
                      aria-label={`${p.name} の供給量`}
                      value={shown(inputs.incoming_flow[p.ID])}
                      onChange={(e) =>
                        onChange({ ...inputs, incoming_flow: { ...inputs.incoming_flow, [p.ID]: num(e.target.value) } })
                      }
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </AutoOpenDetails>
        <AutoOpenDetails forceOpen={demandErrors}>
          <summary>配送センターの需要（{network.distribution_centers.length} か所）</summary>
          <table className="input-table">
            <tbody>
              {network.distribution_centers.map((dc) => (
                <tr key={dc.ID} className={errors[`demand:${dc.ID}`] ? "invalid" : ""}>
                  <td>
                    <span className="muted">{dc.ID}</span> {dc.name}
                  </td>
                  <td>
                    <input
                      type="number"
                      min={0}
                      step={10}
                      aria-label={`${dc.ID} ${dc.name} の需要`}
                      value={shown(inputs.demand[dc.ID])}
                      onChange={(e) =>
                        onChange({ ...inputs, demand: { ...inputs.demand, [dc.ID]: num(e.target.value) } })
                      }
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </AutoOpenDetails>
      </section>
      </AutoOpenDetails>
    </aside>
  );
}
