# Databricks notebook source
# MAGIC %md
# MAGIC # 10_load_topology
# MAGIC
# MAGIC One-shot. Loads `data/network_topology.json` into the `cell_sites` table.
# MAGIC The 19 active cells map onto real Manhattan tower coordinates so the
# MAGIC map page can render synthetic telemetry on a real geography. Context
# MAGIC sites render in muted styling — they make the network look plausibly
# MAGIC busy without affecting any pipeline.

# COMMAND ----------
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd().parent
sys.path.insert(0, str(REPO_ROOT))

CATALOG = "srd_vibes_catalog"
SCHEMA = "network_intel"
TABLE = f"{CATALOG}.{SCHEMA}.cell_sites"
TOPO_FILE = REPO_ROOT / "data" / "network_topology.json"

topo = json.loads(TOPO_FILE.read_text())

MCC, MNC, NETWORK = 310, 260, "T-Mobile"


def _row(enodeb_id, cell_id, site_name, lat, lon, azimuth, range_m, band, is_active):
    return (
        str(enodeb_id),
        str(cell_id),
        site_name,
        float(lat),
        float(lon),
        float(azimuth),
        int(range_m),
        "LTE",
        band or "n41",
        MCC,
        MNC,
        NETWORK,
        is_active,
    )


rows = []
for site in topo["active_sites"]:
    for c in site["cells"]:
        rows.append(_row(site["enodeb_id"], c["cell_id"], site["site_name"], site["lat"], site["lon"], c["azimuth"], c["range_m"], c.get("band"), True))

# Context sites — synthesize cell ids and azimuths.
for site in topo["context_sites"]:
    n = site.get("n_sectors", 3)
    azimuths = [int(360 / n) * i for i in range(n)]
    for i, az in enumerate(azimuths):
        rows.append(_row(site["enodeb_id"], f"{site['enodeb_id']}_c{i}", site["site_name"], site["lat"], site["lon"], az, site.get("range_m", 320), None, False))

print(f"loading {len(rows)} rows into {TABLE}")

target_schema = spark.read.table(TABLE).schema
df = spark.createDataFrame(rows, schema=target_schema)
df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(TABLE)

# Sanity
spark.sql(f"SELECT is_active, COUNT(*) FROM {TABLE} GROUP BY is_active").show()
