import { useEffect, useState } from "react";
import clsx from "clsx";
import { api } from "../api/client";

export default function AutopilotToggle() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.autopilotState()
      .then((s) => setEnabled(s.enabled))
      .catch((e) => setError((e as Error).message));
  }, []);

  async function toggle() {
    if (enabled === null) return;
    setBusy(true);
    setError(null);
    try {
      const next = !enabled;
      const r = await api.setAutopilot(next);
      setEnabled(r.enabled);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runOnce(stage: "detect" | "rca" | "remediate" | "verify") {
    setRunning(stage);
    setError(null);
    try {
      await api.runAutopilotStage(stage);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(null);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={toggle}
        disabled={busy || enabled === null}
        className={clsx(
          "text-xs font-semibold px-3 py-1.5 rounded-md ring-1 transition",
          enabled
            ? "bg-emerald-50 text-emerald-700 ring-emerald-200 hover:bg-emerald-100"
            : "bg-slate-100 text-slate-700 ring-slate-200 hover:bg-slate-200",
        )}
        title={enabled ? "Autopilot is running — click to pause" : "Autopilot is paused — click to engage"}
      >
        <span
          className={clsx(
            "inline-block w-1.5 h-1.5 rounded-full mr-1.5 align-middle",
            enabled ? "bg-emerald-500 animate-pulse" : "bg-slate-400",
          )}
          aria-hidden
        />
        Autopilot {enabled === null ? "…" : enabled ? "ON" : "OFF"}
      </button>
      {enabled && (
        <div className="flex gap-1">
          {(["detect", "rca", "remediate", "verify"] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => runOnce(s)}
              disabled={running !== null}
              className="text-[10px] font-medium px-1.5 py-0.5 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              title={`Trigger autopilot ${s} now`}
            >
              {running === s ? "…" : s}
            </button>
          ))}
        </div>
      )}
      {error && <span className="text-xs text-rose-700 ml-2">{error}</span>}
    </div>
  );
}
