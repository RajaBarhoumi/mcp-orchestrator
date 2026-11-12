# MCP Orchestrator

A FastAPI service that takes a user message and picks **the best MCP server**, along with its
most relevant tools, to handle it. It does not call an LLM and does not execute any tool: it
**decides** what to use, based on semantic vector search.

Why: an agent that sees every tool reads every description on every request. With **200 tools**,
that is **14,907 tokens** of tool definitions per request, and 200 ways to pick something that is
almost right. The orchestrator puts a routing step in front of the model, which then only sees a
shortlist of about **500 tokens** (see [Metrics](#metrics)).

There is **no database**: MCP servers, their tools and user connections are loaded from
[app/data/mock_data.json](app/data/mock_data.json).

## Table of contents

- [How it works](#how-it-works)
- [Mock data](#mock-data)
- [Installation](#installation)
- [Testing with real requests](#testing-with-real-requests)
- [API endpoints](#api-endpoints)
- [Metrics](#metrics)
- [Configuration](#configuration)
- [Project structure](#project-structure)

## How it works

**Indexing.** Each tool is turned into a text (readable name, description, parameter names),
then embedded into a vector. The service builds one FAISS index per MCP server, plus a
**centroid** per server (the mean of its tool vectors).

**Routing.** Each message is routed in two levels:

1. **MCP level.** The message is compared with every server centroid. A server is kept if its
   centroid score exceeds `THRESHOLD_MCP` (0.20), **or** if one of its tools exceeds
   `THRESHOLD_TOOL` (0.28). At most 4 servers are kept.
2. **Tool level.** Among the kept servers that the user is **connected** to, tools scoring above
   `THRESHOLD_TOOL` are returned. Each server gets a quota of tools, then remaining slots go to
   the best scores overall.

The matching works on meaning, not keywords: "who did I not call back this week?" is routed to the
CRM although the word "CRM" never appears.

Every response has one of these statuses:

| `status` | Meaning |
|---|---|
| `tools_found` | Tools are proposed. `best_mcp` is the server of the top-ranked tool. |
| `mcp_not_connected` | The right server exists but the user is not connected to it. `suggested_mcps` says which one to connect. One of its tools must exceed `THRESHOLD_SUGGEST` (0.40). |
| `mcp_out_of_scope` | The relevant server is connected but excluded from the requested scope. |
| `direct_answer` | No tool fits, or the message is a knowledge question ("what is…", "explain…"): the LLM should answer on its own. |

A suggestion can also come with a `tools_found` response, as a bonus.

**Startup.** Indexes are reloaded from `./data/orchestrator`. Only servers whose catalog changed
(different hash) are re-embedded.

## Mock data

All data is **fictitious**: generic public MCP servers, no real data. Regenerate the file with
`python scripts/build_mock_data.py`, or edit it by hand.

**22 MCP servers, 200 tools.** The second wave of servers overlaps with the first one on purpose
(tasks in Jira, Asana and Trello; invoices in Stripe and QuickBooks; files in Drive and Dropbox;
meetings in Calendar and Zoom; tickets in Jira and Zendesk): that is what makes routing hard as a
catalog grows.

| Server | Tools | Server | Tools |
|---|---|---|---|
| `github` | 11 | `hubspot` (CRM) | 14 |
| `slack` | 9 | `zendesk` (support) | 12 |
| `gmail` | 9 | `shopify` (store) | 14 |
| `google_calendar` | 7 | `quickbooks` (accounting) | 12 |
| `notion` | 9 | `asana` | 10 |
| `stripe` | 11 | `google_sheets` | 10 |
| `jira` | 8 | `zoom` | 8 |
| `openweather` | 3 | `mailchimp` | 10 |
| `google_drive` | 6 | `twilio` (SMS, calls) | 6 |
| | | `dropbox` | 8 |
| | | `docusign` | 7 |
| | | `google_maps` | 6 |
| | | `trello` | 10 |

`python scripts/build_mock_data.py --core-only --out <file>` rebuilds the original 9-server
catalog (73 tools), used to measure the effect of the catalog size.

**Users:**

| `user_id` | Profile | Allowed servers |
|---|---|---|
| 1 | Developer | github, jira, slack, trello |
| 2 | Sales rep | stripe, gmail, google_calendar, hubspot, quickbooks, docusign, zoom |
| 3 | Admin | all 22 |
| 4 | New user | none |
| 5 | Writer | notion, google_sheets (google_drive in `error` and openweather `disconnected` are refused) |
| 6 | Support lead | zendesk, shopify, twilio, mailchimp |

Only the `connected` status grants access to a server. `error` and `disconnected` count as no
connection.

File structure:

```json
{
  "mcp_servers": [{"key": "github", "label": "GitHub", "description": "...", "naming_convention": "explicit_typed", "is_native": false}],
  "mcp_tools": [{"mcp_key": "github", "tool_name": "create_issue", "description": "...", "input_schema": {"type": "object", "properties": {}}, "is_destructive": true}],
  "users": [{"id": 1, "name": "..."}],
  "mcp_user_connections": [{"user_id": 1, "mcp_key": "github", "status": "connected"}]
}
```

A server with `"is_native": true` is allowed for every user. The file is reloaded on the fly.
After editing tools, call `POST /orchestrator/index/rebuild`.

## Installation

Requirements: Python 3.11 or later.

```bash
pip install -r requirements.txt
```

```bash
cp .env.example .env
```

```bash
uvicorn app.main:app --reload
```

On first launch, the `paraphrase-multilingual-MiniLM-L12-v2` model (about 470 MB) is downloaded
from Hugging Face, then the indexes are built (about 10 seconds for 200 tools on CPU).
Interactive Swagger docs are available at http://127.0.0.1:8000/docs.

## Testing with real requests

### 1. With `requests.http`

[requests.http](requests.http) holds ready-to-run requests covering every case, including the
example of the post ("who did I not call back this week?"), plus `explain` and re-indexing. Open
it in VS Code with the **REST Client** extension, or in a JetBrains IDE, and click "Send Request"
above each one.

### 2. With Swagger

Open http://127.0.0.1:8000/docs, then `POST /orchestrator/route` → "Try it out".

### 3. From the command line

curl, with a JSON body from the [examples/](examples) folder (`unpaid_invoices.json`,
`schedule_meeting.json`, `slack_not_connected.json`, `out_of_domain.json`):

```bash
curl -s -X POST http://127.0.0.1:8000/orchestrator/route -H "Content-Type: application/json" --data-binary @examples/unpaid_invoices.json
```

or inline:

```bash
curl -s -X POST http://127.0.0.1:8000/orchestrator/route -H "Content-Type: application/json" -d '{"query": "who did I not call back this week?", "user_id": 3}'
```

> On Windows (Git Bash, cmd), inline bodies containing non-ASCII characters (accents) are sent
> in the local code page and the API answers `There was an error parsing the body`. Use a
> UTF-8 JSON file with `--data-binary @file.json` in that case.

PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/orchestrator/route -ContentType "application/json; charset=utf-8" -Body '{"query": "who did I not call back this week?", "user_id": 3}' | ConvertTo-Json -Depth 6
```

Actual response for `examples/unpaid_invoices.json` (shortened: 3 of the 8 tools):

```json
{
  "status": "tools_found",
  "best_mcp": "stripe",
  "tools": [
    {"namespaced_name": "stripe__list_invoices", "mcp": "stripe", "tool_name": "list_invoices",
     "description": "List invoices, filtered by status (paid, unpaid, overdue).",
     "input_schema": {"type": "object", "properties": {"customer_id": {"type": "string"}, "status": {"type": "string"}}, "required": []},
     "requires_confirmation": false, "convention": "explicit_typed", "score": 0.723},
    {"namespaced_name": "quickbooks__record_payment", "score": 0.679, "...": "..."},
    {"namespaced_name": "quickbooks__list_invoices", "score": 0.673, "...": "..."}
  ],
  "matched_mcps": [{"mcp": "stripe", "score": 0.584}, {"mcp": "quickbooks", "score": 0.647},
                   {"mcp": "docusign", "score": 0.36}, {"mcp": "hubspot", "score": 0.269}],
  "suggested_mcps": [],
  "out_of_scope_mcps": []
}
```

`requires_confirmation: true` flags a tool that changes data (create, send, delete): the
calling application should ask for confirmation before running it.

Results observed on the running server (200 tools):

| Message | `user_id` | Result | Top tool (score) |
|---|---|---|---|
| list the unpaid invoices | 3 | `tools_found`, stripe | `stripe__list_invoices` (0.72), QuickBooks close behind |
| who did I not call back this week? | 3 | `tools_found`, hubspot | `list_overdue_follow_ups` (0.41) |
| who did I not call back this week? | 1 | `mcp_not_connected`, suggests hubspot | — |
| merge PR 42 in the frontend repo | 3 | `tools_found`, github | `merge_pull_request` (0.50) |
| what's the weather like in Lyon? | 3 | `tools_found`, openweather | `get_forecast` (0.29) |
| send a Slack message to the team about the meeting | 4 | `mcp_not_connected`, suggests slack | — |
| what is a pull request? | 3 | `direct_answer` | — |
| write me a poem about autumn | 3 | `direct_answer` | — |
| schedule a meeting with Sophie on Thursday at 2pm | 3 | `tools_found`, zoom (valid) | `zoom__update_meeting` (0.39): **wrong tool** |
| email paul@example.com to confirm the appointment | 3 | `tools_found`, zendesk | `zendesk__reply_to_ticket` (0.41): **wrong server** |
| share the report.pdf file from the Drive with Paul | 5 | `tools_found` + suggests google_drive | `google_sheets__share_spreadsheet`: **false lead** |

The last three rows are the kind of near-misses a bigger catalog produces: see the comparison
between 73 and 200 tools below.

The `/route` body accepts either `user_id` (allowed servers read from the mock data) or
`allowed_mcps` (explicit list), plus `top_k` (1 to 15, default 8).

### 4. Automated tests

```bash
python -m pytest -q
```

The tests use a fake embedding and do not load the model. They run in a few seconds.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/orchestrator/health` | Service status and number of indexed tools per server |
| GET | `/orchestrator/mcps` | Servers declared in the mock data |
| GET | `/orchestrator/users` | Fictitious users and their allowed servers |
| POST | `/orchestrator/route` | **Picks the best server and tools for a message** |
| POST | `/orchestrator/route/explain` | Every raw score, no thresholds (diagnostics) |
| POST | `/orchestrator/index/rebuild` | Re-indexes every server (`?force=true` recomputes everything) |
| POST | `/orchestrator/index/sync/{mcp_key}` | Re-indexes one server |
| DELETE | `/orchestrator/index/{mcp_key}` | Removes the index of one server |

## Metrics

Measured on November 11, 2026 with `python scripts/evaluate.py --sweep --compare-core`. Setup:
local model `paraphrase-multilingual-MiniLM-L12-v2`, default thresholds, CPU, 22 servers and 200
tools. The full report is written to [reports/metrics.md](reports/metrics.md) and per-query
details to `reports/eval_details.json`.

The evaluation set [eval/eval_queries.json](eval/eval_queries.json) holds **122 labeled
queries**, in English:

- 92 action requests (`in_domain`), including ambiguous ones where several servers are right
  ("create a task to call the supplier tomorrow": Asana, Trello, HubSpot or Jira);
- 12 requests for a server the user is not connected to (`not_connected`);
- 7 knowledge questions and 11 questions unrelated to any server.

69 of them (`core`) were written for the original 9-server catalog; 53 (`extended`) were added
with the 200-tool catalog.

### Server and tool selection (92 action requests, user connected to everything)

| Metric | Value |
|---|---|
| **Correct best server** (`best_mcp`) | **79.3%** (73/92) |
| Expected server among kept servers | 93.5% (86/92) |
| Right tool ranked first (Hit@1) | 60.9% (56/92) |
| Right tool in the top 3 (Hit@3) | 76.1% (70/92) |
| Right tool among returned tools (Hit@8) | 81.5% (75/92) |
| Tool MRR | 0.686 |
| Tools returned per query, on average | 6.6 |

### Decision

| Metric | Value |
|---|---|
| Correct status, all queries | 94.3% (115/122) |
| Correct status, action requests | 96.7% (89/92) |
| Correct status, knowledge and unrelated questions | 100% (18/18) |
| Right connector suggested when it is missing | 91.7% (11/12) |
| False positives: tools proposed for a general question | 0% (0/18) |

### Context sent to the model

Tokens of the tool definitions as the model would receive them (OpenAI function format, counted
with `tiktoken`, `o200k_base`), for the admin user who can use all 200 tools:

| | Tokens per request |
|---|---|
| Whole catalog, no routing | **14,907** |
| Routed shortlist, mean / p95 | **503** / 637 |
| Reduction | **96.6%** |

### Catalog size: the same queries on 73 and 200 tools

The 69 `core` queries run unchanged against the original catalog (9 servers, 73 tools) and the
full one (22 servers, 200 tools). Answers from the new servers are accepted when they are also
correct (unpaid invoices in QuickBooks, a meeting in Zoom).

| Metric | 73 tools | 200 tools |
|---|---|---|
| **Correct best server** | **83.3%** (40/48) | **68.8%** (33/48) |
| Right tool ranked first (Hit@1) | 58.3% | 52.1% |
| Right tool among returned tools (Hit@8) | 87.5% | 77.1% |
| Raw Hit@1, no thresholds | 60.4% | 54.2% |
| Correct status | 92.8% | 92.8% |
| False positives on general questions | 0% | 0% |
| Whole catalog, tokens | 5,488 | 14,907 |
| Routed shortlist, tokens (mean) | 400 | 495 |
| `route()` latency p50 | 45 ms | 45 ms |

**More tools hurt, even with routing.** Going from 73 to 200 tools, the right server is picked 14.5
points less often on the same questions. New servers that look alike pull the questions away:
"move ticket PROJ-12 to done" goes to Zendesk instead of Jira; "find the client presentation in
the Drive" goes to Dropbox. Without routing, the model would face the same 200 look-alike tools
with **30 times more context** to read on every request.

The routing cost does not grow with the catalog (45 ms p50 at both sizes), and the shortlist stays
around 500 tokens.

### Performance

| Metric | Value |
|---|---|
| `route()` latency (model loaded) | mean 49 ms, p50 47 ms, p95 58 ms |
| Full indexing of the 200 tools | 10.4 s |

### Choosing `THRESHOLD_TOOL`

| Threshold | Correct status | Correct best server | False positives |
|---|---|---|---|
| 0.20 | 88.5% | 80.4% | 55.6% |
| 0.25 | 91.8% | 80.4% | 27.8% |
| **0.28 (default)** | **94.3%** | **79.3%** | **0%** |
| 0.30 | 93.4% | 78.3% | 0% |
| 0.35 | 91.8% | 77.2% | 0% |
| 0.40 | 86.1% | 72.8% | 0% |

0.28 remains the best trade-off at 200 tools: lower thresholds pick the right server slightly
more often but propose tools for unrelated questions; higher thresholds miss real actions.

### How to read these numbers

- **Server selection is reliable, exact tool selection much less so.** When the expected tool is
  not first, it is usually a neighbor from the same server. The final tool is meant to be chosen
  by an LLM among the proposed ones, so Hit@8 (81.5%) matters more for it than Hit@1.
- **Typical errors.** Generic verbs and nouns shared by several servers ("ticket", "share",
  "cancel", "email") pull the question to the wrong server: "email paul@example.com to confirm the
  appointment" goes to Zendesk's reply tool, "cancel Friday's appointment" to Shopify's cancel
  order. Short messages with few keywords ("assign PROJ-45 to Karim") can fall below every
  threshold.
- **`not_connected` status at 66.7% while the suggestion is right 91.7% of the time.** When the
  user has other servers connected, one of their tools often passes the threshold, so the status
  becomes `tools_found`. The right suggestion is still returned in `suggested_mcps`.
- **Limits of the measurement.** 122 queries is small (about ±8 points of uncertainty on a
  percentage). The queries and the tool descriptions were written by the same author, which makes
  the results somewhat optimistic. For representative numbers, add real user messages to
  `eval/eval_queries.json` and re-run the script.

### Re-running the evaluation

```bash
python scripts/evaluate.py
```

```bash
python scripts/evaluate.py --sweep --compare-core -v
```

`--sweep` adds the threshold sweep, `--compare-core` adds the 73 vs 200 tools comparison and `-v`
prints every error (expected / got). The script evaluates exactly the `route()` function used by
the API, with the current configuration. To compare another model, change
`EMBEDDING_MODEL_NAME`, or set `EMBEDDING_PROVIDER=openai`, in `.env`, then run it again.

## Configuration

Environment variables or `.env` file (see [.env.example](.env.example)):

| Variable | Default | Purpose |
|---|---|---|
| `MOCK_DATA_PATH` | `app/data/mock_data.json` | Data file |
| `EMBEDDING_PROVIDER` | `local` | `local` (sentence-transformers) or `openai` |
| `EMBEDDING_MODEL_NAME` | `paraphrase-multilingual-MiniLM-L12-v2` | Local model |
| `OPENAI_API_KEY` / `OPENAI_EMBEDDING_MODEL` | — / `text-embedding-3-small` | When using `openai` |
| `ORCH_INDEX_DIR` | `./data/orchestrator` | FAISS index folder |
| `THRESHOLD_MCP` | 0.20 | Centroid threshold (level 1) |
| `THRESHOLD_TOOL` | 0.28 | Tool threshold (level 2) |
| `THRESHOLD_SUGGEST` | 0.40 | Threshold to suggest a non-connected server |
| `MAX_SUGGESTED_MCPS` | 1 | Maximum number of suggestions |
| `KNOWLEDGE_GUARD_ENABLED` | true | Knowledge questions → `direct_answer` |

Changing the model automatically invalidates the existing indexes: they are rebuilt on the next
startup. The knowledge-question detection matches English phrasing.

## Project structure

```
├── app/
│   ├── main.py            # FastAPI app, indexing at startup
│   ├── routes.py          # /orchestrator/* endpoints
│   ├── router_service.py  # routing decision: pure decide(), route(), explain()
│   ├── indexer.py         # incremental indexing (catalog hash)
│   ├── store.py           # FAISS indexes + centroids per server, disk persistence
│   ├── embedding.py       # local / OpenAI embeddings, L2-normalized
│   ├── repository.py      # mock data access
│   ├── schema_utils.py    # tool JSON Schema normalization
│   ├── schemas.py         # request models
│   ├── config.py          # settings
│   └── data/mock_data.json
├── eval/eval_queries.json # labeled evaluation set
├── examples/              # JSON request bodies for curl
├── reports/metrics.md     # latest evaluation report
├── scripts/
│   ├── build_mock_data.py # (re)generates the mock data, 200 or 73 tools
│   └── evaluate.py        # metrics, catalog-size comparison, context tokens
├── tests/                 # pytest suite (fake embedding)
└── requests.http          # ready-to-run test requests
```
