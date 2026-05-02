export type KpiRow = {
  enodeb_id: string;
  cell_id: string;
  measurement_end: string;
  erab_success_rate: number;
  retainability: number;
};

export type Thresholds = {
  erab_success_rate_min: number;
  retainability_max: number;
};

export type ViolationRow = {
  enodeb_id: string;
  cell_id: string;
  violation_windows: number;
  first_seen: string;
  last_seen: string;
  avg_erab_success_rate: number;
  avg_retainability: number;
};

export type Incident = {
  incident_id: string;
  enodeb_id: string;
  cell_id: string;
  start_ts: string;
  end_ts: string | null;
  status: string;
  description: string;
  severity: string | null;
  kpi_missed: { kpi: string; value: number }[];
  preliminary_analysis?: string | null;
  final_analysis?: string | null;
  events?: string | null;
  cause?: string | null;
  resolution?: string | null;
  created_ts: string;
};

export type ChatMessage = {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  tool_call_id?: string;
  tool_calls?: { id: string; type: "function"; function: { name: string; arguments: string } }[];
};

async function jsonFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${await response.text()}`);
  return response.json();
}

export const api = {
  kpis: (params: { enodeb_id?: string; cell_id?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.enodeb_id) q.set("enodeb_id", params.enodeb_id);
    if (params.cell_id) q.set("cell_id", params.cell_id);
    const qs = q.toString();
    return jsonFetch<{ thresholds: Thresholds; rows: KpiRow[] }>(`/api/kpis${qs ? `?${qs}` : ""}`);
  },
  violations: () => jsonFetch<{ rows: ViolationRow[] }>("/api/kpis/violations"),
  incidents: () => jsonFetch<{ rows: Incident[] }>("/api/incidents"),
  incident: (id: string) => jsonFetch<Incident>(`/api/incidents/${id}`),
  chat: (agent: string, messages: ChatMessage[]) =>
    jsonFetch<unknown>(`/api/chat/${agent}/non-streaming`, {
      method: "POST",
      body: JSON.stringify({ messages }),
    }),
  chatStream: (agent: string, messages: ChatMessage[]) =>
    fetch(`/api/chat/${agent}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    }),
};
