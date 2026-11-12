# Orchestrator metrics (2026-11-11)

- Embedding model: `paraphrase-multilingual-MiniLM-L12-v2` (local)
- Catalog: 22 MCP servers, 200 tools
- Thresholds: MCP 0.2 / tool 0.28 / suggestion 0.4
- Evaluation set: 122 labeled queries (eval/eval_queries.json)

## Overall decision

| Metric | Value |
|---|---|
| Status accuracy (all queries) | 94.3% (115/122) |
| Status accuracy, `in_domain` | 96.7% (89/92) |
| Status accuracy, `knowledge` | 100.0% (7/7) |
| Status accuracy, `not_connected` | 66.7% (8/12) |
| Status accuracy, `out_of_domain` | 100.0% (11/11) |

## MCP and tool selection (92 in-domain queries, user connected to everything)

| Metric | Value |
|---|---|
| **Correct best MCP** (`best_mcp`) | 79.3% (73/92) |
| Expected MCP in `matched_mcps` | 93.5% (86/92) |
| Expected tool ranked first (Hit@1) | 60.9% (56/92) |
| Expected tool in the top 3 (Hit@3) | 76.1% (70/92) |
| Expected tool among returned tools (Hit@8) | 81.5% (75/92) |
| MRR of returned tools | 0.686 |
| Tools returned per query (mean) | 6.6 |
| MCP servers kept per query (mean) | 3.6 |

Raw embedding quality (ranking of all tools, no thresholds):

| Metric | Value |
|---|---|
| Raw Hit@1 | 62.0% (57/92) |
| Raw Hit@3 | 78.3% (72/92) |
| Raw MRR | 0.721 |

## Context sent to the model (tool definitions, tiktoken o200k_base)

| Metric | Value |
|---|---|
| Whole catalog of the user (no routing) | 14,907 tokens |
| Routed shortlist, mean / p95 | 503 / 637 tokens |
| Reduction | 96.6% |

## Missing connectors and false positives

| Metric | Value |
|---|---|
| Right connector suggested when it is not connected | 91.7% (11/12) |
| False positives (tools proposed for a general question) | 0.0% (0/18) |

## Performance

| Metric | Value |
|---|---|
| Mean `route()` latency | 49.3 ms |
| p50 / p95 / max latency | 47.4 / 57.7 / 161.7 ms |
| Full indexing (`force=True`) | 10.37 s |

## Catalog size: same core queries, 73 vs 200 tools

The core queries were written for the original 9-server catalog; here they run unchanged
against both catalogs (answers from the new servers are accepted when they are also correct).

| Metric | 73 tools | 200 tools |
|---|---|---|
| Status accuracy (core queries) | 92.8% (64/69) | 92.8% (64/69) |
| **Correct best MCP** | 83.3% (40/48) | 68.8% (33/48) |
| Expected tool ranked first (Hit@1) | 58.3% (28/48) | 52.1% (25/48) |
| Expected tool among returned tools (Hit@8) | 87.5% (42/48) | 77.1% (37/48) |
| Raw Hit@1 (no thresholds) | 60.4% (29/48) | 54.2% (26/48) |
| False positives on general questions | 0.0% (0/13) | 0.0% (0/13) |
| Whole catalog, tokens | 5,488 | 14,907 |
| Routed shortlist, tokens (mean) | 400 | 495 |
| `route()` latency p50 | 45 ms | 45 ms |

## THRESHOLD_TOOL sweep

| Tool threshold | Status accuracy | Correct best MCP | False positive rate |
|---|---|---|---|
| 0.20 | 88.5% | 80.4% | 55.6% |
| 0.25 | 91.8% | 80.4% | 27.8% |
| 0.28 | 94.3% | 79.3% | 0.0% |
| 0.30 | 93.4% | 78.3% | 0.0% |
| 0.35 | 91.8% | 77.2% | 0.0% |
| 0.40 | 86.1% | 72.8% | 0.0% |
| 0.45 | 74.6% | 63.0% | 0.0% |
| 0.50 | 66.4% | 56.5% | 0.0% |
