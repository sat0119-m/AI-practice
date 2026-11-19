"""多目的最適化（ε制約法）Web アプリの FastAPI バックエンド

起動方法（multiobjective_app/backend で実行）::

    uvicorn main:app --reload

API:
    GET  /api/network   ノード・区間の経路座標と、画面の初期値（パラメータ・需要・供給量）
    POST /api/frontier  ユートピア点・ナディア点とパレートフロント（＋スライダー用の 0.01 刻みの解）
    POST /api/solve     指定した ε で1回だけ解く

frontend/dist（npm run build の出力）があれば、それを / で配信する。
"""

import math
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import multiobjective_core as core

app = FastAPI(title="Multi-Objective Optimization - Epsilon Constraint Method")

# Vite の開発サーバー (npm run dev) からのアクセスを許可
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Params(BaseModel):
    """アークのコスト・排出量・所要時間を計算するためのパラメータ"""

    cost_mile_road: float = Field(ge=0)
    cost_mile_rail: float = Field(ge=0)
    min_cost_road: float = Field(ge=0)
    min_cost_rail: float = Field(ge=0)
    emission_road_lb: float = Field(ge=0)
    emission_rail_lb: float = Field(ge=0)
    speed_road: float = Field(gt=0)
    speed_rail: float = Field(gt=0)
    hours_day: float = Field(gt=0, le=24)
    duration_rail_terminal: float = Field(ge=0)


class Inputs(BaseModel):
    """画面からの入力（パラメータ・需要・供給量・主目的）"""

    params: Params
    demand: dict[str, float]                       # 配送センターID → 需要
    incoming_flow: dict[str, float]                # 港ID → 流入量（供給量）
    primary: Literal["duration", "cost"] = "duration"


class FrontierRequest(Inputs):
    """パレートフロントの計算リクエスト"""

    n_points: int = Field(default=11, ge=2, le=50)


class Bounds(BaseModel):
    """ユートピア点とナディア点"""

    utopia_cost: float
    nadir_cost: float
    utopia_duration: float
    nadir_duration: float


class SolveRequest(Inputs):
    """1回だけ解くリクエスト（bounds を省略すると、ユートピア点・ナディア点から求める）"""

    epsilon: float = Field(ge=0, le=1)
    bounds: Bounds | None = None


# 入力チェックのエラーを日本語で返すための項目名
FIELD_LABELS = {
    "cost_mile_road": "道路のコスト", "cost_mile_rail": "鉄道のコスト",
    "min_cost_road": "道路の最低コスト", "min_cost_rail": "鉄道の最低コスト",
    "emission_road_lb": "道路の CO2 排出係数", "emission_rail_lb": "鉄道の CO2 排出係数",
    "speed_road": "道路の平均速度", "speed_rail": "鉄道の平均速度",
    "hours_day": "1日の稼働時間", "duration_rail_terminal": "鉄道ターミナルでの滞留",
    "params": "パラメータ", "demand": "需要", "incoming_flow": "供給量",
    "primary": "主目的", "n_points": "点の数", "epsilon": "ε", "bounds": "ユートピア点・ナディア点",
}


def _describe(error):
    """pydantic の入力エラー1件を、日本語の文に直す"""
    loc = [str(x) for x in error.get("loc", []) if x != "body"]
    name = " の ".join(FIELD_LABELS.get(x, x) for x in loc) or "リクエスト"
    ctx = error.get("ctx", {})
    kind = error.get("type", "")
    if kind == "greater_than":
        return f"{name}は {ctx.get('gt')} より大きい値にしてください"
    if kind == "greater_than_equal":
        return f"{name}は {ctx.get('ge')} 以上にしてください"
    if kind == "less_than_equal":
        return f"{name}は {ctx.get('le')} 以下にしてください"
    if kind in ("float_type", "float_parsing", "int_type", "int_parsing", "int_from_float"):
        return f"{name}を数値で入力してください"
    if kind == "missing":
        return f"{name}がありません"
    if kind == "literal_error":
        return f"{name}は {ctx.get('expected')} のどれかにしてください"
    return f"{name}: {error.get('msg')}"


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    """入力チェックのエラーを、画面にそのまま出せる日本語のメッセージにして 422 で返す"""
    return JSONResponse(status_code=422, content={"detail": "入力が不正です: " + "／".join(_describe(e) for e in exc.errors())})


def _run(func, *args):
    """計算を実行し、入力エラーや AMPL が見つからないときは 422 / 500 に変換する"""
    try:
        return func(*args)
    except core.ModelError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/network")
def get_network():
    """ノード・区間の経路座標と、画面の初期値を返す"""
    return {**core.load_network(), "defaults": core.default_inputs()}


@app.post("/api/frontier")
async def post_frontier(req: FrontierRequest):
    """ユートピア点・ナディア点とパレートフロントを計算する"""
    return await run_in_threadpool(
        _run, core.compute_frontier,
        req.params.model_dump(), req.demand, req.incoming_flow, req.primary, req.n_points,
    )


@app.post("/api/solve")
async def post_solve(req: SolveRequest):
    """指定した ε で1回だけ解く"""
    bounds = req.bounds.model_dump() if req.bounds else None
    if bounds and not all(math.isfinite(v) for v in bounds.values()):
        raise HTTPException(status_code=422, detail="bounds の値が不正です")
    return await run_in_threadpool(
        _run, core.solve_single,
        req.params.model_dump(), req.demand, req.incoming_flow, req.primary, req.epsilon, bounds,
    )


# ビルド済みのフロントエンドがあれば配信する（npm run build 後に uvicorn だけで動かせる）
DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="frontend")
