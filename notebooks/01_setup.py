# Databricks notebook source
# MAGIC %md
# MAGIC # 01_setup
# MAGIC
# MAGIC Idempotent bootstrap for the telco RCA demo:
# MAGIC 1. UC catalog / schema / volume
# MAGIC 2. Delta tables: `performance`, `cell_traces`, `incidents`, `rca_rules`
# MAGIC 3. Vector Search endpoint
# MAGIC 4. Vector Search indexes for `rca_rules` and prior `incidents`

# COMMAND ----------
# MAGIC %pip install -q databricks-vectorsearch
# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
from pathlib import Path
import sys

# Make `tan` importable when running as a job from the bundled workspace files.
REPO_ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd().parent
sys.path.insert(0, str(REPO_ROOT))

from tan.sql.schema import create_table_sql

CATALOG = dbutils.widgets.get("catalog") if dbutils.widgets.getAll() else "srd_vibes_catalog"
SCHEMA = dbutils.widgets.get("schema") if dbutils.widgets.getAll() else "network_intel"
VOLUME = dbutils.widgets.get("volume") if dbutils.widgets.getAll() else "raw"
VS_ENDPOINT = dbutils.widgets.get("vs_endpoint") if dbutils.widgets.getAll() else "srd-vibes-vs"
RULES_INDEX = dbutils.widgets.get("rules_index") if dbutils.widgets.getAll() else "rca_rules_vs_idx"
INCIDENTS_INDEX = dbutils.widgets.get("incidents_index") if dbutils.widgets.getAll() else "incidents_vs_idx"
EMBED_ENDPOINT = dbutils.widgets.get("embedding_endpoint") if dbutils.widgets.getAll() else "databricks-gte-large-en"

print(f"catalog={CATALOG} schema={SCHEMA} volume={VOLUME}")
print(f"vs_endpoint={VS_ENDPOINT} embedding={EMBED_ENDPOINT}")

# COMMAND ----------
# MAGIC %md ## 1. UC catalog / schema / volume

# COMMAND ----------
# Catalog: only create if missing. CREATE CATALOG IF NOT EXISTS still validates
# a default storage location on Default-Storage metastores, which fails on
# workspaces (like FEVM Stable Serverless) where the metastore has no default
# storage root configured. Caller is expected to have provisioned the catalog;
# we just create the schema + volume.
existing_catalogs = {r.catalog for r in spark.sql("SHOW CATALOGS").collect()}
if CATALOG not in existing_catalogs:
    raise RuntimeError(
        f"Catalog '{CATALOG}' does not exist. Create it via the workspace UI or "
        f"with `CREATE CATALOG {CATALOG} MANAGED LOCATION 's3://...';` first."
    )

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.{VOLUME}")

# COMMAND ----------
# MAGIC %md ## 2. Delta tables (schemas preserved verbatim from upstream BQ schema JSON)

# COMMAND ----------
schemas_dir = REPO_ROOT / "data" / "schemas"

ddl = create_table_sql(
    f"{CATALOG}.{SCHEMA}.performance",
    schemas_dir / "performance.json",
    cluster_by=["enodeb_id", "cell_id", "measurement_end"],
    properties={"delta.enableChangeDataFeed": "false"},
)
print(ddl)
spark.sql(ddl)

# COMMAND ----------
ddl = create_table_sql(
    f"{CATALOG}.{SCHEMA}.cell_traces",
    schemas_dir / "cell_traces.json",
    cluster_by=["start_enodeb_id", "start_cell_id", "starttime"],
)
print(ddl)
spark.sql(ddl)

# COMMAND ----------
# Incidents table — `events_embeddings` becomes ARRAY<DOUBLE> in Spark
# (BigQuery FLOAT64 REPEATED → ARRAY<DOUBLE>). Vector Search will recompute
# embeddings from the `events` text column when we sync the index, so this
# stored array is informational only.
ddl = create_table_sql(
    f"{CATALOG}.{SCHEMA}.incidents",
    schemas_dir / "incidents.json",
    properties={
        "delta.enableChangeDataFeed": "true",  # required for Vector Search Delta-sync
    },
)
print(ddl)
spark.sql(ddl)

# COMMAND ----------
ddl = create_table_sql(
    f"{CATALOG}.{SCHEMA}.rca_rules",
    schemas_dir / "rca_rules.json",
    properties={
        "delta.enableChangeDataFeed": "true",
    },
)
print(ddl)
spark.sql(ddl)

# COMMAND ----------
# MAGIC %md ## 3. Vector Search endpoint

# COMMAND ----------
from databricks.vector_search.client import VectorSearchClient

vsc = VectorSearchClient(disable_notice=True)

existing = {e["name"] for e in vsc.list_endpoints().get("endpoints", [])}
if VS_ENDPOINT not in existing:
    print(f"Creating Vector Search endpoint: {VS_ENDPOINT}")
    vsc.create_endpoint(name=VS_ENDPOINT, endpoint_type="STANDARD")
else:
    print(f"Endpoint {VS_ENDPOINT} already exists.")

# COMMAND ----------
# MAGIC %md ## 4. Vector Search indexes (Delta-sync; managed embeddings via FMAPI)

# COMMAND ----------
def _ensure_index(
    index_name: str,
    source_table: str,
    primary_key: str,
    embed_col: str,
    columns_to_sync: list[str],
):
    full = f"{CATALOG}.{SCHEMA}.{index_name}"
    try:
        existing_indexes = {i["name"] for i in vsc.list_indexes(name=VS_ENDPOINT).get("vector_indexes", [])}
    except Exception:
        existing_indexes = set()

    if full in existing_indexes:
        print(f"Index {full} already exists.")
        return

    print(f"Creating index {full} from {source_table}.{embed_col}")
    vsc.create_delta_sync_index(
        endpoint_name=VS_ENDPOINT,
        index_name=full,
        source_table_name=source_table,
        pipeline_type="TRIGGERED",
        primary_key=primary_key,
        embedding_source_column=embed_col,
        embedding_model_endpoint_name=EMBED_ENDPOINT,
        columns_to_sync=columns_to_sync,
    )


# rca_rules — scalar + ARRAY<STRING> columns are all VS-compatible.
_ensure_index(
    index_name=RULES_INDEX,
    source_table=f"{CATALOG}.{SCHEMA}.rca_rules",
    primary_key="id",
    embed_col="search_text",
    columns_to_sync=[
        "id",
        "description",
        "kpi_missed",
        "processing_rule",
        "processing_rule_tools",
        "severity_determination_rule",
        "severity_determination_rule_tools",
        "vendor",
        "author",
        "search_text",
    ],
)

# incidents — exclude `kpi_missed` (ARRAY<STRUCT>) and `events_embeddings`
# (ARRAY<DOUBLE>, regenerated by VS) since they're not VS-syncable column types.
_ensure_index(
    index_name=INCIDENTS_INDEX,
    source_table=f"{CATALOG}.{SCHEMA}.incidents",
    primary_key="incident_id",
    embed_col="events",
    columns_to_sync=[
        "incident_id",
        "start_ts",
        "end_ts",
        "status",
        "description",
        "enodeb_id",
        "cell_id",
        "severity",
        "preliminary_analysis",
        "final_analysis",
        "events",
        "cause",
        "resolution",
        "created_ts",
    ],
)

# COMMAND ----------
print("Setup complete.")
