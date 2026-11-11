# Orchestrator metrics (2026-11-11)

- Embedding model: `paraphrase-multilingual-MiniLM-L12-v2` (local)
- Catalog: 9 MCP servers, 73 tools
- Thresholds: MCP 0.2 / tool 0.28 / suggestion 0.4
- Evaluation set: 69 labeled queries (eval/eval_queries.json)

## Overall decision

| Metric | Value |
|---|---|
| Status accuracy (all queries) | 92.8% (64/69) |
| Status accuracy, `in_domain` | 95.8% (46/48) |
| Status accuracy, `knowledge` | 100.0% (5/5) |
| Status accuracy, `not_connected` | 62.5% (5/8) |
| Status accuracy, `out_of_domain` | 100.0% (8/8) |

## MCP and tool selection (48 in-domain queries, user connected to everything)

| Metric | Value |
|---|---|
| **Correct best MCP** (`best_mcp`) | 83.3% (40/48) |
| Expected MCP in `matched_mcps` | 93.8% (45/48) |
| Expected tool ranked first (Hit@1) | 58.3% (28/48) |
| Expected tool in the top 3 (Hit@3) | 75.0% (36/48) |
| Expected tool among returned tools (Hit@8) | 87.5% (42/48) |
| MRR of returned tools | 0.688 |
| Tools returned per query (mean) | 5.1 |
| MCP servers kept per query (mean) | 2.7 |

Raw embedding quality (ranking of all tools, no thresholds):

| Metric | Value |
|---|---|
| Raw Hit@1 | 60.4% (29/48) |
| Raw Hit@3 | 79.2% (38/48) |
| Raw MRR | 0.726 |

## Missing connectors and false positives

| Metric | Value |
|---|---|
| Right connector suggested when it is not connected | 87.5% (7/8) |
| False positives (tools proposed for a general question) | 0.0% (0/13) |

## Performance

| Metric | Value |
|---|---|
| Mean `route()` latency | 81.6 ms |
| p50 / p95 / max latency | 78.9 / 113.7 / 135.8 ms |
| Full indexing (`force=True`) | 4.69 s |

## THRESHOLD_TOOL sweep

| Tool threshold | Status accuracy | Correct best MCP | False positive rate |
|---|---|---|---|
| 0.20 | 81.2% | 85.4% | 53.8% |
| 0.25 | 88.4% | 85.4% | 23.1% |
| 0.28 | 92.8% | 83.3% | 0.0% |
| 0.30 | 91.3% | 81.2% | 0.0% |
| 0.35 | 91.3% | 81.2% | 0.0% |
| 0.40 | 81.2% | 72.9% | 0.0% |
| 0.45 | 72.5% | 62.5% | 0.0% |
| 0.50 | 59.4% | 45.8% | 0.0% |
