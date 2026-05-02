import { useEffect, useState } from "react";
import { api, type KpiRow, type Thresholds, type ViolationRow } from "../api/client";
import KpiChart from "../components/KpiChart";
import CellMap from "../components/CellMap";
import AnomalyButton from "../components/AnomalyButton";

const CELLS: Array<{ enodeb: string; cell: string }> = [
  { enodeb: "1", cell: "12310" },
  { enodeb: "1", cell: "12311" },
  { enodeb: "1", cell: "12312" },
  { enodeb: "1", cell: "12313" },
  { enodeb: "1", cell: "12314" },
  { enodeb: "1", cell: "12315" },
  { enodeb: "2", cell: "22310" },
  { enodeb: "2", cell: "22311" },
  { enodeb: "2", cell: "22312" },
  { enodeb: "2", cell: "22313" },
  { enodeb: "2", cell: "22314" },
  { enodeb: "2", cell: "22315" },
  { enodeb: "2", cell: "22414" },
  { enodeb: "3", cell: "32310" },
  { enodeb: "3", cell: "32311" },
  { enodeb: "3", cell: "32312" },
  { enodeb: "3", cell: "32313" },
  { enodeb: "3", cell: "32314" },
  { enodeb: "3", cell: "32315" },
];

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

      <section className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="text-sm font-semibold text-slate-700 mb-1">Inject test anomaly</h2>
        <p className="text-xs text-slate-500 mb-3">
          Pick a cell to bias the next 15-min generator tick toward a degraded KPI. Use the Workbench's incident_detector
          afterward to watch the agent surface the new violation.
        </p>
        <div className="flex flex-wrap gap-2">
          {CELLS.map(({ enodeb, cell }) => (
            <AnomalyButton key={`${enodeb}/${cell}`} enodebId={enodeb} cellId={cell} label="Inject" />
          ))}
        </div>
      </section>
    </div>
  );
}
