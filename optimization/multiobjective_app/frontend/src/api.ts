import type { Bounds, FrontierResult, Inputs, Network, Primary, Solution } from "./types";

/** API を呼び出す。エラー時は FastAPI の detail（日本語メッセージ）を Error にして投げる */
async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new Error("サーバーに接続できません。バックエンド（uvicorn）が起動しているか確認してください。");
  }
  const text = await res.text();
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(`サーバーの応答を読めませんでした（HTTP ${res.status}）: ${text.slice(0, 200)}`);
  }
  if (!res.ok) {
    const detail = (data as { detail?: unknown }).detail;
    const message = typeof detail === "string" ? detail : JSON.stringify(detail);
    throw new Error(res.status === 422 ? message : `HTTP ${res.status}: ${message}`);
  }
  return data as T;
}

export function fetchNetwork(signal?: AbortSignal): Promise<Network> {
  return request<Network>("/api/network", undefined, signal);
}

export function fetchFrontier(inputs: Inputs, primary: Primary, nPoints: number): Promise<FrontierResult> {
  return request<FrontierResult>("/api/frontier", { ...inputs, primary, n_points: nPoints });
}

export async function solveEpsilon(
  inputs: Inputs,
  primary: Primary,
  epsilon: number,
  bounds: Bounds,
): Promise<Solution> {
  const res = await request<{ bounds: Bounds; solution: Solution }>("/api/solve", {
    ...inputs,
    primary,
    epsilon,
    bounds,
  });
  return res.solution;
}
