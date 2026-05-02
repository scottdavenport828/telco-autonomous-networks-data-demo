import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Incident } from "../api/client";

export default function Incidents() {
  const [rows, setRows] = useState<Incident[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.incidents()
      .then((r) => setRows(r.rows))
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="text-red-600">Error: {error}</div>;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Incidents</h1>
      <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-100 text-slate-700">
            <tr>
              <th className="text-left px-3 py-2">ID</th>
              <th className="text-left px-3 py-2">Cell</th>
              <th className="text-left px-3 py-2">Status</th>
              <th className="text-left px-3 py-2">Severity</th>
              <th className="text-left px-3 py-2">Description</th>
              <th className="text-left px-3 py-2">Started</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.incident_id} className="border-t border-slate-200 hover:bg-slate-50">
                <td className="px-3 py-2 font-mono text-xs">
                  <Link to={`/incidents/${r.incident_id}`} className="text-blue-700 underline">
                    {r.incident_id.slice(0, 8)}…
                  </Link>
                </td>
                <td className="px-3 py-2 font-mono text-xs">{r.enodeb_id}/{r.cell_id}</td>
                <td className="px-3 py-2">{r.status}</td>
                <td className="px-3 py-2">{r.severity ?? "—"}</td>
                <td className="px-3 py-2">{r.description}</td>
                <td className="px-3 py-2 text-xs">{new Date(r.start_ts).toLocaleString()}</td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-slate-500">
                  No incidents yet. Open the Workbench to detect some.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
