import type { Network, Solution } from "../types";
import { fmtTon } from "../format";

interface Props {
  network: Network;
  solution: Solution;
}

/** 選択中の解の輸送フロー一覧（輸送量の多い順） */
export default function FlowTable({ network, solution }: Props) {
  const portName = new Map(network.ports.map((p) => [p.ID, p.name]));
  const dcName = new Map(network.distribution_centers.map((d) => [d.ID, `${d.ID} ${d.name}`]));
  const rows = [...solution.flows].sort((a, b) => b.flow - a.flow);

  return (
    <details className="flow-table">
      <summary>輸送フローの一覧（{rows.length} 件）</summary>
      <table>
        <thead>
          <tr>
            <th>港</th>
            <th>配送センター</th>
            <th>輸送モード</th>
            <th className="num">輸送量</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((f) => (
            <tr key={`${f.port}|${f.dc}|${f.mode}`}>
              <td>{portName.get(f.port)}</td>
              <td>{dcName.get(f.dc)}</td>
              <td>{f.mode === "road_only" ? "道路のみ" : "鉄道＋道路"}</td>
              <td className="num">{fmtTon(f.flow)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
