// What-if シナリオ（applyScenario）と入力チェック（validate）の回帰テスト
// 実行: npm test（Node 22.6 以上。TypeScript をそのまま実行する）
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { applyScenario, DEFAULT_SCENARIO, DEMAND_SCALES, scenarioError, type Scenario } from "../src/scenario.ts";
import { validate } from "../src/validate.ts";
import type { Inputs, Network } from "../src/types.ts";

// バックエンドの network.json から、画面の初期値と同じ入力を作る
const raw = JSON.parse(readFileSync(new URL("../../backend/data/network.json", import.meta.url), "utf8"));
const network = raw as Network;
const base: Inputs = {
  params: {
    cost_mile_road: 0.1, cost_mile_rail: 0.05, min_cost_road: 25, min_cost_rail: 45,
    emission_road_lb: 0.4, emission_rail_lb: 0.05, speed_road: 60, speed_rail: 35,
    hours_day: 8, duration_rail_terminal: 1.5,
  },
  demand: Object.fromEntries(network.distribution_centers.map((d) => [d.ID, d.demand])),
  incoming_flow: Object.fromEntries(network.ports.map((p) => [p.ID, p.incoming_flow])),
};
const sum = (r: Record<string, number>) => Object.values(r).reduce((a, b) => a + b, 0);
const ports = network.ports.map((p) => p.ID);

test("港の停止と需要の倍率をどう組み合わせても、供給不足と誤判定しない（全15通り × 4倍率）", () => {
  for (const demandScale of DEMAND_SCALES) {
    for (let mask = 0; mask < (1 << ports.length) - 1; mask++) {
      const closedPorts = ports.filter((_, i) => (mask >> i) & 1);
      const s: Scenario = { ...DEFAULT_SCENARIO, closedPorts, demandScale };
      const e = applyScenario(base, s);
      assert.deepEqual(validate(e, "11").messages, [], `停止 ${closedPorts.join(",") || "なし"} ×${demandScale}`);
      assert.equal(scenarioError(network, base, s), null);
      // 停止した港の供給は0、合計は需要と一致する
      for (const id of closedPorts) assert.equal(e.incoming_flow[id], 0);
      assert.ok(Math.abs(sum(e.incoming_flow) - sum(e.demand)) < 1e-6);
    }
  }
});

test("停止した港の貨物は、ほかの港へ供給量の比率で振り替える", () => {
  const e = applyScenario(base, { ...DEFAULT_SCENARIO, closedPorts: ["pt_houston"] });
  const open = ports.filter((id) => id !== "pt_houston");
  const openTotal = open.reduce((a, id) => a + base.incoming_flow[id], 0);
  for (const id of open) {
    const expected = base.incoming_flow[id] * (1 + base.incoming_flow.pt_houston / openTotal);
    assert.ok(Math.abs(e.incoming_flow[id] - expected) < 1e-6, id);
  }
});

test("全港を停止すると、理由を返して計算させない", () => {
  const s = { ...DEFAULT_SCENARIO, closedPorts: ports };
  assert.match(scenarioError(network, base, s) ?? "", /すべての港/);
});

test("燃料・鉄道の遅延はパラメータだけを変え、シナリオなしなら入力は変わらない", () => {
  const e = applyScenario(base, { ...DEFAULT_SCENARIO, fuelScale: 1.3, railDelayDays: 1.5 });
  assert.ok(Math.abs(e.params.cost_mile_road - 0.13) < 1e-12);
  assert.equal(e.params.duration_rail_terminal, 3);
  assert.deepEqual(applyScenario(base, DEFAULT_SCENARIO), base);
});
