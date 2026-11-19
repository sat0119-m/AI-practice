"""多目的最適化（ε制約法）の計算部分

09Multi_09Optimization_Epsilon_Constraint_Method_Python_Exercise_ja.py の
「アーク（コスト・排出量・所要時間）の計算」と「最適化モデル（AMPL）」を Web アプリ用に
まとめたもの。距離は precompute_network.py で事前計算した data/network.json から読む。

ε制約法（課題1）の実装:
    - 主目的を所要時間にした場合: 平均所要日数を最小化し、正規化した総コストに上限 ε をかける
          (総コスト - ユートピアコスト) / (ナディアコスト - ユートピアコスト) <= ε
    - 主目的をコストにした場合: 総コストを最小化し、正規化した平均所要日数に上限 ε をかける
    ε = 0 は副目的を最良（ユートピア値）に固定、ε = 1 は副目的の上限がナディア値になる。
"""

import json
import math
import os
import shutil
from functools import lru_cache
from pathlib import Path

from amplpy import AMPL, Environment

DATA_FILE = Path(__file__).resolve().parent / "data" / "network.json"

# 輸送モード（道路のみ / 鉄道＋道路）
TRANSPORTATION_MODES = ["road_only", "rail_road"]

# 使用するソルバー（AMPL に同梱の HiGHS）。環境変数 AMPL_SOLVER で変更できる（例: cbc）
SOLVER = os.environ.get("AMPL_SOLVER", "highs")

# AMPL 本体のよく使われるインストール先（AMPL_DIR も PATH も使えないときに順に探す）
AMPL_DIR_CANDIDATES = [
    r"C:\AMPL",                                  # Windows
    os.path.expanduser("~/ampl"),                # Windows / Linux / WSL（ホーム直下に展開した場合）
    os.path.expanduser("~/AMPL"),
    "/opt/ampl",                                 # Linux / WSL
    "/Applications/AMPL",                        # macOS
]

# ε の上限を少しだけ緩める割合（ε = 0 のとき数値誤差で実行不可能になるのを防ぐ）
CAP_TOLERANCE = 1e-7

# パラメータの初期値（スクリプトの値）
DEFAULT_PARAMS = {
    "cost_mile_road": 0.10,          # 道路輸送のトン・マイル当たりコスト
    "cost_mile_rail": 0.05,          # 鉄道輸送のトン・マイル当たりコスト
    "min_cost_road": 25.0,           # 道路のトン当たり最低コスト（距離に依存しない）
    "min_cost_rail": 45.0,           # 鉄道のトン当たり最低コスト（距離に依存しない）
    "emission_road_lb": 0.4,         # 道路輸送の CO2 排出量（トン・マイル当たりポンド）
    "emission_rail_lb": 0.05,        # 鉄道輸送の CO2 排出量（トン・マイル当たりポンド）
    "speed_road": 60.0,              # 道路輸送の平均速度（マイル/時）
    "speed_rail": 35.0,              # 鉄道輸送の平均速度（マイル/時）
    "hours_day": 8.0,                # 1日の稼働時間
    "duration_rail_terminal": 1.5,   # 鉄道ターミナルでの滞留時間（日）
}

TON_TO_POUNDS = 2204.62              # トンからポンドへの換算係数

# AMPL モデル
#
# スクリプトの AMPL_MODEL（決定変数・目的関数の式・制約）を、複数の問題（ブロック）を
# 1回のソルバー呼び出しでまとめて解けるよう、集合 K で添字付けしたもの。
# ブロック同士は変数も制約も共有しない独立な問題なので、目的関数の合計を最小化すると
# 各ブロックがそれぞれ最適になる。ソルバーは呼ぶたびに別プロセスとして起動され、
# その起動に1秒以上かかることがあるため、呼び出し回数を減らす目的でこうしている。
AMPL_MODEL = r"""
set K;                                          # ブロック（同時に解く問題）
set PORTS;                                      # 港
set DCS;                                        # 配送センター
set MODES;                                      # 輸送モード（road_only, rail_road）

param demand {DCS} >= 0;                        # 配送センターの需要
param incoming_flow {PORTS} >= 0;               # 港への流入量（供給量）
param total_demand > 0;                         # 総需要
param unit_cost {PORTS, DCS, MODES} >= 0;       # 輸送1トン当たりのコスト
param duration {PORTS, DCS, MODES} >= 0;        # 輸送所要時間（日）

param w_cost {K} default 0;                     # 各ブロックの目的関数における総コストの重み
param w_duration {K} default 0;                 # 各ブロックの目的関数における平均所要日数の重み
param cost_cap {K} default Infinity;            # ε制約: 総コストの上限
param duration_cap {K} default Infinity;        # ε制約: 平均所要日数の上限

# 決定変数: ブロック・港・配送センター・輸送モードごとのフロー（連続変数）
var flow {K, PORTS, DCS, MODES} >= 0;

# 総コストと平均所要日数（フローとコスト・所要時間の加重和）
var TotalCost {k in K} = sum {p in PORTS, d in DCS, t in MODES} unit_cost[p,d,t] * flow[k,p,d,t];
var AvgDuration {k in K} = sum {p in PORTS, d in DCS, t in MODES} duration[p,d,t] / total_demand * flow[k,p,d,t];

# 目的関数: 各ブロックで選んだ目的（重み 1）の合計を最小化
minimize Objective:
    sum {k in K} (w_cost[k] * TotalCost[k] + w_duration[k] * AvgDuration[k]);

# 各配送センターへの流入フローの合計が需要を満たす
subject to Demand {k in K, d in DCS}:
    sum {p in PORTS, t in MODES} flow[k,p,d,t] >= demand[d];

# 各港からの流出フローの合計が流入量（利用可能な供給量）以下
subject to Supply {k in K, p in PORTS}:
    sum {d in DCS, t in MODES} flow[k,p,d,t] <= incoming_flow[p];

# ε制約（上限が Infinity のブロックでは実質的に無効）
subject to CostCap {k in K}: TotalCost[k] <= cost_cap[k];
subject to DurationCap {k in K}: AvgDuration[k] <= duration_cap[k];
"""


class ModelError(ValueError):
    """入力が不正、またはモデルが解けないときの例外（API では 422 として返す）"""


# ===========================================================================
# データ
# ===========================================================================

@lru_cache(maxsize=1)
def load_network():
    """事前計算済みのネットワーク（ノード・区間の距離・経路座標）を読み込む"""
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def default_inputs():
    """画面の初期値（パラメータ・需要・供給量）を返す"""
    network = load_network()
    return {
        "params": dict(DEFAULT_PARAMS),
        "demand": {dc["ID"]: dc["demand"] for dc in network["distribution_centers"]},
        "incoming_flow": {p["ID"]: p["incoming_flow"] for p in network["ports"]},
    }


def compute_arc_data(params):
    """アークのコスト・排出量・所要時間の計算

    スクリプトの compute_unit_costs()・compute_unit_emissions()・compute_durations() と
    同じ式で、港 × 配送センター × 輸送モードごとの値を計算する。
    """
    network = load_network()
    distances = {(leg["from"], leg["to"], leg["mode"]): leg["distance_mi"] for leg in network["legs"]}
    emission_fact_road = params["emission_road_lb"] / TON_TO_POUNDS
    emission_fact_rail = params["emission_rail_lb"] / TON_TO_POUNDS
    per_day_road = params["speed_road"] * params["hours_day"]       # 道路の1日当たり走行距離
    per_day_rail = params["speed_rail"] * params["hours_day"]       # 鉄道の1日当たり走行距離

    unit_cost, unit_emissions, duration = {}, {}, {}
    for port in network["ports"]:
        s = port["ID"]
        for dc in network["distribution_centers"]:
            d, r = dc["ID"], dc["rail_terminal"]
            road = distances[s, d, "road"]                 # 港 → 配送センター（道路）
            rail_leg = distances[s, r, "rail"]             # 港 → 最寄り鉄道ターミナル（鉄道）
            road_leg = distances[r, d, "road"]             # 最寄り鉄道ターミナル → 配送センター（道路）

            # コスト（各区間に距離に依存しない最低コストを適用）
            unit_cost[s, d, "road_only"] = max(road * params["cost_mile_road"], params["min_cost_road"])
            unit_cost[s, d, "rail_road"] = (max(rail_leg * params["cost_mile_rail"], params["min_cost_rail"])
                                            + max(road_leg * params["cost_mile_road"], params["min_cost_road"]))

            # CO2 排出量（トン）
            unit_emissions[s, d, "road_only"] = road * emission_fact_road
            unit_emissions[s, d, "rail_road"] = rail_leg * emission_fact_rail + road_leg * emission_fact_road

            # 所要時間（日）
            duration[s, d, "road_only"] = road / per_day_road
            duration[s, d, "rail_road"] = rail_leg / per_day_rail + road_leg / per_day_road + params["duration_rail_terminal"]

    return unit_cost, unit_emissions, duration


# ===========================================================================
# 最適化（AMPL）
# ===========================================================================

def find_ampl_dir():
    """AMPL 本体（ライセンス付き）のフォルダを探して返す

    次の順に探し、最初に見つかったものを返す。見つからなければ例外を送出する。
        1. 環境変数 AMPL_DIR で指定したフォルダ
        2. PATH 上にある ampl（Windows では ampl.exe）のフォルダ
        3. AMPL_DIR_CANDIDATES のうち、ampl の実行ファイルがあるフォルダ
    """
    def has_ampl(folder):
        return any(os.path.isfile(os.path.join(folder, name)) for name in ("ampl", "ampl.exe"))

    env_dir = os.environ.get("AMPL_DIR")
    if env_dir:
        if not has_ampl(env_dir):
            raise FileNotFoundError(f"AMPL_DIR に ampl がありません: {env_dir}")
        return env_dir

    ampl_path = shutil.which("ampl")
    if ampl_path:
        return os.path.dirname(os.path.realpath(ampl_path))

    for folder in AMPL_DIR_CANDIDATES:
        if has_ampl(folder):
            return folder

    raise FileNotFoundError("AMPL が見つかりません。環境変数 AMPL_DIR に AMPL 本体のフォルダを指定してください。")


class EpsilonModel:
    """データを渡した AMPL モデル（1リクエストにつき1つ作り、with 文で使う）"""

    def __init__(self, params, demand, incoming_flow):
        network = load_network()
        self.ports = [p["ID"] for p in network["ports"]]
        self.dcs = [dc["ID"] for dc in network["distribution_centers"]]

        # 入力の確認
        for key in DEFAULT_PARAMS:
            value = params.get(key)
            if value is None or not math.isfinite(value) or value < 0:
                raise ModelError(f"パラメータ {key} は 0 以上の数値にしてください")
        for key in ("speed_road", "speed_rail", "hours_day"):
            if params[key] <= 0:
                raise ModelError(f"パラメータ {key} は 0 より大きい値にしてください")
        demand = {d: float(demand.get(d, 0)) for d in self.dcs}
        incoming_flow = {p: float(incoming_flow.get(p, 0)) for p in self.ports}
        if any(v < 0 for v in [*demand.values(), *incoming_flow.values()]):
            raise ModelError("需要と供給量は 0 以上にしてください")
        self.total_demand = sum(demand.values())
        total_supply = sum(incoming_flow.values())
        if self.total_demand <= 0:
            raise ModelError("需要の合計が 0 です")
        if total_supply < self.total_demand - 1e-9:
            raise ModelError(f"供給量の合計（{total_supply:,.0f}）が需要の合計（{self.total_demand:,.0f}）より少ないため、解がありません")

        self.unit_cost, self.unit_emissions, self.duration = compute_arc_data(params)

        # AMPL の起動とモデルの読み込み、データの受け渡し
        self.ampl = AMPL(Environment(find_ampl_dir()))
        self.ampl.option["solver"] = SOLVER
        self.ampl.eval(AMPL_MODEL)
        self.ampl.set["PORTS"] = self.ports
        self.ampl.set["DCS"] = self.dcs
        self.ampl.set["MODES"] = TRANSPORTATION_MODES
        self.ampl.param["demand"] = demand
        self.ampl.param["incoming_flow"] = incoming_flow
        self.ampl.param["total_demand"] = self.total_demand
        self.ampl.param["unit_cost"] = self.unit_cost
        self.ampl.param["duration"] = self.duration

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.ampl.close()

    def solve_blocks(self, problems):
        """複数の問題を1回のソルバー呼び出しでまとめて解く

        problems は (目的, コスト上限, 所要日数上限) のリスト。目的は 'cost' か 'duration'。
        各問題の解（評価指標と輸送フロー）を同じ順のリストで返す。
        """
        keys = [f"k{i}" for i in range(len(problems))]
        self.ampl.eval("reset data K, w_cost, w_duration, cost_cap, duration_cap;")
        self.ampl.set["K"] = keys
        self.ampl.param["w_cost"] = {k: float(obj == "cost") for k, (obj, _, _) in zip(keys, problems)}
        self.ampl.param["w_duration"] = {k: float(obj == "duration") for k, (obj, _, _) in zip(keys, problems)}
        cost_caps = {k: cap for k, (_, cap, _) in zip(keys, problems) if math.isfinite(cap)}
        duration_caps = {k: cap for k, (_, _, cap) in zip(keys, problems) if math.isfinite(cap)}
        if cost_caps:
            self.ampl.param["cost_cap"] = cost_caps
        if duration_caps:
            self.ampl.param["duration_cap"] = duration_caps

        self.ampl.solve()
        if self.ampl.solve_result != "solved":
            raise ModelError(f"最適解が得られませんでした（solve_result = {self.ampl.solve_result}）")

        flows_by_key = {k: [] for k in keys}
        for (k, p, d, t), v in self.ampl.var["flow"].to_dict().items():
            if v > 1e-6:
                flows_by_key[k].append({"port": p, "dc": d, "mode": t, "flow": v})
        return [self._evaluate(flows_by_key[k]) for k in keys]

    def _evaluate(self, flows):
        """輸送フローから評価指標（総コスト・平均所要日数・CO2・輸送モードの割合）を計算する"""
        def total(values):
            return sum(values[f["port"], f["dc"], f["mode"]] * f["flow"] for f in flows)

        road = sum(f["flow"] for f in flows if f["mode"] == "road_only")
        rail = sum(f["flow"] for f in flows if f["mode"] == "rail_road")
        return {
            "cost": total(self.unit_cost),
            "duration": total(self.duration) / self.total_demand,
            "emissions": total(self.unit_emissions),
            "share_road": 100 * road / self.total_demand,
            "share_rail": 100 * rail / self.total_demand,
            "flows": flows,
        }

    def find_utopia_nadir(self):
        """ユートピア点とナディア点の探索

        コストを最小化してコストのユートピア点を、所要時間を最小化して所要時間の
        ユートピア点を求める（1回目の呼び出し）。ナディア点は、片方を最良値に固定したうえで
        もう片方を最小化して求める（2回目の呼び出し。辞書式最適化）。単に片方だけを
        最小化すると、最適解が複数あるときもう片方が必要以上に悪い解が選ばれ、
        ナディア点がずれることがあるため。
        """
        inf = math.inf
        min_cost, min_duration = self.solve_blocks([("cost", inf, inf), ("duration", inf, inf)])
        utopia_cost, utopia_duration = min_cost["cost"], min_duration["duration"]
        lex_cost, lex_duration = self.solve_blocks([
            ("duration", utopia_cost * (1 + CAP_TOLERANCE), inf),     # コストを最良に固定して所要時間を最小化
            ("cost", inf, utopia_duration * (1 + CAP_TOLERANCE)),     # 所要時間を最良に固定してコストを最小化
        ])
        return {
            "utopia_cost": utopia_cost, "nadir_cost": lex_duration["cost"],
            "utopia_duration": utopia_duration, "nadir_duration": lex_cost["duration"],
        }

    def solve_epsilon(self, primary, epsilons, bounds):
        """ε制約法による求解（課題1）

        primary='duration': 平均所要日数を最小化し、正規化した総コストを ε 以下に制限する。
        primary='cost'    : 総コストを最小化し、正規化した平均所要日数を ε 以下に制限する。
        ε は 0〜1（0 = 副目的をユートピア値に固定、1 = 副目的の上限がナディア値）。
        複数の ε をまとめて1回のソルバー呼び出しで解き、解のリストを返す。
        """
        if any(not 0 <= e <= 1 for e in epsilons):
            raise ModelError("ε は 0〜1 の範囲で指定してください")
        if primary not in ("duration", "cost"):
            raise ModelError(f"主目的は 'duration' か 'cost' を指定してください: {primary}")

        secondary = "cost" if primary == "duration" else "duration"
        lo, hi = bounds[f"utopia_{secondary}"], bounds[f"nadir_{secondary}"]
        caps = [lo + e * (hi - lo) for e in epsilons]
        relaxed = [cap + abs(cap) * CAP_TOLERANCE for cap in caps]
        if primary == "duration":
            problems = [("duration", cap, math.inf) for cap in relaxed]
        else:
            problems = [("cost", math.inf, cap) for cap in relaxed]
        solutions = self.solve_blocks(problems)
        return [{"epsilon": e, "cap": cap, **s} for e, cap, s in zip(epsilons, caps, solutions)]


def compute_frontier(params, demand, incoming_flow, primary, n_points, grid_steps=100):
    """パレートフロントの計算

    ユートピア点とナディア点を求め、その間を等間隔に分けた n_points 個の ε で解く（グラフの点）。
    同じソルバー呼び出しで、ε を 1/grid_steps 刻みにした解（スライダー用）もまとめて解く。
    ソルバーの呼び出しは合計3回（ユートピア点・ナディア点・全 ε 点）。
    """
    if not 2 <= n_points <= 50:
        raise ModelError("点の数は 2〜50 の範囲で指定してください")
    point_eps = [i / (n_points - 1) for i in range(n_points)]
    grid_eps = [i / grid_steps for i in range(grid_steps + 1)]
    all_eps = sorted({round(e, 12) for e in point_eps + grid_eps})
    with EpsilonModel(params, demand, incoming_flow) as model:
        bounds = model.find_utopia_nadir()
        solutions = {round(s["epsilon"], 12): s for s in model.solve_epsilon(primary, all_eps, bounds)}
    return {
        "bounds": bounds,
        "points": [solutions[round(e, 12)] for e in point_eps],
        "grid": [solutions[round(e, 12)] for e in grid_eps],
    }


def solve_single(params, demand, incoming_flow, primary, epsilon, bounds=None):
    """指定した ε で1回だけ解く（bounds が無ければユートピア点・ナディア点から求める）"""
    with EpsilonModel(params, demand, incoming_flow) as model:
        if bounds is None:
            bounds = model.find_utopia_nadir()
        return {"bounds": bounds, "solution": model.solve_epsilon(primary, [epsilon], bounds)[0]}
