import { useEffect, useState } from "react";
import { api, type KpiRow, type Thresholds, type ViolationRow } from "../api/client";
import KpiChart from "../components/KpiChart";
import CellMap from "../components/CellMap";

export default function Dashboard() {
  const [kpis, setKpis] = useState<KpiRow[]>([]);
  const [thresholds, setThresholds] = useState<Thresholds>({ erab_success_rate_min: 97, retainability_max: 3 });
  const [violations, setViolations] = useState<ViolationRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.kpis(), api.violations()])
      .then(([k, v]) => {
        setKpis(k.rows);
        setThresholds(k.thresholds);
        setViolations(v.rows);
      })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="text-red-600">Error loading data: {error}</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Network operations</h1>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <KpiChart rows={kpis} thresholds={thresholds} metric="erab_success_rate" />
        <KpiChart rows={kpis} thresholds={thresholds} metric="retainability" />
      </section>

      <section>
        <h2 className="text-sm font-semibold text-slate-700 mb-2">Cells with KPI violations</h2>
        <CellMap rows={violations} />
      </section>
    </div>
  );
}
