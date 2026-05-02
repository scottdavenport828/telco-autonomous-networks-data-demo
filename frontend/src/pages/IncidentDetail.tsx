import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import clsx from "clsx";
import { api, type Incident } from "../api/client";

type Tab = "report" | "events";

function severityClass(severity: string | null | undefined): string {
  const s = (severity ?? "").toUpperCase();
  if (s === "HIGH" || s === "CRITICAL") {
    return "bg-rose-100 text-rose-800 ring-1 ring-rose-200";
  }
  if (s === "MEDIUM" || s === "MED") {
    return "bg-amber-100 text-amber-800 ring-1 ring-amber-200";
  }
  if (s === "LOW") {
    return "bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200";
  }
  return "bg-slate-100 text-slate-700 ring-1 ring-slate-200";
}

function statusClass(status: string | null | undefined): string {
  const s = (status ?? "").toLowerCase();
  if (s.includes("resolv") || s.includes("closed")) {
    return "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200";
  }
  if (s.includes("progress") || s.includes("investig")) {
    return "bg-sky-50 text-sky-700 ring-1 ring-sky-200";
  }
  if (s.includes("open") || s.includes("new")) {
    return "bg-amber-50 text-amber-700 ring-1 ring-amber-200";
  }
  return "bg-slate-50 text-slate-700 ring-1 ring-slate-200";
}

function formatDuration(startTs: string, endTs: string | null): string {
  const start = new Date(startTs).getTime();
  const end = endTs ? new Date(endTs).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end) || end <= start) return "—";
  const ms = end - start;
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hours < 24) return `${hours}h ${mins}m`;
  const days = Math.floor(hours / 24);
  const hrs = hours % 24;
  return `${days}d ${hrs}h`;
}

export default function IncidentDetail() {
  const { id } = useParams();
  const [incident, setIncident] = useState<Incident | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("report");

  useEffect(() => {
    if (!id) return;
    api
      .incident(id)
      .then(setIncident)
      .catch((e) => setError(e.message));
  }, [id]);

  const shortId = useMemo(() => (incident ? incident.incident_id.slice(0, 8) : ""), [incident]);

  if (error) return <div className="text-rose-600">Error: {error}</div>;
  if (!incident) return <div className="text-slate-500">Loading…</div>;

  const hasReport = Boolean(incident.preliminary_analysis && incident.preliminary_analysis.trim());
  const hasEvents = Boolean(incident.events && incident.events.trim());
  const workbenchHref = `/workbench?agent=rca&incident_id=${encodeURIComponent(incident.incident_id)}`;

  return (
    <div className="space-y-5">
      {/* Header */}
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Link to="/incidents" className="text-sm text-slate-500 hover:text-slate-700">
              Incidents
            </Link>
            <span className="text-slate-300">/</span>
            <span className="font-mono text-sm text-slate-700">{shortId}…</span>
          </div>
          <h1 className="text-xl font-semibold text-ink">
            Cell <span className="font-mono">{incident.enodeb_id}/{incident.cell_id}</span>
            <span className="text-slate-400 font-normal text-base"> — {incident.description}</span>
          </h1>
        </div>
        <span
          className={clsx(
            "inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide",
            severityClass(incident.severity),
          )}
        >
          {incident.severity ?? "unknown severity"}
        </span>
      </header>

      {/* Metadata block */}
      <section className="bg-white rounded-lg border border-slate-200 p-4 space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-slate-500 text-xs uppercase tracking-wide">Status</div>
            <div className="mt-1">
              <span className={clsx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", statusClass(incident.status))}>
                {incident.status}
              </span>
            </div>
          </div>
          <div>
            <div className="text-slate-500 text-xs uppercase tracking-wide">Started</div>
            <div className="mt-1 text-slate-900">{new Date(incident.start_ts).toLocaleString()}</div>
          </div>
          <div>
            <div className="text-slate-500 text-xs uppercase tracking-wide">Ended</div>
            <div className="mt-1 text-slate-900">
              {incident.end_ts ? new Date(incident.end_ts).toLocaleString() : "—"}
            </div>
          </div>
          <div>
            <div className="text-slate-500 text-xs uppercase tracking-wide">Duration</div>
            <div className="mt-1 text-slate-900">{formatDuration(incident.start_ts, incident.end_ts)}</div>
          </div>
        </div>

        {incident.kpi_missed?.length > 0 && (
          <div>
            <div className="text-slate-500 text-xs uppercase tracking-wide mb-2">Missed KPIs</div>
            <div className="flex flex-wrap gap-2">
              {incident.kpi_missed.map((k, i) => (
                <span
                  key={`${k.kpi}-${i}`}
                  className="bg-slate-200 rounded px-2 py-0.5 text-xs font-mono text-slate-800"
                >
                  {k.kpi} <span className="text-slate-500">·</span> {k.value.toFixed(2)}
                </span>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Tabs / report */}
      {hasReport || hasEvents ? (
        <section className="bg-white rounded-lg border border-slate-200">
          <div className="flex items-center gap-1 border-b border-slate-200 px-2 pt-2">
            <button
              type="button"
              onClick={() => setTab("report")}
              className={clsx(
                "px-3 py-2 text-sm font-medium rounded-t-md",
                tab === "report"
                  ? "bg-white text-ink border border-slate-200 border-b-white -mb-px"
                  : "text-slate-500 hover:text-slate-800",
              )}
            >
              RCA report
            </button>
            <button
              type="button"
              onClick={() => setTab("events")}
              className={clsx(
                "px-3 py-2 text-sm font-medium rounded-t-md",
                tab === "events"
                  ? "bg-white text-ink border border-slate-200 border-b-white -mb-px"
                  : "text-slate-500 hover:text-slate-800",
              )}
            >
              Raw events
            </button>
          </div>

          <div className="p-5">
            {tab === "report" &&
              (hasReport ? (
                <article className="prose prose-slate max-w-none prose-headings:scroll-mt-20 prose-h2:text-base prose-h2:font-semibold prose-h2:text-ink prose-h2:border-b prose-h2:border-slate-200 prose-h2:pb-2 prose-h3:text-sm prose-h3:font-semibold prose-a:text-blue-700 prose-code:text-rose-700 prose-code:bg-slate-100 prose-code:px-1 prose-code:rounded prose-code:before:content-none prose-code:after:content-none prose-pre:bg-slate-900 prose-pre:text-slate-100">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {incident.preliminary_analysis ?? ""}
                  </ReactMarkdown>
                </article>
              ) : (
                <div className="text-sm text-slate-500">No RCA report yet.</div>
              ))}

            {tab === "events" &&
              (hasEvents ? (
                <pre className="text-xs whitespace-pre-wrap font-mono bg-slate-50 border border-slate-200 rounded p-3 text-slate-800 overflow-x-auto">
                  {incident.events}
                </pre>
              ) : (
                <div className="text-sm text-slate-500">No raw events recorded.</div>
              ))}
          </div>
        </section>
      ) : (
        <section className="bg-white rounded-lg border border-dashed border-slate-300 p-6 text-center">
          <h2 className="text-base font-semibold text-ink mb-1">RCA not yet run</h2>
          <p className="text-sm text-slate-500 mb-4">
            Open the Workbench to analyse this incident with the <code>rca_orchestrator</code> agent.
          </p>
          <Link
            to={workbenchHref}
            className="inline-flex items-center rounded-md bg-ink px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
          >
            Open in Workbench
          </Link>
        </section>
      )}

      {/* Footer */}
      <footer className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
        <div className="bg-white rounded-lg border border-slate-200 p-3">
          <div className="text-slate-500 text-xs uppercase tracking-wide mb-1">Cause</div>
          <div className="text-slate-900">{incident.cause || "—"}</div>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-3">
          <div className="text-slate-500 text-xs uppercase tracking-wide mb-1">Resolution</div>
          <div className="text-slate-900">{incident.resolution || "—"}</div>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-3">
          <div className="text-slate-500 text-xs uppercase tracking-wide mb-1">Created</div>
          <div className="text-slate-900">{new Date(incident.created_ts).toLocaleString()}</div>
        </div>
      </footer>
    </div>
  );
}
