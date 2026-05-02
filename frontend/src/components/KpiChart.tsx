import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";
import type { KpiRow, Thresholds } from "../api/client";

type Props = {
  rows: KpiRow[];
  thresholds: Thresholds;
  metric: "erab_success_rate" | "retainability";
};

export default function KpiChart({ rows, thresholds, metric }: Props) {
  const data = rows.map((r) => ({
    ts: new Date(r.measurement_end).toLocaleString(),
    value: r[metric],
    cell: `${r.enodeb_id}/${r.cell_id}`,
  }));

  const threshold = metric === "erab_success_rate" ? thresholds.erab_success_rate_min : thresholds.retainability_max;
  const label = metric === "erab_success_rate" ? "ERAB success rate (%)" : "Retainability (releases/hour)";

  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h3 className="text-sm font-semibold mb-2 text-slate-700">{label}</h3>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="ts" tick={{ fontSize: 10 }} interval={Math.floor(data.length / 8)} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip />
          <Legend />
          <ReferenceLine y={threshold} stroke="#E63946" strokeDasharray="4 4" label={{ value: `threshold: ${threshold}`, fontSize: 10, fill: "#E63946" }} />
          <Line type="monotone" dataKey="value" stroke="#1F4068" strokeWidth={1.5} dot={false} name={metric} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
