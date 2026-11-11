"""Pydantic schemas of the HTTP requests."""

from pydantic import BaseModel, Field


class RouteQueryBase(BaseModel):
    """An explicit `allowed_mcps` takes precedence; otherwise it is resolved from
    `user_id` in the mock data; otherwise empty (no MCP connected, a valid case)."""

    query: str = Field(..., min_length=1)
    user_id: int | None = None
    allowed_mcps: list[str] | None = None


class RouteRequest(RouteQueryBase):
    top_k: int = Field(8, ge=1, le=15)


class ExplainRequest(RouteQueryBase):
    pass
