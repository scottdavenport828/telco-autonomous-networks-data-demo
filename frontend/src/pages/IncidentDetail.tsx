import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type Incident } from "../api/client";

export default function IncidentDetail() {
  const { id } = useParams();
  const [incident, setIncident] = useState<Incident | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api.incident(id)
      .then(setIncident)
      .catch((e) => setError(e.message));
  }, [id]);

  if (error) return <div className="text-red-600">Error: {error}</div>;
  if (!incident) return <div>Loading…</div>;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Incident {incident.incident_id}</h1>

      <section className="bg-white rounded-lg border border-slate-200 p-4 grid grid-cols-2 gap-3 text-sm">
        <div><span className="text-slate-500">Cell:</span> {incident.enodeb_id}/{incident.cell_id}</div>
        <div><span className="text-slate-500">Status:</span> {incident.status}</div>
        <div><span className="text-slate-500">Severity:</span> {incident.severity ?? "—"}</div>
        <div><span className="text-slate-500">Description:</span> {incident.description}</div>
        <div><span className="text-slate-500">Started:</span> {new Date(incident.start_ts).toLocaleString()}</div>
        <div><span className="text-slate-500">Ended:</span> {incident.end_ts ? new Date(incident.end_ts).toLocaleString() : "—"}</div>
      </section>

      <section className="bg-white rounded-lg border border-slate-200 p-4">
        <h2 className="font-semibold text-sm text-slate-700 mb-2">Missed KPIs</h2>
        <ul className="text-sm list-disc pl-4">
          {incident.kpi_missed.map((k, i) => (
            <li key={i}>
              <code>{k.kpi}</code> = {k.value.toFixed(2)}
            </li>
          ))}
        </ul>
      </section>

      {incident.preliminary_analysis && (
        <section className="bg-white rounded-lg border border-slate-200 p-4">
          <h2 className="font-semibold text-sm text-slate-700 mb-2">Analysis report</h2>
          <pre className="text-sm whitespace-pre-wrap font-sans">{incident.preliminary_analysis}</pre>
        </section>
      )}

      {incident.events && (
        <section className="bg-white rounded-lg border border-slate-200 p-4">
          <h2 className="font-semibold text-sm text-slate-700 mb-2">Events</h2>
          <pre className="text-xs whitespace-pre-wrap font-sans">{incident.events}</pre>
        </section>
      )}
    </div>
  );
}
