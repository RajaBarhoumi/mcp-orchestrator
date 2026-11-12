"""Server context in tool texts, explicit mentions and keyword (BM25) search."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import indexer
from app.config import settings
from app.lexical import BM25Index, find_mentions, lexical_boost, tokenize
from app.repository import McpServer, McpTool, repository
from app.router_service import decide
from tests.test_orchestrator import KW, _tool, fake_embeddings  # noqa: F401 (fixture)

SERVERS = [
    McpServer(key="slack", label="Slack", aliases=("slack",)),
    McpServer(key="jira", label="Jira", aliases=("jira",)),
    McpServer(key="google_drive", label="Google Drive", aliases=("google drive", "the drive", "my drive")),
    McpServer(key="notion", label="Notion", aliases=("notion",)),
]


# ---------------------------------------------------------------- mentions


def test_product_names_are_mentions():
    assert find_mentions("add a row to my Notion reading list", SERVERS) == {"notion"}
    assert find_mentions("find the presentation in the Drive", SERVERS) == {"google_drive"}
    assert find_mentions("share my Notion page on Slack", SERVERS) == {"notion", "slack"}


def test_generic_words_are_not_mentions():
    assert find_mentions("how long does it take to drive to Grenoble?", SERVERS) == set()
    assert find_mentions("take notions of time", SERVERS) == set()  # whole words only


def test_product_conventions():
    assert find_mentions("post in #general that we shipped", SERVERS) == {"slack"}
    assert find_mentions("refund order #1047", SERVERS) == set()  # a number is not a channel
    assert find_mentions("move ticket PROJ-12 to done", SERVERS) == {"jira"}
    assert find_mentions("send invoice INV-2031 to the customer", SERVERS) == set()  # no issue word


def test_real_catalog_aliases():
    keys = {s.key for s in repository.list_servers()}
    assert all(s.aliases for s in repository.list_servers())
    assert find_mentions("upload it to Dropbox", repository.list_servers()) == {"dropbox"}
    assert "weather" not in {a for s in repository.list_servers() for a in s.aliases}  # generic word
    assert {"slack", "jira"} <= keys


# ---------------------------------------------------------------- decision with mentions


def test_mention_restricts_candidates_to_the_named_server():
    hits = {
        "trello": [_tool("trello", "create_card", 0.60)],
        "notion": [_tool("notion", "add_database_entry", 0.25)],
    }
    result = decide([("trello", 0.4), ("notion", 0.2)], hits, {"trello", "notion"}, mentioned={"notion"}, threshold_tool_mentioned=0.2, **KW)
    assert result["status"] == "tools_found"
    assert [t["mcp"] for t in result["tools"]] == ["notion"]


def test_mentioned_server_not_connected_is_suggested():
    hits = {"google_drive": [_tool("google_drive", "share_file", 0.30)], "google_sheets": [_tool("google_sheets", "share_spreadsheet", 0.38)]}
    result = decide([("google_drive", 0.3), ("google_sheets", 0.3)], hits, {"google_sheets"}, mentioned={"google_drive"}, **KW)
    # Below the suggestion threshold (0.40), but explicitly named: suggested, and no false lead.
    assert result["status"] == "mcp_not_connected"
    assert result["suggested_mcps"][0]["mcp"] == "google_drive"
    assert result["tools"] == []


def test_unknown_mention_is_ignored():
    hits = {"crm": [_tool("crm", "list_contacts", 0.6)]}
    result = decide([("crm", 0.3)], hits, {"crm"}, mentioned={"not_indexed"}, **KW)
    assert result["status"] == "tools_found"


def test_knowledge_guard_wins_over_mentions():
    result = decide([("notion", 0.9)], {}, {"notion"}, knowledge_query=True, mentioned={"notion"}, **KW)
    assert result["status"] == "direct_answer"


# ---------------------------------------------------------------- keyword search


def test_tokenize_drops_stopwords_and_plurals():
    assert tokenize("What are the unpaid Invoices?") == ["unpaid", "invoice"]


def test_bm25_prefers_rare_matching_words():
    index = BM25Index(
        {
            "mailchimp__get_campaign_report": "Mailchimp. Email marketing. get campaign report. Newsletter open rate.",
            "stripe__create_subscription": "Stripe. Payments. create subscription. Monthly plan.",
            "gmail__send_email": "Gmail. Email. send email. Send an email.",
        }
    )
    scores = index.scores("how did last week's newsletter perform?")
    assert max(scores, key=scores.get) == "mailchimp__get_campaign_report"
    assert "stripe__create_subscription" not in scores
    assert index.scores("hello there") == {}


def test_boost_is_bounded():
    assert lexical_boost(0) == 0
    assert 0.49 < lexical_boost(5.0) < 0.51
    assert lexical_boost(1e9) < 1


# ---------------------------------------------------------------- server context and end to end


def test_server_context_is_embedded_and_changes_the_hash(monkeypatch):
    server = McpServer(key="zendesk", label="Zendesk", description="Customer support: tickets.")
    tool = McpTool(mcp_key="zendesk", tool_name="get_ticket", description="Show a support ticket.")
    monkeypatch.setattr(settings, "SERVER_CONTEXT_IN_TOOL_TEXT", True)
    context = indexer.server_context(server)
    assert indexer._tool_to_text(tool, context).startswith("Zendesk. Customer support: tickets. get ticket.")
    monkeypatch.setattr(settings, "SERVER_CONTEXT_IN_TOOL_TEXT", False)
    assert indexer.server_context(server) == ""
    assert indexer.compute_catalog_hash([tool], context) != indexer.compute_catalog_hash([tool], "")


def test_route_reports_mentions_and_score_components(fake_embeddings):
    indexer.reindex_all()
    from app.routes import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    body = client.post("/orchestrator/route", json={"query": "create a card on Trello for the launch", "user_id": 3}).json()
    assert body["mentioned_mcps"] == ["trello"]
    assert body["status"] == "tools_found"
    assert {t["mcp"] for t in body["tools"]} == {"trello"}
    top = body["tools"][0]
    assert top["score"] >= top["semantic_score"] and 0 <= top["keyword_score"] < 1

    # User 1 has Trello but not Dropbox: a named, unconnected server is suggested.
    body = client.post("/orchestrator/route", json={"query": "upload the logo to Dropbox", "user_id": 1}).json()
    assert body["status"] == "mcp_not_connected"
    assert body["suggested_mcps"][0]["mcp"] == "dropbox"
