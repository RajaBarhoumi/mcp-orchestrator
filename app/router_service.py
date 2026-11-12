"""Two-level routing of a user message to the best MCP server and tools.

1. MCP level: an MCP is relevant if its centroid exceeds `THRESHOLD_MCP` OR if
   one of its tools exceeds `THRESHOLD_TOOL` ("best tool" fallback, because
   the centroid of a large heterogeneous catalog is diluted).
2. Tool level: among MCPs that are relevant AND allowed, keep the tools above
   `THRESHOLD_TOOL`, with a per-MCP quota (scores are not comparable from one
   catalog to another).

A tool's score is its semantic similarity plus a keyword (BM25) boost, and a
server named in the message ("in Notion", "#general") restricts routing to it
(see `candidates()` and `app/lexical.py`).

Outcomes: `tools_found` / `mcp_not_connected` / `mcp_out_of_scope` / `direct_answer`.
"""

from __future__ import annotations

import re

from app import embedding
from app.config import settings
from app.lexical import find_mentions
from app.repository import MockRepository, normalize_mcp_key, repository
from app.store import VectorStore, store

_MAX_RELEVANT_MCPS = 4
DEFAULT_TOP_K = 8


def _format_tool(tool: dict) -> dict:
    return {
        "namespaced_name": tool["namespaced_name"],
        "mcp": tool["mcp_key"],
        "tool_name": tool["tool_name"],
        "description": tool["description"],
        "input_schema": tool["input_schema"],
        "requires_confirmation": tool["requires_confirmation"],
        "convention": tool["convention"],
        "score": tool["score"],
        # Components of the score: similarity of meaning, and keyword boost (before weighting).
        "semantic_score": tool.get("semantic_score", tool["score"]),
        "keyword_score": tool.get("keyword_score", 0.0),
    }


def _format_mcp_scores(pairs: list[tuple[str, float]]) -> list[dict]:
    return [{"mcp": mcp_key, "score": score} for mcp_key, score in pairs]


def _format_suggestions(pairs: list[tuple[str, float]], tools: dict[str, dict | None]) -> list[dict]:
    """Connection suggestions, each with the tool that justifies it."""
    out = []
    for mcp_key, score in pairs:
        tool = tools.get(mcp_key)
        out.append(
            {
                "mcp": mcp_key,
                "score": score,
                "tool": None
                if tool is None
                else {"tool_name": tool["tool_name"], "description": tool.get("description") or "", "score": tool["score"]},
            }
        )
    return out


# KNOWLEDGE and meta questions: the discriminating signal is the shape of the
# sentence, not the similarity ("what is a pull request" strongly matches the
# GitHub tools although no action is requested). Data questions such as
# "what are my unpaid invoices" deliberately do NOT match.
_KNOWLEDGE_PATTERNS = re.compile(
    r"""^\s*(
        what\s+(is|are)\s+(a|an)\b
      | what\s+(is|are)\s+\w+\s+used\s+for
      | what\s+(is\s+)?the\s+difference
      | what\s+does\s+.+\s+mean
      | how\s+(does|do)\s+.+\s+work
      | explain\b
      | define\b
      | why\s+(can't|cannot|can\s+not|don't|do\s+you|are\s+you|is\s+it)
      | (is|was)\s+it\s+because
      | you\s+can'?t\b
      | who\s+are\s+you
      | what\s+can\s+you\s+do
      | what\s+(are\s+)?your\s+(capabilities|features|limits)
      | (which|what)\s+model
      | (give|send)\s+me\s+(the|a)\s+(link|url)
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def is_knowledge_query(query: str) -> bool:
    return bool(_KNOWLEDGE_PATTERNS.match(query or ""))


def decide(
    centroid_scores: list[tuple[str, float]],
    hits_by_mcp: dict[str, list[dict]],
    allowed: set[str],
    *,
    threshold_mcp: float,
    threshold_tool: float,
    top_k: int,
    knowledge_query: bool = False,
    connected: set[str] | None = None,
    threshold_suggest: float | None = None,
    max_suggested: int = 1,
    mentioned: set[str] | None = None,
    threshold_tool_mentioned: float | None = None,
) -> dict:
    """Routing decision core, PURE (no store/embedding/data access).

    `allowed`: routing scope. `connected`: everything the user can use
    (None = same as `allowed`). A candidate outside `allowed` goes to
    `suggested_mcps` if it is not connected, to `out_of_scope_mcps` otherwise.

    `mentioned`: servers explicitly named in the message ("in Notion", "#general").
    When it is not empty, ONLY those servers are candidates, with the tool threshold
    `threshold_tool_mentioned`: the user said where to act. A named server that is
    not connected is always suggested, whatever its tool scores.
    """
    if knowledge_query:
        return {"status": "direct_answer", "tools": [], "matched_mcps": [], "suggested_mcps": [], "out_of_scope_mcps": []}

    known_connected = allowed if connected is None else connected
    indexed = {key for key, _ in centroid_scores}
    mentioned = {key for key in (mentioned or set()) if key in indexed}
    mention_floor = threshold_tool if threshold_tool_mentioned is None else threshold_tool_mentioned

    candidates: list[tuple[str, float, float, list[dict]]] = []
    if mentioned:
        # Explicit mention: the named servers are the only candidates.
        for mcp_key, centroid_score in centroid_scores:
            if mcp_key in mentioned:
                hits = [tool for tool in hits_by_mcp.get(mcp_key, []) if tool["score"] >= mention_floor]
                best_tool_score = max((tool["score"] for tool in hits), default=0.0)
                candidates.append((mcp_key, centroid_score, best_tool_score, hits))
    else:
        # Level 1: centroid score OR best tool score above its threshold.
        for mcp_key, centroid_score in centroid_scores:
            hits = [tool for tool in hits_by_mcp.get(mcp_key, []) if tool["score"] >= threshold_tool]
            best_tool_score = max((tool["score"] for tool in hits), default=0.0)
            if centroid_score >= threshold_mcp or best_tool_score >= threshold_tool:
                candidates.append((mcp_key, centroid_score, best_tool_score, hits))

    # Rank by the STRONGER of the two signals, then cap.
    candidates.sort(key=lambda c: max(c[1], c[2]), reverse=True)
    candidates = candidates[:_MAX_RELEVANT_MCPS]

    matched_mcps = [(key, centroid) for key, centroid, _b, _h in candidates if key in allowed]

    # Connection suggestion: never on the centroid alone, only when a TOOL exceeds the threshold.
    suggest_floor = threshold_tool if threshold_suggest is None else threshold_suggest
    suggested_raw = [
        c
        for c in candidates
        if c[0] not in allowed and c[0] not in known_connected and (c[2] >= suggest_floor or c[0] in mentioned)
    ]
    suggested_raw.sort(key=lambda c: max(c[1], c[2]), reverse=True)
    suggested_raw = suggested_raw[: max(0, max_suggested)]
    suggested_mcps = [(key, centroid) for key, centroid, _b, _h in suggested_raw]
    suggested_tools = {key: (max(hits, key=lambda t: t["score"]) if hits else None) for key, _c, _b, hits in suggested_raw}

    out_of_scope_mcps = [(key, centroid) for key, centroid, _b, _h in candidates if key not in allowed and key in known_connected]

    # Level 2: per-MCP quota, then fill the remaining slots by global score.
    matched_with_hits = [(key, hits) for key, _c, _b, hits in candidates if key in allowed]
    tools: list[dict] = []
    if matched_with_hits:
        quota = max(1, top_k // len(matched_with_hits))
        taken: set[str] = set()
        for _key, hits in matched_with_hits:
            for tool in hits[:quota]:
                tools.append(_format_tool(tool))
                taken.add(tool["namespaced_name"])
        leftovers = [
            _format_tool(tool)
            for _key, hits in matched_with_hits
            for tool in hits
            if tool["namespaced_name"] not in taken
        ]
        leftovers.sort(key=lambda t: t["score"], reverse=True)
        tools.extend(leftovers[: max(0, top_k - len(tools))])

    tools.sort(key=lambda t: t["score"], reverse=True)
    tools = tools[:top_k]

    if tools:
        status = "tools_found"
    elif suggested_mcps:
        status = "mcp_not_connected"
    elif out_of_scope_mcps:
        status = "mcp_out_of_scope"
    else:
        status = "direct_answer"

    return {
        "status": status,
        "tools": tools,
        "matched_mcps": _format_mcp_scores(matched_mcps),
        "suggested_mcps": _format_suggestions(suggested_mcps, suggested_tools),
        "out_of_scope_mcps": _format_mcp_scores(out_of_scope_mcps),
    }


def candidates(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    vector_store: VectorStore | None = None,
    repo: MockRepository | None = None,
) -> tuple[list[tuple[str, float]], dict[str, list[dict]], set[str]]:
    """Scores that `decide()` works on: centroid scores, best tools per server, mentioned servers.

    A tool's score is its semantic similarity plus a keyword boost:
        score = cosine + LEXICAL_WEIGHT * bm25_boost   (bm25_boost in [0, 1))
    The boost only adds evidence: a tool that shares no rare word with the message keeps
    its semantic score. Catalogs are small per server, so every tool is scored.
    """
    # Defaults resolved at call time (not as default arguments), so they can be swapped in tests.
    vector_store = vector_store or store
    repo = repo or repository
    qvec = embedding.embed(query)
    centroid_scores = vector_store.search_centroids(qvec)
    weight = settings.LEXICAL_WEIGHT
    lexical = vector_store.lexical_scores(query) if weight > 0 else {}

    hits_by_mcp: dict[str, list[dict]] = {}
    for key, _score in centroid_scores:
        hits = vector_store.search_tools(qvec, key, k=10_000)
        for hit in hits:
            boost = lexical.get(hit["namespaced_name"], 0.0)
            hit["semantic_score"] = hit["score"]
            hit["keyword_score"] = boost
            hit["score"] = hit["score"] + weight * boost
        hits.sort(key=lambda t: t["score"], reverse=True)
        hits_by_mcp[key] = hits[:top_k]

    mentioned = find_mentions(query, repo.list_servers()) if settings.EXPLICIT_MENTION_ENABLED else set()
    return centroid_scores, hits_by_mcp, mentioned


def route(
    query: str,
    allowed_mcps: list[str],
    top_k: int = DEFAULT_TOP_K,
    connected_mcps: list[str] | None = None,
    vector_store: VectorStore | None = None,
    repo: MockRepository | None = None,
) -> dict:
    """Route `query` to the relevant MCPs / tools within `allowed_mcps`."""
    allowed = {normalize_mcp_key(k) for k in allowed_mcps}
    connected = None if connected_mcps is None else {normalize_mcp_key(k) for k in connected_mcps}

    centroid_scores, hits_by_mcp, mentioned = candidates(query, top_k, vector_store, repo)

    result = decide(
        centroid_scores,
        hits_by_mcp,
        allowed,
        threshold_mcp=settings.THRESHOLD_MCP,
        threshold_tool=settings.THRESHOLD_TOOL,
        top_k=top_k,
        knowledge_query=settings.KNOWLEDGE_GUARD_ENABLED and is_knowledge_query(query),
        connected=connected,
        threshold_suggest=settings.THRESHOLD_SUGGEST,
        max_suggested=settings.MAX_SUGGESTED_MCPS,
        mentioned=mentioned,
        threshold_tool_mentioned=settings.THRESHOLD_TOOL_MENTIONED,
    )
    # Convenience fields: THE best MCP to answer the message (None if none), and the servers
    # the message named explicitly.
    result["best_mcp"] = result["tools"][0]["mcp"] if result["tools"] else None
    result["mentioned_mcps"] = sorted(mentioned)
    return result


def explain(
    query: str, allowed_mcps: list[str], vector_store: VectorStore | None = None, repo: MockRepository | None = None
) -> dict:
    """Same computation as `route()` but every raw score, no thresholds (calibration)."""
    allowed = {normalize_mcp_key(k) for k in allowed_mcps}
    centroid_scores, hits_by_mcp, mentioned = candidates(query, 20, vector_store, repo)

    all_tools: list[dict] = [_format_tool(t) for hits in hits_by_mcp.values() for t in hits]
    all_tools.sort(key=lambda t: t["score"], reverse=True)

    return {
        "query": query,
        "thresholds": {
            "mcp": settings.THRESHOLD_MCP,
            "tool": settings.THRESHOLD_TOOL,
            "suggest": settings.THRESHOLD_SUGGEST,
        },
        "knowledge_query": is_knowledge_query(query),
        "mentioned_mcps": sorted(mentioned),
        "mcp_scores": [{"mcp": k, "score": s, "allowed": k in allowed} for k, s in centroid_scores],
        "top_tools": [{k: v for k, v in t.items() if k != "input_schema"} for t in all_tools[:20]],
    }
