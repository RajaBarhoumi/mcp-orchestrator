"""Measure each routing improvement on its own and combined (ablation study).

    python scripts/ablation.py

Configurations, all on the same 147 labeled queries and the 200-tool catalog:

- baseline: semantic similarity only (the router before the improvements);
- server context (item 3): server name (and optionally its domain) in front of every tool text;
- explicit mentions (item 1a): a server named in the message restricts routing to it;
- keyword search (item 1b): BM25 boost added to the semantic score;
- combinations; the default configuration (mentions + keywords) is marked.

The "fresh" queries were written before the improvements and never used to tune them:
they show whether the gains generalize. The fixed / broken list compares the baseline with
the default configuration. Report: reports/ablation.md.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import embedding  # noqa: E402
from app.config import settings  # noqa: E402
from app.indexer import reindex_all  # noqa: E402
from app.repository import MockRepository, repository  # noqa: E402
from app.store import VectorStore  # noqa: E402
from scripts.build_mock_data import build  # noqa: E402
from scripts.evaluate import evaluate, pct  # noqa: E402

def config(context: str, mentions: bool, keywords: bool) -> dict:
    """context: "none" | "name" (server name only) | "domain" (server name + domain description)."""
    return {
        "SERVER_CONTEXT_IN_TOOL_TEXT": context != "none",
        "SERVER_CONTEXT_INCLUDE_DOMAIN": context == "domain",
        "EXPLICIT_MENTION_ENABLED": mentions,
        "LEXICAL_WEIGHT": 0.15 if keywords else 0.0,
    }


CONFIGS = [
    ("Baseline (semantic only)", config("none", False, False)),
    ("3: server name + domain in tool text", config("domain", False, False)),
    ("3 (light): server name only", config("name", False, False)),
    ("1a: explicit mentions", config("none", True, False)),
    ("1b: keyword search", config("none", False, True)),
    ("**1: mentions + keywords (default)**", config("none", True, True)),
    ("1 + 3 (light)", config("name", True, True)),
    ("1 + 3 (name + domain)", config("domain", True, True)),
]


def best_mcp_rate(rows: list[dict], query_set: str | None = None) -> str:
    selected = [r for r in rows if r["category"] == "in_domain" and (query_set is None or r["set"] == query_set)]
    return pct(sum(r["best_mcp"] in r["expected_mcp"] for r in selected), len(selected))


def main() -> None:
    queries = json.loads((ROOT / "eval" / "eval_queries.json").read_text(encoding="utf-8"))["queries"]
    core = [q for q in queries if q["set"] == "core"]

    # The 73-tool catalog, to see whether the improvements close the catalog-size gap.
    tmp = ROOT / "data" / "ablation"
    tmp.mkdir(parents=True, exist_ok=True)
    core_path = tmp / "mock_data_core.json"
    core_path.write_text(json.dumps(build(core_only=True), ensure_ascii=False), encoding="utf-8")
    repo73 = MockRepository(core_path)

    embedding.embed("model loading")
    default_settings = {key: getattr(settings, key) for key in CONFIGS[0][1]}
    results = []
    for name, overrides in CONFIGS:
        for key, value in overrides.items():
            setattr(settings, key, value)
        variant = "plain" if not settings.SERVER_CONTEXT_IN_TOOL_TEXT else ("domain" if settings.SERVER_CONTEXT_INCLUDE_DOMAIN else "name")
        vs200, vs73 = VectorStore(tmp / f"index200_{variant}"), VectorStore(tmp / f"index73_{variant}")
        vs200.load()
        vs73.load()
        reindex_all(repo=repository, vector_store=vs200)
        reindex_all(repo=repo73, vector_store=vs73)

        metrics, rows, _ = evaluate(queries, repository, vs200, verbose=False)
        metrics73, rows73, _ = evaluate(core, repo73, vs73, verbose=False)
        nc = [r for r in rows if r["category"] == "not_connected"]
        results.append(
            {
                "name": name,
                "all": best_mcp_rate(rows),
                "core": best_mcp_rate(rows, "core"),
                "extended": best_mcp_rate(rows, "extended"),
                "fresh": best_mcp_rate(rows, "fresh"),
                "core73": best_mcp_rate(rows73),
                "hit8": pct(metrics["tool_hitk"], metrics["n_in_domain"]),
                "status": pct(metrics["status_accuracy"], metrics["n_queries"]),
                "suggest": pct(sum(bool(r["suggested"]) and r["suggested"][0] in r["expected_mcp"] for r in nc), len(nc)),
                "fp": pct(metrics["false_positive"], metrics["n_direct"]),
                "p50": f"{metrics['latency_ms']['p50']:.0f} ms",
                "rows": rows,
            }
        )
        print(f"{name}: best MCP {results[-1]['all']} | fresh {results[-1]['fresh']} | FP {results[-1]['fp']}")

    lines = [
        f"# Ablation: routing improvements ({date.today().isoformat()})",
        "",
        f"- Embedding model `{embedding.get_active_model_name()}`, thresholds MCP {settings.THRESHOLD_MCP} / tool "
        f"{settings.THRESHOLD_TOOL} / tool in a named server {settings.THRESHOLD_TOOL_MENTIONED}, keyword weight 0.15",
        f"- {len(queries)} labeled queries, 200-tool catalog unless stated",
        "",
        "## Correct best server, by query set",
        "",
        "| Configuration | All action requests | core | extended | **fresh (held out)** | core on 73 tools |",
        "|---|---|---|---|---|---|",
    ]
    lines += [f"| {r['name']} | {r['all']} | {r['core']} | {r['extended']} | {r['fresh']} | {r['core73']} |" for r in results]
    lines += [
        "",
        "## Other metrics (all queries, 200 tools)",
        "",
        "| Configuration | Right tool in shortlist (Hit@8) | Correct status | Right connector suggested | False positives | `route()` p50 |",
        "|---|---|---|---|---|---|",
    ]
    lines += [f"| {r['name']} | {r['hit8']} | {r['status']} | {r['suggest']} | {r['fp']} | {r['p50']} |" for r in results]

    # Which questions changed between the baseline and the final configuration.
    base = {r["query"] + str(r["user_id"]): r for r in results[0]["rows"]}
    fixed, broken = [], []
    default = next(r for r in results if "(default)" in r["name"])
    for r in default["rows"]:
        if r["category"] != "in_domain":
            continue
        before = base[r["query"] + str(r["user_id"])]["best_mcp"] in r["expected_mcp"]
        after = r["best_mcp"] in r["expected_mcp"]
        if after and not before:
            fixed.append(r)
        elif before and not after:
            broken.append(r)
    lines += ["", f"## Changes between the baseline and the default configuration: {len(fixed)} fixed, {len(broken)} broken", ""]
    lines += ["| | Query | Set | Expected | Got |", "|---|---|---|---|---|"]
    lines += [f"| fixed | {r['query']} | {r['set']} | {', '.join(r['expected_mcp'])} | {r['best_mcp']} |" for r in fixed]
    lines += [f"| **broken** | {r['query']} | {r['set']} | {', '.join(r['expected_mcp'])} | {r['best_mcp']} |" for r in broken]

    report = "\n".join(lines) + "\n"
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "ablation.md").write_text(report, encoding="utf-8")
    print("\n" + report)


if __name__ == "__main__":
    main()
