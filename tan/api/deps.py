"""Dependency-injection helpers for the FastAPI app.

Two flavours of `WorkspaceClient`:

* `app_client` — uses the App's service-principal token (default Databricks SDK
  auth chain when running inside Databricks Apps). Used for read paths to
  shared resources.

* `user_client` — derived from the per-request `X-Forwarded-Access-Token`
  header that Databricks Apps injects when user_authorization is enabled.
  Used for any write that should be attributed to the end user.
"""

from __future__ import annotations

from typing import Annotated

from databricks.sdk import WorkspaceClient
from databricks.sdk.config import Config
from fastapi import Depends, Header

from tan.agents.sql import SqlClient
from tan.settings import SETTINGS, Settings


def get_settings() -> Settings:
    return SETTINGS


def get_app_client() -> WorkspaceClient:
    """SDK client using the app's service-principal token."""
    return WorkspaceClient()


def get_user_client(
    x_forwarded_access_token: Annotated[str | None, Header(alias="X-Forwarded-Access-Token")] = None,
) -> WorkspaceClient:
    """SDK client scoped to the calling user (OBO).

    Falls back to the app client when the header is absent (e.g. during local dev).
    """
    if not x_forwarded_access_token:
        return WorkspaceClient()
    cfg = Config(host=WorkspaceClient().config.host, token=x_forwarded_access_token, auth_type="pat")
    return WorkspaceClient(config=cfg)


def get_sql_client(
    settings: Annotated[Settings, Depends(get_settings)],
    client: Annotated[WorkspaceClient, Depends(get_user_client)],
) -> SqlClient:
    return SqlClient(settings.sql_warehouse_id, workspace=client)
