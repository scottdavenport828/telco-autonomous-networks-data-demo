import clsx from "clsx";

// ---------------------------------------------------------------------------
// Architecture page — explains the seven layers of the demo end-to-end with
// the concrete artifact names that exist on the workspace today. Pure HTML +
// Tailwind, no diagramming library.
// ---------------------------------------------------------------------------

type Layer = {
  id: string;
  step: number;
  title: string;
  subtitle: string;
  accent: string;
  description: string;
  artifacts: { label: string; value: string; kind?: "table" | "view" | "endpoint" | "job" | "pipeline" | "page" | "code" }[];
};

const LAYERS: Layer[] = [
  {
    id: "data",
    step: 1,
    title: "Data layer",
    subtitle: "Unity Catalog Delta tables",
    accent: "indigo",
    description:
      "Schema preserved verbatim from the upstream BQ JSON files. The streaming generator produces fresh 15-min PM batches; an anomaly_schedule table biases specific cells on demand.",
    artifacts: [
      { label: "Catalog / schema", value: "srd_vibes_catalog.network_intel", kind: "table" },
      { label: "performance", value: "20,831 rows · 19 cells · 164-day span", kind: "table" },
      { label: "cell_traces", value: "26,685 rows · per-UE signaling events", kind: "table" },
      { label: "incidents", value: "RCA records w/ events_embeddings", kind: "table" },
      { label: "rca_rules", value: "2 vendor RCA rule docs", kind: "table" },
      { label: "cell_sites", value: "31 sites · Manhattan geo for the map", kind: "table" },
      { label: "anomaly_schedule", value: "demo control plane (CDF on)", kind: "table" },
      { label: "cell_profiles", value: "per-(cell, col) stats for generator", kind: "table" },
      { label: "actions_taken", value: "autopilot remediation tracking", kind: "table" },
      { label: "autopilot_state", value: "single-row ON/OFF toggle", kind: "table" },
      { label: "Generator job", value: "telco-rca-streaming-data-generator (15-min cron)", kind: "job" },
      { label: "Generator code", value: "tan/data_generator/{profile,generator,anomaly}.py", kind: "code" },
    ],
  },
  {
    id: "compute",
    step: 2,
    title: "KPI compute",
    subtitle: "Lakeflow Declarative Pipeline",
    accent: "sky",
    description:
      "Materialised view that computes ERAB success rate and retainability per (cell, 15-min window). Re-runs after every generator tick so the dashboard's last-24h view stays fresh.",
    artifacts: [
      { label: "Materialised view", value: "performance_kpi · 20,831 rows", kind: "view" },
      { label: "Pipeline", value: "telco-rca-performance-kpi", kind: "pipeline" },
      { label: "Pipeline ID", value: "503939ca-cc3f-4cba-b4f1-cb161e2e2878", kind: "pipeline" },
      { label: "Thresholds", value: "ERAB < 97% · retainability > 3.0 rel/hr", kind: "code" },
      { label: "Definition", value: "notebooks/03_create_kpi_view.py", kind: "code" },
    ],
  },
  {
    id: "rag",
    step: 3,
    title: "RAG / Vector Search",
    subtitle: "Delta-sync indexes",
    accent: "violet",
    description:
      "Domain knowledge for the agents. RCA rules drive which tools the analyzer uses; prior-incident similarity lets the agent cite relevant historical context.",
    artifacts: [
      { label: "Endpoint", value: "srd-vibes-vs (ONLINE)", kind: "endpoint" },
      { label: "RCA rules index", value: "srd_vibes_catalog.network_intel.rca_rules_vs_idx", kind: "endpoint" },
      { label: "Prior incidents index", value: "srd_vibes_catalog.network_intel.incidents_vs_idx", kind: "endpoint" },
      { label: "Sync mode", value: "Delta-sync (auto on table change)", kind: "code" },
      { label: "Wrapper", value: "tan/agents/vsearch.py", kind: "code" },
    ],
  },
  {
    id: "models",
    step: 4,
    title: "Models",
    subtitle: "FMAPI + Unity AI Gateway",
    accent: "teal",
    description:
      "Native Databricks-hosted Claude Opus 4.6 — no Anthropic API key needed. Unity AI Gateway adds rate limits, PII guardrails, usage tracking, and an inference table that powers the Observability tab.",
    artifacts: [
      { label: "LLM endpoint", value: "databricks-claude-opus-4-6 (READY)", kind: "endpoint" },
      { label: "Embedding endpoint", value: "databricks-gte-large-en (READY)", kind: "endpoint" },
      { label: "AI Gateway features", value: "rate limits · PII BLOCK · usage tracking · inference table", kind: "code" },
      { label: "Inference table", value: "srd_vibes_catalog.network_intel.gw_inference_payload", kind: "table" },
      { label: "Setup job", value: "telco-rca-apply-ai-gateway", kind: "job" },
    ],
  },
  {
    id: "agents",
    step: 5,
    title: "Agents",
    subtitle: "Mosaic AI ChatAgents",
    accent: "amber",
    description:
      "Two MLflow ChatAgents registered to UC and deployed behind one serving endpoint. Both implement the OpenAI-style tool-use loop against the LLM endpoint; tools execute SQL, Vector Search, and embedding calls server-side.",
    artifacts: [
      { label: "Agent endpoint", value: "telco-rca-agents (READY)", kind: "endpoint" },
      { label: "Registered models", value: "srd_vibes_catalog.network_intel.{incident_detector, rca_orchestrator}", kind: "table" },
      { label: "incident_detector", value: "scans performance_kpi → INSERT incidents", kind: "code" },
      { label: "rca_orchestrator", value: "8 tools, 8-section markdown report", kind: "code" },
      { label: "Tool surface", value: "get_potential_incidents · find_rca_rules · get_cell_trace_statistics · prior_incident_search · update_incident · initiate_uplink_configuration_adjustment · …", kind: "code" },
      { label: "Register job", value: "telco-rca-register-agents", kind: "job" },
      { label: "Inference log", value: "srd_vibes_catalog.network_intel.incident_detector_payload", kind: "table" },
    ],
  },
  {
    id: "autopilot",
    step: 6,
    title: "Autopilot",
    subtitle: "Closed-loop autonomous triage",
    accent: "rose",
    description:
      "Four stages run on staggered crons (paused by default — UI toggle controls them) AND inline from the FastAPI process for click-to-run demos. Every stage reads autopilot_state.enabled before doing work.",
    artifacts: [
      { label: "Stage 1: detect", value: "telco-rca-autopilot-detect (5m cron) · pure SQL", kind: "job" },
      { label: "Stage 2: rca", value: "telco-rca-autopilot-rca (10m cron) · runs RcaOrchestratorAgent", kind: "job" },
      { label: "Stage 3: remediate", value: "telco-rca-autopilot-remediate (5m cron) · PROPOSED → APPLIED + healing anomaly", kind: "job" },
      { label: "Stage 4: verify", value: "telco-rca-autopilot-verify (5m cron) · close on KPI recovery", kind: "job" },
      { label: "Inline runner", value: "tan/autopilot/inline.py (no Spark, no jobs API)", kind: "code" },
      { label: "Toggle table", value: "srd_vibes_catalog.network_intel.autopilot_state", kind: "table" },
    ],
  },
  {
    id: "app",
    step: 7,
    title: "Databricks App",
    subtitle: "FastAPI + React + Vite",
    accent: "emerald",
    description:
      "Service principal auth for read paths (SQL warehouse, serving endpoints); user OBO when an action should be attributed to the operator. Static React build served from inside the Python container, SSE for streams.",
    artifacts: [
      { label: "App", value: "telco-rca · status RUNNING", kind: "endpoint" },
      { label: "URL", value: "https://telco-rca-7474651138512079.aws.databricksapps.com", kind: "endpoint" },
      { label: "Backend", value: "tan/api/main.py (FastAPI)", kind: "code" },
      { label: "Routers", value: "kpis · incidents · chat · observability · anomaly · network_map · autopilot", kind: "code" },
      { label: "Pages", value: "Dashboard · Incidents · Workbench · Network · Observability · Architecture", kind: "page" },
      { label: "Auth", value: "SP (M2M OAuth) for SQL · OBO for write paths", kind: "code" },
    ],
  },
];

const ACCENT_BG: Record<string, string> = {
  indigo: "bg-indigo-50 ring-indigo-200",
  sky: "bg-sky-50 ring-sky-200",
  violet: "bg-violet-50 ring-violet-200",
  teal: "bg-teal-50 ring-teal-200",
  amber: "bg-amber-50 ring-amber-200",
  rose: "bg-rose-50 ring-rose-200",
  emerald: "bg-emerald-50 ring-emerald-200",
};
const ACCENT_BADGE: Record<string, string> = {
  indigo: "bg-indigo-600 text-white",
  sky: "bg-sky-600 text-white",
  violet: "bg-violet-600 text-white",
  teal: "bg-teal-600 text-white",
  amber: "bg-amber-600 text-white",
  rose: "bg-rose-600 text-white",
  emerald: "bg-emerald-600 text-white",
};
const ACCENT_TEXT: Record<string, string> = {
  indigo: "text-indigo-700",
  sky: "text-sky-700",
  violet: "text-violet-700",
  teal: "text-teal-700",
  amber: "text-amber-700",
  rose: "text-rose-700",
  emerald: "text-emerald-700",
};

const KIND_BADGE: Record<string, string> = {
  table: "bg-slate-200 text-slate-700",
  view: "bg-cyan-100 text-cyan-800",
  endpoint: "bg-violet-100 text-violet-800",
  job: "bg-amber-100 text-amber-800",
  pipeline: "bg-sky-100 text-sky-800",
  page: "bg-emerald-100 text-emerald-800",
  code: "bg-slate-100 text-slate-600",
};

const DEMO_FLOW: { title: string; detail: string }[] = [
  {
    title: "Operator clicks Inject on Dashboard",
    detail: "POST /api/anomaly inserts a row into anomaly_schedule with target ERAB 0.85 for 30 min.",
  },
  {
    title: "Streaming generator tick fires (≤15 min)",
    detail: "Reads cell_profiles + active anomalies, samples one new row per cell into performance + ~6 rows per cell into cell_traces. Healing anomalies bias toward 0.99.",
  },
  {
    title: "Lakeflow pipeline refreshes performance_kpi",
    detail: "MV recomputes erab_success_rate and retainability for the new windows. Best-effort; falls back to a triggered pipeline run if REFRESH MATERIALIZED VIEW isn't allowed on the compute.",
  },
  {
    title: "Autopilot detect runs",
    detail: "Pure SQL scans performance_kpi for 60-min averages outside threshold, dedupes against open incidents (one per cell+kpi), inserts NEW rows into incidents.",
  },
  {
    title: "Autopilot RCA runs",
    detail: "RcaOrchestratorAgent.predict() loops Claude Opus 4.6 with 8 tools — find_rca_rules (Vector Search), get_cell_trace_statistics (SQL), prior_incident_search (VS + embeddings), and finally update_incident with the markdown report. Every call is logged to gw_inference_payload.",
  },
  {
    title: "Action proposed",
    detail: "The analyzer's initiate_uplink_configuration_adjustment tool inserts a PROPOSED row in actions_taken, referenced from the incident's resolution text.",
  },
  {
    title: "Autopilot remediate",
    detail: "Promotes PROPOSED → APPLIED, schedules a 30-min healing anomaly that biases the cell to 99% ERAB, moves the incident to IN_PROGRESS.",
  },
  {
    title: "Next tick lands a healthy row",
    detail: "Generator picks up the healing anomaly, writes erab≈99% at the next 15-min boundary. The map's blue agent_call pulses give way to a quiet cell.",
  },
  {
    title: "Autopilot verify closes the loop",
    detail: "Action → VERIFIED, incident → RESOLVED with end_ts and 'Auto-remediated and recovery verified' in resolution. Network-map sector recolours to green.",
  },
];

export default function Architecture() {
  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">Architecture</h1>
        <p className="text-sm text-slate-600 max-w-3xl">
          A Databricks-native port of Google's <code className="bg-slate-100 px-1 rounded">telco-autonomous-networks-data-demo</code>.
          Every GCP service maps to a Databricks primitive and runs end-to-end inside a single Asset Bundle. Below is what's
          actually deployed on <code className="bg-slate-100 px-1 rounded">fevm-srd-vibes</code> right now, layer by layer.
        </p>
      </header>

      {/* Layered diagram */}
      <section className="space-y-2">
        {LAYERS.map((layer, i) => (
          <div key={layer.id} className="flex flex-col items-stretch">
            <article
              id={layer.id}
              className={clsx(
                "rounded-lg ring-1 px-4 py-3 flex flex-col gap-2",
                ACCENT_BG[layer.accent],
              )}
            >
              <div className="flex items-baseline gap-3">
                <span
                  className={clsx(
                    "inline-flex items-center justify-center rounded-full w-7 h-7 text-xs font-semibold shrink-0",
                    ACCENT_BADGE[layer.accent],
                  )}
                >
                  {layer.step}
                </span>
                <div className="flex-1">
                  <h2 className={clsx("text-base font-semibold", ACCENT_TEXT[layer.accent])}>
                    {layer.title}
                    <span className="ml-2 text-xs font-normal text-slate-500">{layer.subtitle}</span>
                  </h2>
                  <p className="text-sm text-slate-700 mt-1">{layer.description}</p>
                </div>
              </div>
              <ul className="grid grid-cols-1 md:grid-cols-2 gap-1.5 mt-1 text-xs">
                {layer.artifacts.map((a, ix) => (
                  <li key={ix} className="flex items-start gap-2">
                    {a.kind && (
                      <span className={clsx("shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide", KIND_BADGE[a.kind])}>
                        {a.kind}
                      </span>
                    )}
                    <div className="min-w-0">
                      <div className="font-medium text-slate-800">{a.label}</div>
                      <div className="text-slate-600 font-mono text-[11px] truncate" title={a.value}>
                        {a.value}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </article>
            {i < LAYERS.length - 1 && (
              <div className="flex justify-center my-1 text-slate-400 select-none" aria-hidden>
                <svg width="14" height="22" viewBox="0 0 14 22">
                  <line x1="7" y1="0" x2="7" y2="16" stroke="currentColor" strokeWidth="1.5" />
                  <polyline points="3,14 7,20 11,14" fill="none" stroke="currentColor" strokeWidth="1.5" />
                </svg>
              </div>
            )}
          </div>
        ))}
      </section>

      {/* Demo flow */}
      <section className="bg-white rounded-lg border border-slate-200 p-5 space-y-4">
        <header>
          <h2 className="text-lg font-semibold">Live closed-loop flow</h2>
          <p className="text-sm text-slate-600">
            What happens between an operator clicking <span className="font-mono text-xs bg-slate-100 px-1 rounded">Inject</span> on the Dashboard and the
            incident auto-resolving on the Network map.
          </p>
        </header>
        <ol className="space-y-3">
          {DEMO_FLOW.map((step, i) => (
            <li key={i} className="flex gap-3">
              <span className="shrink-0 inline-flex items-center justify-center rounded-full w-6 h-6 text-[11px] font-semibold bg-slate-900 text-white">
                {i + 1}
              </span>
              <div>
                <div className="text-sm font-medium text-slate-800">{step.title}</div>
                <div className="text-xs text-slate-600">{step.detail}</div>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* GCP -> Databricks mapping */}
      <section className="bg-white rounded-lg border border-slate-200 p-5 space-y-3">
        <header>
          <h2 className="text-lg font-semibold">GCP → Databricks one-to-one</h2>
          <p className="text-sm text-slate-600">
            Every artifact in the upstream README maps to a Databricks-native equivalent.
          </p>
        </header>
        <table className="w-full text-xs">
          <thead className="text-[11px] uppercase tracking-wide text-slate-500">
            <tr>
              <th className="text-left font-medium pb-2">GCP</th>
              <th className="text-left font-medium pb-2">Databricks</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            <Row gcp="BigQuery dataset telco_demo" db="srd_vibes_catalog.network_intel (UC schema)" />
            <Row gcp="performance — LTE PM data" db="performance Delta table · 20,831 rows" />
            <Row gcp="performance_kpi — materialised view" db="performance_kpi · Lakeflow Declarative MV" />
            <Row gcp="cell_traces — UE event log" db="cell_traces Delta · 26,685 rows" />
            <Row gcp="incidents — incident records" db="incidents Delta · CDF on" />
            <Row gcp="Vertex AI Search rca_rules data store" db="rca_rules Delta + rca_rules_vs_idx (Delta-sync)" />
            <Row gcp="Vertex AI Search rca_rules_search app" db="srd-vibes-vs Vector Search endpoint" />
            <Row gcp="bin/load-performance-data.sh" db="DAB job telco-rca-load-data (notebooks/02_load_data.py)" />
            <Row gcp="bin/load-cell-traces-data.sh" db="same job (single notebook covers both)" />
            <Row gcp="bin/add-rca-rules.sh" db="same job · Delta + Vector Search sync at the end" />
            <Row gcp="Gemini 3-Pro / 2.5-Flash" db="databricks-claude-opus-4-6 (FMAPI + AI Gateway)" />
            <Row gcp="gemini-embedding-001" db="databricks-gte-large-en" />
            <Row gcp="Google ADK incident_detector + RCA orchestrator (11 subagents)" db="Mosaic AI ChatAgent ×2 on telco-rca-agents" />
            <Row gcp="adk web (local UI)" db="Databricks App telco-rca (FastAPI + React)" />
            <Row gcp="Terraform" db="Databricks Asset Bundle (databricks.yml + resources/)" />
          </tbody>
        </table>
      </section>

      {/* Beyond the GCP repo */}
      <section className="bg-white rounded-lg border border-slate-200 p-5 space-y-3">
        <header>
          <h2 className="text-lg font-semibold">Beyond the upstream</h2>
          <p className="text-sm text-slate-600">
            Capabilities added on top that the GCP reference does not have.
          </p>
        </header>
        <ul className="grid md:grid-cols-2 gap-3 text-sm">
          <Bullet
            title="Streaming synthetic data"
            body="Profile-based generator on a 15-min cron keeps the data live. Anomaly schedule lets the operator bias specific cells on demand."
          />
          <Bullet
            title="Autonomous closed loop"
            body="Detect → RCA → remediate → verify, on schedules and on click, with a single autopilot_state toggle."
          />
          <Bullet
            title="Unity AI Gateway"
            body="PII guardrails (BLOCK), rate limits, payload logging — every Claude call traceable from the Observability tab."
          />
          <Bullet
            title="Network map"
            body="MapLibre GL on real Manhattan tower coordinates. KPI status colours each sector; pulses animate live agent + anomaly events via SSE."
          />
          <Bullet
            title="Vector Search for prior incidents"
            body="Semantic similarity over historical incidents.events_embeddings — the orchestrator can cite the closest past RCA."
          />
          <Bullet
            title="MLflow tracing"
            body="Every agent tool call is a span; the trace tree shows up in the MLflow UI alongside its inputs/outputs."
          />
        </ul>
      </section>

      <p className="text-xs text-slate-500">
        Source: <a className="underline hover:text-slate-700" href="https://github.com/scottdavenport828/telco-autonomous-networks-data-demo" target="_blank" rel="noreferrer">
          scottdavenport828/telco-autonomous-networks-data-demo
        </a> @ branch <code className="font-mono">databricks-port</code>.
      </p>
    </div>
  );
}

function Row({ gcp, db }: { gcp: string; db: string }) {
  return (
    <tr>
      <td className="py-2 pr-3 font-mono text-[11px] text-slate-600 align-top">{gcp}</td>
      <td className="py-2 font-mono text-[11px] text-slate-800 align-top">{db}</td>
    </tr>
  );
}

function Bullet({ title, body }: { title: string; body: string }) {
  return (
    <li className="rounded-md border border-slate-200 p-3">
      <div className="font-medium text-slate-800 text-sm">{title}</div>
      <div className="text-xs text-slate-600 mt-0.5">{body}</div>
    </li>
  );
}
