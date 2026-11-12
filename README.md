# MCP Orchestrator

A FastAPI service that takes a user message and picks **the best MCP server**, along with its
most relevant tools, to handle it. It does not call an LLM and does not execute any tool: it
**decides** what to use, combining semantic vector search and keyword search.

Why: an agent that sees every tool reads every description on every request. With **200 tools**,
that is **14,907 tokens** of tool definitions per request, and 200 ways to pick something that is
almost right. The orchestrator puts a routing step in front of the model, which then only sees a
shortlist of about **500 tokens**, and picks the right server **89% of the time** (see
[Metrics](#metrics)).

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
then embedded into a vector. The service builds one FAISS index per MCP server, a **centroid** per
server (the mean of its tool vectors), and a **keyword index** (BM25) over all tool texts.

**Scoring.** Each tool gets a score that combines meaning and keywords:

```
score = semantic similarity + 0.15 × keyword boost
```

- The **semantic similarity** (cosine of the embeddings) understands meaning: "who did I not call
  back this week?" matches the CRM's follow-up tool although the word "CRM" never appears.
- The **keyword boost** (BM25, mapped to [0, 1)) rewards rare words shared with the tool:
  "newsletter", "VAT", "transcript", product names. It only adds evidence: a tool sharing no word
  with the message keeps its semantic score.

**Explicit mentions.** When the message names a server, routing is **restricted to it**:
"add a row to my **Notion** reading list" only considers Notion, even if a Trello tool scores
higher. A server is named by a product name ("Notion", "Dropbox", "the Drive"; whole words only,
so "drive from Lyon" is not Google Drive) or by a product convention: a Slack channel
(`#general`) or a Jira-style key next to an issue word ("ticket PROJ-12"). A named server that the
user has not connected is always suggested.

**Routing.** Each message is routed in two levels:

1. **MCP level.** A server is kept if its centroid score exceeds `THRESHOLD_MCP` (0.20), **or** if
   one of its tools exceeds `THRESHOLD_TOOL` (0.28). At most 4 servers are kept. With an explicit
   mention, only the named servers are kept, with a tool threshold of 0.20.
2. **Tool level.** Among the kept servers that the user is **connected** to, tools scoring above
   the threshold are returned. Each server gets a quota of tools, then remaining slots go to the
   best scores overall.

Every response has one of these statuses:

| `status` | Meaning |
|---|---|
| `tools_found` | Tools are proposed. `best_mcp` is the server of the top-ranked tool. |
| `mcp_not_connected` | The right server exists but the user is not connected to it. `suggested_mcps` says which one to connect. One of its tools must exceed `THRESHOLD_SUGGEST` (0.40), or the server must be named in the message. |
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

| Server | Domain | Tools | Wave |
|---|---|---|---|
| `github` | Code: repositories, issues, pull requests, branches, commits | 11 | core |
| `slack` | Team messaging: channels, messages, reactions, status | 9 | core |
| `gmail` | Email: send, search, drafts, replies, labels | 9 | core |
| `google_calendar` | Calendar: events, free slots, invitations | 7 | core |
| `notion` | Notes and wiki: pages, blocks, databases | 9 | core |
| `stripe` | Payments: customers, invoices, refunds, subscriptions | 11 | core |
| `jira` | Agile projects: tickets, statuses, sprints | 8 | core |
| `openweather` | Weather: current, forecast, air quality | 3 | core |
| `google_drive` | File storage: search, folders, sharing | 6 | core |
| `hubspot` | CRM: contacts, deals, calls, follow-ups | 14 | extra |
| `zendesk` | Customer support: tickets, replies, macros, satisfaction | 12 | extra |
| `shopify` | Online store: products, orders, inventory, discounts | 14 | extra |
| `quickbooks` | Accounting: invoices, bills, expenses, reports, tax | 12 | extra |
| `asana` | Work management: projects, tasks, workload | 10 | extra |
| `google_sheets` | Spreadsheets: read, write, append, charts | 10 | extra |
| `zoom` | Video meetings: schedule, recordings, transcripts | 8 | extra |
| `mailchimp` | Email marketing: audiences, campaigns, reports | 10 | extra |
| `twilio` | Phone: SMS, calls, numbers | 6 | extra |
| `dropbox` | File storage: files, folders, shared links | 8 | extra |
| `docusign` | E-signature: envelopes, templates, status | 7 | extra |
| `google_maps` | Places, directions, travel time | 6 | extra |
| `trello` | Kanban boards: boards, cards, checklists | 10 | extra |
| **Total** | | **200** | 73 core + 127 extra |

Each server also has `aliases`: the product names that designate it in a message (by default its
label, e.g. "google sheets"). Only product names, never generic nouns: `openweather` is not
designated by "weather", and Google Drive by "google drive", "the drive", "my drive" but not by
"drive" alone.

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
  "mcp_servers": [{"key": "github", "label": "GitHub", "description": "...", "aliases": ["github"], "naming_convention": "explicit_typed", "is_native": false}],
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

[requests.http](requests.http) holds ready-to-run requests covering every case: the example of the
post ("who did I not call back this week?"), explicit mentions ("Notion", "ticket PROJ-12"), a
missing connector, `explain` and re-indexing. Open it in VS Code with the **REST Client**
extension, or in a JetBrains IDE, and click "Send Request" above each one.

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
  "mentioned_mcps": [],
  "tools": [
    {"namespaced_name": "stripe__list_invoices", "mcp": "stripe", "tool_name": "list_invoices",
     "description": "List invoices, filtered by status (paid, unpaid, overdue).",
     "input_schema": {"type": "object", "properties": {"customer_id": {"type": "string"}, "status": {"type": "string"}}, "required": []},
     "requires_confirmation": false, "convention": "explicit_typed",
     "score": 0.827, "semantic_score": 0.723, "keyword_score": 0.688},
    {"namespaced_name": "quickbooks__list_invoices", "score": 0.756, "...": "..."},
    {"namespaced_name": "quickbooks__record_payment", "score": 0.750, "...": "..."}
  ],
  "matched_mcps": [{"mcp": "stripe", "score": 0.584}, {"mcp": "quickbooks", "score": 0.647},
                   {"mcp": "docusign", "score": 0.36}, {"mcp": "hubspot", "score": 0.269}],
  "suggested_mcps": [],
  "out_of_scope_mcps": []
}
```

- `score` = `semantic_score` + 0.15 × `keyword_score`. Here "invoices" and "unpaid" appear in
  the tool's text, which lifts it from 0.723 to 0.827.
- `mentioned_mcps` lists the servers named in the message (none here).
- `requires_confirmation: true` flags a tool that changes data (create, send, delete): the calling
  application should ask for confirmation before running it.

Results observed on the running server (200 tools):

| Message | `user_id` | Result | Top tool (score) |
|---|---|---|---|
| list the unpaid invoices | 3 | `tools_found`, stripe | `stripe__list_invoices` (0.83), QuickBooks close behind |
| who did I not call back this week? | 3 | `tools_found`, hubspot | `list_overdue_follow_ups` (0.51) |
| who did I not call back this week? | 1 | `mcp_not_connected`, suggests hubspot | — |
| add a row to my Notion reading list for the book Dune | 3 | `tools_found`, notion (named) | `notion__get_page` (0.43) |
| move ticket PROJ-12 to done | 3 | `tools_found`, jira (named by the key) | `update_ticket_status` (0.63) |
| merge PR 42 in the frontend repo | 3 | `tools_found`, github | `merge_pull_request` (0.59) |
| what's the weather like in Lyon? | 3 | `tools_found`, openweather | `get_forecast` (0.36) |
| share the report.pdf file from the Drive with Paul | 5 | `mcp_not_connected`, suggests google_drive (named) | — |
| send a Slack message to the team about the meeting | 4 | `mcp_not_connected`, suggests slack | — |
| what is a pull request? | 3 | `direct_answer` | — |
| write me a poem about autumn | 3 | `direct_answer` | — |
| schedule a meeting with Sophie on Thursday at 2pm | 3 | `tools_found`, zoom (valid) | `zoom__update_meeting` (0.46), `create_meeting` (0.45) right behind: **wrong tool first** |
| email paul@example.com to confirm the appointment | 3 | `tools_found`, zendesk | `zendesk__create_ticket` (0.42): **wrong server** |

The `/route` body accepts either `user_id` (allowed servers read from the mock data) or
`allowed_mcps` (explicit list), plus `top_k` (1 to 15, default 8).

### 4. Automated tests

```bash
python -m pytest -q
```

22 tests, with a fake embedding: they do not load the model and run in a few seconds.

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/orchestrator/health` | Service status and number of indexed tools per server |
| GET | `/orchestrator/mcps` | Servers declared in the mock data |
| GET | `/orchestrator/users` | Fictitious users and their allowed servers |
| POST | `/orchestrator/route` | **Picks the best server and tools for a message** |
| POST | `/orchestrator/route/explain` | Every raw score, no thresholds, with the semantic and keyword parts (diagnostics) |
| POST | `/orchestrator/index/rebuild` | Re-indexes every server (`?force=true` recomputes everything) |
| POST | `/orchestrator/index/sync/{mcp_key}` | Re-indexes one server |
| DELETE | `/orchestrator/index/{mcp_key}` | Removes the index of one server |

## Metrics

Measured on November 12, 2026, CPU, local model `paraphrase-multilingual-MiniLM-L12-v2`, default
configuration, 22 servers and 200 tools. Full reports:
[reports/metrics.md](reports/metrics.md) (`python scripts/evaluate.py --sweep --compare-core`) and
[reports/ablation.md](reports/ablation.md) (`python scripts/ablation.py`).

### Evaluation set

[eval/eval_queries.json](eval/eval_queries.json) holds **147 labeled queries**, in English:

| Set | Written | Action requests | Missing connector | Knowledge / unrelated |
|---|---|---|---|---|
| `core` | for the original 9-server catalog | 48 | 8 | 13 |
| `extended` | with the 200-tool catalog | 44 | 4 | 5 |
| `fresh` | **held out**: written before the routing improvements, never used to tune them | 19 | 3 | 3 |
| **Total** | | **111** | **15** | **21** |

Some action requests are ambiguous on purpose, and accept several servers ("create a task to call
the supplier tomorrow": Asana, Trello, HubSpot or Jira). The `fresh` set also contains traps: a
named product with nothing to do ("who founded Shopify?") and a keyword with nothing to do ("how
long should a good newsletter subject line be?").

### Routing improvements: what each one brings

Same 147 queries, 200 tools. "Correct best server" is the server of the top-ranked tool.

| Configuration | Correct best server | **Fresh (held out)** | Right tool in shortlist | False positives |
|---|---|---|---|---|
| Baseline: semantic only | 76.6% (85/111) | 63.2% (12/19) | 81.1% | 14.3% (3/21) |
| Server name + domain in tool text | 73.9% | 68.4% | 69.4% | 19.0% |
| Server name only in tool text | 77.5% | 68.4% | 79.3% | 14.3% |
| Explicit mentions | 85.6% | 78.9% | 86.5% | 14.3% |
| Keyword search (BM25) | 84.7% | 84.2% | 85.6% | 14.3% |
| **Mentions + keywords (default)** | **89.2%** (99/111) | **89.5%** (17/19) | **89.2%** | **14.3%** (3/21) |
| Mentions + keywords + server name | 88.3% | 89.5% | 90.1% | 14.3% |

- **Explicit mentions and keyword search both work, and they add up**: +12.6 points on all
  action requests, and **+26.3 points on the held-out queries** (63.2% → 89.5%). Compared with
  the baseline, 14 questions are fixed and **none is broken**.
- **Adding the server name and domain to the tool texts did not help** with this embedding model:
  with the domain description, every tool of a server gets a similar vector, and telling them
  apart gets harder (right tool in shortlist 81.1% → 69.4%). The name alone is neutral. This
  option is kept, off by default (`SERVER_CONTEXT_IN_TOOL_TEXT`), to re-test with other models.
- **False positives did not increase**: the 3 remaining ones are the 3 traps of the fresh set
  (see below). On the general questions of the core set, false positives stay at 0 (0/13).

### Server and tool selection (default configuration, 111 action requests)

| Metric | Value |
|---|---|
| **Correct best server** (`best_mcp`) | **89.2%** (99/111) |
| Expected server among kept servers | 97.3% (108/111) |
| Right tool ranked first (Hit@1) | 65.8% (73/111) |
| Right tool in the top 3 (Hit@3) | 84.7% (94/111) |
| Right tool among returned tools (Hit@8) | 89.2% (99/111) |
| Tool MRR | 0.751 |
| Tools returned per query, on average | 6.7 |

### Decision

| Metric | Value |
|---|---|
| Correct status, all queries | 93.9% (138/147) |
| Correct status, action requests | 96.4% (107/111) |
| Right connector suggested when it is missing | 93.3% (14/15) |
| False positives: tools proposed for a general question | 14.3% (3/21), all 3 in the fresh traps |

### Context sent to the model

Tokens of the tool definitions as the model would receive them (OpenAI function format, counted
with `tiktoken`, `o200k_base`), for the admin user who can use all 200 tools:

| | Tokens per request |
|---|---|
| Whole catalog, no routing | **14,907** |
| Routed shortlist, mean / p95 | **517** / 635 |
| Reduction | **96.5%** |

### Catalog size: the same queries on 73 and 200 tools

The 48 `core` action requests, written for the original 9-server catalog, run unchanged on the
original catalog (73 tools) and on the full one (200 tools).

| Correct best server | 73 tools | 200 tools |
|---|---|---|
| Before the improvements (semantic only) | 83.3% | 68.8% |
| **After (mentions + keywords)** | **85.4%** | **85.4%** |

Before, going from 73 to 200 tools cost 14.5 points: new servers that look alike pulled the
questions away ("move ticket PROJ-12 to done" went to Zendesk). With mentions and keywords, **the
200-tool router does as well as the 73-tool one**, and better than the old router on the small
catalog. The shortlist stays around 500 tokens while the full catalog grows from 5,488 to 14,907.

### Performance

| Metric | Value |
|---|---|
| `route()` latency (model loaded) | mean 43 ms, p50 42 ms, p95 50 ms |
| Full indexing of the 200 tools | 8.6 s |

The keyword index and the mention detection add about 2 ms (42 → 44 ms p50 in the ablation run).

### Choosing `THRESHOLD_TOOL`

| Threshold | Correct status | Correct best server | False positives |
|---|---|---|---|
| 0.20 | 88.4% | 91.0% | 61.9% |
| 0.25 | 91.2% | 91.0% | 42.9% |
| **0.28 (default)** | **93.9%** | **89.2%** | **14.3%** |
| 0.30 | 93.9% | 89.2% | 14.3% |
| 0.35 | 92.5% | 88.3% | 14.3% |
| 0.40 | 91.2% | 86.5% | 14.3% |

0.28 remains the best trade-off: below it, tools are proposed for general questions; above it,
real actions are missed.

### What is still wrong

12 of the 111 action requests still go to the wrong server, or to none. Typical cases:

- **Generic verbs and nouns, with no product named**: "email paul@example.com to confirm the
  appointment" goes to Zendesk, "cancel Friday's appointment" to Shopify's cancel order, "how did
  last week's newsletter perform?" to Asana.
- **Named, but no tool above the threshold**: "post in #general that the production release is
  done" is restricted to Slack, but no Slack tool reaches 0.20, so nothing is proposed.
- **The traps of the fresh set**: "who founded Shopify?" names Shopify, so Shopify tools are
  proposed; "how long should a good newsletter subject line be?" gets a keyword boost from
  "newsletter"; "what's the difference between Asana and Trello?" slips past the knowledge-question
  detection, which recognizes "what is the difference" but not the contraction "what's".

Next steps, in order of expected impact: example user questions indexed for each tool, a
cross-encoder reranker on the top 20 candidates, and a stronger embedding model. Each one can be
added behind a setting and measured with `scripts/ablation.py`.

### Limits of the measurement

147 queries is small (about ±6 points of uncertainty on 111 action requests, ±14 on the 19 fresh
ones). The queries and the tool descriptions were written by the same author, which makes the
results somewhat optimistic; the fresh set limits, but does not remove, the risk of tuning to the
test set. For representative numbers, add real user messages to `eval/eval_queries.json` and re-run
the scripts.

### Re-running the evaluation

```bash
python scripts/evaluate.py --sweep --compare-core -v
```

```bash
python scripts/ablation.py
```

`--sweep` adds the threshold sweep, `--compare-core` the 73 vs 200 tools comparison and `-v`
prints every error (expected / got). `ablation.py` runs every configuration of the improvements
on the same queries and lists the questions fixed and broken. Both evaluate exactly the `route()`
function used by the API.

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
| `EXPLICIT_MENTION_ENABLED` | true | A server named in the message restricts routing to it |
| `THRESHOLD_TOOL_MENTIONED` | 0.20 | Tool threshold inside a named server |
| `LEXICAL_WEIGHT` | 0.15 | Weight of the keyword (BM25) boost; 0 disables keyword search |
| `SERVER_CONTEXT_IN_TOOL_TEXT` | false | Server name in front of each embedded tool text (did not help, see above) |
| `SERVER_CONTEXT_INCLUDE_DOMAIN` | true | With the option above, also add the server's domain description |

Changing the model or the tool text options automatically invalidates the existing indexes: they
are rebuilt on the next startup. The knowledge-question detection matches English phrasing.

## Project structure

```
├── app/
│   ├── main.py            # FastAPI app, indexing at startup
│   ├── routes.py          # /orchestrator/* endpoints
│   ├── router_service.py  # scoring (candidates), pure decide(), route(), explain()
│   ├── lexical.py         # BM25 keyword index, explicit server mentions
│   ├── indexer.py         # incremental indexing (catalog hash), tool texts
│   ├── store.py           # FAISS indexes + centroids + keyword index, disk persistence
│   ├── embedding.py       # local / OpenAI embeddings, L2-normalized
│   ├── repository.py      # mock data access
│   ├── schema_utils.py    # tool JSON Schema normalization
│   ├── schemas.py         # request models
│   ├── config.py          # settings
│   └── data/mock_data.json
├── eval/eval_queries.json # labeled evaluation set (core, extended, fresh)
├── examples/              # JSON request bodies for curl
├── reports/
│   ├── metrics.md         # latest evaluation report
│   └── ablation.md        # what each routing improvement brings
├── scripts/
│   ├── build_mock_data.py # (re)generates the mock data, 200 or 73 tools
│   ├── evaluate.py        # metrics, catalog-size comparison, context tokens
│   └── ablation.py        # every configuration of the improvements, fixed / broken questions
├── tests/                 # pytest suite (fake embedding)
└── requests.http          # ready-to-run test requests
```
