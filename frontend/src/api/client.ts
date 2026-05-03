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

// ---- Streaming agent events --------------------------------------------------
// These mirror the events emitted by `tan/agents/stream.py::stream_predict`.

export type ToolStartEvent = {
  type: "tool_start";
  id: string;
  name: string;
  args: Record<string, unknown>;
  ts_ms: number;
};

export type ToolEndEvent = {
  type: "tool_end";
  id: string;
  result: unknown;
  elapsed_ms: number;
  status: "ok" | "error";
  error?: string | null;
};

export type AssistantMessageEvent = {
  type: "assistant_message";
  id: string;
  content: string;
};

export type DoneEvent = { type: "done" };

export type AgentStreamEvent =
  | ToolStartEvent
  | ToolEndEvent
  | AssistantMessageEvent
  | DoneEvent;

// ---- Observability types -----------------------------------------------------

export type TokenBucket = {
  hr: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  calls: number;
};

export type LatencyBucket = {
  hr: string;
  source: "gateway" | "agent" | string;
  calls: number;
  p50: number;
  p95: number;
  p99: number;
};

export type RecentCall = {
  ts: string;
  source: "gateway" | "agent" | string;
  model: string;
  latency_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  status: number;
  request_id: string;
  requester: string | null;
};

export type PiiBucket = {
  hr: string;
  direction: "input" | "output" | string;
  events: number;
};

export type PiiSample = {
  ts: string;
  request_id: string;
  status: number;
  direction: "input" | "output" | string;
  message: string;
};

export type TokensResponse = {
  hours: number;
  rows: TokenBucket[];
  source: string;
  error: string | null;
};

export type LatencyResponse = {
  hours: number;
  rows: LatencyBucket[];
  threshold_ms: number;
  error: string | null;
};

export type RecentResponse = {
  rows: RecentCall[];
  error: string | null;
};

export type PiiResponse = {
  hours: number;
  total: number;
  by_direction: { input: number; output: number };
  buckets: PiiBucket[];
  samples: PiiSample[];
  error: string | null;
};

async function jsonFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${await response.text()}`);
  return response.json();
}

/**
 * Open a streaming chat with the given agent and yield typed lifecycle events.
 *
 * Reads the `text/event-stream` body via `response.body.getReader()` +
 * `TextDecoder`, parses each SSE frame (`data: {json}\n\n`), and yields the
 * decoded event. The generator returns when an `event: done` frame is seen
 * or the stream ends.
 */
export async function* chatStream(
  agent: string,
  messages: ChatMessage[],
  signal?: AbortSignal,
): AsyncGenerator<AgentStreamEvent, void, void> {
  const response = await fetch(`/api/chat/${agent}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ messages }),
    signal,
  });
  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => "");
    throw new Error(`chat ${agent} failed: ${response.status} ${response.statusText} ${text}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line.
      let separatorIndex = buffer.indexOf("\n\n");
      while (separatorIndex !== -1) {
        const frame = buffer.slice(0, separatorIndex);
        buffer = buffer.slice(separatorIndex + 2);
        const event = parseSseFrame(frame);
        if (event) yield event;
        separatorIndex = buffer.indexOf("\n\n");
      }
    }

    // Flush any tail bytes (no trailing blank line on a clean close).
    buffer += decoder.decode();
    if (buffer.trim()) {
      const event = parseSseFrame(buffer);
      if (event) yield event;
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // ignore — already released
    }
  }
}

function parseSseFrame(frame: string): AgentStreamEvent | null {
  // Each frame can have multiple `field: value` lines; we only care about
  // `event` and `data`. Comments (`:`) are ignored.
  let eventName: string | null = null;
  const dataLines: string[] = [];

  for (const rawLine of frame.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    if (!line || line.startsWith(":")) continue;
    const colonIdx = line.indexOf(":");
    if (colonIdx === -1) continue;
    const field = line.slice(0, colonIdx).trim();
    // SSE spec strips a single optional leading space from the value.
    const value = line.slice(colonIdx + 1).replace(/^\s/, "");
    if (field === "event") eventName = value;
    else if (field === "data") dataLines.push(value);
  }

  if (eventName === "done") return { type: "done" };
  if (!dataLines.length) return null;

  const payload = dataLines.join("\n");
  if (!payload || payload === "{}") return null;
  try {
    return JSON.parse(payload) as AgentStreamEvent;
  } catch (err) {
    // Tolerate malformed frames rather than crashing the whole stream.
    // eslint-disable-next-line no-console
    console.warn("chatStream: dropping malformed frame", err, payload);
    return null;
  }
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
  chatStream,
  obsTokens: (hours = 24) => jsonFetch<TokensResponse>(`/api/obs/tokens?hours=${hours}`),
  obsLatency: (hours = 24) => jsonFetch<LatencyResponse>(`/api/obs/latency?hours=${hours}`),
  obsRecent: (limit = 50) => jsonFetch<RecentResponse>(`/api/obs/recent?limit=${limit}`),
  obsPii: (hours = 24) => jsonFetch<PiiResponse>(`/api/obs/pii?hours=${hours}`),
  injectAnomaly: (req: AnomalyRequest) =>
    jsonFetch<Anomaly>("/api/anomaly", {
      method: "POST",
      body: JSON.stringify(req),
    }),
  listAnomalies: () => jsonFetch<{ rows: Anomaly[] }>("/api/anomaly"),
  mapCells: () => jsonFetch<MapCellsResponse>("/api/map/cells"),
  mapAnomalies: () => jsonFetch<{ rows: MapAnomaly[] }>("/api/map/anomalies"),
  autopilotState: () => jsonFetch<{ enabled: boolean; raw: Record<string, string> }>("/api/autopilot/state"),
  setAutopilot: (enabled: boolean) =>
    jsonFetch<{ enabled: boolean }>("/api/autopilot/state", {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),
  runAutopilotStage: (stage: "detect" | "rca" | "remediate" | "verify") =>
    jsonFetch<{ run_id: number; job_id: number; stage: string }>(`/api/autopilot/run/${stage}`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  recentActions: () => jsonFetch<{ rows: ActionTaken[] }>("/api/autopilot/recent"),
};

export type ActionTaken = {
  id: string;
  incident_id: string;
  action_name: string;
  enodeb_id: string;
  cell_id: string;
  status: "PROPOSED" | "APPLIED" | "VERIFIED" | "FAILED" | string;
  applied_ts: string | null;
  verified_ts: string | null;
  result_note: string | null;
  created_ts: string;
};

// ---- Network map types -------------------------------------------------------

export type MapCell = {
  enodeb_id: string;
  cell_id: string;
  site_name: string;
  lat: number;
  lon: number;
  azimuth: number;
  range_m: number;
  radio: string;
  band: string | null;
  mcc: number;
  mnc: number;
  network_name: string;
  is_active: boolean;
  erab_success_rate: number | null;
  retainability: number | null;
  latest_ts: string | null;
};

export type MapCellsResponse = {
  rows: MapCell[];
  thresholds: Thresholds;
};

export type MapAnomaly = {
  id: string;
  enodeb_id: string;
  cell_id: string;
  kpi: string;
  magnitude: number;
  start_ts: string;
  end_ts: string;
  status: string;
};

export type MapEvent = {
  ts: string;
  kind: "agent_call" | "anomaly" | "incident";
  id: string;
  latency_ms?: number | null;
  in_tokens?: number | null;
  out_tokens?: number | null;
  status_code?: number | null;
  enodeb_id?: string | null;
  cell_id?: string | null;
  magnitude?: number | null;
  kpi?: string | null;
};

// ---- Anomaly types -----------------------------------------------------------

export type AnomalyRequest = {
  enodeb_id: string;
  cell_id: string;
  kpi: "erab_success_rate" | "retainability";
  magnitude: number;
  duration_minutes?: number;
  note?: string;
};

export type Anomaly = {
  id: string;
  enodeb_id: string;
  cell_id: string;
  kpi: string;
  start_ts: string;
  end_ts: string;
  magnitude: number;
  note: string | null;
  status: string;
  created_ts?: string;
};
