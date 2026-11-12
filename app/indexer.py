"""Incremental indexing of MCP tools from the mock data.

For each MCP: hash the catalog -> if it matches the existing index, no
embedding is recomputed; otherwise only THIS MCP is re-embedded.
"""

from __future__ import annotations

import hashlib
import json
import logging

from app import embedding
from app.config import settings
from app.repository import McpServer, McpTool, MockRepository, normalize_mcp_key, repository
from app.schema_utils import normalize_input_schema
from app.store import VectorStore, store

logger = logging.getLogger(__name__)

# OpenAI function name limit: `{mcp_key}__{tool_name}` longer than this is skipped.
OPENAI_TOOL_NAME_MAX_CHARS = 64

# Part of the hash: changing `_tool_to_text` must invalidate existing indexes.
TEXT_FORMULA_VERSION = "3"


def naming_convention_for(mcp_key: str, repo: MockRepository | None = None) -> str:
    """Parameter naming convention (metadata passed to the LLM, no effect on
    routing), read from `mcp_servers[].naming_convention`."""
    key = normalize_mcp_key(mcp_key)
    for server in (repo or repository).list_servers():
        if normalize_mcp_key(server.key) == key:
            return server.naming_convention
    return "unknown"


def server_context(server: McpServer | None) -> str:
    """Prefix embedded in front of every tool of a server: "Zendesk. Customer support: ...".

    Without it, "get ticket" of Zendesk and "get ticket" of Jira have nearly the same
    text, hence the same vector: nothing tells them apart but the server.
    """
    if server is None or not settings.SERVER_CONTEXT_IN_TOOL_TEXT:
        return ""
    if settings.SERVER_CONTEXT_INCLUDE_DOMAIN and server.description.strip():
        return f"{server.label}. {server.description.strip()} "
    return f"{server.label}. "


def compute_catalog_hash(tools: list[McpTool], context: str = "") -> str:
    """Stable fingerprint of a catalog: independent of tool order and JSON formatting.
    Includes the server context, so toggling SERVER_CONTEXT_IN_TOOL_TEXT re-embeds."""
    entries = sorted(
        (
            tool.tool_name,
            tool.description or "",
            json.dumps(normalize_input_schema(tool.input_schema), sort_keys=True),
        )
        for tool in tools
    )
    canonical = json.dumps([TEXT_FORMULA_VERSION, context, entries])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _tool_to_text(tool: McpTool, context: str = "") -> str:
    """Server context + readable name + description + parameter NAMES.

    The full JSON Schema is not embedded: its structural noise drowns the
    useful signal and flattens the similarity scores.
    """
    schema = normalize_input_schema(tool.input_schema)
    param_names = ", ".join(list(schema.get("properties", {}).keys())[:12])
    readable_name = tool.tool_name.replace("_", " ").replace("-", " ")
    text = f"{context}{readable_name}. {(tool.description or '').strip()}"
    return f"{text} Parameters: {param_names}." if param_names else text


def _tool_to_metadata(tool: McpTool, convention: str, text: str = "") -> dict:
    mcp_key = normalize_mcp_key(tool.mcp_key)
    return {
        "mcp_key": mcp_key,
        "tool_name": tool.tool_name,
        "namespaced_name": f"{mcp_key}__{tool.tool_name}",
        # Exact text that was embedded; also the document of the keyword (BM25) index.
        "text": text,
        "description": tool.description or "",
        "input_schema": normalize_input_schema(tool.input_schema),
        "requires_confirmation": bool(tool.is_destructive),
        "convention": convention,
    }


def reindex_mcp(
    mcp_key: str,
    force: bool = False,
    repo: MockRepository | None = None,
    vector_store: VectorStore | None = None,
) -> dict:
    """Return {"status": "empty" | "unchanged" | "indexed", "count": n}."""
    repo, vector_store = repo or repository, vector_store or store  # resolved at call time
    normalized_key = normalize_mcp_key(mcp_key)
    tools = repo.list_tools(normalized_key)
    if not tools:
        return {"status": "empty", "count": 0}

    indexable = [t for t in tools if len(f"{normalized_key}__{t.tool_name}") <= OPENAI_TOOL_NAME_MAX_CHARS]
    skipped = len(tools) - len(indexable)
    if skipped:
        logger.warning("reindex_mcp(%s): %d tool(s) skipped, name too long for OpenAI", mcp_key, skipped)
    if not indexable:
        return {"status": "empty", "count": 0, "skipped": skipped}

    server = next((s for s in repo.list_servers() if normalize_mcp_key(s.key) == normalized_key), None)
    context = server_context(server)
    new_hash = compute_catalog_hash(tools, context)
    if not force and vector_store.get_hash(normalized_key) == new_hash:
        result = {"status": "unchanged", "count": len(indexable)}
    else:
        texts = [_tool_to_text(t, context) for t in indexable]
        vectors = embedding.embed_batch(texts)  # one batch per MCP
        convention = naming_convention_for(normalized_key, repo)
        metadatas = [_tool_to_metadata(t, convention, text) for t, text in zip(indexable, texts)]
        vector_store.replace_mcp(normalized_key, vectors, metadatas, new_hash)
        vector_store.save()
        result = {"status": "indexed", "count": len(indexable)}
    if skipped:
        result["skipped"] = skipped
    return result


def reindex_all(
    force: bool = False,
    repo: MockRepository | None = None,
    vector_store: VectorStore | None = None,
) -> dict[str, dict]:
    """(Re)index every MCP of the mock data and purge the ones that disappeared."""
    repo, vector_store = repo or repository, vector_store or store  # resolved at call time
    server_keys = {normalize_mcp_key(s.key) for s in repo.list_servers()}
    results = {key: reindex_mcp(key, force=force, repo=repo, vector_store=vector_store) for key in sorted(server_keys)}
    for stale in set(vector_store.keys()) - server_keys:
        vector_store.remove_mcp(stale)
        results[stale] = {"status": "removed", "count": 0}
    return results
