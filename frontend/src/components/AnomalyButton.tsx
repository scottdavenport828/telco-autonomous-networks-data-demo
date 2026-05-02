import { useState } from "react";
import clsx from "clsx";
import { api, type AnomalyRequest } from "../api/client";

type Props = {
  enodebId: string;
  cellId: string;
  /** Tailwind sizing for the trigger; default is a small inline button. */
  className?: string;
  label?: string;
  /** Called after a successful injection. */
  onInjected?: () => void;
};

const KPI_PRESETS: Array<{
  label: string;
  kpi: AnomalyRequest["kpi"];
  magnitude: number;
  description: string;
}> = [
  { label: "ERAB success ↓ 85%", kpi: "erab_success_rate", magnitude: 0.85, description: "Pushes ERAB success rate below the 97% threshold." },
  { label: "ERAB success ↓ 75%", kpi: "erab_success_rate", magnitude: 0.75, description: "Severe degradation; triggers high-severity classification." },
  { label: "Retainability ↑ 4.2", kpi: "retainability", magnitude: 4.2, description: "Active E-RAB releases per hour above the 3.0 threshold." },
];

export default function AnomalyButton({ enodebId, cellId, className, label = "Inject anomaly", onInjected }: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [duration, setDuration] = useState(60);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function inject(preset: typeof KPI_PRESETS[number]) {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await api.injectAnomaly({
        enodeb_id: enodebId,
        cell_id: cellId,
        kpi: preset.kpi,
        magnitude: preset.magnitude,
        duration_minutes: duration,
        note: preset.label,
      });
      setSuccess(`Scheduled ${preset.label} until ${new Date(result.end_ts).toLocaleTimeString()}.`);
      onInjected?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative inline-block">
      <button
        type="button"
        className={clsx(
          "text-xs font-medium rounded-md px-2.5 py-1.5 bg-rose-50 text-rose-700 ring-1 ring-rose-200 hover:bg-rose-100",
          className,
        )}
        onClick={() => setOpen((v) => !v)}
      >
        {label} · {enodebId}/{cellId}
      </button>
      {open && (
        <div className="absolute z-10 mt-1 w-80 bg-white border border-slate-200 rounded-md shadow-lg p-3 right-0">
          <div className="text-xs font-semibold text-slate-700 mb-1">
            Inject anomaly on cell {enodebId}/{cellId}
          </div>
          <div className="text-[11px] text-slate-500 mb-3">
            The next 15-min generator tick will bias this cell toward the chosen KPI value.
          </div>
          <div className="space-y-1.5 mb-3">
            {KPI_PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                disabled={busy}
                onClick={() => inject(p)}
                className="w-full text-left text-xs px-2 py-1.5 rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-50"
              >
                <div className="font-medium text-slate-800">{p.label}</div>
                <div className="text-[11px] text-slate-500">{p.description}</div>
              </button>
            ))}
          </div>
          <label className="block text-[11px] text-slate-500 mb-3">
            Duration (min)
            <input
              type="number"
              min={5}
              max={1440}
              value={duration}
              onChange={(e) => setDuration(parseInt(e.target.value || "60", 10))}
              className="w-full mt-1 px-2 py-1 text-xs border border-slate-300 rounded"
            />
          </label>
          {error && <div className="text-xs text-rose-700 mb-2">{error}</div>}
          {success && <div className="text-xs text-emerald-700 mb-2">{success}</div>}
          <div className="flex justify-end">
            <button
              type="button"
              className="text-xs text-slate-500 hover:text-slate-800"
              onClick={() => setOpen(false)}
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
