# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = [
#     "amplpy",
#     "pandas",
#     "folium",
#     "geopy",
#     "matplotlib",
#     "scgraph==2.1.0",
#     "scgraph_data==2.0.0",
# ]
# ///
"""
SCM.275x - Advanced Supply Chain Systems Planning and Network Design
多目的最適化 - イプシロン制約法 - 演習

港（Port）から配送センター（Distribution Center, DC）への輸送計画を対象に、
「トラックのみ（road_only）」と「鉄道＋トラック（rail_road）」の2つの輸送モードを
選択できるネットワークを構築し、コスト・リードタイム（所要日数）・CO2排出量の
複数の目的をイプシロン制約法で扱う。

最適化は AMPL（モデルは本スクリプト内の AMPL_MODEL）で行い、データは amplpy で渡す。
ソルバーは AMPL に同梱の HiGHS を使う。

必要なパッケージは uv で導入する。先頭の `# /// script` ブロック（PEP 723 の
インラインメタデータ）に依存パッケージを書いてあるので、次のコマンドだけで
パッケージの導入と実行が行われる:
    uv run 09Multi_09Optimization_Epsilon_Constraint_Method_Python_Exercise.py

    amplpy                 AMPL の Python API
    pandas                 データ操作
    folium                 地図の作成
    geopy                  2地点間の測地線距離
    matplotlib             グラフ描画
    scgraph==2.1.0         実際の交通ネットワーク上の経路・距離計算
    scgraph_data==2.0.0    scgraph の道路網・鉄道網データ

AMPL 本体（ライセンス付き）は、次の順に探して最初に見つかったものを使う
（Windows・WSL（Linux）・macOS で共通。詳しくは find_ampl_dir()）:
    1. 環境変数 AMPL_DIR で指定したフォルダ
    2. PATH 上にある ampl（ampl.exe）のフォルダ
    3. よく使われるインストール先（C:\\AMPL, ~/ampl, /opt/ampl, /Applications/AMPL など）
WSL では Linux 版の AMPL が必要（Windows 側の ampl.exe は使えない）。

実行すると、地図を maps/ フォルダに HTML で保存する。
"""

import os                             # For file paths and environment variables
import shutil                         # For finding the ampl executable on PATH
import pandas as pd                   # For data manipulation and analysis
from amplpy import AMPL, Environment  # AMPL Python API (data is passed to AMPL with amplpy)
import folium                         # For creating interactive maps
import folium.plugins as plugins      # Additional plugins for folium
from geopy.distance import geodesic   # For calculating geodesic distances between two points

import scgraph                                                                # For computing paths and distances on a real-world transportation network
from scgraph.geographs.us_freeway import us_freeway_geograph                  # Data on US highway network (for road paths and distances)
from scgraph.geographs.north_america_rail import north_america_rail_geograph  # Data on rail routes (for rail paths and distances)
import matplotlib.pyplot as plt                                               # Plotting library


# 輸送モード（トラックのみ / 鉄道＋トラック）
TRANSPORTATION_MODES = ['road_only', 'rail_road']

# AMPL 本体のよく使われるインストール先（AMPL_DIR も PATH も使えないときに順に探す）
AMPL_DIR_CANDIDATES = [
    r'C:\AMPL',                                  # Windows
    os.path.expanduser('~/ampl'),                # Linux / WSL（ホーム直下に展開した場合）
    os.path.expanduser('~/AMPL'),
    '/opt/ampl',                                 # Linux / WSL
    '/Applications/AMPL',                        # macOS
]

# 使用するソルバーと地図の保存先
SOLVER = 'highs'
MAP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'maps')

# AMPL モデル（集合は大文字、パラメータは小文字、各項は「パラメータ × 変数」の順）
AMPL_MODEL = r"""
set PORTS;                                   # 港
set DCS;                                     # 配送センター
set MODES;                                   # 輸送モード（road_only, rail_road）

param demand {DCS} >= 0;                     # DC の需要量 [ton]
param supply {PORTS} >= 0;                   # 港の入荷量（供給量） [ton]
param total_demand > 0;                      # 総需要量 [ton]
param cost {PORTS, DCS, MODES} >= 0;         # 輸送1トン当たりのコスト
param duration {PORTS, DCS, MODES} >= 0;     # 所要日数 [day]
param emissions {PORTS, DCS, MODES} >= 0;    # 輸送1トン当たりの CO2 排出量 [ton]

var flow {PORTS, DCS, MODES} >= 0;           # 輸送量 [ton]

# 目的関数の候補（実際に使うものは `objective` 文で選ぶ）
minimize TotalCost:
    sum {p in PORTS, d in DCS, t in MODES} cost[p,d,t] * flow[p,d,t];
minimize AvgDuration:
    sum {p in PORTS, d in DCS, t in MODES} duration[p,d,t] / total_demand * flow[p,d,t];
minimize TotalEmissions:
    sum {p in PORTS, d in DCS, t in MODES} emissions[p,d,t] * flow[p,d,t];

# 各 DC への流入量は需要量以上
subject to Demand {d in DCS}:
    sum {p in PORTS, t in MODES} flow[p,d,t] >= demand[d];

# 各港からの流出量は入荷量以下
subject to Supply {p in PORTS}:
    sum {d in DCS, t in MODES} flow[p,d,t] <= supply[p];
"""


# =============================================================================
# ヘルパー関数
# =============================================================================

def plot_nodes(map,                         # Folium map object to plot the nodes on
               nodes,                       # Dictionary of node objects where each node contains attributes like latitude and longitude
               icon,                        # Icon symbol to use for the markers on the map
               active_color,                # Color of the marker icon for active nodes
               background_color,            # Background color of the marker icon
               inactive_color='grey',       # Color of the marker icon for inactive nodes
               ):
    """地図上にノードを描画する。

    folium を用いて、ノード（DC・港・鉄道ターミナルなど）を地図上にマーカーとして描画する。
    アクティブなノードは active_color、非アクティブなノードは inactive_color で表示する。
    """
    # Loop through each node in the dictionary
    for node in nodes.values():

        # Create a folium marker
        marker = folium.Marker(
            location=[node.lat, node.lon],              # Set the marker's location
            popup=(node.ID + "-" + node.name),          # Create a marker popup with the node ID and name
            icon=plugins.BeautifyIcon(                  # Create a marker's icon
                icon=icon,
                icon_shape="circle",
                text_color=active_color if node.active == True else inactive_color,
                border_color=active_color if node.active == True else inactive_color,
                background_color=background_color,
            )
        )

        # Add a folium marker to the map
        marker.add_to(map)


def shortest_path(origin, destination, mode, result, unit='mi'):
    """実際の道路網または鉄道網上で2地点間の最短経路を計算する。

    Args:
        origin: 出発地点のオブジェクト（lat, lon 属性を持つ）
        destination: 到着地点のオブジェクト（lat, lon 属性を持つ）
        mode: 'rail'（鉄道網）または 'road'（道路網）
        result: 'distance'（総距離を返す）または 'coordinate_path'（経路の座標列を返す）
        unit: 距離の単位（既定はマイル）
    """
    # Extract coordinates from origin and destination objects
    origin_coordinates = (origin.lat, origin.lon)
    destination_coordinates = (destination.lat, destination.lon)

    # Calculate the shortest path on the rail network
    if mode == 'rail':
        output = north_america_rail_geograph.get_shortest_path(
            origin_node={"latitude": origin.lat, "longitude": origin.lon},
            destination_node={"latitude": destination.lat, "longitude": destination.lon},
            output_units=unit
        )

    # Calculate the shortest path on the road network
    elif mode == 'road':
        output = us_freeway_geograph.get_shortest_path(
            origin_node={"latitude": origin.lat, "longitude": origin.lon},
            destination_node={"latitude": destination.lat, "longitude": destination.lon},
            output_units=unit
        )

    # Return the total distance of the path
    if result == 'distance':
        return output['length']

    # Return the coordinates representing the path
    elif result == 'coordinate_path':
        return output['coordinate_path']


def adjustArcPath(path):
    """経路の経度が地球を一周する際にも連続になるよう調整する。"""
    for index in range(1, len(path)):
        x = path[index][1]
        prevX = path[index - 1][1]
        path[index][1] = x - (round((x - prevX) / 360, 0) * 360)
    return path


def modifyArcPathLong(points, amount):
    """経路の全座標の経度を amount だけずらす。"""
    return [[i[0], i[1] + amount] for i in points]


def getCleanArcPath(path):
    """経度の連続性を確保した経路と、±360度・±720度ずらした複製経路のリストを返す。"""
    path = adjustArcPath(path)
    return [
        path,
        modifyArcPathLong(path, 360),
        modifyArcPathLong(path, -360),
        modifyArcPathLong(path, 720),
        modifyArcPathLong(path, -720)
    ]


def plot_real_flows(map,              # Folium map object where flows will be plotted.
                    flows,            # Dictionary of flow values {(port, dc, mode): value} from the optimization model
                    nodes,            # Dictionary of node objects
                    max_width=30,     # Maximum line width for the flows, default is 30
                    opacity=0.5):     # Opacity of the lines, default is 0.5
    """地図上にフロー（実ネットワーク上の経路）を描画する。

    最適化モデルの結果に基づき、正のフローを持つ輸送経路を folium の地図上に描画する。
    線の太さはフロー量に比例する（最大フローで正規化）。
    road_only はオレンジの1本の線、rail_road は鉄道区間（緑）と
    鉄道ターミナルから DC までの道路区間（オレンジ）の2本の線で表示する。
    flows は get_flows() が返す {(港, DC, 輸送モード): 輸送量} の辞書。
    """
    # Find the maximum flow value to normalize line widths
    max_val = max(flows.values())

    # Iterate over flow values (keys represent node pairs and the transportation mode used)
    for (node1_key, node2_key, t), value in flows.items():

        # Plot only positive flows
        if value > 1e-6:

            # If the transportation mode is road only, we add a single polyline to the map
            if t == 'road_only':

                # Get the shortest path coordinates for the node pair by road
                path = shortest_path(nodes[node1_key], nodes[node2_key], mode='road', result='coordinate_path')

                # Add the road path as a polyline on the map, with width proportional to the flow value
                folium.PolyLine(getCleanArcPath(path),
                                color='orange',
                                weight=value / max_val * max_width,   # Normalize weight by maximum flow value
                                opacity=opacity).add_to(map)

            # If the transportation mode is a combination of rail and road, we add two polylines to the map
            elif t == 'rail_road':

                # Get the shortest path coordinates for the path between the port (i.e., node1_key) and the rail terminal (i.e., rail terminal associated to node2_key) by rail
                rail_path = shortest_path(nodes[node1_key], nodes[node2_key].rail_terminal, mode='rail', result='coordinate_path')

                # Add the road path as a polyline on the map, with width proportional to the flow value
                folium.PolyLine(getCleanArcPath(rail_path),
                                color='green',
                                weight=value / max_val * max_width,   # Normalize weight by maximum flow value
                                opacity=opacity).add_to(map)

                # Get the shortest path coordinates for the path between the rail terminal (i.e., rail terminal associated to node2_key) and the distribution center (i.e., node2_key)
                road_path = shortest_path(nodes[node2_key].rail_terminal, nodes[node2_key], mode='road', result='coordinate_path')

                # Add the road path as a polyline on the map, with width proportional to the flow value
                folium.PolyLine(getCleanArcPath(road_path),
                                color='orange',
                                weight=value / max_val * max_width,   # Normalize weight by maximum flow value
                                opacity=opacity).add_to(map)


def find_closest_rail_terminal(dc,                # DC object
                               rail_terminals):   # Dictionnary of rail terminals
    """指定した配送センターに最も近い鉄道ターミナルを求める。

    各鉄道ターミナルとの測地線距離（マイル）を計算し、最小となるターミナルのオブジェクトを返す。
    """
    # Create a dictionary to store distances between the distribution center and each rail terminal
    distances = dict()

    # Iterate over all rail terminals in the dictionary and calculate the geodesic distance
    for rt in rail_terminals.values():
        distances[rt.ID] = geodesic((rt.lat, rt.lon), (dc.lat, dc.lon)).mi

    # Find the rail terminal with the minimum distance to the distribution center
    closest_terminal_id = min(distances.items(), key=lambda x: x[1])[0]

    # Retrieve the rail terminal object using the closest terminal ID
    closest_terminal = rail_terminals[closest_terminal_id]

    # Return the closest rail terminal object
    return closest_terminal


# =============================================================================
# クラス定義
# =============================================================================

class DistributionCenter():
    """配送センター（DC）を表すクラス。

    ID・名称・需要量・緯度経度を保持し、初期状態ではアクティブとする。
    """
    def __init__(self, ID, name, demand, lat, lon):
        self.ID = ID              # DC's ID
        self.name = name          # DC's name
        self.demand = demand      # DC's demand
        self.lat = lat            # DC's latitude
        self.lon = lon            # DC's longitude

        self.active = True        # Initializing node as active


class Port():
    """港を表すクラス。

    ID・名称・入荷量（供給量）・緯度経度を保持し、初期状態ではアクティブとする。
    """
    def __init__(self, ID, name, incoming_flow, lat, lon):
        self.ID = ID                          # Port's ID
        self.name = name                      # Port's name
        self.incoming_flow = incoming_flow    # Port's incoming flow (i.e., supply)
        self.lat = lat                        # Port's latitude
        self.lon = lon                        # Port's longitude

        self.active = True                    # Initializing node as active


class RailTerminal():
    """鉄道ターミナルを表すクラス。

    ID・名称・緯度経度を保持し、初期状態ではアクティブとする。
    """
    def __init__(self, ID, name, lat, lon):
        self.ID = ID                  # Rail Terminal's ID
        self.name = name              # Rail Terminal's name
        self.lat = lat                # Rail Terminal's latitude
        self.lon = lon                # Rail Terminal's longitude

        self.active = True            # Initializing node as active


# =============================================================================
# データの準備と前処理
# =============================================================================

def load_data():
    """入力ファイルを読み込む。

    配送センター・港・鉄道ターミナルの CSV を GitHub から読み込み、
    それぞれの DataFrame を返す（港は先頭4件のみ使用）。
    """
    # File containing data on distribution centers
    dcs_data_file = 'https://raw.githubusercontent.com/scm275/problem_sets_scm275/main/multiple_objectives/distribution_centers.csv'

    # Loading dc data into a pandas DataFrame
    distribution_centers_df = pd.read_csv(dcs_data_file)

    # Displaying the first few rows of the DataFrame to verify the data
    print(distribution_centers_df.head())

    # File containing port data
    ports_data_file = 'https://raw.githubusercontent.com/scm275/problem_sets_scm275/main/multiple_objectives/ports.csv'

    # Loading port data into a pandas DataFrame
    ports_df = pd.read_csv(ports_data_file)
    ports_df = ports_df[0:4]

    # Displaying the first few rows of the DataFrame to verify the data
    print(ports_df.head())

    # File containing rail terminal data
    rail_terminal_data_file = 'https://raw.githubusercontent.com/scm275/problem_sets_scm275/main/multiple_objectives/rail_terminals.csv'

    # Loading rail terminal data into a pandas DataFrame
    rail_terminal_df = pd.read_csv(rail_terminal_data_file)

    # Displaying the first few rows of the DataFrame to verify the data
    print(rail_terminal_df.head())

    return distribution_centers_df, ports_df, rail_terminal_df


def create_nodes(distribution_centers_df, ports_df, rail_terminal_df):
    """ノードオブジェクトを生成する。

    各 DataFrame から配送センター・港・鉄道ターミナルのオブジェクトの辞書を作り、
    すべてを統合した nodes 辞書を作成する。あわせて総需要量を計算する。

    Returns:
        nodes, distribution_centers, ports, rail_terminals, total_demand
    """
    nodes = dict()

    # Creating a dictionary of distribution centers objects
    distribution_centers = dict()
    for i, row in distribution_centers_df.iterrows():
        distribution_centers[row['ID']] = DistributionCenter(ID=row['ID'],           # DC's ID
                                                             name=row['name'],       # DC's name
                                                             lat=row['lat'],         # DC's latitude
                                                             lon=row['lon'],         # DC's longitude
                                                             demand=row['demand'])   # DC's demand

    # Merging the distribution centers dictionary into the existing nodes dictionary
    nodes = {**nodes, **distribution_centers}

    # Finding a value of total demand
    total_demand = sum([dc.demand for dc in distribution_centers.values()])

    # Another method:
    total_demand = 0
    for d, distribution_center in distribution_centers.items():
        total_demand = total_demand + distribution_center.demand

    print('Total demand: ', total_demand)

    # Creating a dictionary of ports objects
    ports = dict()
    for i, row in ports_df.iterrows():
        ports[row['ID']] = Port(ID=row['ID'],                             # Port's ID
                                name=row['name'],                         # Port's name
                                lat=row['lat'],                           # Port's latitude
                                lon=row['lon'],                           # Port's longitude
                                incoming_flow=row['incoming_flow'])       # Port's incoming flow

    # Merging the ports dictionary into the existing nodes dictionary
    nodes = {**nodes, **ports}

    # Creating a dictionary of rail terminal objects
    rail_terminals = dict()
    for i, row in rail_terminal_df.iterrows():
        rail_terminals[row['ID']] = RailTerminal(ID=row['ID'],            # Rail Terminal's ID
                                                 name=row['name'],        # Rail Terminal's name
                                                 lat=row['lat'],          # Rail Terminal's latitude
                                                 lon=row['lon'])          # Rail Terminal's longitude

    # Merging the rail terminals dictionary into the existing nodes dictionary
    nodes = {**nodes, **rail_terminals}

    return nodes, distribution_centers, ports, rail_terminals, total_demand


def assign_closest_rail_terminals(distribution_centers, rail_terminals):
    """各配送センターに最も近い鉄道ターミナルを求め、rail_terminal 属性に設定する。"""
    # Iterate over all distribution center objects in the dictionary
    for d in distribution_centers.values():

        # Find the closest rail terminal to the current distribution center and assign it to the rail_terminal attribute of the distribution center
        d.rail_terminal = find_closest_rail_terminal(d, rail_terminals)


def visualize_nodes(distribution_centers, ports, rail_terminals, output_file='nodes_map.html'):
    """ノードオブジェクトを地図上に可視化する。

    配送センター（倉庫アイコン）、港（錨アイコン）、鉄道ターミナル（列車アイコン）を描画し、
    HTML ファイルとして保存する（ノートブックでは地図をセル出力として表示していた）。
    """
    # Create a new map
    m = folium.Map([40, -100.0], zoom_start=5)

    # Plot distribution center locations with a warehouse icon, green color, and yellow background
    plot_nodes(map=m, nodes=distribution_centers, icon='warehouse', active_color='green', background_color='yellow')

    # Plot port locations with an anchor icon, blue color, and white background
    plot_nodes(map=m, nodes=ports, icon='anchor', active_color='blue', background_color='white')

    # Plot rail terminal locations with a train icon, orange color, and yellow background
    plot_nodes(map=m, nodes=rail_terminals, icon='train', active_color='orange', background_color='yellow')

    # Add a tile layer for better map visualization (cartodbpositron theme)
    # NOTE: CartoDB のタイルは API キーが必要になり、表示すると地図が隠れるため使わない
    #       （folium 既定の OpenStreetMap のタイルで表示する）
    # folium.TileLayer('cartodbpositron').add_to(m)

    # Save the map with all the plotted data
    m.save(output_file)
    return m


def compute_distances(ports, distribution_centers, rail_terminals):
    """前処理ステップ：距離を計算する。

    輸送モードごとに以下の距離（マイル）を実ネットワーク上で計算し、辞書で返す。
    - 港 → 配送センター（道路）
    - 港 → 鉄道ターミナル（鉄道）
    - 鉄道ターミナル → 配送センター（道路）
    """
    # Initialize dictionary to store distances by transportation mode
    distances = dict()

    # Calculate road distances between ports and distribution centers
    for s, port in ports.items():
        for d, dc in distribution_centers.items():
            distances[s, d, 'road'] = shortest_path(port, dc, 'road', 'distance', unit='mi')

    # Calculate rail distances between ports and rail terminals
    for s, port in ports.items():
        for r, rail_terminal in rail_terminals.items():
            distances[s, r, 'rail'] = shortest_path(port, rail_terminal, 'rail', 'distance', unit='mi')

    # Calculate road distances between rail terminals and distribution centers
    for r, rail_terminal in rail_terminals.items():
        for d, dc in distribution_centers.items():
            distances[r, d, 'road'] = shortest_path(rail_terminal, dc, 'road', 'distance', unit='mi')

    return distances


def compute_unit_costs(ports, distribution_centers, distances):
    """アークの輸送コストを計算する。

    トンマイル当たり単価（道路 0.10、鉄道 0.05）と、距離に依存しない
    トン当たり最低料金（道路 25、鉄道 45）を用いて、港・DC・輸送モードごとの
    トン当たり輸送コストを求める。rail_road は鉄道区間と道路区間のコストの和とする。
    """
    cost_mile_road = 0.10                         # Cost per ton-mile for road transport
    cost_mile_rail = 0.05                         # Cost per ton-mile for rail transport

    min_cost_road = 25                            # Minimum cost (independant of distance) per ton for road
    min_cost_rail = 45                            # Minimum cost (independant of distance) per ton for rail

    unit_cost = dict()                            # Dictionary to store transportation costs

    # Calculate transport costs for each port and distribution center
    for s, port in ports.items():
        for d, dc in distribution_centers.items():
            # Calculate road-only transport cost, ensuring a minimum distance is considered
            unit_cost[s, d, 'road_only'] = max(distances[s, d, 'road'] * cost_mile_road, min_cost_road)

            # Calculate combined rail-road transport cost, ensuring minimum distances for both modes
            cost_rail_leg = max(distances[s, distribution_centers[d].rail_terminal.ID, 'rail'] * cost_mile_rail, min_cost_rail)
            cost_road_leg = max(distances[distribution_centers[d].rail_terminal.ID, d, 'road'] * cost_mile_road, min_cost_road)
            unit_cost[s, d, 'rail_road'] = cost_rail_leg + cost_road_leg

    return unit_cost


def compute_unit_emissions(ports, distribution_centers, distances):
    """アークの CO2 排出量を計算する。

    トンマイル当たりの排出係数（道路 0.4 ポンド、鉄道 0.05 ポンドをトン換算）を用いて、
    港・DC・輸送モードごとの輸送1トン当たり CO2 排出量（トン）を求める。

    出典:
        Shirley, C., & Gecan, R. (2022). Emissions of Carbon Dioxide in the Transportation Sector.
        https://www.cbo.gov/system/files/2022-12/58566-co2-emissions-transportation.pdf
    """
    ton_to_pounds = 2204.62                        # Conversion factor from tons to pounds
    emission_fact_road = 0.4 / ton_to_pounds       # Emission factor for road transport (tons of CO2 per ton-mile)
    emission_fact_rail = 0.05 / ton_to_pounds      # Emission factor for rail transport (tons of CO2 per ton-mile)

    unit_emissions = dict()                        # Dictionary to store emissions per ton transported (in tons of CO2)

    # Calculate emissions for each port and distribution center
    for s, port in ports.items():
        for d, dc in distribution_centers.items():
            # Calculate emissions for road-only transport
            unit_emissions[s, d, 'road_only'] = distances[s, d, 'road'] * emission_fact_road

            # Calculate emissions for combined rail-road transport
            emissions_rail_leg = distances[s, distribution_centers[d].rail_terminal.ID, 'rail'] * emission_fact_rail
            emissions_road_leg = distances[distribution_centers[d].rail_terminal.ID, d, 'road'] * emission_fact_road

            unit_emissions[s, d, 'rail_road'] = emissions_rail_leg + emissions_road_leg

    return unit_emissions


def compute_durations(ports, distribution_centers, distances):
    """アークの所要日数を計算する。

    平均速度（道路 60 mph、鉄道 35 mph）と1日8時間稼働を仮定して所要日数を求める。
    rail_road の場合は鉄道ターミナルでの滞留時間 1.5 日を加算する。
    """
    speed_road = 60                              # Average speed for road transport in miles per hour
    speed_rail = 35                              # Average speed for rail transport in miles per hour
    hours_day = 8                                # Number of operational hours per day
    duration_rail_terminal = 1.5                 # Time spent at the rail terminal in days

    duration = dict()                            # Dictionary to store transportation duration (in days)

    # Calculate transport duration for each port and distribution center
    for s, port in ports.items():
        for d, dc in distribution_centers.items():
            # Calculate duration for road-only transport
            duration[s, d, 'road_only'] = distances[s, d, 'road'] / speed_road / hours_day

            # Calculate duration for combined rail-road transport
            duration_rail_leg = distances[s, distribution_centers[d].rail_terminal.ID, 'rail'] / speed_rail / hours_day
            duration_road_leg = distances[distribution_centers[d].rail_terminal.ID, d, 'road'] / speed_road / hours_day
            duration[s, d, 'rail_road'] = duration_rail_leg + duration_road_leg + duration_rail_terminal

    return duration


def print_arc_examples(ports, distribution_centers, distances, duration, unit_emissions, unit_cost):
    """アークの例（ロサンゼルス港 → ポートランド DC）を表示する。

    トラックのみの場合と、鉄道＋トラックの場合（ポートランドに最も近い鉄道ターミナルは
    ボイシ 'r12'）について、距離・所要日数・排出量・コストを表示する。
    """
    # Example of road only arc
    origin = 'pt_los_angeles'
    destination = 'd1'

    print('Origin Port: ', ports['pt_los_angeles'].name)
    print('Destination: ', distribution_centers['d1'].name)
    print('Distance [miles]: ', round(distances['pt_los_angeles', 'd1', 'road'], 2))
    print('Duration [days]: ', round(duration['pt_los_angeles', 'd1', 'road_only'], 2))
    print('Emissions [per ton transported]: ', round(unit_emissions['pt_los_angeles', 'd1', 'road_only'], 2))
    print('Cost [per ton transported]: ', round(unit_cost['pt_los_angeles', 'd1', 'road_only'], 2))

    # Example of rail - road arc
    # Note: the closest rail terminal to Portland is Boise (i.e., 'r12')
    print('Origin Port: ', ports['pt_los_angeles'].name)
    print('Destination: ', distribution_centers['d1'].name)

    print('Distance to rail terminal [miles]: ', round(distances['pt_los_angeles', 'r12', 'rail'], 2))
    print('Distance from rail terminal [miles]: ', round(distances['r12', 'd1', 'road'], 2))

    print('Duration [days]: ', round(duration['pt_los_angeles', 'd1', 'rail_road'], 2))
    print('Emissions [per ton transported]: ', round(unit_emissions['pt_los_angeles', 'd1', 'rail_road'], 2))
    print('Cost [per ton transported]: ', round(unit_cost['pt_los_angeles', 'd1', 'rail_road'], 2))


# =============================================================================
# 最適化モデル
# =============================================================================

def find_ampl_dir():
    """AMPL 本体（ライセンス付き）のフォルダを探して返す。

    次の順に探し、最初に見つかったものを返す。見つからなければ例外を送出する。
        1. 環境変数 AMPL_DIR で指定したフォルダ
        2. PATH 上にある ampl（Windows では ampl.exe）のフォルダ
        3. AMPL_DIR_CANDIDATES のうち、ampl の実行ファイルがあるフォルダ
    WSL では Linux 版の AMPL が必要（Windows 側の ampl.exe は WSL の Python からは使えない）。
    """
    def has_ampl(folder):
        return any(os.path.isfile(os.path.join(folder, name)) for name in ('ampl', 'ampl.exe'))

    # 1. Folder given by the AMPL_DIR environment variable
    env_dir = os.environ.get('AMPL_DIR')
    if env_dir:
        if not has_ampl(env_dir):
            raise FileNotFoundError(f'AMPL_DIR に ampl がありません: {env_dir}')
        return env_dir

    # 2. Folder of the ampl executable on PATH
    ampl_path = shutil.which('ampl')
    if ampl_path:
        return os.path.dirname(os.path.realpath(ampl_path))

    # 3. Common installation folders
    for folder in AMPL_DIR_CANDIDATES:
        if has_ampl(folder):
            return folder

    raise FileNotFoundError('AMPL が見つかりません。環境変数 AMPL_DIR に AMPL 本体のフォルダを指定してください。')


def build_model(ports, distribution_centers, total_demand, duration, unit_cost, unit_emissions,
                transportation_modes=TRANSPORTATION_MODES):
    """最適化モデルの構成要素を作成する。

    AMPL を起動してモデル（AMPL_MODEL：決定変数、目的関数に用いる式〔平均所要日数・
    総コスト・総排出量〕、制約）を読み込み、集合とパラメータを amplpy で渡す。
    同じコードを何度も書かずに済むよう、ここでは使う目的関数はまだ選ばず、
    後のステップで `objective` 文により選ぶ。

    Returns:
        データを設定済みの AMPL オブジェクト
    """
    # Initializing AMPL with the licensed installation, and the solver
    ampl = AMPL(Environment(find_ampl_dir()))
    ampl.option['solver'] = SOLVER

    # Reading the model (variables, objective expressions, and constraints)
    ampl.eval(AMPL_MODEL)

    # Passing the sets
    ampl.set['PORTS'] = list(ports.keys())
    ampl.set['DCS'] = list(distribution_centers.keys())
    ampl.set['MODES'] = list(transportation_modes)

    # Passing the parameters (keys of the dictionaries are AMPL indices)
    ampl.param['demand'] = {d: float(dc.demand) for d, dc in distribution_centers.items()}
    ampl.param['supply'] = {p: float(port.incoming_flow) for p, port in ports.items()}
    ampl.param['total_demand'] = float(total_demand)
    ampl.param['cost'] = unit_cost
    ampl.param['duration'] = duration
    ampl.param['emissions'] = unit_emissions

    return ampl


def solve(ampl, objective_name):
    """指定した目的関数を選んで AMPL で解く。

    `objective` 文で目的関数を選び、ソルバーで解く。最適解が得られなければ例外を送出する。
    """
    ampl.eval(f'objective {objective_name};')   # Select the objective to minimize
    ampl.solve()
    if ampl.solve_result != 'solved':
        raise RuntimeError(f'{objective_name}: solve_result = {ampl.solve_result}')


def get_flows(ampl):
    """AMPL の解から輸送量を取り出し、{(港, DC, 輸送モード): 輸送量} の辞書で返す。"""
    return {key: value for key, value in ampl.var['flow'].to_dict().items()}


def print_mode_share(flows, total_demand):
    """トラックのみ（road）と鉄道＋トラック（rail）の輸送量の割合 [%] を表示する。"""
    print('Share road: ', round(100 * sum(v for (p, d, t), v in flows.items() if t == 'road_only') / total_demand, 2))
    print('Share rail: ', round(100 * sum(v for (p, d, t), v in flows.items() if t == 'rail_road') / total_demand, 2))


def find_utopia_nadir(ampl, total_demand):
    """多目的最適化（コストと所要日数）：ユートピア点とナディア点を求める。

    コストを最小化してユートピアコストとナディア所要日数を、
    所要日数を最小化してユートピア所要日数とナディアコストを求める。

    Returns:
        (各点の値の辞書, コスト最小化の解の輸送量, 所要日数最小化の解の輸送量)
    """
    # Optimizing for cost to find utopia cost and nadir duration
    print('Optimizing for cost to find utopia cost and nadir duration')
    solve(ampl, 'TotalCost')                              # Minimize total cost
    utopia_cost = ampl.obj['TotalCost'].value()           # Utopia point for cost
    nadir_duration = ampl.get_value('AvgDuration')        # Nadir point for duration
    flows_cost = get_flows(ampl)

    # Printing the share of road and rail transport
    print_mode_share(flows_cost, total_demand)

    print('')

    # Optimizing for duration to find utopia duration and nadir cost
    print('Optimizing for duration to find utopia duration and nadir cost')
    solve(ampl, 'AvgDuration')                            # Minimize total duration
    flows_duration = get_flows(ampl)

    # Printing the share of road and rail transport
    print_mode_share(flows_duration, total_demand)

    utopia_duration = ampl.obj['AvgDuration'].value()     # Utopia point for duration
    nadir_cost = ampl.get_value('TotalCost')              # Nadir point for cost

    print('')

    # Printing the results for utopia and nadir points
    print('Nadir Cost: ', round(nadir_cost, 0))
    print('Utopia Cost: ', round(utopia_cost, 0))

    print('')
    print('Nadir Duration (days): ', round(nadir_duration, 2))
    print('Utopia Duration (days): ', round(utopia_duration, 2))

    points = dict(utopia_cost=utopia_cost, nadir_cost=nadir_cost,
                  utopia_duration=utopia_duration, nadir_duration=nadir_duration)
    return points, flows_cost, flows_duration


def visualize_flows(flows, nodes, distribution_centers, ports, rail_terminals, output_file):
    """最適解の輸送フローを地図上に可視化し、HTML ファイルとして保存する。

    ノード（DC・港・鉄道ターミナル）と、正の輸送量を持つ経路
    （道路：オレンジ、鉄道：緑、線の太さは輸送量に比例）を描画する。
    """
    m = folium.Map([40, -100.0], zoom_start=4)
    plot_real_flows(m, flows, nodes)
    plot_nodes(map=m, nodes=distribution_centers, icon='warehouse', active_color='green', background_color='yellow')
    plot_nodes(map=m, nodes=ports, icon='anchor', active_color='blue', background_color='white')
    plot_nodes(map=m, nodes=rail_terminals, icon='train', active_color='orange', background_color='yellow')
    m.save(output_file)
    return m


def epsilon_constraint(ampl, points, total_demand):
    """イプシロン制約法による最適化モデルを設定する。

    ❗課題1：所要日数を主目的としてイプシロン制約法を適用せよ。
    以下のコードを修正すること（AMPL の式・制約は ampl.eval で追加できる）。
    """
    # Your code here

    # Normalize cost and duration using utopia and nadir points

    # Setting cost as a primary objective

    # Adding the epsilon constraint

    # Printing the share of road and rail transport
    print_mode_share(get_flows(ampl), total_demand)


# =============================================================================
# メイン
# =============================================================================

def main():
    """データ準備から最適化までを順に実行し、地図を MAP_DIR に保存する。"""
    os.makedirs(MAP_DIR, exist_ok=True)

    distribution_centers_df, ports_df, rail_terminal_df = load_data()
    nodes, distribution_centers, ports, rail_terminals, total_demand = create_nodes(
        distribution_centers_df, ports_df, rail_terminal_df)
    assign_closest_rail_terminals(distribution_centers, rail_terminals)
    visualize_nodes(distribution_centers, ports, rail_terminals,
                    output_file=os.path.join(MAP_DIR, 'nodes_map.html'))

    distances = compute_distances(ports, distribution_centers, rail_terminals)
    unit_cost = compute_unit_costs(ports, distribution_centers, distances)
    unit_emissions = compute_unit_emissions(ports, distribution_centers, distances)
    duration = compute_durations(ports, distribution_centers, distances)
    print_arc_examples(ports, distribution_centers, distances, duration, unit_emissions, unit_cost)

    ampl = build_model(ports, distribution_centers, total_demand, duration, unit_cost, unit_emissions)
    points, flows_cost, flows_duration = find_utopia_nadir(ampl, total_demand)

    visualize_flows(flows_cost, nodes, distribution_centers, ports, rail_terminals,
                    os.path.join(MAP_DIR, 'flows_min_cost.html'))
    visualize_flows(flows_duration, nodes, distribution_centers, ports, rail_terminals,
                    os.path.join(MAP_DIR, 'flows_min_duration.html'))

    epsilon_constraint(ampl, points, total_demand)


if __name__ == "__main__":
    main()
