"""Entry point: uvicorn app.main:app --reload"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.indexer import reindex_all
from app.routes import router
from app.store import store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestrator")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load the existing indexes, then only re-embed the catalogs that changed.
    store.load()
    results = reindex_all()
    logger.info("MCP index ready: %s", {k: v["status"] for k, v in results.items()})
    yield


app = FastAPI(title="MCP Orchestrator", version="1.0.0", lifespan=lifespan)
app.include_router(router)


@app.get("/")
async def root():
    return {"service": "mcp-orchestrator", "docs": "/docs"}
