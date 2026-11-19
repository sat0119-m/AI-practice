"""道路網・鉄道網上の距離と経路の事前計算

09Multi_09Optimization_Epsilon_Constraint_Method_Python_Exercise_ja.py の
「データの準備と前処理」のうち、scgraph を使う重い処理（最短経路の計算）だけを
一度だけ実行し、結果を data/network.json に保存する。Web アプリ本体はこの JSON を
読むだけなので、scgraph（と大きな道路網・鉄道網データ）は不要になる。

保存する内容:
    - ノード（配送センター・港・鉄道ターミナル）
    - 各配送センターに最も近い鉄道ターミナル（測地線距離で判定）
    - アプリで使う区間（leg）ごとの距離 [マイル] と、地図に描くための経路座標
        * 港 → 配送センター（道路）
        * 港 → 配送センターの最寄り鉄道ターミナル（鉄道）
        * 最寄り鉄道ターミナル → 配送センター（道路）

実行方法（backend フォルダで。scgraph が Python 3.13 未満を要するため 3.12 を指定）::

    uv run --python 3.12 --with-requirements requirements-precompute.txt python precompute_network.py
"""

import csv
import json
from pathlib import Path

from geopy.distance import geodesic
from scgraph.geographs.us_freeway import us_freeway_geograph
from scgraph.geographs.north_america_rail import north_america_rail_geograph

DATA_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_FILE = DATA_DIR / "network.json"

# 地図に描く経路の座標は、この点数以下になるよう間引く（JSON を小さく保つため）
MAX_PATH_POINTS = 250


def read_csv(name):
    """data フォルダの CSV を辞書のリストとして読み込む（名前の前後の空白は除く）"""
    with open(DATA_DIR / name, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["name"] = row["name"].strip()
    return rows


def shortest_path(origin, destination, mode):
    """実際の道路網（mode='road'）または鉄道網（mode='rail'）上の最短経路を計算する

    スクリプトの shortest_path() と同じ計算。距離 [マイル] と経路座標 [[緯度, 経度], ...] を返す。
    """
    graph = north_america_rail_geograph if mode == "rail" else us_freeway_geograph
    output = graph.get_shortest_path(
        origin_node={"latitude": origin["lat"], "longitude": origin["lon"]},
        destination_node={"latitude": destination["lat"], "longitude": destination["lon"]},
        output_units="mi",
    )
    return output["length"], output["coordinate_path"]


def thin_path(path):
    """経路座標を MAX_PATH_POINTS 点以下に間引き、小数第4位で丸める（始点と終点は残す）"""
    step = max(1, -(-len(path) // MAX_PATH_POINTS))
    thinned = path[::step]
    if thinned[-1] != path[-1]:
        thinned.append(path[-1])
    return [[round(lat, 4), round(lon, 4)] for lat, lon in thinned]


def find_closest_rail_terminal(dc, rail_terminals):
    """配送センターに最も近い鉄道ターミナル（測地線距離が最小のもの）を返す"""
    return min(rail_terminals, key=lambda rt: geodesic((rt["lat"], rt["lon"]), (dc["lat"], dc["lon"])).mi)


def main():
    distribution_centers = read_csv("distribution_centers.csv")
    ports = read_csv("ports.csv")[0:4]          # ノートブックと同じく先頭4港を使う
    rail_terminals = read_csv("rail_terminals.csv")

    # 数値の列を変換
    for dc in distribution_centers:
        dc.update(lat=float(dc["lat"]), lon=float(dc["lon"]), demand=float(dc["demand"]))
    for port in ports:
        port.update(lat=float(port["lat"]), lon=float(port["lon"]), incoming_flow=float(port["incoming_flow"]))
    for rt in rail_terminals:
        rt.update(lat=float(rt["lat"]), lon=float(rt["lon"]))

    # 各配送センターの最寄り鉄道ターミナル
    for dc in distribution_centers:
        dc["rail_terminal"] = find_closest_rail_terminal(dc, rail_terminals)["ID"]

    rt_by_id = {rt["ID"]: rt for rt in rail_terminals}
    legs = []

    def add_leg(origin, destination, mode):
        distance, path = shortest_path(origin, destination, mode)
        legs.append({
            "from": origin["ID"], "to": destination["ID"], "mode": mode,
            "distance_mi": round(distance, 3), "path": thin_path(path),
        })
        print(f"  {mode:4s} {origin['ID']:>15s} -> {destination['ID']:<5s} {distance:9.1f} mi")

    print("港 → 配送センター（道路）")
    for port in ports:
        for dc in distribution_centers:
            add_leg(port, dc, "road")

    print("港 → 最寄り鉄道ターミナル（鉄道）")
    used_terminals = sorted({dc["rail_terminal"] for dc in distribution_centers}, key=lambda r: int(r[1:]))
    for port in ports:
        for r in used_terminals:
            add_leg(port, rt_by_id[r], "rail")

    print("最寄り鉄道ターミナル → 配送センター（道路）")
    for dc in distribution_centers:
        add_leg(rt_by_id[dc["rail_terminal"]], dc, "road")

    network = {
        "distribution_centers": distribution_centers,
        "ports": ports,
        "rail_terminals": rail_terminals,
        "legs": legs,
    }
    OUTPUT_FILE.write_text(json.dumps(network, ensure_ascii=False), encoding="utf-8")
    print(f"{len(legs)} 区間を {OUTPUT_FILE} に保存しました")


if __name__ == "__main__":
    main()
