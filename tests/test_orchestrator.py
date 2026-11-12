"""Fast tests: pure decision logic, mock data, indexing and API (fake embedding, no model)."""

import re
import zlib

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import embedding, indexer, router_service
from app.repository import repository
from app.router_service import decide, is_knowledge_query
from app.store import VectorStore

_DIM = 256


def _fake_embed_batch(texts):
    """Hashed bag of words: two texts sharing words get a similarity > 0."""
    out = np.zeros((len(texts), _DIM), dtype=np.float32)
    for i, text in enumerate(texts):
        for word in re.findall(r"\w{3,}", text.lower()):
            out[i, zlib.crc32(word.encode()) % _DIM] += 1.0
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return out / norms


@pytest.fixture()
def fake_embeddings(monkeypatch, tmp_path):
    monkeypatch.setattr(embedding, "embed_batch", _fake_embed_batch)
    monkeypatch.setattr(embedding, "embed", lambda t: _fake_embed_batch([t])[0])
    monkeypatch.setattr(embedding, "get_active_model_name", lambda: "fake")
    monkeypatch.setattr(embedding, "get_embedding_dim", lambda: _DIM)
    vs = VectorStore(tmp_path / "index")
    monkeypatch.setattr(indexer, "store", vs)
    monkeypatch.setattr(router_service, "store", vs)
    return vs


def _tool(mcp, name, score):
    return {
        "mcp_key": mcp,
        "tool_name": name,
        "namespaced_name": f"{mcp}__{name}",
        "description": "",
        "input_schema": {},
        "requires_confirmation": False,
        "convention": "unknown",
        "score": score,
    }


KW = dict(threshold_mcp=0.20, threshold_tool=0.28, top_k=8, threshold_suggest=0.40)


def test_decide_tools_found_for_connected_mcp():
    result = decide([("crm", 0.3), ("cms", 0.1)], {"crm": [_tool("crm", "list_contacts", 0.6)]}, {"crm"}, **KW)
    assert result["status"] == "tools_found"
    assert result["tools"][0]["namespaced_name"] == "crm__list_contacts"


def test_decide_suggests_unconnected_mcp_only_on_strong_tool():
    hits = {"cms": [_tool("cms", "create_draft", 0.55)]}
    result = decide([("cms", 0.25)], hits, set(), **KW)
    assert result["status"] == "mcp_not_connected"
    assert result["suggested_mcps"][0]["mcp"] == "cms"
    # Centroid alone above the threshold: no suggestion.
    weak = decide([("cms", 0.35)], {"cms": [_tool("cms", "x", 0.30)]}, set(), **KW)
    assert weak["status"] == "direct_answer"


def test_decide_out_of_scope_when_connected_but_restricted():
    hits = {"cms": [_tool("cms", "create_draft", 0.55)]}
    result = decide([("cms", 0.3)], hits, allowed=set(), connected={"cms"}, **KW)
    assert result["status"] == "mcp_out_of_scope"
    assert result["suggested_mcps"] == []


def test_knowledge_guard():
    assert is_knowledge_query("what is a pull request?")
    assert is_knowledge_query("explain the difference between merge and rebase")
    assert not is_knowledge_query("what are my unpaid invoices?")
    assert not is_knowledge_query("what is the weather in Lyon?")
    assert decide([("crm", 0.9)], {}, {"crm"}, knowledge_query=True, **KW)["status"] == "direct_answer"


def test_mock_data_allowed_mcps():
    assert repository.get_allowed_mcps(1) == ["github", "jira", "slack", "trello"]
    assert repository.get_allowed_mcps(4) == []
    # google_drive in "error" and openweather "disconnected" are not allowed.
    assert repository.get_allowed_mcps(5) == ["google_sheets", "notion"]


def test_no_tool_name_exceeds_openai_limit():
    for tool in repository.list_tools():
        assert len(f"{tool.mcp_key}__{tool.tool_name}") <= indexer.OPENAI_TOOL_NAME_MAX_CHARS


def test_reindex_is_incremental(fake_embeddings):
    first = indexer.reindex_all()
    assert all(r["status"] == "indexed" for r in first.values())
    second = indexer.reindex_all()
    assert all(r["status"] == "unchanged" for r in second.values())


def test_route_endpoint(fake_embeddings):
    indexer.reindex_all()
    from app.routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    res = client.post("/orchestrator/route", json={"query": "create an invoice for a customer", "user_id": 3})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] in {"tools_found", "direct_answer"}
    assert "best_mcp" in body

    assert client.get("/orchestrator/health").json()["status"] == "ok"
    assert len(client.get("/orchestrator/mcps").json()) == 22


def test_catalog_has_200_unique_tools():
    tools = repository.list_tools()
    names = {f"{t.mcp_key}__{t.tool_name}" for t in tools}
    assert len(tools) == len(names) == 200
