# MCP Orchestrator

A FastAPI service that takes a user message and picks **the best MCP server**, along with its
most relevant tools, to handle it. It does not call an LLM and does not execute any tool: it
**decides** what to use, based on semantic vector search.

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

**9 MCP servers, 73 tools:**

| Server | Tools |
|---|---|
| `github` | 11: repositories, issues, pull requests, branches, commits, code search |
| `slack` | 9: messages, channels, reactions, status, files |
| `gmail` | 9: sending, search, drafts, replies, labels, archiving |
| `google_calendar` | 7: events, free slots, invitations |
| `notion` | 9: pages, blocks, databases |
| `stripe` | 11: customers, invoices, payments, refunds, subscriptions |
| `jira` | 8: tickets, statuses, assignment, comments, sprints |
| `openweather` | 3: current weather, forecast, air quality |
| `google_drive` | 6: search, folders, sharing, upload |

**Users:**

| `user_id` | Profile | Allowed servers |
|---|---|---|
| 1 | Developer | github, jira, slack |
| 2 | Sales rep | stripe, gmail, google_calendar |
| 3 | Admin | all 9 |
| 4 | New user | none |
| 5 | Writer | notion (google_drive in `error` and openweather `disconnected` are refused) |

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
from Hugging Face, then the indexes are built (a few seconds). Interactive Swagger docs are
available at http://127.0.0.1:8000/docs.

## Testing with real requests

### 1. With `requests.http`

[requests.http](requests.http) holds 12 ready-to-run requests covering every case, plus
`explain` and re-indexing. Open it in VS Code with the **REST Client** extension, or in a
JetBrains IDE, and click "Send Request" above each one.

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
curl -s -X POST http://127.0.0.1:8000/orchestrator/route -H "Content-Type: application/json" -d '{"query": "list the unpaid invoices", "user_id": 3}'
```

> On Windows (Git Bash, cmd), inline bodies containing non-ASCII characters (accents) are sent
> in the local code page and the API answers `There was an error parsing the body`. Use a
> UTF-8 JSON file with `--data-binary @file.json` in that case.

PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/orchestrator/route -ContentType "application/json; charset=utf-8" -Body '{"query": "schedule a meeting with Sophie on Thursday at 2pm", "user_id": 3}' | ConvertTo-Json -Depth 6
```

Actual response for `examples/unpaid_invoices.json` (shortened: 3 of the 8 tools):

```json
{
  "status": "tools_found",
  "best_mcp": "stripe",
  "tools": [
    {"namespaced_name": "stripe__list_invoices", "mcp": "stripe", "tool_name": "list_invoices",
     "description": "List invoices, filtered by status (paid, unpaid, overdue).",
     "input_schema": {"type": "object", "properties": {"customer_id": {"type": "string"}, "status": {"type": "string"}}, "required": ["customer_id"]},
     "requires_confirmation": false, "convention": "explicit_typed", "score": 0.723},
    {"namespaced_name": "stripe__list_payments", "score": 0.574, "...": "..."},
    {"namespaced_name": "stripe__send_invoice", "score": 0.540, "...": "..."}
  ],
  "matched_mcps": [{"mcp": "stripe", "score": 0.584}, {"mcp": "github", "score": 0.256},
                   {"mcp": "google_calendar", "score": 0.228}, {"mcp": "gmail", "score": 0.25}],
  "suggested_mcps": [],
  "out_of_scope_mcps": []
}
```

`requires_confirmation: true` flags a tool that changes data (create, send, delete): the
calling application should ask for confirmation before running it.

Results observed on the running server:

| Message | `user_id` | Result | Top tool (score) |
|---|---|---|---|
| list the unpaid invoices | 3 | `tools_found`, stripe | `list_invoices` (0.72) |
| merge PR 42 in the frontend repo | 3 | `tools_found`, github | `merge_pull_request` (0.50) |
| schedule a meeting with Sophie on Thursday at 2pm | 3 | `tools_found`, google_calendar | `find_free_slots` (0.38), then `create_event` (0.32) |
| what's the weather like in Lyon? | 3 | `tools_found`, openweather | `get_forecast` (0.29) |
| send a Slack message to the team about the meeting | 4 | `mcp_not_connected`, suggests slack | — |
| share the report.pdf file from the Drive with Paul | 5 | `mcp_not_connected`, suggests google_drive | — |
| what is a pull request? | 3 | `direct_answer` | — |
| write me a poem about autumn | 3 | `direct_answer` | — |

The right server is picked every time, but the top-ranked tool is not always the exact one
(`find_free_slots` instead of `create_event`): see [Metrics](#metrics).

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

Measured on November 11, 2026 with `python scripts/evaluate.py --sweep`. Setup: local model
`paraphrase-multilingual-MiniLM-L12-v2`, default thresholds, CPU, 9 servers and 73 tools. The
full report is written to `reports/metrics.md` and per-query details to
`reports/eval_details.json`.

The evaluation set [eval/eval_queries.json](eval/eval_queries.json) holds **69 labeled
queries**, in English:

- 48 action requests (`in_domain`);
- 8 requests for a server the user is not connected to (`not_connected`);
- 5 knowledge questions (`knowledge`);
- 8 questions unrelated to any server (`out_of_domain`).

### Server selection (48 action requests, user connected to everything)

| Metric | Value |
|---|---|
| **Correct best server** (`best_mcp`) | **83.3%** (40/48) |
| Expected server among kept servers | 93.8% (45/48) |
| Right tool ranked first (Hit@1) | 58.3% (28/48) |
| Right tool in the top 3 (Hit@3) | 75.0% (36/48) |
| Right tool among returned tools (Hit@8) | 87.5% (42/48) |
| Tool MRR | 0.688 |
| Tools returned per query, on average | 5.1 |

### Decision

| Metric | Value |
|---|---|
| Correct status, all queries | 92.8% (64/69) |
| Correct status, action requests | 95.8% (46/48) |
| Correct status, knowledge questions | 100% (5/5) |
| Correct status, unrelated questions | 100% (8/8) |
| Right connector suggested when it is missing | 87.5% (7/8) |
| False positives: tools proposed for a general question | 0% (0/13) |

### Performance

| Metric | Value |
|---|---|
| `route()` latency (model loaded) | mean 82 ms, p50 79 ms, p95 114 ms |
| Full indexing of the 73 tools | 4.7 s |

### Choosing `THRESHOLD_TOOL`

| Threshold | Correct status | Correct best server | False positives |
|---|---|---|---|
| 0.20 | 81.2% | 85.4% | 53.8% |
| 0.25 | 88.4% | 85.4% | 23.1% |
| **0.28 (default)** | **92.8%** | **83.3%** | **0%** |
| 0.30 | 91.3% | 81.2% | 0% |
| 0.35 | 91.3% | 81.2% | 0% |
| 0.40 | 81.2% | 72.9% | 0% |

0.28 is the best trade-off on this set: lower thresholds pick the right server slightly more
often but propose tools for unrelated questions; higher thresholds miss real actions.

### How to read these numbers

- **Server selection is reliable, exact tool selection much less so.** When the expected tool is
  not first, it is usually a neighbor from the same server (for example `find_free_slots`
  instead of `create_event`). The final tool is meant to be chosen by an LLM among the
  proposed ones, so Hit@8 (87.5%) matters more for it than Hit@1.
- **Typical errors.** Generic verbs ("cancel", "add", "find") pull tools from other servers:
  "cancel Friday's appointment" ranks `stripe__cancel_subscription` first, and "add Marie to
  the #design channel" goes to Jira. Short messages with few keywords ("assign PROJ-45 to
  Karim") can fall below every threshold.
- **`not_connected` status at 62.5% while the suggestion is right 87.5% of the time.** When the
  user has other servers connected, one of their tools often passes the threshold, so the
  status becomes `tools_found`. The right suggestion is still returned in `suggested_mcps`.
- **Limits of the measurement.** 69 queries is small (about ±10 points of uncertainty on a
  percentage). The queries and the tool descriptions were written by the same author, which
  makes the results somewhat optimistic. For representative numbers, add real user messages to
  `eval/eval_queries.json` and re-run the script.

### Re-running the evaluation

```bash
python scripts/evaluate.py
```

```bash
python scripts/evaluate.py --sweep -v
```

`--sweep` adds the threshold sweep and `-v` prints every error (expected / got). The script
evaluates exactly the `route()` function used by the API, with the current configuration. To
compare another model, change `EMBEDDING_MODEL_NAME`, or set `EMBEDDING_PROVIDER=openai`, in
`.env`, then run it again.

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
│   ├── build_mock_data.py # (re)generates the mock data
│   └── evaluate.py        # metrics
├── tests/                 # pytest suite (fake embedding)
└── requests.http          # ready-to-run test requests
```
