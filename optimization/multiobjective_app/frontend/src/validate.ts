import type { Inputs, Params } from "./types";

/** パラメータの名前と、許される範囲 */
export const PARAM_RULES: Record<keyof Params, { label: string; positive?: boolean; max?: number }> = {
  cost_mile_road: { label: "道路のコスト" },
  cost_mile_rail: { label: "鉄道のコスト" },
  min_cost_road: { label: "道路の最低コスト" },
  min_cost_rail: { label: "鉄道の最低コスト" },
  speed_road: { label: "道路の平均速度", positive: true },
  speed_rail: { label: "鉄道の平均速度", positive: true },
  hours_day: { label: "1日の稼働時間", positive: true, max: 24 },
  duration_rail_terminal: { label: "鉄道ターミナルでの滞留" },
  emission_road_lb: { label: "道路の CO2 排出係数" },
  emission_rail_lb: { label: "鉄道の CO2 排出係数" },
};

export const N_POINTS_MIN = 5;
export const N_POINTS_MAX = 21;

export interface Validation {
  /** 入力欄ごとのエラー（キーはパラメータ名、"demand:<ID>"、"supply:<ID>"、"nPoints"） */
  fields: Record<string, string>;
  /** 計算ボタンの近くに出す、全体のエラー */
  messages: string[];
}

/** 画面の入力を確認し、計算できない理由を日本語で返す（バックエンドに送る前に確認する） */
export function validate(inputs: Inputs, nPointsText: string): Validation {
  const fields: Record<string, string> = {};

  for (const [key, rule] of Object.entries(PARAM_RULES) as [keyof Params, (typeof PARAM_RULES)[keyof Params]][]) {
    const v = inputs.params[key];
    if (!Number.isFinite(v)) fields[key] = `${rule.label}を入力してください`;
    else if (rule.positive && v <= 0) fields[key] = `${rule.label}は 0 より大きい値にしてください`;
    else if (v < 0) fields[key] = `${rule.label}は 0 以上にしてください`;
    else if (rule.max !== undefined && v > rule.max) fields[key] = `${rule.label}は ${rule.max} 以下にしてください`;
  }

  for (const [id, v] of Object.entries(inputs.demand)) {
    if (!Number.isFinite(v) || v < 0) fields[`demand:${id}`] = "0 以上の数値";
  }
  for (const [id, v] of Object.entries(inputs.incoming_flow)) {
    if (!Number.isFinite(v) || v < 0) fields[`supply:${id}`] = "0 以上の数値";
  }

  const n = Number(nPointsText);
  if (nPointsText.trim() === "" || !Number.isInteger(n) || n < N_POINTS_MIN || n > N_POINTS_MAX) {
    fields.nPoints = `点の数は ${N_POINTS_MIN}〜${N_POINTS_MAX} の整数にしてください`;
  }

  const messages = Object.entries(fields)
    .filter(([k]) => !k.startsWith("demand:") && !k.startsWith("supply:"))
    .map(([, m]) => m);
  if (Object.keys(fields).some((k) => k.startsWith("demand:"))) messages.push("需要に 0 以上の数値でない欄があります");
  if (Object.keys(fields).some((k) => k.startsWith("supply:"))) messages.push("供給量に 0 以上の数値でない欄があります");

  const total = (r: Record<string, number>) => Object.values(r).reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0);
  const totalDemand = total(inputs.demand);
  const totalSupply = total(inputs.incoming_flow);
  if (totalDemand <= 0) messages.push("需要の合計が 0 です");
  else if (totalSupply < totalDemand) messages.push("供給量の合計が需要の合計より少ないため、計算できません");

  return { fields, messages };
}
