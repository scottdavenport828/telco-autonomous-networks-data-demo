import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  api,
  type LatencyBucket,
  type LatencyResponse,
  type PiiResponse,
  type RecentCall,
  type RecentResponse,
  type TokenBucket,
  type TokensResponse,
} from "../api/client";

const HOURS = 24;
const LATENCY_THRESHOLD_MS = 5000;

function formatHour(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
  });
}

function formatTs(iso: string) {
  return new Date(iso).toLocaleString();
}

// ---------- Token usage panel ----------

type TokenChartRow = {
  hr: string;
  hrIso: string;
  input_tokens: number;
  output_tokens: number;
  models: { model: string; input: number; output: number; calls: number }[];
};

function buildTokenChart(rows: TokenBucket[]): TokenChartRow[] {
  const byHour = new Map<string, TokenChartRow>();
  for (const r of rows) {
    const existing = byHour.get(r.hr) ?? {
      hr: formatHour(r.hr),
      hrIso: r.hr,
      input_tokens: 0,
      output_tokens: 0,
      models: [],
    };
    existing.input_tokens += Number(r.input_tokens) || 0;
    existing.output_tokens += Number(r.output_tokens) || 0;
    existing.models.push({
      model: r.model,
      input: Number(r.input_tokens) || 0,
      output: Number(r.output_tokens) || 0,
      calls: Number(r.calls) || 0,
    });
    byHour.set(r.hr, existing);
  }
  return Array.from(byHour.values()).sort((a, b) => a.hrIso.localeCompare(b.hrIso));
}

function TokenUsagePanel({ data }: { data: TokensResponse | null }) {
  const chart = useMemo(() => (data ? buildTokenChart(data.rows) : []), [data]);
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h3 className="text-sm font-semibold mb-2 text-slate-700">
        Token usage <span className="text-slate-400 font-normal">(last {HOURS}h)</span>
      </h3>
      {data?.error ? (
        <div className="text-amber-700 text-xs mb-2">No data: {data.error}</div>
      ) : null}
      {chart.length === 0 ? (
        <div className="text-slate-500 text-sm py-12 text-center">No gateway calls in the last {HOURS} hours.</div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chart} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="hr" tick={{ fontSize: 10 }} interval={0} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload || !payload.length) return null;
                const row = payload[0].payload as TokenChartRow;
                return (
                  <div className="bg-white border border-slate-200 rounded-md shadow-sm p-2 text-xs">
                    <div className="font-semibold text-slate-700">{row.hr}</div>
                    <div className="text-slate-600 mt-1">
                      input: <span className="font-mono">{row.input_tokens.toLocaleString()}</span>
                    </div>
                    <div className="text-slate-600">
                      output: <span className="font-mono">{row.output_tokens.toLocaleString()}</span>
                    </div>
                    <div className="border-t border-slate-100 mt-2 pt-1 text-slate-500">By model:</div>
                    {row.models.map((m) => (
                      <div key={m.model} className="text-slate-600">
                        {m.model}: <span className="font-mono">{(m.input + m.output).toLocaleString()}</span> tok ({m.calls} calls)
                      </div>
                    ))}
                  </div>
                );
              }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Bar dataKey="input_tokens" stackId="t" fill="#1F4068" name="input tokens" />
            <Bar dataKey="output_tokens" stackId="t" fill="#F4A261" name="output tokens" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

// ---------- Latency panel ----------

type LatencyChartRow = {
  hr: string;
  hrIso: string;
  p50: number;
  p95: number;
  p99: number;
  calls: number;
};

function buildLatencyChart(rows: LatencyBucket[]): LatencyChartRow[] {
  // Aggregate gateway + agent into one timeline by taking the max percentile
  // per hour (avoids two competing series per metric).
  const byHour = new Map<string, LatencyChartRow>();
  for (const r of rows) {
    const e = byHour.get(r.hr) ?? {
      hr: formatHour(r.hr),
      hrIso: r.hr,
      p50: 0,
      p95: 0,
      p99: 0,
      calls: 0,
    };
    e.p50 = Math.max(e.p50, Number(r.p50) || 0);
    e.p95 = Math.max(e.p95, Number(r.p95) || 0);
    e.p99 = Math.max(e.p99, Number(r.p99) || 0);
    e.calls += Number(r.calls) || 0;
    byHour.set(r.hr, e);
  }
  return Array.from(byHour.values()).sort((a, b) => a.hrIso.localeCompare(b.hrIso));
}

function LatencyPanel({ data }: { data: LatencyResponse | null }) {
  const chart = useMemo(() => (data ? buildLatencyChart(data.rows) : []), [data]);
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h3 className="text-sm font-semibold mb-2 text-slate-700">
        Latency p50 / p95 / p99 <span className="text-slate-400 font-normal">(last {HOURS}h)</span>
      </h3>
      {data?.error ? (
        <div className="text-amber-700 text-xs mb-2">No data: {data.error}</div>
      ) : null}
      {chart.length === 0 ? (
        <div className="text-slate-500 text-sm py-12 text-center">No calls in the last {HOURS} hours.</div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={chart} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="hr" tick={{ fontSize: 10 }} interval={0} />
            <YAxis tick={{ fontSize: 10 }} unit=" ms" />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine
              y={LATENCY_THRESHOLD_MS}
              stroke="#E63946"
              strokeDasharray="4 4"
              label={{ value: `${LATENCY_THRESHOLD_MS} ms`, fontSize: 10, fill: "#E63946" }}
            />
            <Line type="monotone" dataKey="p50" stroke="#1F4068" strokeWidth={1.5} dot={false} name="p50" />
            <Line type="monotone" dataKey="p95" stroke="#F4A261" strokeWidth={1.5} dot={false} name="p95" />
            <Line type="monotone" dataKey="p99" stroke="#E63946" strokeWidth={1.5} dot={false} name="p99" />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

// ---------- PII guardrails panel ----------

function PiiPanel({ data }: { data: PiiResponse | null }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h3 className="text-sm font-semibold mb-2 text-slate-700">
        PII guardrails <span className="text-slate-400 font-normal">(last {HOURS}h)</span>
      </h3>
      {data?.error ? (
        <div className="text-amber-700 text-xs mb-2">No data: {data.error}</div>
      ) : null}
      <div className="grid grid-cols-3 gap-3 mb-3">
        <Stat label="Total redactions" value={data?.total ?? 0} accent="ink" />
        <Stat label="Input" value={data?.by_direction.input ?? 0} accent="violation" />
        <Stat label="Output" value={data?.by_direction.output ?? 0} accent="amber" />
      </div>
      <h4 className="text-xs font-semibold text-slate-700 mb-1">Last 5 events</h4>
      {data?.samples.length ? (
        <div className="overflow-y-auto max-h-40 border border-slate-200 rounded">
          <table className="min-w-full text-xs">
            <thead className="bg-slate-100 text-slate-700 sticky top-0">
              <tr>
                <th className="text-left px-2 py-1">When</th>
                <th className="text-left px-2 py-1">Dir</th>
                <th className="text-left px-2 py-1">Status</th>
                <th className="text-left px-2 py-1">Message</th>
              </tr>
            </thead>
            <tbody>
              {data.samples.map((s) => (
                <tr key={s.request_id} className="border-t border-slate-200">
                  <td className="px-2 py-1 whitespace-nowrap">{formatTs(s.ts)}</td>
                  <td className="px-2 py-1">{s.direction}</td>
                  <td className="px-2 py-1">{s.status}</td>
                  <td className="px-2 py-1 text-slate-600 truncate max-w-[260px]" title={s.message}>
                    {s.message}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-slate-500 text-xs py-4 text-center">No PII or guardrail blocks in the last {HOURS}h.</div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: "ink" | "violation" | "amber";
}) {
  const cls =
    accent === "violation"
      ? "text-violation"
      : accent === "amber"
        ? "text-amber-600"
        : "text-ink";
  return (
    <div className="bg-slate-50 rounded-md p-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`text-2xl font-semibold ${cls}`}>{value.toLocaleString()}</div>
    </div>
  );
}

// ---------- Recent calls panel ----------

function statusColor(status: number) {
  if (status < 300) return "text-emerald-600";
  if (status < 500) return "text-amber-600";
  return "text-violation";
}

function RecentPanel({ data }: { data: RecentResponse | null }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <h3 className="text-sm font-semibold mb-2 text-slate-700">Recent calls</h3>
      {data?.error ? (
        <div className="text-amber-700 text-xs mb-2">No data: {data.error}</div>
      ) : null}
      <div className="overflow-y-auto max-h-96 border border-slate-200 rounded">
        <table className="min-w-full text-xs">
          <thead className="bg-slate-100 text-slate-700 sticky top-0">
            <tr>
              <th className="text-left px-2 py-1">When</th>
              <th className="text-left px-2 py-1">Source</th>
              <th className="text-left px-2 py-1">Model</th>
              <th className="text-right px-2 py-1">Latency</th>
              <th className="text-right px-2 py-1">In</th>
              <th className="text-right px-2 py-1">Out</th>
              <th className="text-left px-2 py-1">Status</th>
              <th className="text-left px-2 py-1">Request</th>
            </tr>
          </thead>
          <tbody>
            {(data?.rows ?? []).map((r: RecentCall) => (
              <tr key={r.request_id} className="border-t border-slate-200 hover:bg-slate-50">
                <td className="px-2 py-1 whitespace-nowrap">{formatTs(r.ts)}</td>
                <td className="px-2 py-1">
                  <span
                    className={
                      r.source === "gateway"
                        ? "bg-slate-200 text-slate-700 rounded px-1.5 py-0.5"
                        : "bg-blue-100 text-blue-800 rounded px-1.5 py-0.5"
                    }
                  >
                    {r.source}
                  </span>
                </td>
                <td className="px-2 py-1 text-slate-600 truncate max-w-[200px]" title={r.model}>
                  {r.model}
                </td>
                <td className="px-2 py-1 text-right font-mono">
                  {r.latency_ms != null ? `${Number(r.latency_ms).toLocaleString()} ms` : "—"}
                </td>
                <td className="px-2 py-1 text-right font-mono">
                  {r.input_tokens != null ? Number(r.input_tokens).toLocaleString() : "—"}
                </td>
                <td className="px-2 py-1 text-right font-mono">
                  {r.output_tokens != null ? Number(r.output_tokens).toLocaleString() : "—"}
                </td>
                <td className={`px-2 py-1 font-mono ${statusColor(Number(r.status))}`}>{r.status}</td>
                <td className="px-2 py-1 font-mono text-slate-500 truncate max-w-[160px]" title={r.request_id}>
                  {r.request_id.slice(0, 8)}…
                </td>
              </tr>
            ))}
            {!data?.rows?.length && (
              <tr>
                <td colSpan={8} className="px-3 py-6 text-center text-slate-500">
                  No calls yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------- Page ----------

export default function Observability() {
  const [tokens, setTokens] = useState<TokensResponse | null>(null);
  const [latency, setLatency] = useState<LatencyResponse | null>(null);
  const [piiData, setPiiData] = useState<PiiResponse | null>(null);
  const [recent, setRecent] = useState<RecentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [t, l, p, r] = await Promise.all([
        api.obsTokens(HOURS),
        api.obsLatency(HOURS),
        api.obsPii(HOURS),
        api.obsRecent(50),
      ]);
      setTokens(t);
      setLatency(l);
      setPiiData(p);
      setRecent(r);
      setUpdatedAt(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    // Intentionally no auto-polling — manual refresh only.
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Observability</h1>
        <div className="flex items-center gap-3 text-sm">
          <span
            className={
              loading
                ? "inline-flex items-center gap-1 text-amber-600"
                : "inline-flex items-center gap-1 text-emerald-600"
            }
          >
            <span
              className={
                loading
                  ? "inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse"
                  : "inline-block w-2 h-2 rounded-full bg-emerald-500"
              }
            />
            {loading ? "loading…" : "live"}
          </span>
          <span className="text-slate-500 text-xs">
            {updatedAt ? `updated ${updatedAt.toLocaleTimeString()}` : "—"}
          </span>
          <button
            onClick={() => void refresh()}
            disabled={loading}
            className="bg-ink text-white px-3 py-1.5 rounded-md disabled:opacity-50"
          >
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className="text-violation text-sm">Error loading data: {error}</div> : null}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <TokenUsagePanel data={tokens} />
        <LatencyPanel data={latency} />
        <PiiPanel data={piiData} />
        <RecentPanel data={recent} />
      </div>
    </div>
  );
}
