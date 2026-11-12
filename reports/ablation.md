# Ablation: routing improvements (2026-11-12)

- Embedding model `paraphrase-multilingual-MiniLM-L12-v2`, thresholds MCP 0.2 / tool 0.28 / tool in a named server 0.2, keyword weight 0.15
- 147 labeled queries, 200-tool catalog unless stated

## Correct best server, by query set

| Configuration | All action requests | core | extended | **fresh (held out)** | core on 73 tools |
|---|---|---|---|---|---|
| Baseline (semantic only) | 76.6% (85/111) | 68.8% (33/48) | 90.9% (40/44) | 63.2% (12/19) | 83.3% (40/48) |
| 3: server name + domain in tool text | 73.9% (82/111) | 68.8% (33/48) | 81.8% (36/44) | 68.4% (13/19) | 75.0% (36/48) |
| 3 (light): server name only | 77.5% (86/111) | 68.8% (33/48) | 90.9% (40/44) | 68.4% (13/19) | 81.2% (39/48) |
| 1a: explicit mentions | 85.6% (95/111) | 83.3% (40/48) | 90.9% (40/44) | 78.9% (15/19) | 85.4% (41/48) |
| 1b: keyword search | 84.7% (94/111) | 77.1% (37/48) | 93.2% (41/44) | 84.2% (16/19) | 85.4% (41/48) |
| **1: mentions + keywords (default)** | 89.2% (99/111) | 85.4% (41/48) | 93.2% (41/44) | 89.5% (17/19) | 85.4% (41/48) |
| 1 + 3 (light) | 88.3% (98/111) | 79.2% (38/48) | 97.7% (43/44) | 89.5% (17/19) | 85.4% (41/48) |
| 1 + 3 (name + domain) | 86.5% (96/111) | 83.3% (40/48) | 93.2% (41/44) | 78.9% (15/19) | 87.5% (42/48) |

## Other metrics (all queries, 200 tools)

| Configuration | Right tool in shortlist (Hit@8) | Correct status | Right connector suggested | False positives | `route()` p50 |
|---|---|---|---|---|---|
| Baseline (semantic only) | 81.1% (90/111) | 91.8% (135/147) | 86.7% (13/15) | 14.3% (3/21) | 43 ms |
| 3: server name + domain in tool text | 69.4% (77/111) | 85.0% (125/147) | 86.7% (13/15) | 19.0% (4/21) | 42 ms |
| 3 (light): server name only | 79.3% (88/111) | 89.8% (132/147) | 80.0% (12/15) | 14.3% (3/21) | 43 ms |
| 1a: explicit mentions | 86.5% (96/111) | 93.2% (137/147) | 93.3% (14/15) | 14.3% (3/21) | 42 ms |
| 1b: keyword search | 85.6% (95/111) | 92.5% (136/147) | 86.7% (13/15) | 14.3% (3/21) | 42 ms |
| **1: mentions + keywords (default)** | 89.2% (99/111) | 93.9% (138/147) | 93.3% (14/15) | 14.3% (3/21) | 43 ms |
| 1 + 3 (light) | 90.1% (100/111) | 93.9% (138/147) | 93.3% (14/15) | 14.3% (3/21) | 43 ms |
| 1 + 3 (name + domain) | 87.4% (97/111) | 91.8% (135/147) | 86.7% (13/15) | 19.0% (4/21) | 42 ms |

## Changes between the baseline and the default configuration: 14 fixed, 0 broken

| | Query | Set | Expected | Got |
|---|---|---|---|---|
| fixed | find where the parse_date function is used in the code | core | github | github |
| fixed | what was discussed in the #support channel today? | core | slack | slack |
| fixed | add Marie to the #design channel | core | slack | slack |
| fixed | add a row to my Notion reading list for the book Dune | core | notion | notion |
| fixed | move ticket PROJ-12 to done | core | jira | jira |
| fixed | comment on ticket PROJ-7: blocked waiting for the client | core | jira | jira |
| fixed | create an Invoices 2026 folder in my Drive | core | google_drive | google_drive |
| fixed | find the client presentation in the Drive | core | google_drive | google_drive |
| fixed | log a call with Sarah: she wants a demo next week | extended | hubspot | hubspot |
| fixed | what are my biggest open deals in HubSpot? | fresh | hubspot | hubspot |
| fixed | send a Zendesk reply telling Mia her replacement has shipped | fresh | zendesk | zendesk |
| fixed | how much revenue did the shop make yesterday? | fresh | shopify | shopify |
| fixed | open the Q4 budget sheet and read the totals row | fresh | google_sheets | google_sheets |
| fixed | save these meeting notes in Notion | fresh | notion | notion |
