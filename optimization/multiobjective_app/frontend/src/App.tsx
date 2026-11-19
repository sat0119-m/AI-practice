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

/** 計算に使った入力（入力を変えたあとは「再計算が必要」と表示するため） */
interface Computed {
  inputs: Inputs;
  primary: Primary;
  nPoints: number;
  result: FrontierResult;
}

const GRID_STEPS = 100; // スライダーの刻み（0.01）
const DEFAULT_N_POINTS = 11;

export default function App() {
  const [network, setNetwork] = useState<Network | null>(null);
  const [inputs, setInputs] = useState<Inputs | null>(null);
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

  const compute = useCallback(async (inp: Inputs, prim: Primary, n: number) => {
    const id = ++computeSeq.current;
    solveSeq.current++; // 前の結果に対する「この ε で解く」は無効にする
    setSolving(false);
    setComputing(true);
    setError(null);
    try {
      const result = await fetchFrontier(inp, prim, n);
      if (id !== computeSeq.current) return;
      setComputed({ inputs: inp, primary: prim, nPoints: n, result });
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
        compute(net.defaults, "duration", DEFAULT_N_POINTS);
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => ac.abort();
  }, [compute]);

  const validation = useMemo(
    () => (inputs ? validate(inputs, nPointsText) : { fields: {}, messages: [] }),
    [inputs, nPointsText],
  );

  if (!network || !inputs) {
    return <div className="loading-page">{error ? <p className="error">{error}</p> : "読み込み中…"}</div>;
  }

  const nPoints = Number(nPointsText);
  const stale =
    computed !== null &&
    (JSON.stringify(computed.inputs) !== JSON.stringify(inputs) ||
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
        ? `総コストの上限 = ${fmtCost(b.utopia_cost + epsilon * (b.nadir_cost - b.utopia_cost))}`
        : `平均所要日数の上限 = ${fmtDays(b.utopia_duration + epsilon * (b.nadir_duration - b.utopia_duration))}`
      : "";
  const degenerate =
    b && Math.abs(b.nadir_cost - b.utopia_cost) <= 1e-6 * Math.max(1, b.utopia_cost) &&
    Math.abs(b.nadir_duration - b.utopia_duration) <= 1e-9 * Math.max(1, b.utopia_duration);

  return (
    <div className="app">
      <header className="header">
        <h1>多目的最適化 ― ε制約法</h1>
        <p>
          港から配送センターへの輸送で「道路のみ」と「鉄道＋道路」を選び、総コストと平均所要日数のトレードオフ
          （パレートフロント）を AMPL で求めます。
        </p>
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
            setPrimary("duration");
            setNPointsText(String(DEFAULT_N_POINTS));
          }}
          onCompute={() => {
            if (validation.messages.length === 0) compute(inputs, primary, nPoints);
          }}
          computing={computing}
        />

        <main className="main">
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          {stale && !computing && (
            <div className="notice">
              入力が変わりました。「計算」を押すと新しい入力で計算し直します（表示中の結果は前回の入力のものです）。
            </div>
          )}
          {computing && (
            <div className="notice busy">
              AMPL で計算中です…（ユートピア点・ナディア点・パレートフロントの順に、ソルバーを3回呼び出します）
            </div>
          )}

          {computed && b && (
            <>
              <section className="card">
                <h2>ユートピア点とナディア点</h2>
                {degenerate && (
                  <p className="muted small">
                    ユートピア点とナディア点が一致しました。総コストと平均所要日数を同時に最良にできる解があるため、トレードオフはありません。
                  </p>
                )}
                <div className="stats four">
                  <div className="stat">
                    <div className="stat-label">総コスト（ユートピア）</div>
                    <div className="stat-value">{fmtCost(b.utopia_cost)}</div>
                  </div>
                  <div className="stat">
                    <div className="stat-label">総コスト（ナディア）</div>
                    <div className="stat-value">{fmtCost(b.nadir_cost)}</div>
                  </div>
                  <div className="stat">
                    <div className="stat-label">平均所要日数（ユートピア）</div>
                    <div className="stat-value">{fmtDays(b.utopia_duration)}</div>
                  </div>
                  <div className="stat">
                    <div className="stat-label">平均所要日数（ナディア）</div>
                    <div className="stat-value">{fmtDays(b.nadir_duration)}</div>
                  </div>
                </div>
              </section>

              <section className="card">
                <h2>パレートフロント</h2>
                <FrontierChart frontier={computed.result} selected={selected} onSelect={onPointSelect} />
              </section>

              <section className="card">
                <h2>ε を選ぶ</h2>
                <p className="muted small">
                  {computed.primary === "duration"
                    ? "平均所要日数を最小化し、正規化した総コストを ε 以下に制限します（0 = コスト最小、1 = 制限なし）。"
                    : "総コストを最小化し、正規化した平均所要日数を ε 以下に制限します（0 = 日数最短、1 = 制限なし）。"}
                </p>
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
                <p className="cap">{capLabel}</p>
                {selected && <ResultPanel solution={selected} bounds={b} primary={computed.primary} />}
              </section>

              <section className="card">
                <h2>輸送フローの地図</h2>
                <MapView network={network} solution={selected} />
                {selected && <FlowTable network={network} solution={selected} />}
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
