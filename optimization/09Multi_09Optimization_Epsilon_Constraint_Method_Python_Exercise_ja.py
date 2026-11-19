"""SCM.275x - 発展サプライチェーンシステム計画とネットワーク設計

多目的最適化 - ε制約法 - 演習
(Multi-Objective Optimization - Epsilon Constraint Method - Exercise)

ノートブック「09Multi_09Optimization_Epsilon_Constraint_Method_Python_Exercise.ipynb」の
コードセルを抽出して単一のPythonスクリプトにまとめたもの。各セル直前の説明は、
対応する関数・クラスのDocStringに日本語で記載している。

最適化は元のノートブックの gurobipy（mypulp）ではなく AMPL で行う。モデルは本スクリプト内の
AMPL_MODEL に記述し、集合・パラメータは amplpy で渡す。ソルバーは HiGHS を使う。
AMPL 本体（ライセンス付き）の場所は find_ampl_dir() を参照。

必要なパッケージ（必要に応じてインストール）::

    pip install amplpy                 # AMPL の Python API
    pip install pandas                # データ分析・操作用ライブラリ Pandas
    pip install folium                 # インタラクティブマップ作成用ライブラリ Folium
    pip install geopy                  # 距離計算・地理データ処理用ライブラリ Geopy
    pip install scgraph==2.1.0         # 実際の輸送ネットワーク上の経路・距離を計算するパッケージ
    pip install scgraph_data==2.0.0    # 同上（ネットワークデータ）
"""

# 必要なパッケージをすべてインポート

import os                             # ファイルパスと環境変数の操作用
import shutil                         # PATH 上の ampl 実行ファイルの探索用
import pandas as pd                   # データの操作と分析用
from amplpy import AMPL, Environment  # AMPL の Python API（データは amplpy で AMPL に渡す）
import folium                        # インタラクティブマップ作成用
import folium.plugins as plugins      # folium 用追加プラグイン
from geopy.distance import geodesic   # 2地点間の測地線距離計算用

import scgraph                                                                # 実際の輸送ネットワーク上の経路・距離計算用
from scgraph.geographs.us_freeway import us_freeway_geograph                  # 米国高速道路網のデータ（道路の経路・距離用）
from scgraph.geographs.north_america_rail import north_america_rail_geograph  # 鉄道路線のデータ（鉄道の経路・距離用）
import matplotlib.pyplot as plt                                               # 描画ライブラリ


# ===========================================================================
# ヘルパー関数 (Helper functions)
# ===========================================================================

def plot_nodes(map,                         # ノードをプロットする Folium マップオブジェクト
               nodes,                       # ノードオブジェクトの辞書（各ノードは緯度や経度などの属性を含む）
               icon,                        # 地図上のマーカーに使用するアイコン記号
               active_color,                # アクティブなノードのマーカーアイコンの色
               background_color,            # マーカーアイコンの背景色
               inactive_color='grey',       # 非アクティブなノードのマーカーアイコンの色
               ):
    """地図上へのノードのプロット

    folium を使って地図上にノードをプロットする関数。
    """
    # 辞書内の各ノードをループ処理
    for node in nodes.values():

        # folium マーカーを作成
        marker = folium.Marker(
            location=[node.lat, node.lon],              # マーカーの位置を設定
            popup=(node.ID + "-" + node.name),          # ノードIDと名前のポップアップを作成
            icon=plugins.BeautifyIcon(                  # マーカーアイコンを作成
                icon=icon,
                icon_shape="circle",
                text_color=active_color if node.active == True else inactive_color,
                border_color=active_color if node.active == True else inactive_color,
                background_color=background_color,
            )
        )

        # folium マーカーを地図に追加
        marker.add_to(map)


def shortest_path(origin, destination, mode, result, unit='mi'):
    """実際の道路網または鉄道網上での2地点間の最短経路の計算

    mode に 'rail'（鉄道）または 'road'（道路）を指定し、result に 'distance' を
    指定すると経路の総距離を、'coordinate_path' を指定すると経路の座標列を返す。
    """
    # 出発地と目的地のオブジェクトから座標を取り出す
    origin_coordinates = (origin.lat, origin.lon)
    destination_coordinates = (destination.lat, destination.lon)

    # 鉄道網上の最短経路を計算
    if mode == 'rail':
        output = north_america_rail_geograph.get_shortest_path(
            origin_node={"latitude": origin.lat, "longitude": origin.lon},
            destination_node={"latitude": destination.lat, "longitude": destination.lon},
            output_units=unit
        )

    # 道路網上の最短経路を計算
    elif mode == 'road':
        output = us_freeway_geograph.get_shortest_path(
            origin_node={"latitude": origin.lat, "longitude": origin.lon},
            destination_node={"latitude": destination.lat, "longitude": destination.lon},
            output_units=unit
        )

    # 経路の総距離を返す
    if result == 'distance':
        return output['length']

    # 経路を表す座標列を返す
    elif result == 'coordinate_path':
        return output['coordinate_path']


def adjustArcPath(path):
    """地球全体で経度が連続するようにアーク経路を調整する

    隣接する点の経度差が 180 度を超えないように、360 度単位で経度を補正する。
    """
    for index in range(1, len(path)):
        x = path[index][1]
        prevX = path[index - 1][1]
        path[index][1] = x - (round((x - prevX) / 360, 0) * 360)
    return path


def modifyArcPathLong(points, amount):
    """経路上の全点の経度を amount だけずらした経路を返す"""
    return [[i[0], i[1] + amount] for i in points]


def getCleanArcPath(path):
    """経度の連続性を確保したアーク経路を返す

    調整済みの経路と、それを ±360 度・±720 度ずらした経路のリストを返す
    （地図を横にスクロールしても経路が表示されるようにするため）。
    """
    path = adjustArcPath(path)
    return [
        path,
        modifyArcPathLong(path, 360),
        modifyArcPathLong(path, -360),
        modifyArcPathLong(path, 720),
        modifyArcPathLong(path, -720)
    ]


def plot_real_flows(map,               # フローをプロットする Folium マップオブジェクト
                    vars,              # 最適解の輸送量の辞書 {(港, DC, 輸送モード): 輸送量}
                    nodes,             # ノードオブジェクトの辞書
                    max_width=30,      # フローの最大線幅（デフォルトは 30）
                    opacity=0.5):      # 線の不透明度（デフォルトは 0.5）
    """地図上への（実ネットワーク上の）フローのプロット

    最適化モデルの結果に基づき、実際の道路網・鉄道網上のフローを Folium マップ上に
    プロットする。道路のみ（'road_only'）はオレンジ色、鉄道区間は緑色で描画する。
    """
    # 線幅を正規化するためにフローの最大値を求める
    max_val = max([var for (node1_key, node2_key, t), var in vars.items()])

    # フロー決定変数を反復処理（キーはノードの組と使用する輸送モードを表す）
    for (node1_key, node2_key, t), var in vars.items():

        # 正のフローのみプロット
        if var > 0:

            # 輸送モードが道路のみの場合、地図に1本のポリラインを追加
            if t == 'road_only':

                # ノードの組の道路による最短経路の座標を取得
                path = shortest_path(nodes[node1_key], nodes[node2_key], mode='road', result='coordinate_path')

                # フロー値に比例した線幅で道路経路をポリラインとして地図に追加
                folium.PolyLine(getCleanArcPath(path),
                                color='orange',
                                weight=var / max_val * max_width,   # 線幅をフローの最大値で正規化
                                opacity=opacity).add_to(map)

            # 輸送モードが鉄道と道路の組合せの場合、地図に2本のポリラインを追加
            elif t == 'rail_road':

                # 港（node1_key）から鉄道ターミナル（node2_key に対応する鉄道ターミナル）までの鉄道による最短経路の座標を取得
                rail_path = shortest_path(nodes[node1_key], nodes[node2_key].rail_terminal, mode='rail', result='coordinate_path')

                # フロー値に比例した線幅で鉄道経路をポリラインとして地図に追加
                folium.PolyLine(getCleanArcPath(rail_path),
                                color='green',
                                weight=var / max_val * max_width,   # 線幅をフローの最大値で正規化
                                opacity=opacity).add_to(map)

                # 鉄道ターミナル（node2_key に対応）から配送センター（node2_key）までの最短経路の座標を取得
                road_path = shortest_path(nodes[node2_key].rail_terminal, nodes[node2_key], mode='road', result='coordinate_path')

                # フロー値に比例した線幅で道路経路をポリラインとして地図に追加
                folium.PolyLine(getCleanArcPath(road_path),
                                color='orange',
                                weight=var / max_val * max_width,   # 線幅をフローの最大値で正規化
                                opacity=opacity).add_to(map)


def find_closest_rail_terminal(dc,                # 配送センター（DC）オブジェクト
                               rail_terminals):   # 鉄道ターミナルの辞書
    """指定された配送センターに最も近い鉄道ターミナルを求める

    測地線距離（マイル）が最小となる鉄道ターミナルオブジェクトを返す。
    """
    # 配送センターと各鉄道ターミナルの距離を格納する辞書を作成
    distances = dict()

    # 辞書内のすべての鉄道ターミナルについて測地線距離を計算
    for rt in rail_terminals.values():
        distances[rt.ID] = geodesic((rt.lat, rt.lon), (dc.lat, dc.lon)).mi

    # 配送センターまでの距離が最小となる鉄道ターミナルを求める
    closest_terminal_id = min(distances.items(), key=lambda x: x[1])[0]

    # 最も近いターミナルIDから鉄道ターミナルオブジェクトを取得
    closest_terminal = rail_terminals[closest_terminal_id]

    # 最も近い鉄道ターミナルオブジェクトを返す
    return closest_terminal


# ===========================================================================
# データの準備と前処理 (Data setup and preprocessing) - ノード
# ===========================================================================

def load_distribution_centers():
    """入力ファイルの読み込み（配送センター）

    配送センターのデータを CSV から pandas の DataFrame に読み込む。
    """
    # 配送センターのデータを含むファイル
    dcs_data_file = 'https://raw.githubusercontent.com/scm275/problem_sets_scm275/main/multiple_objectives/distribution_centers.csv'

    # 配送センターのデータを pandas の DataFrame に読み込む
    distribution_centers_df = pd.read_csv(dcs_data_file)

    # データ確認のため DataFrame の先頭数行を表示
    print(distribution_centers_df.head())
    return distribution_centers_df


def load_ports():
    """入力ファイルの読み込み（港）

    港のデータを CSV から pandas の DataFrame に読み込む（先頭4港のみ使用）。
    """
    # 港のデータを含むファイル
    ports_data_file = 'https://raw.githubusercontent.com/scm275/problem_sets_scm275/main/multiple_objectives/ports.csv'

    # 港のデータを pandas の DataFrame に読み込む
    ports_df = pd.read_csv(ports_data_file)
    ports_df = ports_df[0:4]

    # データ確認のため DataFrame の先頭数行を表示
    print(ports_df.head())
    return ports_df


def load_rail_terminals():
    """入力ファイルの読み込み（鉄道ターミナル）

    鉄道ターミナルのデータを CSV から pandas の DataFrame に読み込む。
    """
    # 鉄道ターミナルのデータを含むファイル
    rail_terminal_data_file = 'https://raw.githubusercontent.com/scm275/problem_sets_scm275/main/multiple_objectives/rail_terminals.csv'

    # 鉄道ターミナルのデータを pandas の DataFrame に読み込む
    rail_terminal_df = pd.read_csv(rail_terminal_data_file)

    # データ確認のため DataFrame の先頭数行を表示
    print(rail_terminal_df.head())
    return rail_terminal_df


class DistributionCenter():
    """配送センター（Distribution Center）オブジェクトを表すクラス"""

    def __init__(self, ID, name, demand, lat, lon):
        self.ID = ID              # 配送センターのID
        self.name = name          # 配送センターの名前
        self.demand = demand      # 配送センターの需要
        self.lat = lat            # 配送センターの緯度
        self.lon = lon            # 配送センターの経度

        self.active = True        # ノードをアクティブとして初期化


class Port():
    """港（Port）オブジェクトを表すクラス"""

    def __init__(self, ID, name, incoming_flow, lat, lon):
        self.ID = ID                          # 港のID
        self.name = name                      # 港の名前
        self.incoming_flow = incoming_flow    # 港への流入量（すなわち供給量）
        self.lat = lat                        # 港の緯度
        self.lon = lon                        # 港の経度

        self.active = True                    # ノードをアクティブとして初期化


class RailTerminal():
    """鉄道ターミナル（Rail Terminal）オブジェクトを表すクラス"""

    def __init__(self, ID, name, lat, lon):
        self.ID = ID                  # 鉄道ターミナルのID
        self.name = name              # 鉄道ターミナルの名前
        self.lat = lat                # 鉄道ターミナルの緯度
        self.lon = lon                # 鉄道ターミナルの経度

        self.active = True            # ノードをアクティブとして初期化


def create_nodes(distribution_centers_df, ports_df, rail_terminal_df):
    """ノードオブジェクトの作成

    配送センター・港・鉄道ターミナルのオブジェクトを作成し、すべてを1つの
    ノード辞書にまとめる。あわせて総需要を計算して表示する。
    """
    nodes = dict()

    # 配送センターオブジェクトの辞書を作成
    distribution_centers = dict()
    for i, row in distribution_centers_df.iterrows():
        distribution_centers[row['ID']] = DistributionCenter(ID=row['ID'],             # 配送センターのID
                                                             name=row['name'],         # 配送センターの名前
                                                             lat=row['lat'],           # 配送センターの緯度
                                                             lon=row['lon'],           # 配送センターの経度
                                                             demand=row['demand'])     # 配送センターの需要

    # 配送センターの辞書を既存のノード辞書に統合
    nodes = {**nodes, **distribution_centers}

    # 総需要の値を求める
    total_demand = sum([dc.demand for dc in distribution_centers.values()])

    # 別の方法:
    total_demand = 0
    for d, distribution_center in distribution_centers.items():
        total_demand = total_demand + distribution_center.demand

    print('Total demand: ', total_demand)

    # 港オブジェクトの辞書を作成
    ports = dict()
    for i, row in ports_df.iterrows():
        ports[row['ID']] = Port(ID=row['ID'],                               # 港のID
                                name=row['name'],                           # 港の名前
                                lat=row['lat'],                             # 港の緯度
                                lon=row['lon'],                             # 港の経度
                                incoming_flow=row['incoming_flow'])         # 港への流入量

    # 港の辞書を既存のノード辞書に統合
    nodes = {**nodes, **ports}

    # 鉄道ターミナルオブジェクトの辞書を作成
    rail_terminals = dict()
    for i, row in rail_terminal_df.iterrows():
        rail_terminals[row['ID']] = RailTerminal(ID=row['ID'],              # 鉄道ターミナルのID
                                                 name=row['name'],          # 鉄道ターミナルの名前
                                                 lat=row['lat'],            # 鉄道ターミナルの緯度
                                                 lon=row['lon'])            # 鉄道ターミナルの経度

    # 鉄道ターミナルの辞書を既存のノード辞書に統合
    nodes = {**nodes, **rail_terminals}

    return nodes, distribution_centers, ports, rail_terminals, total_demand


def assign_closest_rail_terminals(distribution_centers, rail_terminals):
    """配送センターに最も近い鉄道ターミナルの探索

    各配送センターに最も近い鉄道ターミナルを求め、配送センターの
    rail_terminal 属性に割り当てる。
    """
    # 辞書内のすべての配送センターオブジェクトを反復処理
    for d in distribution_centers.values():

        # 現在の配送センターに最も近い鉄道ターミナルを求め、配送センターの rail_terminal 属性に割り当てる
        d.rail_terminal = find_closest_rail_terminal(d, rail_terminals)


def visualize_nodes(distribution_centers, ports, rail_terminals):
    """ノードオブジェクトの可視化

    配送センター・港・鉄道ターミナルの位置を地図上にプロットした folium マップを返す。
    """
    # 新しい地図を作成
    map = folium.Map([40, -100.0], zoom_start=5)

    # 配送センターの位置を倉庫アイコン、緑色、黄色背景でプロット
    plot_nodes(map=map, nodes=distribution_centers, icon='warehouse', active_color='green', background_color='yellow')

    # 港の位置を錨アイコン、青色、白背景でプロット
    plot_nodes(map=map, nodes=ports, icon='anchor', active_color='blue', background_color='white')

    # 鉄道ターミナルの位置を列車アイコン、オレンジ色、黄色背景でプロット
    plot_nodes(map=map, nodes=rail_terminals, icon='train', active_color='orange', background_color='yellow')

    # 地図の視覚化を向上させるためのタイルレイヤーを追加（cartodbpositron テーマ）
    folium.TileLayer('cartodbpositron').add_to(map)

    # すべてのデータをプロットした地図を返す
    return map


# ===========================================================================
# データの準備と前処理 (Data setup and preprocessing) - アーク
# ===========================================================================

def compute_distances(ports, distribution_centers, rail_terminals):
    """前処理ステップ - 距離の計算

    輸送モード別に、港→配送センター（道路）、港→鉄道ターミナル（鉄道）、
    鉄道ターミナル→配送センター（道路）の距離（マイル）を計算する。
    """
    # 輸送モード別の距離を格納する辞書を初期化
    distances = dict()

    # 港と配送センター間の道路距離を計算
    for s, port in ports.items():
        for d, dc in distribution_centers.items():
            distances[s, d, 'road'] = shortest_path(port, dc, 'road', 'distance', unit='mi')

    # 港と鉄道ターミナル間の鉄道距離を計算
    for s, port in ports.items():
        for r, rail_terminal in rail_terminals.items():
            distances[s, r, 'rail'] = shortest_path(port, rail_terminal, 'rail', 'distance', unit='mi')

    # 鉄道ターミナルと配送センター間の道路距離を計算
    for r, rail_terminal in rail_terminals.items():
        for d, dc in distribution_centers.items():
            distances[r, d, 'road'] = shortest_path(rail_terminal, dc, 'road', 'distance', unit='mi')

    return distances


def compute_unit_costs(ports, distribution_centers, distances):
    """アークコストの計算

    道路のみ（'road_only'）と鉄道＋道路（'rail_road'）の各輸送モードについて、
    トン当たり輸送コストを計算する。各区間には距離に依存しない最低コストを適用する。
    """
    cost_mile_road = 0.10                         # 道路輸送のトン・マイル当たりコスト
    cost_mile_rail = 0.05                         # 鉄道輸送のトン・マイル当たりコスト

    min_cost_road = 25                            # 道路のトン当たり最低コスト（距離に依存しない）
    min_cost_rail = 45                            # 鉄道のトン当たり最低コスト（距離に依存しない）

    unit_cost = dict()                            # 輸送コストを格納する辞書

    # 各港と配送センターの組について輸送コストを計算
    for s, port in ports.items():
        for d, dc in distribution_centers.items():
            # 道路のみの輸送コストを計算（最低コストを考慮）
            unit_cost[s, d, 'road_only'] = max(distances[s, d, 'road'] * cost_mile_road, min_cost_road)

            # 鉄道＋道路の組合せの輸送コストを計算（両モードの最低コストを考慮）
            cost_rail_leg = max(distances[s, distribution_centers[d].rail_terminal.ID, 'rail'] * cost_mile_rail, min_cost_rail)
            cost_road_leg = max(distances[distribution_centers[d].rail_terminal.ID, d, 'road'] * cost_mile_road, min_cost_road)
            unit_cost[s, d, 'rail_road'] = cost_rail_leg + cost_road_leg

    return unit_cost


def compute_unit_emissions(ports, distribution_centers, distances):
    """アーク排出量の計算

    各輸送モードについて、輸送1トン当たりの CO2 排出量（トン）を計算する。

    排出係数の出典:
    Shirley, C., & Gecan, R. (2022). Emissions of Carbon Dioxide in the Transportation Sector.
    https://www.cbo.gov/system/files/2022-12/58566-co2-emissions-transportation.pdf
    """
    ton_to_pounds = 2204.62                        # トンからポンドへの換算係数
    emission_fact_road = 0.4 / ton_to_pounds       # 道路輸送の排出係数（トン・マイル当たり CO2 トン）
    emission_fact_rail = 0.05 / ton_to_pounds      # 鉄道輸送の排出係数（トン・マイル当たり CO2 トン）

    unit_emissions = dict()                        # 輸送1トン当たりの排出量（CO2 トン）を格納する辞書

    # 各港と配送センターの組について排出量を計算
    for s, port in ports.items():
        for d, dc in distribution_centers.items():
            # 道路のみの輸送の排出量を計算
            unit_emissions[s, d, 'road_only'] = distances[s, d, 'road'] * emission_fact_road

            # 鉄道＋道路の組合せの輸送の排出量を計算
            emissions_rail_leg = distances[s, distribution_centers[d].rail_terminal.ID, 'rail'] * emission_fact_rail
            emissions_road_leg = distances[distribution_centers[d].rail_terminal.ID, d, 'road'] * emission_fact_road

            unit_emissions[s, d, 'rail_road'] = emissions_rail_leg + emissions_road_leg

    return unit_emissions


def compute_durations(ports, distribution_centers, distances):
    """アーク所要時間の計算

    各輸送モードについて輸送の所要日数を計算する。鉄道＋道路の場合は
    鉄道ターミナルでの滞留時間も加算する。
    """
    speed_road = 60                              # 道路輸送の平均速度（マイル/時）
    speed_rail = 35                              # 鉄道輸送の平均速度（マイル/時）
    hours_day = 8                                # 1日の稼働時間
    duration_rail_terminal = 1.5                 # 鉄道ターミナルでの滞留時間（日）

    duration = dict()                            # 輸送所要時間（日）を格納する辞書

    # 各港と配送センターの組について輸送所要時間を計算
    for s, port in ports.items():
        for d, dc in distribution_centers.items():
            # 道路のみの輸送の所要時間を計算
            duration[s, d, 'road_only'] = distances[s, d, 'road'] / speed_road / hours_day

            # 鉄道＋道路の組合せの輸送の所要時間を計算
            duration_rail_leg = distances[s, distribution_centers[d].rail_terminal.ID, 'rail'] / speed_rail / hours_day
            duration_road_leg = distances[distribution_centers[d].rail_terminal.ID, d, 'road'] / speed_road / hours_day
            duration[s, d, 'rail_road'] = duration_rail_leg + duration_road_leg + duration_rail_terminal

    return duration


def print_example_arcs(ports, distribution_centers, distances, duration, unit_emissions, unit_cost):
    """アークの例の表示

    ロサンゼルス港から配送センター d1 への、道路のみのアークと鉄道＋道路のアークの
    距離・所要時間・排出量・コストを表示する。
    """
    # 道路のみのアークの例

    origin = 'pt_los_angeles'
    destination = 'd1'

    print('Origin Port: ', ports['pt_los_angeles'].name)
    print('Destination: ', distribution_centers['d1'].name)
    print('Distance [miles]: ', round(distances['pt_los_angeles', 'd1', 'road'], 2))
    print('Duration [days]: ', round(duration['pt_los_angeles', 'd1', 'road_only'], 2))
    print('Emissions [per ton transported]: ', round(unit_emissions['pt_los_angeles', 'd1', 'road_only'], 2))
    print('Cost [per ton transported]: ', round(unit_cost['pt_los_angeles', 'd1', 'road_only'], 2))

    print('')

    # 鉄道＋道路のアークの例
    # 注: ポートランドに最も近い鉄道ターミナルはボイシ（'r12'）

    origin = 'pt_los_angeles'
    destination = 'd1'

    print('Origin Port: ', ports['pt_los_angeles'].name)
    print('Destination: ', distribution_centers['d1'].name)

    print('Distance to rail terminal [miles]: ', round(distances['pt_los_angeles', 'r12', 'rail'], 2))
    print('Distance from rail terminal [miles]: ', round(distances['r12', 'd1', 'road'], 2))

    print('Duration [days]: ', round(duration['pt_los_angeles', 'd1', 'rail_road'], 2))
    print('Emissions [per ton transported]: ', round(unit_emissions['pt_los_angeles', 'd1', 'rail_road'], 2))
    print('Cost [per ton transported]: ', round(unit_cost['pt_los_angeles', 'd1', 'rail_road'], 2))


# 輸送モード (Transportation modes)
transportation_modes = ['road_only', 'rail_road']


# ===========================================================================
# 最適化モデル (Optimization model) - AMPL
# ===========================================================================

# 使用するソルバー（AMPL に同梱の HiGHS）
SOLVER = 'highs'

# AMPL 本体のよく使われるインストール先（AMPL_DIR も PATH も使えないときに順に探す）
AMPL_DIR_CANDIDATES = [
    r'C:\AMPL',                                  # Windows
    os.path.expanduser('~/ampl'),                # Windows / Linux / WSL（ホーム直下に展開した場合）
    os.path.expanduser('~/AMPL'),
    '/opt/ampl',                                 # Linux / WSL
    '/Applications/AMPL',                        # macOS
]

# AMPL モデル（ノートブックの決定変数・目的関数の式・制約を AMPL で記述したもの）
AMPL_MODEL = r"""
set PORTS;                                   # 港
set DCS;                                     # 配送センター
set MODES;                                   # 輸送モード（road_only, rail_road）

param demand {DCS} >= 0;                     # 配送センターの需要
param incoming_flow {PORTS} >= 0;            # 港への流入量（供給量）
param total_demand > 0;                      # 総需要
param unit_cost {PORTS, DCS, MODES} >= 0;       # 輸送1トン当たりのコスト
param duration {PORTS, DCS, MODES} >= 0;        # 輸送所要時間（日）
param unit_emissions {PORTS, DCS, MODES} >= 0;  # 輸送1トン当たりの CO2 排出量（トン）

# 決定変数: 港・配送センター・輸送モードごとのフロー（連続変数）
var flow {PORTS, DCS, MODES} >= 0;

# 目的関数の候補（実際に使うものは `objective` 文で選ぶ）
# 総輸送所要時間（フローと所要時間の加重和を総需要で割ったもの）
minimize total_duration:
    sum {p in PORTS, d in DCS, t in MODES} duration[p,d,t] / total_demand * flow[p,d,t];

# 総輸送コスト（フローとコストの加重和）
minimize total_cost:
    sum {p in PORTS, d in DCS, t in MODES} unit_cost[p,d,t] * flow[p,d,t];

# 総排出量（フローと排出量の加重和）
minimize total_emissions:
    sum {p in PORTS, d in DCS, t in MODES} unit_emissions[p,d,t] * flow[p,d,t];

# 各配送センターへの流入フローの合計が需要を満たす
subject to Demand {d in DCS}:
    sum {p in PORTS, t in MODES} flow[p,d,t] >= demand[d];

# 各港からの流出フローの合計が流入量（利用可能な供給量）以下
subject to Supply {p in PORTS}:
    sum {d in DCS, t in MODES} flow[p,d,t] <= incoming_flow[p];
"""


def find_ampl_dir():
    """AMPL 本体（ライセンス付き）のフォルダを探して返す

    次の順に探し、最初に見つかったものを返す。見つからなければ例外を送出する。
        1. 環境変数 AMPL_DIR で指定したフォルダ
        2. PATH 上にある ampl（Windows では ampl.exe）のフォルダ
        3. AMPL_DIR_CANDIDATES のうち、ampl の実行ファイルがあるフォルダ
    WSL では Linux 版の AMPL が必要（Windows 側の ampl.exe は WSL の Python からは使えない）。
    """
    def has_ampl(folder):
        return any(os.path.isfile(os.path.join(folder, name)) for name in ('ampl', 'ampl.exe'))

    # 1. 環境変数 AMPL_DIR で指定したフォルダ
    env_dir = os.environ.get('AMPL_DIR')
    if env_dir:
        if not has_ampl(env_dir):
            raise FileNotFoundError(f'AMPL_DIR に ampl がありません: {env_dir}')
        return env_dir

    # 2. PATH 上にある ampl のフォルダ
    ampl_path = shutil.which('ampl')
    if ampl_path:
        return os.path.dirname(os.path.realpath(ampl_path))

    # 3. よく使われるインストール先
    for folder in AMPL_DIR_CANDIDATES:
        if has_ampl(folder):
            return folder

    raise FileNotFoundError('AMPL が見つかりません。環境変数 AMPL_DIR に AMPL 本体のフォルダを指定してください。')


def build_model(ports, distribution_centers, total_demand, duration, unit_cost, unit_emissions):
    """最適化モデルの構成要素の作成

    決定変数、目的関数の各式（総所要時間・総コスト・総排出量）、制約条件を作成する。
    目的関数そのものはここでは設定せず、後のステップで定義する。
    同じコードを何度も書き直さずに済むようにするためである。

    AMPL を起動してモデル（AMPL_MODEL）を読み込み、集合とパラメータを amplpy で渡す。
    使う目的関数は後のステップで `objective` 文により選ぶ（solve() を参照）。
    """
    # モデルの初期化（ライセンス付きの AMPL 本体を使い、ソルバーを指定）
    ampl = AMPL(Environment(find_ampl_dir()))
    ampl.option['solver'] = SOLVER

    # モデル（決定変数・目的関数の各式・制約条件）の読み込み
    ampl.eval(AMPL_MODEL)

    # 集合を渡す
    ampl.set['PORTS'] = list(ports.keys())
    ampl.set['DCS'] = list(distribution_centers.keys())
    ampl.set['MODES'] = list(transportation_modes)

    # パラメータを渡す（辞書のキーが AMPL の添字になる）
    ampl.param['demand'] = {d: float(dc.demand) for d, dc in distribution_centers.items()}
    ampl.param['incoming_flow'] = {p: float(port.incoming_flow) for p, port in ports.items()}
    ampl.param['total_demand'] = float(total_demand)
    ampl.param['unit_cost'] = unit_cost
    ampl.param['duration'] = duration
    ampl.param['unit_emissions'] = unit_emissions

    return ampl


def solve(ampl, objective_name):
    """指定した目的関数を選んで AMPL で解く

    `objective` 文で最小化する目的関数を選び、ソルバーで解く。
    最適解が得られなければ例外を送出する。
    """
    ampl.eval(f'objective {objective_name};')   # 最小化する目的関数を選ぶ
    ampl.solve()
    if ampl.solve_result != 'solved':
        raise RuntimeError(f'{objective_name}: solve_result = {ampl.solve_result}')


def get_flows(ampl):
    """AMPL の解から輸送量を取り出し、{(港, 配送センター, 輸送モード): 輸送量} の辞書で返す"""
    return ampl.var['flow'].to_dict()


def find_utopia_nadir(ampl, total_demand):
    """多目的最適化（コストと所要時間）- ユートピア点とナディア点の探索

    コストを最小化してコストのユートピア点と所要時間のナディア点を求め、
    次に所要時間を最小化して所要時間のユートピア点とコストのナディア点を求める。

    注: 元のノートブックでは値の取得・表示部分がコメントアウトされている（演習用）。
    コメントアウト部分も AMPL 用に書き換えてある。
    """
    # コストを最適化して、コストのユートピア点と所要時間のナディア点を求める
    print('Optimizing for cost to find utopia cost and nadir duration')
    solve(ampl, 'total_cost')                          # 目的関数を総コストの最小化に設定して解く
    # utopia_cost = ampl.obj['total_cost'].value()       # コストのユートピア点
    # nadir_duration = ampl.get_value('total_duration')  # 所要時間のナディア点

    # # 道路輸送と鉄道輸送の割合を表示
    # flows = get_flows(ampl)
    # print('Share road: ', round(100 * sum(v for (p, d, t), v in flows.items() if t == 'road_only') / total_demand, 2))
    # print('Share rail: ', round(100 * sum(v for (p, d, t), v in flows.items() if t == 'rail_road') / total_demand, 2))

    print('')

    # 所要時間を最適化して、所要時間のユートピア点とコストのナディア点を求める
    print('Optimizing for duration to find utopia duration and nadir cost')
    solve(ampl, 'total_duration')                      # 目的関数を総所要時間の最小化に設定して解く

    # 道路輸送と鉄道輸送の割合を表示
    # flows = get_flows(ampl)
    # print('Share road: ', round(100 * sum(v for (p, d, t), v in flows.items() if t == 'road_only') / total_demand, 2))
    # print('Share rail: ', round(100 * sum(v for (p, d, t), v in flows.items() if t == 'rail_road') / total_demand, 2))

    # utopia_duration = ampl.obj['total_duration'].value()  # 所要時間のユートピア点
    # nadir_cost = ampl.get_value('total_cost')             # コストのナディア点

    # print ('')

    # # ユートピア点とナディア点の結果を表示
    # print('Nadir Cost: ', round(nadir_cost, 0))
    # print('Utopia Cost: ', round(utopia_cost, 0))

    # print('')
    # print('Nadir Duration (days): ', round(nadir_duration, 2))
    # print('Utopia Duration (days): ', round(utopia_duration, 2))


def epsilon_constraint_method(ampl, total_demand):
    """ε制約法を用いた最適化モデルの設定

    ❗課題1: 所要時間を主目的としてε制約法を適用せよ。
    以下のコードを修正すること（AMPL の式・制約は ampl.eval で追加できる）。
    """
    # ここにコードを記述

    # ユートピア点とナディア点を用いてコストと所要時間を正規化

    # コストを主目的として設定

    # ε制約を追加

    # 道路輸送と鉄道輸送の割合を表示
    flows = get_flows(ampl)
    print('Share road: ', round(100 * sum(v for (p, d, t), v in flows.items() if t == 'road_only') / total_demand, 2))
    print('Share rail: ', round(100 * sum(v for (p, d, t), v in flows.items() if t == 'rail_road') / total_demand, 2))


if __name__ == "__main__":
    # ノード
    distribution_centers_df = load_distribution_centers()
    ports_df = load_ports()
    rail_terminal_df = load_rail_terminals()
    nodes, distribution_centers, ports, rail_terminals, total_demand = create_nodes(
        distribution_centers_df, ports_df, rail_terminal_df
    )
    assign_closest_rail_terminals(distribution_centers, rail_terminals)

    # ノートブックでは地図をセル出力として表示するが、スクリプトでは HTML に保存する
    visualize_nodes(distribution_centers, ports, rail_terminals).save("epsilon_constraint_nodes.html")

    # アーク
    distances = compute_distances(ports, distribution_centers, rail_terminals)
    unit_cost = compute_unit_costs(ports, distribution_centers, distances)
    unit_emissions = compute_unit_emissions(ports, distribution_centers, distances)
    duration = compute_durations(ports, distribution_centers, distances)
    print_example_arcs(ports, distribution_centers, distances, duration, unit_emissions, unit_cost)

    # 最適化モデル（AMPL）
    ampl = build_model(ports, distribution_centers, total_demand, duration, unit_cost, unit_emissions)
    find_utopia_nadir(ampl, total_demand)
    epsilon_constraint_method(ampl, total_demand)
