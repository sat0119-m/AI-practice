# 多目的最適化 ― ε制約法 Web アプリ

`09Multi_09Optimization_Epsilon_Constraint_Method_Python_Exercise_ja.py` をもとにした、React + FastAPI の Web アプリです。
港から配送センターへの輸送で「道路のみ」と「鉄道＋道路」を選び、**総コスト**と**平均所要日数**のトレードオフ（パレートフロント）を **AMPL**（ソルバーは HiGHS）で求めます。CO2 排出量は、各解の評価指標として表示します。

ローカルの PC で動かすためのアプリです（Vercel などへの公開は想定していません）。

## できること

- ユートピア点とナディア点を求め、その間を等間隔に分けた ε でパレートフロントを描く（点の数は 5〜21）
- ε をスライダーで動かし、その解の総コスト・平均所要日数・CO2・輸送モードの割合と、地図上の輸送フローを表示する
- 主目的の切り替え
  - **所要日数を最小化**（総コストに上限 ε。初期値）
  - **総コストを最小化**（平均所要日数に上限 ε）
- パラメータ（マイル当たりのコスト・最低コスト・速度・稼働時間・ターミナル滞留日数・CO2 排出係数）と、需要・供給量の変更

## フォルダ構成

```
multiobjective_app/
├── README.md
├── backend/                         FastAPI（Python）
│   ├── main.py                      API（/api/network, /api/frontier, /api/solve）
│   ├── multiobjective_core.py       コスト等の計算と AMPL モデル（ε制約法）
│   ├── precompute_network.py        道路・鉄道の距離と経路の事前計算（scgraph を使う。通常は実行不要）
│   ├── requirements.txt             アプリ本体の依存パッケージ
│   ├── requirements-precompute.txt  事前計算だけで使う依存パッケージ
│   └── data/
│       ├── distribution_centers.csv / ports.csv / rail_terminals.csv   元データ
│       └── network.json             事前計算の結果（同梱済み）
└── frontend/                        React + TypeScript（Vite）
    ├── package.json
    └── src/
        ├── App.tsx                  画面全体
        ├── api.ts / types.ts / format.ts
        └── components/              入力パネル・パレートフロントのグラフ・地図・結果表示
```

## 他の PC で動かす手順

### 1. 必要なもの

| もの | バージョン | 備考 |
|---|---|---|
| Python | 3.10 以上 | 3.12 と 3.14 で動作を確認済み |
| Node.js | 20.19 以上、または 22.12 以上 | Vite 7 の要件。`node --version` で確認 |
| AMPL 本体 | ライセンス付きのもの | HiGHS ソルバー（`highs` / `highs.exe`）が同じフォルダに入っていること |

道路・鉄道の距離は `backend/data/network.json` に同梱済みなので、`scgraph` は不要です（データを作り直すときだけ使います。[事前計算](#事前計算をやり直す場合)を参照）。

### 2. AMPL の場所を設定する

アプリは AMPL 本体のフォルダを、次の順に探して最初に見つかったものを使います（`multiobjective_core.py` の `find_ampl_dir()`）。

1. 環境変数 `AMPL_DIR` で指定したフォルダ
2. PATH 上にある `ampl`（Windows では `ampl.exe`）のフォルダ
3. よくあるインストール先: `C:\AMPL`、`~/ampl`、`~/AMPL`、`/opt/ampl`、`/Applications/AMPL`

上の 2 か 3 に当てはまれば設定は不要です。それ以外の場所に AMPL がある場合は、`AMPL_DIR` を設定してください。

**Windows（PowerShell）**

```powershell
# いま開いているターミナルだけで有効
$env:AMPL_DIR = "D:\tools\ampl"

# 今後ずっと有効にする（設定後、ターミナルを開き直す）
setx AMPL_DIR "D:\tools\ampl"
```

**macOS / Linux / WSL（bash・zsh）**

```bash
export AMPL_DIR="$HOME/ampl"                         # いま開いているターミナルだけで有効
echo 'export AMPL_DIR="$HOME/ampl"' >> ~/.bashrc    # 今後ずっと有効にする（zsh なら ~/.zshrc）
```

WSL では Linux 版の AMPL が必要です（Windows 側の `ampl.exe` は WSL の Python からは使えません）。

ソルバーを HiGHS 以外にしたいときは、環境変数 `AMPL_SOLVER` に AMPL のソルバー名を指定します（例: `cbc`、`gurobi`）。

### 3. バックエンドの準備（初回のみ）

```bash
cd multiobjective_app/backend
python -m venv .venv
```

仮想環境を有効にします。

```powershell
.venv\Scripts\Activate.ps1          # Windows（PowerShell）
```

```bash
source .venv/bin/activate           # macOS / Linux / WSL
```

パッケージを入れます。

```bash
pip install -r requirements.txt
```

AMPL が見つかるかを確認します（AMPL のフォルダが表示されれば OK）。

```bash
python -c "import multiobjective_core as c; print(c.find_ampl_dir())"
```

> [uv](https://docs.astral.sh/uv/) を使う場合は、仮想環境を作らずに
> `uv run --with-requirements requirements.txt uvicorn main:app --reload` で起動できます。

### 4. フロントエンドの準備（初回のみ）

```bash
cd multiobjective_app/frontend
npm install
```

npm 12 以降では `esbuild` の postinstall について `allow-scripts` の警告が出ることがありますが、そのままで動きます。
もし `npm run dev` や `npm run build` が esbuild のエラーで止まる場合は、`npm approve-scripts esbuild` を実行してから `npm install` をやり直してください。

### 5. 起動する

**A. 開発モード（ターミナルを2つ使う。コードを直すとすぐ反映される）**

```bash
# ターミナル1: バックエンド（http://localhost:8000）
cd multiobjective_app/backend
# （仮想環境を有効にしてから）
uvicorn main:app --reload
```

```bash
# ターミナル2: フロントエンド（http://localhost:5173）
cd multiobjective_app/frontend
npm run dev
```

ブラウザで **http://localhost:5173** を開きます（`/api` へのアクセスは Vite がバックエンドに転送します）。

**B. ビルドして1つで動かす**

```bash
cd multiobjective_app/frontend
npm run build                 # frontend/dist ができる

cd ../backend
uvicorn main:app              # dist があれば FastAPI が画面も配信する
```

ブラウザで **http://localhost:8000** を開きます。

> **`--reload` について**: 計算中（AMPL の実行中）に `backend` の Python ファイルを書き換えると、Windows では
> 自動の再起動が「Reloading...」のまま終わらず、古いコードが動き続けることがあります。その場合は
> uvicorn を Ctrl+C で止めて起動し直してください。

### 計算時間について

AMPL はソルバーを呼ぶたびに別プロセスとして起動します。作成した PC（Windows）では、この起動だけで1回あたり2〜4秒かかりました。そこで、互いに独立な複数の問題を1つの線形計画にまとめて解き、呼び出し回数を減らしています。

- 「計算」ボタン: ソルバーを3回呼びます（ユートピア点 → ナディア点 → パレートフロントの全点）。作成した PC では 12〜17 秒でした。
- スライダー: 3回目の呼び出しで ε = 0, 0.01, …, 1 の 101 点もまとめて解いてあるので、待ち時間なしで切り替わります。
- 「この ε で解く」: 0.01 刻みでない ε（例: 0.333）は、その場で1回解きます（作成した PC で約5秒）。

## ε制約法の中身

`multiobjective_core.py` の `EpsilonModel.solve_epsilon()` で、ノートブックの課題1（ε制約法）を実装しています。主目的を所要日数にした場合は、次の問題を解きます。

```
minimize    平均所要日数
subject to  (総コスト − ユートピアコスト) / (ナディアコスト − ユートピアコスト) ≤ ε
            需要・供給の制約（スクリプトと同じ）
```

- ε = 0 は総コストを最小値に固定（コスト最小の解の中で所要日数が最短の解）、ε = 1 は制約なし（所要日数が最短の解）です。
- ナディア点は、片方の目的を最良値に固定したうえでもう片方を最小化して求めています（辞書式最適化）。単に片方だけを最小化すると、最適解が複数あるときにナディア点がずれることがあるためです。
- 主目的を総コストに切り替えても、得られるパレートフロントは同じ曲線になります。

## API

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/api/network` | ノード・区間の経路座標と、画面の初期値（パラメータ・需要・供給量） |
| POST | `/api/frontier` | ユートピア点・ナディア点、パレートフロント（`points`）、スライダー用の 101 点（`grid`） |
| POST | `/api/solve` | 指定した ε で1回だけ解く（`bounds` を省略するとユートピア点・ナディア点から求める） |

入力に誤りがあるとき（例: 供給量の合計が需要の合計より少ない）は、HTTP 422 と日本語のメッセージを返します。
`uvicorn` の起動中は http://localhost:8000/docs で API を試せます。

## 事前計算をやり直す場合

元データ（`data/*.csv`）を変えたときだけ、`network.json` を作り直します。`scgraph` は Python 3.13 未満が必要です。

```bash
cd multiobjective_app/backend
pip install -r requirements-precompute.txt
python precompute_network.py
```

uv を使う場合:

```bash
uv run --python 3.12 --with-requirements requirements-precompute.txt python precompute_network.py
```

道路・鉄道網のデータのダウンロードと最短経路の計算に数分かかります。
