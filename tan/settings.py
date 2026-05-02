"""Centralised, env-driven configuration. Mirrors the GCP source's `settings.py` modules."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    catalog: str
    schema: str
    volume: str

    llm_endpoint: str
    embedding_endpoint: str
    agent_endpoint: str

    vs_endpoint: str
    rules_index: str
    incidents_index: str

    sql_warehouse_id: str

    similarity_search_cutoff: float
    similarity_search_likely_match: float
    similarity_search_max_results: int

    erab_success_rate_threshold: float
    retainability_threshold: float

    @property
    def perf_table(self) -> str:
        return f"{self.catalog}.{self.schema}.performance"

    @property
    def cell_traces_table(self) -> str:
        return f"{self.catalog}.{self.schema}.cell_traces"

    @property
    def incidents_table(self) -> str:
        return f"{self.catalog}.{self.schema}.incidents"

    @property
    def perf_kpi_view(self) -> str:
        return f"{self.catalog}.{self.schema}.performance_kpi"

    @property
    def rca_rules_table(self) -> str:
        return f"{self.catalog}.{self.schema}.rca_rules"

    @property
    def volume_root(self) -> str:
        return f"/Volumes/{self.catalog}/{self.schema}/{self.volume}"

    @property
    def rules_index_full(self) -> str:
        return f"{self.catalog}.{self.schema}.{self.rules_index}"

    @property
    def incidents_index_full(self) -> str:
        return f"{self.catalog}.{self.schema}.{self.incidents_index}"


def load_settings() -> Settings:
    return Settings(
        catalog=os.environ.get("CATALOG", "telco_demo"),
        schema=os.environ.get("SCHEMA", "network_intel"),
        volume=os.environ.get("VOLUME", "raw"),
        llm_endpoint=os.environ.get("LLM_ENDPOINT", "claude-opus-4-7-gw"),
        embedding_endpoint=os.environ.get("EMBEDDING_ENDPOINT", "databricks-gte-large-en"),
        agent_endpoint=os.environ.get("AGENT_ENDPOINT", "telco-rca-agents"),
        vs_endpoint=os.environ.get("VS_ENDPOINT", "srd-vibes-vs"),
        rules_index=os.environ.get("RULES_INDEX", "rca_rules_vs_idx"),
        incidents_index=os.environ.get("INCIDENTS_INDEX", "incidents_vs_idx"),
        sql_warehouse_id=os.environ.get("SQL_WAREHOUSE_ID", ""),
        similarity_search_cutoff=float(os.environ.get("SIM_CUTOFF", "0.5")),
        similarity_search_likely_match=float(os.environ.get("SIM_LIKELY", "0.9")),
        similarity_search_max_results=int(os.environ.get("SIM_MAX", "5")),
        erab_success_rate_threshold=float(os.environ.get("ERAB_THRESHOLD", "97.0")),
        retainability_threshold=float(os.environ.get("RETAIN_THRESHOLD", "3.0")),
    )


SETTINGS = load_settings()
