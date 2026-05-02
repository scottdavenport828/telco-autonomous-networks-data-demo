# Telco Autonomous Networks — Databricks-native Demo

A multi-agent system for detecting anomalies and performing root cause analysis (RCA) on LTE Radio Access Network incidents, **rebuilt entirely on Databricks**. Originally a Google Cloud reference architecture (BigQuery + Vertex AI Search + Gemini + Google ADK), this port replaces every GCP service with its Databricks-native equivalent and ships as a single Databricks App.

> Acknowledgement: synthetic eNodeB performance management (PM) data and cell traces were originally provided by [DigitalRoute](https://www.digitalroute.com/) for the Google Cloud demo. Data is preserved verbatim in `data/`.

## Architecture

| Layer | Databricks primitive |
|---|---|
| Storage | Unity Catalog Delta tables under `srd_vibes_catalog.network_intel` |
| Raw fixtures | UC Volume `srd_vibes_catalog.network_intel.raw` |
| Materialized KPIs | Lakeflow Declarative Pipelines (`performance_kpi` MV) |
| RAG | Databricks Vector Search (`rca_rules_vs_idx`, `incidents_vs_idx`) |
| LLM | Native FMAPI endpoint `databricks-claude-opus-4-7` with Unity AI Gateway features (rate limits, usage tracking, inference table, PII guardrails) applied via `notebooks/04_apply_ai_gateway.py` |
| Embeddings | FMAPI `databricks-gte-large-en` |
| Agents | Mosaic AI Agent Framework (MLflow `ChatAgent`) — `incident_detector`, `rca_orchestrator` |
| Backend | FastAPI |
| Frontend | React + TypeScript + Vite |
| Hosting | Databricks Apps |
| IaC | Databricks Asset Bundle (`databricks.yml`) |

## Repo layout

```
.
├── databricks.yml             # DAB root
├── app.yaml                   # Databricks App entrypoint
├── pyproject.toml
├── data/                      # synthetic CSV/JSON fixtures (preserved from upstream)
├── resources/                 # DAB resource yaml (catalog, jobs, app, endpoints)
├── tan/                       # Python package
│   ├── settings.py
│   ├── sql/                   # DDL + KPI SQL
│   ├── data_loader/           # CSV/JSON → Delta loaders
│   ├── agents/                # Mosaic AI ChatAgent implementations + tools
│   └── api/                   # FastAPI app + routers
├── frontend/                  # React + Vite + TS UI
└── notebooks/                 # idempotent setup, load, register notebooks
```

## Demo scenarios

1. **Incident Detection** — chat with the `incident_detector` agent: scans `performance_kpi` for cells violating thresholds (`erab_success_rate < 97`, `retainability > 3`), proposes incidents, persists confirmed incidents to the `incidents` Delta table.
2. **Root Cause Analysis** — chat with the `rca_orchestrator` agent: retrieves applicable RCA rules from Vector Search, runs analyzer/severity/prior-incident/report subagents, writes the final report back to the incident.
3. **Network Operations Dashboard** — KPI charts with violation overlays, incident list/detail views, live tool-call trace pane.

## Setup

### Prerequisites

- Databricks workspace with Unity Catalog, Vector Search, Foundation Model API, and Apps enabled.
- Databricks CLI authenticated (`databricks auth login --profile srd-vibes` recommended).
- Node 20+ and Python 3.11+ for local frontend/agent development.

The LLM is `databricks-claude-opus-4-7` (native FMAPI pay-per-token); no provider API key is needed.

### Deploy

```bash
# 1. Build the React frontend (output → tan/api/static/)
cd frontend && npm install && npm run build && cd ..

# 2. Validate and deploy the bundle
databricks bundle validate --profile srd-vibes
databricks bundle deploy --profile srd-vibes

# 3. Run setup jobs in order
databricks bundle run setup --profile srd-vibes              # UC + Vector Search
databricks bundle run load_data --profile srd-vibes          # CSVs → Delta
databricks bundle run apply_ai_gateway --profile srd-vibes   # Gateway features on databricks-claude-opus-4-7
databricks bundle run register_agents --profile srd-vibes    # MLflow log + agents.deploy()

# 4. Launch the app
databricks apps deploy telco-rca --source-code-path /Workspace/Users/$USER/.bundle/telco-autonomous-networks-databricks/dev/files --profile srd-vibes
```

The app URL prints after `apps deploy` succeeds.

### Local development

```bash
# backend
uv pip install -e .
uvicorn tan.api.main:app --reload

# frontend
cd frontend && npm run dev
```

## License

Apache 2.0 — see [LICENSE](LICENSE). Same upstream license as the GCP reference, preserved.
