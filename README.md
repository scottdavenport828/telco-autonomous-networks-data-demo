# Telco Autonomous Networks — Databricks-native Demo

A multi-agent system for detecting anomalies and performing root cause analysis (RCA) on LTE Radio Access Network incidents, **rebuilt entirely on Databricks**. Originally a Google Cloud reference architecture (BigQuery + Vertex AI Search + Gemini + Google ADK), this port replaces every GCP service with its Databricks-native equivalent and ships as a single Databricks App.

> Acknowledgement: synthetic eNodeB performance management (PM) data and cell traces were originally provided by [DigitalRoute](https://www.digitalroute.com/) for the Google Cloud demo. Data is preserved verbatim in `data/`.

## Architecture

| Layer | Databricks primitive |
|---|---|
| Storage | Unity Catalog Delta tables under `telco_demo.network_intel` |
| Raw fixtures | UC Volume `telco_demo.network_intel.raw` |
| Materialized KPIs | Lakeflow Declarative Pipelines (`performance_kpi` MV) |
| RAG | Databricks Vector Search (`rca_rules_vs_idx`, `incidents_vs_idx`) |
| LLM | Claude Opus 4.7 served via Foundation Model API + AI Gateway (`claude-opus-4-7-gw`) |
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
- Anthropic API key (for Claude Opus 4.7) stored in a Databricks Secret scope (see `resources/serving_endpoints.yml`).
- Node 20+ and Python 3.11+ for local frontend/agent development.

### Deploy

```bash
# 1. Build the React frontend (output → tan/api/static/)
cd frontend && npm install && npm run build && cd ..

# 2. Validate and deploy the bundle
databricks bundle validate --profile srd-vibes
databricks bundle deploy --profile srd-vibes

# 3. Run setup notebooks (deploys Vector Search index, registers agents, etc.)
databricks bundle run setup_pipeline --profile srd-vibes
databricks bundle run register_agents --profile srd-vibes

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
