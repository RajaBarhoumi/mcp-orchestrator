# Orchestrator metrics (2026-11-12)

- Embedding model: `paraphrase-multilingual-MiniLM-L12-v2` (local)
- Catalog: 22 MCP servers, 200 tools
- Thresholds: MCP 0.2 / tool 0.28 / suggestion 0.4
- Evaluation set: 147 labeled queries (eval/eval_queries.json)

## Overall decision

| Metric | Value |
|---|---|
| Status accuracy (all queries) | 93.9% (138/147) |
| Status accuracy, `in_domain` | 96.4% (107/111) |
| Status accuracy, `knowledge` | 87.5% (7/8) |
| Status accuracy, `not_connected` | 86.7% (13/15) |
| Status accuracy, `out_of_domain` | 84.6% (11/13) |

## MCP and tool selection (111 in-domain queries, user connected to everything)

| Metric | Value |
|---|---|
| **Correct best MCP** (`best_mcp`) | 89.2% (99/111) |
| Expected MCP in `matched_mcps` | 97.3% (108/111) |
| Expected tool ranked first (Hit@1) | 65.8% (73/111) |
| Expected tool in the top 3 (Hit@3) | 84.7% (94/111) |
| Expected tool among returned tools (Hit@8) | 89.2% (99/111) |
| MRR of returned tools | 0.751 |
| Tools returned per query (mean) | 6.7 |
| MCP servers kept per query (mean) | 2.7 |

Raw embedding quality (ranking of all tools, no thresholds):

| Metric | Value |
|---|---|
| Raw Hit@1 | 55.9% (62/111) |
| Raw Hit@3 | 73.9% (82/111) |
| Raw MRR | 0.677 |

## Context sent to the model (tool definitions, tiktoken o200k_base)

| Metric | Value |
|---|---|
| Whole catalog of the user (no routing) | 14,907 tokens |
| Routed shortlist, mean / p95 | 517 / 635 tokens |
| Reduction | 96.5% |

## Missing connectors and false positives

| Metric | Value |
|---|---|
| Right connector suggested when it is not connected | 93.3% (14/15) |
| False positives (tools proposed for a general question) | 14.3% (3/21) |

## Performance

| Metric | Value |
|---|---|
| Mean `route()` latency | 43.0 ms |
| p50 / p95 / max latency | 42.2 / 50.1 / 74.0 ms |
| Full indexing (`force=True`) | 8.62 s |

## Catalog size: same core queries, 73 vs 200 tools

The core queries were written for the original 9-server catalog; here they run unchanged
against both catalogs (answers from the new servers are accepted when they are also correct).

| Metric | 73 tools | 200 tools |
|---|---|---|
| Status accuracy (core queries) | 92.8% (64/69) | 97.1% (67/69) |
| **Correct best MCP** | 85.4% (41/48) | 85.4% (41/48) |
| Expected tool ranked first (Hit@1) | 58.3% (28/48) | 64.6% (31/48) |
| Expected tool among returned tools (Hit@8) | 91.7% (44/48) | 89.6% (43/48) |
| Raw Hit@1 (no thresholds) | 60.4% (29/48) | 54.2% (26/48) |
| False positives on general questions | 0.0% (0/13) | 0.0% (0/13) |
| Whole catalog, tokens | 5,488 | 14,907 |
| Routed shortlist, tokens (mean) | 467 | 514 |
| `route()` latency p50 | 44 ms | 43 ms |

## THRESHOLD_TOOL sweep

| Tool threshold | Status accuracy | Correct best MCP | False positive rate |
|---|---|---|---|
| 0.20 | 88.4% | 91.0% | 61.9% |
| 0.25 | 91.2% | 91.0% | 42.9% |
| 0.28 | 93.9% | 89.2% | 14.3% |
| 0.30 | 93.9% | 89.2% | 14.3% |
| 0.35 | 92.5% | 88.3% | 14.3% |
| 0.40 | 91.2% | 86.5% | 14.3% |
| 0.45 | 87.1% | 82.9% | 14.3% |
| 0.50 | 82.3% | 77.5% | 14.3% |
