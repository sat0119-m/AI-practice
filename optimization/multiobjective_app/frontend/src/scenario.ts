// What-if 分析のシナリオ
//
// 画面の入力（基準）にシナリオを当てて、計算に使う入力を作る。
// どのシナリオも入力値を変えるだけなので、最適化モデル（AMPL）はそのまま使える。

import type { Inputs, Network } from "./types";

export interface Scenario {
  /** 停止する港（ストライキなど）。その港の貨物は、ほかの港へ供給量の比率で振り替える */
  closedPorts: string[];
  /** 需要の倍率。供給量も同じ倍率にして、供給不足にならないようにする */
  demandScale: number;
  /** 燃料の高騰: 道路の単価（トン・マイル当たり）の倍率 */
  fuelScale: number;
  /** 鉄道の遅延: ターミナルでの滞留に足す日数 */
  railDelayDays: number;
}

export const DEFAULT_SCENARIO: Scenario = {
  closedPorts: [],
  demandScale: 1,
  fuelScale: 1,
  railDelayDays: 0,
};

/** 画面のボタンで選べる値 */
export const DEMAND_SCALES = [1, 1.2, 1.5, 2];
export const FUEL_SCALES = [1, 1.3, 1.5];
export const RAIL_DELAYS = [0, 1.5, 3];

export const isDefaultScenario = (s: Scenario) => JSON.stringify(s) === JSON.stringify(DEFAULT_SCENARIO);

/** 基準の入力にシナリオを当てる */
export function applyScenario(base: Inputs, s: Scenario): Inputs {
  const k = s.demandScale;
  const demand = Object.fromEntries(Object.entries(base.demand).map(([id, v]) => [id, v * k]));
  let supply = Object.fromEntries(Object.entries(base.incoming_flow).map(([id, v]) => [id, v * k]));

  // 港の停止: 停止した港の供給量を、動いている港へ供給量の比率で振り替える
  const closed = new Set(s.closedPorts);
  if (closed.size > 0) {
    const moved = Object.entries(supply).reduce((a, [id, v]) => a + (closed.has(id) ? v : 0), 0);
    const openTotal = Object.entries(supply).reduce((a, [id, v]) => a + (closed.has(id) ? 0 : v), 0);
    supply = Object.fromEntries(
      Object.entries(supply).map(([id, v]) => [
        id,
        closed.has(id) ? 0 : openTotal > 0 ? v + (moved * v) / openTotal : v,
      ]),
    );
    // 比率で分けた端数の誤差をなくすため、動いている最後の港に残りを足して合計を元と一致させる
    const openIds = Object.keys(supply).filter((id) => !closed.has(id));
    if (openTotal > 0 && openIds.length > 0) {
      const last = openIds[openIds.length - 1];
      const others = openIds.slice(0, -1).reduce((a, id) => a + supply[id], 0);
      supply[last] = moved + openTotal - others;
    }
  }

  return {
    demand,
    incoming_flow: supply,
    params: {
      ...base.params,
      cost_mile_road: base.params.cost_mile_road * s.fuelScale,
      duration_rail_terminal: base.params.duration_rail_terminal + s.railDelayDays,
    },
  };
}

/** シナリオで当てられない理由（なければ null） */
export function scenarioError(network: Network, base: Inputs, s: Scenario): string | null {
  const open = network.ports.filter((p) => !s.closedPorts.includes(p.ID));
  if (open.length === 0) return "すべての港を停止すると輸送できません";
  if (s.closedPorts.length > 0 && open.every((p) => !(base.incoming_flow[p.ID] > 0)))
    return "動いている港の供給量がすべて 0 のため、停止した港の貨物を振り替えられません";
  return null;
}

/** シナリオの内容を短い文の一覧にする（結果の見出しなどに使う） */
export function describeScenario(network: Network, s: Scenario): string[] {
  const name = (id: string) => network.ports.find((p) => p.ID === id)?.name ?? id;
  const items: string[] = [];
  if (s.closedPorts.length > 0) items.push(`港の停止：${s.closedPorts.map(name).join("・")}`);
  if (s.demandScale !== 1) items.push(`需要 ×${s.demandScale}`);
  if (s.fuelScale !== 1) items.push(`道路の単価 ×${s.fuelScale}`);
  if (s.railDelayDays !== 0) items.push(`鉄道の遅延 +${s.railDelayDays}日`);
  return items;
}
