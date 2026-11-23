import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchFrontier, fetchNetwork, solveEpsilon } from "./api";
import type { FrontierResult, Inputs, Network, Primary, Solution } from "./types";
import { fmtCost, fmtDays } from "./format";
import { validate } from "./validate";
import ParamPanel from "./components/ParamPanel";
import FrontierChart from "./components/FrontierChart";
import ResultPanel from "./components/ResultPanel";
import MapView from "./components/MapView";
import FlowTable from "./components/FlowTable";
import ScenarioPanel from "./components/ScenarioPanel";
import {
  DEFAULT_SCENARIO,
  applyScenario,
  describeScenario,
  isDefaultScenario,
  scenarioError,
  type Scenario,
} from "./scenario";

/** 計算に使った入力（入力を変えたあとは「再計算が必要」と表示するため） */
interface Computed {
  inputs: Inputs; // シナリオを当てたあとの入力
  scenario: Scenario;
  primary: Primary;
  nPoints: number;
  result: FrontierResult;
}

const GRID_STEPS = 100; // スライダーの刻み（0.01）
const DEFAULT_N_POINTS = 11;
const AUTO_COMPUTE_DELAY = 600; // 入力を変えてから自動で計算するまでの待ち時間（ミリ秒）

export default function App() {
  const [network, setNetwork] = useState<Network | null>(null);
  const [inputs, setInputs] = useState<Inputs | null>(null); // 画面で編集する基準の入力
  const [scenario, setScenario] = useState<Scenario>(DEFAULT_SCENARIO);
  const [primary, setPrimary] = useState<Primary>("duration");
  const [nPointsText, setNPointsText] = useState(String(DEFAULT_N_POINTS));
  const [computed, setComputed] = useState<Computed | null>(null);
  const [computing, setComputing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [epsilon, setEpsilon] = useState(0.5);
  const [epsText, setEpsText] = useState("0.5");
  const [selected, setSelected] = useState<Solution | null>(null);
  const [solving, setSolving] = useState(false);

  // 応答の順番がずれても、最後に出したリクエストの結果だけを使うための番号
  const computeSeq = useRef(0);
  const solveSeq = useRef(0);

  /** 進行中の「この ε で解く」の結果を捨てる（スライダーなどで別の解を選んだとき） */
  const cancelSolve = () => {
    solveSeq.current++;
    setSolving(false);
  };

  const compute = useCallback(async (inp: Inputs, prim: Primary, n: number, sc: Scenario) => {
    const id = ++computeSeq.current;
    solveSeq.current++; // 前の結果に対する「この ε で解く」は無効にする
    setSolving(false);
    setComputing(true);
    setError(null);
    try {
      const result = await fetchFrontier(inp, prim, n);
      if (id !== computeSeq.current) return;
      setComputed({ inputs: inp, scenario: sc, primary: prim, nPoints: n, result });
      setEpsilon(0.5);
      setEpsText("0.5");
      setSelected(result.grid[GRID_STEPS / 2]);
    } catch (e) {
      if (id === computeSeq.current) setError((e as Error).message);
    } finally {
      if (id === computeSeq.current) setComputing(false);
    }
  }, []);

  // 起動時: ネットワークと初期値を読み込み、初期値で計算する
  // （開発モードの StrictMode では effect が2回走るので、1回目は中止して計算を1回にする）
  useEffect(() => {
    const ac = new AbortController();
    fetchNetwork(ac.signal)
      .then((net) => {
        setNetwork(net);
        setInputs(net.defaults);
        compute(applyScenario(net.defaults, DEFAULT_SCENARIO), "duration", DEFAULT_N_POINTS, DEFAULT_SCENARIO);
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => ac.abort();
  }, [compute]);

  // 計算に使う入力 = 基準の入力にシナリオを当てたもの
  const effective = useMemo(() => (inputs ? applyScenario(inputs, scenario) : null), [inputs, scenario]);
  const scenarioErr = network && inputs ? scenarioError(network, inputs, scenario) : null;
  const validation = useMemo(() => {
    if (!inputs || !effective) return { fields: {}, messages: [] };
    // 入力欄のエラーは基準の入力で、計算できるかどうかはシナリオを当てた入力で判定する
    const base = validate(inputs, nPointsText);
    const eff = validate(effective, nPointsText);
    const messages = [...new Set([...base.messages, ...eff.messages, ...(scenarioErr ? [scenarioErr] : [])])];
    return { fields: base.fields, messages };
  }, [inputs, effective, nPointsText, scenarioErr]);

  // 入力・シナリオ・主目的・点の数が変わったら、少し待ってから自動で計算し直す
  // （続けて入力したときに毎回ソルバーを呼ばないよう、最後の変更から AUTO_COMPUTE_DELAY だけ待つ）
  useEffect(() => {
    if (!computed || !effective || validation.messages.length > 0) return;
    const n = Number(nPointsText);
    const changed =
      JSON.stringify(computed.inputs) !== JSON.stringify(effective) ||
      JSON.stringify(computed.scenario) !== JSON.stringify(scenario) ||
      computed.primary !== primary ||
      computed.nPoints !== n;
    if (!changed) return;
    const t = setTimeout(() => compute(effective, primary, n, scenario), AUTO_COMPUTE_DELAY);
    return () => clearTimeout(t);
  }, [computed, effective, scenario, primary, nPointsText, validation, compute]);

  if (!network || !inputs || !effective) {
    return <div className="loading-page">{error ? <p className="error">{error}</p> : "読み込み中…"}</div>;
  }

  const nPoints = Number(nPointsText);
  const stale =
    computed !== null &&
    (JSON.stringify(computed.inputs) !== JSON.stringify(effective) ||
      JSON.stringify(computed.scenario) !== JSON.stringify(scenario) ||
      computed.primary !== primary ||
      computed.nPoints !== nPoints);

  // スライダー: 計算済みの 0.01 刻みの解をその場で表示する
  const onSlide = (v: number) => {
    if (!computed) return;
    cancelSolve();
    setError(null);
    setEpsilon(v);
    setEpsText(String(v));
    setSelected(computed.result.grid[Math.round(v * GRID_STEPS)]);
  };

  // 数値入力: 0.01 刻みなら計算済みの解、それ以外はバックエンドで1回だけ解く
  const onSolveExact = async () => {
    if (!computed) return;
    const v = Number(epsText);
    if (epsText.trim() === "" || !Number.isFinite(v) || v < 0 || v > 1) {
      setError("ε は 0〜1 の数値で入力してください");
      return;
    }
    cancelSolve();
    setError(null);
    setEpsilon(v);
    const k = v * GRID_STEPS;
    if (Math.abs(k - Math.round(k)) < 1e-9) {
      setSelected(computed.result.grid[Math.round(k)]);
      return;
    }
    const id = solveSeq.current;
    setSolving(true);
    try {
      const solution = await solveEpsilon(computed.inputs, computed.primary, v, computed.result.bounds);
      if (id === solveSeq.current) setSelected(solution);
    } catch (e) {
      if (id === solveSeq.current) setError((e as Error).message);
    } finally {
      if (id === solveSeq.current) setSolving(false);
    }
  };

  const onPointSelect = (s: Solution) => {
    cancelSolve();
    setError(null);
    setEpsilon(s.epsilon);
    setEpsText(String(Number(s.epsilon.toFixed(6))));
    setSelected(s);
  };

  const b = computed?.result.bounds;
  const capLabel =
    computed && b
      ? computed.primary === "duration"
        ? `副目的「総輸送コスト」の上限 = ${fmtCost(b.utopia_cost + epsilon * (b.nadir_cost - b.utopia_cost))}`
        : `副目的「平均所要日数」の上限 = ${fmtDays(b.utopia_duration + epsilon * (b.nadir_duration - b.utopia_duration))}`
      : "";
  const degenerate =
    b && Math.abs(b.nadir_cost - b.utopia_cost) <= 1e-6 * Math.max(1, b.utopia_cost) &&
    Math.abs(b.nadir_duration - b.utopia_duration) <= 1e-9 * Math.max(1, b.utopia_duration);

  return (
    <div className="app">
      <header className="header">
        <h1>多目的最適化 ― ε制約法</h1>
        <p>港から配送センターへ「道路のみ」か「鉄道＋道路」で運ぶとき、総輸送コストと平均所要日数のトレードオフを AMPL で求めます。</p>
      </header>

      <div className="layout">
        <ParamPanel
          network={network}
          inputs={inputs}
          onChange={setInputs}
          primary={primary}
          onPrimaryChange={setPrimary}
          nPointsText={nPointsText}
          onNPointsChange={setNPointsText}
          validation={validation}
          onReset={() => {
            setInputs(network.defaults);
            setScenario(DEFAULT_SCENARIO);
            setPrimary("duration");
            setNPointsText(String(DEFAULT_N_POINTS));
          }}
          onCompute={() => {
            if (validation.messages.length === 0) compute(effective, primary, nPoints, scenario);
          }}
          computing={computing}
          stale={stale}
          scenarioSlot={
            <ScenarioPanel
              network={network}
              effective={effective}
              scenario={scenario}
              onChange={setScenario}
              error={scenarioErr}
            />
          }
        />

        <main className="main">
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          {/* 起動直後（まだ結果がないとき）だけ、計算中であることを本文に出す */}
          {computing && !computed && <div className="notice busy">AMPL で計算中です…</div>}

          {computed && b && (
            <>
              {/* シナリオの有無で帯が出たり消えたりすると下がずれるので、帯は常に1行の高さで出す */}
              <div
                className={`scenario-banner ${isDefaultScenario(computed.scenario) ? "base" : ""}`}
                title={describeScenario(network, computed.scenario).join("、") || undefined}
              >
                {isDefaultScenario(computed.scenario) ? (
                  <>
                    <b>基準</b>
                    <span className="muted">元問題の条件で計算した結果</span>
                  </>
                ) : (
                  <>
                    <b>What-if シナリオで計算した結果</b>
                    {describeScenario(network, computed.scenario).map((t) => (
                      <span className="chip" key={t}>
                        {t}
                      </span>
                    ))}
                  </>
                )}
              </div>
              {/* 「入力が変わった」「計算中」は結果の上に重ねて表示し、レイアウトをずらさない */}
              <div className={`viz-grid ${computing ? "is-busy" : stale ? "is-stale" : ""}`}>
                {(computing || stale) && (
                  <div className="viz-overlay" role="status">
                    {computing
                      ? "AMPL で計算中です…"
                      : "入力が変わりました。表示中は前回の入力の結果です（「再計算」で更新）"}
                  </div>
                )}
                <section className="card">
                  <h2>パレートフロントと ε</h2>
                  <p className="bounds-inline">
                      ユートピア点 {fmtCost(b.utopia_cost)}・{fmtDays(b.utopia_duration)}
                      <span className="sep">／</span>
                      ナディア点 {fmtCost(b.nadir_cost)}・{fmtDays(b.nadir_duration)}
                  </p>
                  {degenerate && (
                    <p className="muted small">
                      ユートピア点とナディア点が一致しました。総輸送コストと平均所要日数を同時に最良にできる解があるため、トレードオフはありません。
                    </p>
                  )}
                  <FrontierChart frontier={computed.result} selected={selected} onSelect={onPointSelect} height={250}
                  />
                  <div className="eps-row">
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={1 / GRID_STEPS}
                      value={epsilon}
                      onChange={(e) => onSlide(Number(e.target.value))}
                      aria-label="ε"
                    />
                    <form
                      className="eps-input"
                      noValidate
                      onSubmit={(e) => {
                        e.preventDefault();
                        onSolveExact();
                      }}
                    >
                      <label>
                        ε =
                        <input
                          type="number"
                          min={0}
                          max={1}
                          step="any"
                          value={epsText}
                          onChange={(e) => setEpsText(e.target.value)}
                        />
                      </label>
                      <button type="submit" disabled={solving || computing}>
                        {solving ? "計算中…" : "この ε で解く"}
                      </button>
                    </form>
                  </div>
                  <p className="cap">
                    {capLabel}
                    <span className="muted">
                      {computed.primary === "duration"
                        ? "（0 = コスト最小、1 = 日数最短）"
                        : "（0 = 日数最短、1 = コスト最小）"}
                    </span>
                  </p>
                  {selected && <ResultPanel solution={selected} bounds={b} primary={computed.primary} />}
                </section>

                <section className="card">
                  <h2>輸送フローの地図</h2>
                  <MapView
                    network={network}
                    solution={selected}
                    closedPorts={computed.scenario.closedPorts}
                    speeds={{ road: computed.inputs.params.speed_road, rail: computed.inputs.params.speed_rail }}
                  />
                  {selected && <FlowTable network={network} solution={selected} />}
                </section>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
