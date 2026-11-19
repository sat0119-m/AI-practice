// バックエンド（FastAPI）とやり取りするデータの型

export type Mode = "road_only" | "rail_road";
export type Primary = "duration" | "cost";

export interface DistributionCenter {
  ID: string;
  name: string;
  lat: number;
  lon: number;
  demand: number;
  rail_terminal: string; // 最寄りの鉄道ターミナルID
}

export interface Port {
  ID: string;
  name: string;
  lat: number;
  lon: number;
  incoming_flow: number;
}

export interface RailTerminal {
  ID: string;
  name: string;
  lat: number;
  lon: number;
}

/** 事前計算済みの区間（道路 or 鉄道）と、地図に描く経路座標 [[緯度, 経度], ...] */
export interface Leg {
  from: string;
  to: string;
  mode: "road" | "rail";
  distance_mi: number;
  path: [number, number][];
}

export interface Params {
  cost_mile_road: number;
  cost_mile_rail: number;
  min_cost_road: number;
  min_cost_rail: number;
  emission_road_lb: number;
  emission_rail_lb: number;
  speed_road: number;
  speed_rail: number;
  hours_day: number;
  duration_rail_terminal: number;
}

/** 画面から変えられる入力 */
export interface Inputs {
  params: Params;
  demand: Record<string, number>;
  incoming_flow: Record<string, number>;
}

export interface Network {
  distribution_centers: DistributionCenter[];
  ports: Port[];
  rail_terminals: RailTerminal[];
  legs: Leg[];
  defaults: Inputs;
}

export interface Flow {
  port: string;
  dc: string;
  mode: Mode;
  flow: number;
}

/** ε制約法の1つの解 */
export interface Solution {
  epsilon: number;
  cap: number; // 副目的の上限（実際の値）
  cost: number;
  duration: number;
  emissions: number;
  share_road: number;
  share_rail: number;
  flows: Flow[];
}

/** ユートピア点とナディア点 */
export interface Bounds {
  utopia_cost: number;
  nadir_cost: number;
  utopia_duration: number;
  nadir_duration: number;
}

export interface FrontierResult {
  bounds: Bounds;
  points: Solution[]; // グラフに描く点（n_points 個）
  grid: Solution[]; // スライダー用（ε = 0, 0.01, ..., 1 の 101 個）
}
