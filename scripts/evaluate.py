"""Evaluate the orchestrator on the labeled set eval/eval_queries.json.

    python scripts/evaluate.py            # metrics + report in reports/
    python scripts/evaluate.py --sweep    # + threshold sweep (calibration)
    python scripts/evaluate.py -v         # + details of every error

The evaluated routing is EXACTLY the one used by the API (`router_service.route`),
with the thresholds of the current configuration (.env).
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

from app import embedding  # noqa: E402
from app.config import settings  # noqa: E402
from app.indexer import reindex_all  # noqa: E402
from app.repository import repository  # noqa: E402
from app.router_service import DEFAULT_TOP_K, decide, is_knowledge_query, route  # noqa: E402
from app.store import store  # noqa: E402


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}% ({n}/{d})" if d else "n/a"


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(p / 100 * (len(ordered) - 1))))
    return ordered[idx]


def raw_rank(qvec, expected_tools: list[str]) -> int | None:
    """1-based rank of the first expected tool among ALL tools, without thresholds:
    measures the raw embedding quality, independently of the thresholds."""
    scored = []
    for key, _ in store.search_centroids(qvec):
        scored.extend(store.search_tools(qvec, key, k=1000))
    scored.sort(key=lambda t: t["score"], reverse=True)
    for i, tool in enumerate(scored, start=1):
        if tool["namespaced_name"] in expected_tools:
            return i
    return None


def evaluate(queries: list[dict], verbose: bool) -> tuple[dict, list[dict], list[dict]]:
    rows, cache = [], []
    latencies = []

    # Warm-up (first call loads the model, excluded from latencies).
    route("warm-up", [])

    for q in queries:
        allowed = repository.get_allowed_mcps(q["user_id"])
        t0 = time.perf_counter()
        result = route(q["query"], allowed)
        latencies.append((time.perf_counter() - t0) * 1000)

        qvec = embedding.embed(q["query"])
        centroid_scores = store.search_centroids(qvec)
        hits = {k: store.search_tools(qvec, k, k=DEFAULT_TOP_K) for k, _ in centroid_scores}
        cache.append({"q": q, "allowed": set(allowed), "centroids": centroid_scores, "hits": hits})

        names = [t["namespaced_name"] for t in result["tools"]]
        expected_tools = q.get("expected_tools", [])
        tool_rank = next((i for i, n in enumerate(names, 1) if n in expected_tools), None)
        rows.append(
            {
                **q,
                "status": result["status"],
                "best_mcp": result["best_mcp"],
                "matched": [m["mcp"] for m in result["matched_mcps"]],
                "suggested": [m["mcp"] for m in result["suggested_mcps"]],
                "tools": names,
                "tool_rank": tool_rank,
                "raw_rank": raw_rank(qvec, expected_tools) if expected_tools else None,
            }
        )

    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)

    ind = by_cat["in_domain"]
    nc = by_cat["not_connected"]
    da = by_cat["knowledge"] + by_cat["out_of_domain"]

    m = {
        "n_queries": len(rows),
        "status_accuracy": sum(r["status"] == r["expected_status"] for r in rows),
        "status_by_category": {
            cat: (sum(r["status"] == r["expected_status"] for r in rs), len(rs)) for cat, rs in by_cat.items()
        },
        # Routing (in-domain requests)
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
        # Connection suggestions
        "suggest_correct": sum(bool(r["suggested"]) and r["suggested"][0] in r["expected_mcp"] for r in nc),
        "n_not_connected": len(nc),
        # False positives: tools proposed when none was expected
        "false_positive": sum(r["status"] != "direct_answer" for r in da),
        "n_direct": len(da),
        # route() latency (query embedding + FAISS + decision), warm model
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
                    f"- [{r['category']}] {r['query']}\n    expected {r['expected_status']} {r.get('expected_mcp', '')}"
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


def render(m: dict, index_seconds: float, sweep_rows: list[dict] | None) -> str:
    lat = m["latency_ms"]
    lines = [
        f"# Orchestrator metrics ({date.today().isoformat()})",
        "",
        f"- Embedding model: `{embedding.get_active_model_name()}` ({settings.EMBEDDING_PROVIDER})",
        f"- Catalog: {len(repository.list_servers())} MCP servers, {len(repository.list_tools())} tools",
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(ROOT / "eval" / "eval_queries.json"))
    parser.add_argument("--sweep", action="store_true", help="sweep THRESHOLD_TOOL")
    parser.add_argument("-v", "--verbose", action="store_true", help="print the errors")
    args = parser.parse_args()

    queries = json.loads(Path(args.data).read_text(encoding="utf-8"))["queries"]

    store.load()
    embedding.embed("model loading")  # excluded from the indexing time
    t0 = time.perf_counter()
    reindex_all(force=True)
    index_seconds = time.perf_counter() - t0

    metrics, rows, cache = evaluate(queries, args.verbose)
    sweep_rows = sweep(cache) if args.sweep else None

    report = render(metrics, index_seconds, sweep_rows)
    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "metrics.md").write_text(report, encoding="utf-8")
    (out_dir / "eval_details.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report)
    print(f"Report written to {out_dir / 'metrics.md'} (per-query details: eval_details.json)")


if __name__ == "__main__":
    main()
