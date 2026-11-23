# 問題設定：港から配送センターへの輸送計画（多目的最適化・イプシロン制約法）

出典：MIT SCM.275x *Advanced Supply Chain Systems Planning and Network Design*,
「Multi-Objective Optimization - Epsilon Constraint Method - Exercise」

## 1. 概要

米国の4つの港に届いた貨物を、30か所の配送センター（DC）へ輸送する。
港から DC へは、次の2つの輸送モードのどちらでも運べる。

| 輸送モード | 経路 |
|---|---|
| `road_only`（トラックのみ） | 港 →（道路）→ DC |
| `rail_road`（鉄道＋トラック） | 港 →（鉄道）→ DC に最も近い鉄道ターミナル →（道路）→ DC |

一般に、トラックは速いが高く、CO2 排出量も多い。鉄道は安くて排出量も少ないが、遅い。
そのため **コスト** と **所要日数** はトレードオフの関係になる。
この2つの目的を、イプシロン制約法で同時に扱う。

## 2. データ

データは GitHub（`scm275/problem_sets_scm275/multiple_objectives/`）の CSV から読み込む。

### 港（4か所、`ports.csv` の全4件）

| ID | 名称 | 入荷量（供給量）[ton] |
|---|---|---:|
| `pt_los_angeles` | Los Angeles | 3,500 |
| `pt_tacoma` | Tacoma | 4,500 |
| `pt_houston` | Houston | 5,000 |
| `pt_oakland` | Oakland | 2,000 |
| | **合計** | **15,000** |

### 配送センター（30か所、`distribution_centers.csv`）

需要量の合計は **15,000 ton** で、供給量の合計と等しい。

| ID | 名称 | 需要 | ID | 名称 | 需要 | ID | 名称 | 需要 |
|---|---|---:|---|---|---:|---|---|---:|
| d1 | Portland | 550 | d11 | Jacksonville | 300 | d21 | Las Vegas | 300 |
| d2 | Savannah | 650 | d12 | Orlando | 600 | d22 | Cleveland | 500 |
| d3 | Indianapolis | 700 | d13 | New Orleans | 350 | d23 | Akron | 700 |
| d4 | Minneapolis | 350 | d14 | Portland | 300 | d24 | Salt Lake City | 450 |
| d5 | Harrisburg | 700 | d15 | Charleston | 300 | d25 | Tucson | 400 |
| d6 | Nashville | 700 | d16 | Lousville | 300 | d26 | Cheyenne | 515 |
| d7 | Albuquerque | 400 | d17 | Frederick | 700 | d27 | Casper | 530 |
| d8 | Mobile | 500 | d18 | Lansing | 300 | d28 | Boulder | 545 |
| d9 | Little Rock | 500 | d19 | Springfield | 600 | d29 | Twin Falls | 560 |
| d10 | Phoenix | 700 | d20 | Hattiesburg | 500 | d30 | Fort Collins | 500 |

### 鉄道ターミナル（12か所、`rail_terminals.csv`）

Atlanta (r1), Chicago (r2), Memphis (r3), Kansas City (r4), Denver (r5), Columbus (r6),
Phoenix (r7), Lafayette (r8), St. Louis (r9), Albuquerque (r10), Omaha (r11), Boise (r12)

各 DC は、測地線距離が最も近い鉄道ターミナル $r(d)$ を1つだけ使う。
たとえば Portland（d1）の場合は Boise（r12）を使う。

## 3. 前処理：距離・コスト・排出量・所要日数

### 距離

距離は `scgraph` を使い、実際の米国の高速道路網・北米の鉄道網の上で最短経路として求める（単位はマイル）。

- 港 $p$ → DC $d$ の道路距離：$\ell^{\text{road}}_{pd}$
- 港 $p$ → 鉄道ターミナル $r$ の鉄道距離：$\ell^{\text{rail}}_{pr}$
- 鉄道ターミナル $r$ → DC $d$ の道路距離：$\ell^{\text{road}}_{rd}$

### 輸送1トン当たりのコスト $c_{pdt}$

| | トンマイル当たり単価 | 距離によらない最低料金（1トン当たり） |
|---|---:|---:|
| 道路 | 0.10 | 25 |
| 鉄道 | 0.05 | 45 |

$$
c_{pd,\text{road-only}} = \max(0.10\thinspace \ell^{\text{road}}_{pd},\ 25)
$$

$$
c_{pd,\text{rail-road}} = \max(0.05\thinspace \ell^{\text{rail}}_{p\thinspace r(d)},\ 45) + \max(0.10\thinspace \ell^{\text{road}}_{r(d)\thinspace d},\ 25)
$$

### 輸送1トン当たりの CO2 排出量 $e_{pdt}$ [ton]

排出係数は、トンマイル当たり道路 0.4 ポンド、鉄道 0.05 ポンド
（1 ton = 2204.62 ポンドで換算）。
出典：Shirley & Gecan (2022), *Emissions of Carbon Dioxide in the Transportation Sector*, CBO.

$$
e_{pd,\text{road-only}} = \frac{0.4}{2204.62}\thinspace \ell^{\text{road}}_{pd},\qquad
e_{pd,\text{rail-road}} = \frac{0.05}{2204.62}\thinspace \ell^{\text{rail}}_{p\thinspace r(d)} + \frac{0.4}{2204.62}\thinspace \ell^{\text{road}}_{r(d)\thinspace d}
$$

### 所要日数 $\tau_{pdt}$ [day]

平均速度は道路 60 mph、鉄道 35 mph とし、1日の稼働時間は 8 時間とする。
鉄道ターミナルでは 1.5 日滞留する。

$$
\tau_{pd,\text{road-only}} = \frac{\ell^{\text{road}}_{pd}}{60 \times 8},\qquad
\tau_{pd,\text{rail-road}} = \frac{\ell^{\text{rail}}_{p\thinspace r(d)}}{35 \times 8} + \frac{\ell^{\text{road}}_{r(d)\thinspace d}}{60 \times 8} + 1.5
$$

### 例：Los Angeles 港 → Portland（d1）

| | road_only | rail_road（Boise 経由） |
|---|---:|---:|
| 距離 [mile] | 996.17 | 鉄道 1,222.72 ＋ 道路 434.41 |
| 所要日数 [day] | 2.08 | 6.77 |
| 排出量 [ton/ton] | 0.18 | 0.11 |
| コスト [/ton] | 99.62 | 104.58 |

## 4. 最適化モデル（線形計画）

### 集合

- $P$：港、$D$：配送センター、$T = \lbrace \text{road-only}, \text{rail-road}\rbrace$：輸送モード（コードでは `road_only`, `rail_road`）

### パラメータ

- $q_d$：DC $d$ の需要量、$s_p$：港 $p$ の供給量、$Q = \sum_d q_d = 15{,}000$：総需要量
- $c_{pdt}$、$e_{pdt}$、$\tau_{pdt}$：上で求めたコスト・排出量・所要日数

### 決定変数

- $x_{pdt} \ge 0$：港 $p$ から DC $d$ へ輸送モード $t$ で運ぶ量 [ton]

### 目的関数（候補）

$$
\text{TotalCost} = \sum_{p,d,t} c_{pdt}\thinspace x_{pdt}
$$

$$
\text{AvgDuration} = \sum_{p,d,t} \frac{\tau_{pdt}}{Q}\thinspace x_{pdt}\quad(\text{1トン当たりの平均所要日数})
$$

$$
\text{TotalEmissions} = \sum_{p,d,t} e_{pdt}\thinspace x_{pdt}
$$

演習で扱うのは **TotalCost** と **AvgDuration** の2つ。

### 制約

$$
\sum_{p \in P}\sum_{t \in T} x_{pdt} \ge q_d \quad (\forall d \in D)\qquad\text{（需要を満たす）}
$$

$$
\sum_{d \in D}\sum_{t \in T} x_{pdt} \le s_p \quad (\forall p \in P)\qquad\text{（港の供給量を超えない）}
$$

## 5. ユートピア点とナディア点

各目的を単独で最小化し、もう一方の目的の値も記録する。

| 最小化する目的 | TotalCost | AvgDuration [day] | 道路 / 鉄道の割合 |
|---|---:|---:|---:|
| TotalCost | **1,311,311**（ユートピア） | 5.32（ナディア） | 34.07% / 65.93% |
| AvgDuration | 1,812,413（ナディア） | **2.50**（ユートピア） | 100% / 0% |

コストだけを重視すると鉄道を多く使い、所要日数だけを重視するとすべてトラックで運ぶ。
両者の間で、コストは約 1.38 倍、平均所要日数は約 2.1 倍の差がある。

## 6. イプシロン制約法

1つの目的を主目的として最小化し、もう1つの目的は「ε 以下」という制約に置き換える。
ε を変えながら解くと、パレート最適解（トレードオフ曲線）が得られる。

ユートピア点 $f^U$ とナディア点 $f^N$ で各目的を正規化すると、

$$
\bar f(x) = \frac{f(x) - f^U}{f^N - f^U} \in [0, 1]
$$

となる。所要日数を主目的にすると、モデルは次の形になる。

$$
\min\ \overline{\text{AvgDuration}}(x)\quad \text{s.t.}\quad \overline{\text{TotalCost}}(x) \le \varepsilon,\ \text{上の制約},\ x \ge 0
$$

$\varepsilon = 1$ なら所要日数最小化の解、$\varepsilon = 0$ ならコスト最小化の解と同じ値になる。

### 課題1

> 所要日数を主目的としてイプシロン制約法を適用せよ。

手順は次のとおり。

1. ユートピア点・ナディア点を使って、コストと所要日数を正規化する
2. 主目的を設定する
3. イプシロン制約を追加する
4. 道路・鉄道の輸送量の割合を表示する

注：ノートブックのコードのコメントには「Setting cost as a primary objective」とあり、
課題文（所要日数が主目的）と食い違っている。

## 7. 実装ファイル

| ファイル | 内容 |
|---|---|
| `optimization/09Multi_09Optimization_Epsilon_Constraint_Method_Python_Exercise.ipynb` | 元のノートブック（mypulp ＋ CBC） |
| `optimization/09Multi_09Optimization_Epsilon_Constraint_Method_Python_Exercise_mypulp.py` | ノートブックのコードセルを1本にまとめたスクリプト（mypulp 版） |
| `optimization/09Multi_09Optimization_Epsilon_Constraint_Method_Python_Exercise.py` | 最適化を AMPL（amplpy ＋ HiGHS）に置き換えたスクリプト |
| `optimization/maps/` | AMPL 版を実行すると作られる地図（ノード、コスト最小・所要日数最小の解のフロー） |

AMPL 版は次のコマンドで実行できる（パッケージは uv が自動で入れる）。

```
uv run optimization/09Multi_09Optimization_Epsilon_Constraint_Method_Python_Exercise.py
```

AMPL 本体（ライセンス付き）は、次の順に探して最初に見つかったものを使う。
Windows・WSL・macOS のどれでも同じコマンドで動く。

1. 環境変数 `AMPL_DIR` で指定したフォルダ
2. PATH 上にある `ampl`（Windows では `ampl.exe`）のフォルダ
3. よく使われるインストール先（`C:\AMPL`、`~/ampl`、`/opt/ampl`、`/Applications/AMPL` など）

見つからない場合は、`AMPL_DIR` を指定して実行する。

```
# Windows（PowerShell）
$env:AMPL_DIR = "D:\tools\AMPL"; uv run optimization\09Multi_09Optimization_Epsilon_Constraint_Method_Python_Exercise.py

# WSL / macOS
AMPL_DIR=~/ampl uv run optimization/09Multi_09Optimization_Epsilon_Constraint_Method_Python_Exercise.py
```

WSL では Linux 版の AMPL が必要（Windows 側にインストールした `ampl.exe` は WSL の Python からは使えない）。
