"""FastAPI routes of the orchestrator, under the /orchestrator prefix."""

import asyncio

from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.indexer import reindex_all, reindex_mcp
from app.repository import repository
from app.router_service import explain, route
from app.schemas import ExplainRequest, RouteRequest
from app.store import store

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


@router.get("/health")
async def health():
    return {"status": "ok", "embedding_provider": settings.EMBEDDING_PROVIDER, "mcp_index": store.stats()}


@router.get("/mcps")
async def list_mcps():
    """MCP servers declared in the mock data, with their tool count."""
    return [
        {
            "key": s.key,
            "label": s.label,
            "description": s.description,
            "is_native": s.is_native,
            "tools_count": len(repository.list_tools(s.key)),
        }
        for s in repository.list_servers()
    ]


@router.get("/users")
async def list_users():
    """Fictitious users and the MCP servers they are connected to."""
    return [{**u, "allowed_mcps": repository.get_allowed_mcps(u["id"])} for u in repository.list_users()]


@router.post("/index/sync/{mcp_key}")
async def sync_mcp_index(mcp_key: str, force: bool = Query(False)):
    """(Re)index one MCP after its catalog changed in the mock data."""
    if mcp_key.strip().lower() not in {s.key.strip().lower() for s in repository.list_servers()}:
        raise HTTPException(status_code=404, detail=f"Unknown MCP: {mcp_key}")
    return await asyncio.to_thread(reindex_mcp, mcp_key, force)


@router.post("/index/rebuild")
async def rebuild_index(force: bool = Query(False)):
    """(Re)index every MCP of the mock data."""
    return await asyncio.to_thread(reindex_all, force)


@router.delete("/index/{mcp_key}")
async def remove_mcp_index(mcp_key: str):
    removed = store.remove_mcp(mcp_key.strip().lower())
    return {"mcp_key": mcp_key, "removed": removed, "mcp_index": store.stats()}


def _resolve_allowed_mcps(payload) -> list[str]:
    if payload.allowed_mcps is not None:
        return payload.allowed_mcps
    if payload.user_id is not None:
        return repository.get_allowed_mcps(payload.user_id)
    return []


@router.post("/route")
async def route_query(payload: RouteRequest):
    """Pick the best MCP server(s) and tools to answer the message."""
    allowed = _resolve_allowed_mcps(payload)
    # Embedding + FAISS are CPU-bound: keep them off the asyncio event loop.
    return await asyncio.to_thread(route, payload.query, allowed, payload.top_k)


@router.post("/route/explain")
async def route_query_explain(payload: ExplainRequest):
    """Every raw score, without thresholds (calibration)."""
    allowed = _resolve_allowed_mcps(payload)
    return await asyncio.to_thread(explain, payload.query, allowed)
