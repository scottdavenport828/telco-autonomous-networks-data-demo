"""Dependency-injection helpers for the FastAPI app.

Two flavours of `WorkspaceClient`:

* `app_client` — uses the App's **service-principal** OAuth credentials
  (`DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` exposed by the Apps
  runtime). The SP's scopes come from the resource bindings declared in
  `resources/app.yml` (CAN_USE on the warehouse, CAN_QUERY on the serving
  endpoints). Used for read paths to shared resources.

* `user_client` — derived from the per-request `X-Forwarded-Access-Token`
  header that Databricks Apps injects when user_authorization is enabled.
  Used for any operation that must be attributed to the end user.

Default `WorkspaceClient()` in an App container resolves to the **user's**
forwarded OAuth token (limited scopes: `iam.*` only), so we have to be
explicit about which credentials to use for which call.
"""

from __future__ import annotations

import os
from typing import Annotated

from databricks.sdk import WorkspaceClient
from databricks.sdk.config import Config
from fastapi import Depends, Header

from tan.agents.sql import SqlClient
from tan.settings import SETTINGS, Settings


def get_settings() -> Settings:
    return SETTINGS


def _host() -> str:
    host = os.environ.get("DATABRICKS_HOST", "")
    if host and not host.startswith("https://"):
        host = "https://" + host
    return host


def get_app_client() -> WorkspaceClient:
    """SDK client authenticated as the App's service principal (OAuth M2M)."""
    client_id = os.environ.get("DATABRICKS_CLIENT_ID")
    client_secret = os.environ.get("DATABRICKS_CLIENT_SECRET")
    if client_id and client_secret:
        return WorkspaceClient(
            config=Config(
                host=_host(),
                client_id=client_id,
                client_secret=client_secret,
                auth_type="oauth-m2m",
            )
        )
    return WorkspaceClient()  # local dev fallback


def get_user_client(
    x_forwarded_access_token: Annotated[str | None, Header(alias="X-Forwarded-Access-Token")] = None,
) -> WorkspaceClient:
    """SDK client scoped to the calling user (OBO). Falls back to the app client during local dev."""
    if not x_forwarded_access_token:
        return get_app_client()
    return WorkspaceClient(
        config=Config(host=_host(), token=x_forwarded_access_token, auth_type="pat")
    )


def get_sql_client(
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[WorkspaceClient, Depends(get_app_client)],
) -> SqlClient:
    """Use the SP for SQL — the resource binding grants CAN_USE on the warehouse."""
    return SqlClient(settings.sql_warehouse_id, workspace=client)
