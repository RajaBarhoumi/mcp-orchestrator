"""Evaluate the orchestrator on the labeled set eval/eval_queries.json.

    python scripts/evaluate.py                    # 200-tool catalog, all queries, report in reports/
    python scripts/evaluate.py --compare-core     # + the core queries on the 73-tool catalog vs the 200-tool one
    python scripts/evaluate.py --sweep            # + threshold sweep (calibration)
    python scripts/evaluate.py -v                 # + details of every error

The evaluated routing is EXACTLY the one used by the API (`router_service.route`),
with the thresholds of the current configuration (.env). Context size is measured
in tokens (tiktoken, o200k_base) on the OpenAI function definitions the model would
receive: the whole catalog versus the routed shortlist.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tiktoken  # noqa: E402

from app import embedding  # noqa: E402
from app.config import settings  # noqa: E402
from app.indexer import reindex_all  # noqa: E402
from app.repository import MockRepository, repository  # noqa: E402
from app.router_service import DEFAULT_TOP_K, candidates, decide, is_knowledge_query, route  # noqa: E402
from app.store import VectorStore, store  # noqa: E402
from scripts.build_mock_data import build  # noqa: E402

_ENCODING = tiktoken.get_encoding("o200k_base")


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}% ({n}/{d})" if d else "n/a"


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(p / 100 * (len(ordered) - 1))))
    return ordered[idx]


def function_tokens(tools: list[dict]) -> int:
    """Tokens of the OpenAI function definitions for these tools (what the model reads)."""
    defs = [
        {"type": "function", "function": {"name": t["namespaced_name"], "description": t["description"], "parameters": t["input_schema"]}}
        for t in tools
    ]
    return len(_ENCODING.encode(json.dumps(defs, ensure_ascii=False))) if defs else 0


def all_tool_entries(repo: MockRepository, allowed: list[str]) -> list[dict]:
    from app.indexer import _tool_to_metadata, naming_convention_for

    return [
        _tool_to_metadata(t, naming_convention_for(t.mcp_key, repo))
        for t in repo.list_tools()
        if t.mcp_key in set(allowed)
    ]


def raw_rank(vs: VectorStore, qvec, expected_tools: list[str]) -> int | None:
    """1-based rank of the first expected tool among ALL tools, without thresholds:
    measures the raw embedding quality, independently of the thresholds."""
    scored = []
    for key, _ in vs.search_centroids(qvec):
        scored.extend(vs.search_tools(qvec, key, k=1000))
    scored.sort(key=lambda t: t["score"], reverse=True)
    for i, tool in enumerate(scored, start=1):
        if tool["namespaced_name"] in expected_tools:
            return i
    return None


def evaluate(queries: list[dict], repo: MockRepository, vs: VectorStore, verbose: bool) -> tuple[dict, list[dict], list[dict]]:
    rows, cache, latencies = [], [], []
    route("warm-up", [], vector_store=vs, repo=repo)  # first call loads the model, excluded from latencies

    for q in queries:
        allowed = repo.get_allowed_mcps(q["user_id"])
        t0 = time.perf_counter()
        result = route(q["query"], allowed, vector_store=vs, repo=repo)
        latencies.append((time.perf_counter() - t0) * 1000)

        # Same inputs as route() (semantic + keyword scores, mentions), kept for the threshold sweep.
        qvec = embedding.embed(q["query"])
        centroid_scores, hits, mentioned = candidates(q["query"], DEFAULT_TOP_K, vs, repo)
        cache.append({"q": q, "allowed": set(allowed), "centroids": centroid_scores, "hits": hits, "mentioned": mentioned})

        names = [t["namespaced_name"] for t in result["tools"]]
        expected_tools = q.get("expected_tools", [])
        rows.append(
            {
                **q,
                "status": result["status"],
                "best_mcp": result["best_mcp"],
                "matched": [m["mcp"] for m in result["matched_mcps"]],
                "suggested": [m["mcp"] for m in result["suggested_mcps"]],
                "tools": names,
                "tool_rank": next((i for i, n in enumerate(names, 1) if n in expected_tools), None),
                "raw_rank": raw_rank(vs, qvec, expected_tools) if expected_tools else None,
                "shortlist_tokens": function_tokens(result["tools"]),
                "catalog_tokens": function_tokens(all_tool_entries(repo, allowed)),
            }
        )

    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)
    ind, nc = by_cat["in_domain"], by_cat["not_connected"]
    da = by_cat["knowledge"] + by_cat["out_of_domain"]
    with_tools = [r for r in ind if r["tools"]]

    m = {
        "n_queries": len(rows),
        "status_accuracy": sum(r["status"] == r["expected_status"] for r in rows),
        "status_by_category": {cat: (sum(r["status"] == r["expected_status"] for r in rs), len(rs)) for cat, rs in by_cat.items()},
        "best_mcp_correct": sum(r["best_mcp"] in r["expected_mcp"] for r in ind),
        "mcp_recall": sum(any(k in r["matched"] for k in r["expected_mcp"]) for r in ind),
        "tool_hit1": sum(r["tool_rank"] == 1 for r in ind),
        "tool_hit3": sum(r["tool_rank"] is not None and r["tool_rank"] <= 3 for r in ind),
        "tool_hitk": sum(r["tool_rank"] is not None for r in ind),
        "tool_mrr": sum(1 / r["tool_rank"] for r in ind if r["tool_rank"]) / len(ind) if ind else 0,
        "raw_hit1": sum(r["raw_rank"] == 1 for r in ind),
        "raw_hit3": sum(r["raw_rank"] is not None and r["raw_rank"] <= 3 for r in ind),
        "raw_mrr": sum(1 / r["raw_rank"] for r in ind if r["raw_rank"]) / len(ind) if ind else 0,
        "avg_tools": statistics.mean(len(r["tools"]) for r in ind) if ind else 0,
        "avg_matched_mcps": statistics.mean(len(r["matched"]) for r in ind) if ind else 0,
        "n_in_domain": len(ind),
        "suggest_correct": sum(bool(r["suggested"]) and r["suggested"][0] in r["expected_mcp"] for r in nc),
        "n_not_connected": len(nc),
        "false_positive": sum(r["status"] != "direct_answer" for r in da),
        "n_direct": len(da),
        "catalog_tokens": statistics.mean(r["catalog_tokens"] for r in ind) if ind else 0,
        "shortlist_tokens_mean": statistics.mean(r["shortlist_tokens"] for r in with_tools) if with_tools else 0,
        "shortlist_tokens_p95": percentile([r["shortlist_tokens"] for r in with_tools], 95) if with_tools else 0,
        "latency_ms": {
            "mean": statistics.mean(latencies),
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "max": max(latencies),
        },
    }
    if verbose:
        print("\n=== Errors ===")
        for r in rows:
            wrong_status = r["status"] != r["expected_status"]
            wrong_mcp = r["category"] == "in_domain" and r["best_mcp"] not in r["expected_mcp"]
            if wrong_status or wrong_mcp:
                print(
                    f"- [{r['category']}/{r['set']}] {r['query']}\n    expected {r['expected_status']} {r.get('expected_mcp', '')}"
                    f" | got {r['status']} best={r['best_mcp']} suggested={r['suggested']} tools={r['tools'][:3]}"
                )
    return m, rows, cache


def sweep(cache: list[dict]) -> list[dict]:
    """Replay `decide()` (without re-embedding) for several THRESHOLD_TOOL values."""
    out = []
    for th in [0.20, 0.25, 0.28, 0.30, 0.35, 0.40, 0.45, 0.50]:
        ok = ind_ok = ind_n = fp = da_n = 0
        for c in cache:
            q = c["q"]
            res = decide(
                c["centroids"],
                c["hits"],
                c["allowed"],
                threshold_mcp=settings.THRESHOLD_MCP,
                threshold_tool=th,
                top_k=DEFAULT_TOP_K,
                knowledge_query=settings.KNOWLEDGE_GUARD_ENABLED and is_knowledge_query(q["query"]),
                threshold_suggest=max(th, settings.THRESHOLD_SUGGEST),
                max_suggested=settings.MAX_SUGGESTED_MCPS,
                mentioned=c["mentioned"],
                threshold_tool_mentioned=settings.THRESHOLD_TOOL_MENTIONED,
            )
            ok += res["status"] == q["expected_status"]
            if q["category"] == "in_domain":
                ind_n += 1
                best = res["tools"][0]["mcp"] if res["tools"] else None
                ind_ok += best in q["expected_mcp"]
            if q["expected_status"] == "direct_answer":
                da_n += 1
                fp += res["status"] != "direct_answer"
        out.append({"threshold_tool": th, "status_acc": ok / len(cache), "best_mcp_acc": ind_ok / ind_n, "fp_rate": fp / da_n})
    return out


def render(m: dict, repo: MockRepository, index_seconds: float, sweep_rows: list[dict] | None, comparison: list[tuple] | None) -> str:
    lat = m["latency_ms"]
    lines = [
        f"# Orchestrator metrics ({date.today().isoformat()})",
        "",
        f"- Embedding model: `{embedding.get_active_model_name()}` ({settings.EMBEDDING_PROVIDER})",
        f"- Catalog: {len(repo.list_servers())} MCP servers, {len(repo.list_tools())} tools",
        f"- Thresholds: MCP {settings.THRESHOLD_MCP} / tool {settings.THRESHOLD_TOOL} / suggestion {settings.THRESHOLD_SUGGEST}",
        f"- Evaluation set: {m['n_queries']} labeled queries (eval/eval_queries.json)",
        "",
        "## Overall decision",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Status accuracy (all queries) | {pct(m['status_accuracy'], m['n_queries'])} |",
    ]
    for cat, (ok, n) in sorted(m["status_by_category"].items()):
        lines.append(f"| Status accuracy, `{cat}` | {pct(ok, n)} |")
    n = m["n_in_domain"]
    lines += [
        "",
        f"## MCP and tool selection ({n} in-domain queries, user connected to everything)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| **Correct best MCP** (`best_mcp`) | {pct(m['best_mcp_correct'], n)} |",
        f"| Expected MCP in `matched_mcps` | {pct(m['mcp_recall'], n)} |",
        f"| Expected tool ranked first (Hit@1) | {pct(m['tool_hit1'], n)} |",
        f"| Expected tool in the top 3 (Hit@3) | {pct(m['tool_hit3'], n)} |",
        f"| Expected tool among returned tools (Hit@{DEFAULT_TOP_K}) | {pct(m['tool_hitk'], n)} |",
        f"| MRR of returned tools | {m['tool_mrr']:.3f} |",
        f"| Tools returned per query (mean) | {m['avg_tools']:.1f} |",
        f"| MCP servers kept per query (mean) | {m['avg_matched_mcps']:.1f} |",
        "",
        "Raw embedding quality (ranking of all tools, no thresholds):",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Raw Hit@1 | {pct(m['raw_hit1'], n)} |",
        f"| Raw Hit@3 | {pct(m['raw_hit3'], n)} |",
        f"| Raw MRR | {m['raw_mrr']:.3f} |",
        "",
        "## Context sent to the model (tool definitions, tiktoken o200k_base)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Whole catalog of the user (no routing) | {m['catalog_tokens']:,.0f} tokens |",
        f"| Routed shortlist, mean / p95 | {m['shortlist_tokens_mean']:,.0f} / {m['shortlist_tokens_p95']:,.0f} tokens |",
        f"| Reduction | {100 * (1 - m['shortlist_tokens_mean'] / m['catalog_tokens']):.1f}% |"
        if m["catalog_tokens"]
        else "| Reduction | n/a |",
        "",
        "## Missing connectors and false positives",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Right connector suggested when it is not connected | {pct(m['suggest_correct'], m['n_not_connected'])} |",
        f"| False positives (tools proposed for a general question) | {pct(m['false_positive'], m['n_direct'])} |",
        "",
        "## Performance",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Mean `route()` latency | {lat['mean']:.1f} ms |",
        f"| p50 / p95 / max latency | {lat['p50']:.1f} / {lat['p95']:.1f} / {lat['max']:.1f} ms |",
        f"| Full indexing (`force=True`) | {index_seconds:.2f} s |",
    ]
    if comparison:
        lines += [
            "",
            "## Catalog size: same core queries, 73 vs 200 tools",
            "",
            "The core queries were written for the original 9-server catalog; here they run unchanged",
            "against both catalogs (answers from the new servers are accepted when they are also correct).",
            "",
            "| Metric | 73 tools | 200 tools |",
            "|---|---|---|",
        ]
        lines += [f"| {label} | {a} | {b} |" for label, a, b in comparison]
    if sweep_rows:
        lines += [
            "",
            "## THRESHOLD_TOOL sweep",
            "",
            "| Tool threshold | Status accuracy | Correct best MCP | False positive rate |",
            "|---|---|---|---|",
        ]
        for s in sweep_rows:
            lines.append(
                f"| {s['threshold_tool']:.2f} | {100 * s['status_acc']:.1f}% | {100 * s['best_mcp_acc']:.1f}% | {100 * s['fp_rate']:.1f}% |"
            )
    return "\n".join(lines) + "\n"


def compare_core(queries: list[dict], main_metrics: dict) -> list[tuple]:
    """Run the core queries on a temporary 73-tool catalog and compare with the 200-tool results."""
    tmp = ROOT / "data" / "core_catalog"
    tmp.mkdir(parents=True, exist_ok=True)
    path = tmp / "mock_data_core.json"
    path.write_text(json.dumps(build(core_only=True), ensure_ascii=False), encoding="utf-8")
    repo73, vs73 = MockRepository(path), VectorStore(tmp / "index")
    reindex_all(repo=repo73, vector_store=vs73)

    core = [q for q in queries if q.get("set", "core") == "core"]
    m73, _, _ = evaluate(core, repo73, vs73, verbose=False)
    m200 = main_metrics

    def ratio(m, key, total):
        return pct(m[key], m[total])

    return [
        ("Status accuracy (core queries)", ratio(m73, "status_accuracy", "n_queries"), ratio(m200, "status_accuracy", "n_queries")),
        ("**Correct best MCP**", ratio(m73, "best_mcp_correct", "n_in_domain"), ratio(m200, "best_mcp_correct", "n_in_domain")),
        ("Expected tool ranked first (Hit@1)", ratio(m73, "tool_hit1", "n_in_domain"), ratio(m200, "tool_hit1", "n_in_domain")),
        (f"Expected tool among returned tools (Hit@{DEFAULT_TOP_K})", ratio(m73, "tool_hitk", "n_in_domain"), ratio(m200, "tool_hitk", "n_in_domain")),
        ("Raw Hit@1 (no thresholds)", ratio(m73, "raw_hit1", "n_in_domain"), ratio(m200, "raw_hit1", "n_in_domain")),
        ("False positives on general questions", ratio(m73, "false_positive", "n_direct"), ratio(m200, "false_positive", "n_direct")),
        ("Whole catalog, tokens", f"{m73['catalog_tokens']:,.0f}", f"{m200['catalog_tokens']:,.0f}"),
        ("Routed shortlist, tokens (mean)", f"{m73['shortlist_tokens_mean']:,.0f}", f"{m200['shortlist_tokens_mean']:,.0f}"),
        ("`route()` latency p50", f"{m73['latency_ms']['p50']:.0f} ms", f"{m200['latency_ms']['p50']:.0f} ms"),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(ROOT / "eval" / "eval_queries.json"))
    parser.add_argument("--sweep", action="store_true", help="sweep THRESHOLD_TOOL")
    parser.add_argument("--compare-core", action="store_true", help="also run the core queries on the 73-tool catalog")
    parser.add_argument("-v", "--verbose", action="store_true", help="print the errors")
    args = parser.parse_args()

    queries = json.loads(Path(args.data).read_text(encoding="utf-8"))["queries"]

    store.load()
    embedding.embed("model loading")  # excluded from the indexing time
    t0 = time.perf_counter()
    reindex_all(force=True)
    index_seconds = time.perf_counter() - t0

    metrics, rows, cache = evaluate(queries, repository, store, args.verbose)
    sweep_rows = sweep(cache) if args.sweep else None
    comparison = None
    if args.compare_core:
        core_metrics, _, _ = evaluate([q for q in queries if q.get("set", "core") == "core"], repository, store, verbose=False)
        comparison = compare_core(queries, core_metrics)

    report = render(metrics, repository, index_seconds, sweep_rows, comparison)
    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "metrics.md").write_text(report, encoding="utf-8")
    (out_dir / "eval_details.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report)
    print(f"Report written to {out_dir / 'metrics.md'} (per-query details: eval_details.json)")


if __name__ == "__main__":
    main()
