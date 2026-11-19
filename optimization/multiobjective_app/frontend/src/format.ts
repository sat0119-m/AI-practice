// 数値の表示形式と、グラフ・地図の色

export const fmtCost = (v: number) => `$${Math.round(v).toLocaleString("ja-JP")}`;
export const fmtCostShort = (v: number) => `$${Number((v / 1e6).toFixed(3))}M`;
export const fmtDays = (v: number) => `${v.toFixed(2)} 日`;
export const fmtCo2 = (v: number) => `${Math.round(v).toLocaleString("ja-JP")} t`;
export const fmtTon = (v: number) => `${Math.round(v).toLocaleString("ja-JP")} t`;
export const fmtPct = (v: number) => `${v.toFixed(1)}%`;

// 輸送モードの色（カテゴリ色。道路 = オレンジ、鉄道 = アクア）
export const ROAD_COLOR = "#eb6834";
export const RAIL_COLOR = "#1baf7a";

// CO2 の量を表す単色（青）の段階色。少ない → 薄い、多い → 濃い
const CO2_RAMP = ["#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281"];

export function co2Color(value: number, min: number, max: number): string {
  const t = max > min ? (value - min) / (max - min) : 0.5;
  const i = Math.min(CO2_RAMP.length - 1, Math.max(0, Math.round(t * (CO2_RAMP.length - 1))));
  return CO2_RAMP[i];
}

export const CO2_GRADIENT = `linear-gradient(to right, ${CO2_RAMP.join(", ")})`;
