"""Generate app/data/mock_data.json: generic public MCP servers, fully fictitious data.

    python scripts/build_mock_data.py

The generated JSON is the source of truth read by the service; this script only
exists to rebuild it cleanly. The JSON can also be edited by hand.
"""

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "mock_data.json"

# key: (label, description, [(tool_name, description, params, is_destructive)])
SERVERS = {
    "github": ("GitHub", "Code repositories, issues, pull requests, branches and commits.", [
        ("list_repositories", "List the code repositories the user can access.", ["owner", "visibility"], False),
        ("create_issue", "Create an issue (bug report or feature request) in a GitHub repository.", ["repo", "title", "body", "labels"], True),
        ("list_issues", "List open or closed issues of a repository, filtered by label or assignee.", ["repo", "state", "labels", "assignee"], False),
        ("close_issue", "Close an issue in a repository.", ["repo", "issue_number"], True),
        ("create_pull_request", "Open a pull request to merge one branch into another.", ["repo", "head", "base", "title", "body"], True),
        ("list_pull_requests", "List the pull requests of a repository and their review status.", ["repo", "state"], False),
        ("merge_pull_request", "Merge an approved pull request.", ["repo", "pull_number", "merge_method"], True),
        ("get_file_contents", "Read the contents of a source code file in a repository.", ["repo", "path", "ref"], False),
        ("search_code", "Search source code by keyword across repositories.", ["query", "repo"], False),
        ("list_commits", "List the commit history of a branch.", ["repo", "branch", "since"], False),
        ("create_branch", "Create a new git branch from an existing branch.", ["repo", "branch", "from_branch"], True),
    ]),
    "slack": ("Slack", "Team messaging: channels, messages, reactions, status.", [
        ("send_message", "Send a message to a Slack channel or a direct message to a teammate.", ["channel", "text"], True),
        ("list_channels", "List the Slack channels of the workspace.", ["include_private"], False),
        ("create_channel", "Create a new Slack channel.", ["name", "is_private"], True),
        ("get_channel_history", "Fetch the latest messages posted in a Slack channel.", ["channel", "limit"], False),
        ("search_messages", "Search Slack messages by keyword, author or date.", ["query", "from_user", "after"], False),
        ("add_reaction", "Add an emoji reaction to a Slack message.", ["channel", "timestamp", "emoji"], True),
        ("invite_user_to_channel", "Invite a team member to a Slack channel.", ["channel", "user"], True),
        ("set_status", "Update the user's Slack status (away, in a meeting, on vacation).", ["text", "emoji", "expiration"], True),
        ("upload_file", "Share a file in a Slack channel.", ["channel", "file_url", "comment"], True),
    ]),
    "gmail": ("Gmail", "Mailbox: sending, search, drafts, labels.", [
        ("send_email", "Send an email to one or more recipients.", ["to", "subject", "body", "cc"], True),
        ("search_emails", "Search emails by sender, subject, date or content.", ["query", "max_results"], False),
        ("read_email", "Read the full content of a received email.", ["message_id"], False),
        ("create_draft", "Prepare an email draft without sending it.", ["to", "subject", "body"], True),
        ("reply_to_email", "Reply to a received email.", ["message_id", "body"], True),
        ("list_labels", "List the labels (folders) of the mailbox.", [], False),
        ("add_label", "Apply a label to an email to file it.", ["message_id", "label"], True),
        ("archive_email", "Archive an email to remove it from the inbox.", ["message_id"], True),
        ("delete_email", "Delete an email (move it to trash).", ["message_id"], True),
    ]),
    "google_calendar": ("Google Calendar", "Calendar: events, meetings, availability, invitations.", [
        ("list_events", "List the calendar events and meetings over a period.", ["calendar_id", "time_min", "time_max"], False),
        ("create_event", "Create an event or schedule a meeting in the calendar, with attendees.", ["title", "start", "end", "attendees", "location"], True),
        ("update_event", "Change an existing event (time, location, attendees).", ["event_id", "start", "end", "attendees"], True),
        ("delete_event", "Cancel and delete a calendar event.", ["event_id"], True),
        ("find_free_slots", "Find common free time slots to organize a meeting.", ["attendees", "duration_minutes", "time_min", "time_max"], False),
        ("list_calendars", "List the calendars the user can access.", [], False),
        ("respond_to_invitation", "Accept or decline a meeting invitation.", ["event_id", "response"], True),
    ]),
    "notion": ("Notion", "Wiki and notes: pages, databases, blocks.", [
        ("search_pages", "Search pages and notes in the Notion workspace.", ["query"], False),
        ("get_page", "Read the content of a Notion page.", ["page_id"], False),
        ("create_page", "Create a new notes or documentation page in Notion.", ["parent_id", "title", "content"], True),
        ("update_page", "Change the title or properties of a Notion page.", ["page_id", "properties"], True),
        ("append_block", "Append text, a list or a checkbox at the end of a Notion page.", ["page_id", "content"], True),
        ("create_database", "Create a Notion database (table) with its columns.", ["parent_id", "title", "properties"], True),
        ("query_database", "Query a Notion database with filters and sorts.", ["database_id", "filter", "sorts"], False),
        ("add_database_entry", "Add a row to a Notion database.", ["database_id", "properties"], True),
        ("delete_page", "Archive (delete) a Notion page.", ["page_id"], True),
    ]),
    "stripe": ("Stripe", "Payments: customers, invoices, subscriptions, refunds.", [
        ("create_customer", "Create a customer in Stripe for billing.", ["email", "name"], True),
        ("list_customers", "List the customers registered in Stripe.", ["email", "limit"], False),
        ("create_invoice", "Create an invoice for a customer.", ["customer_id", "items", "due_date"], True),
        ("list_invoices", "List invoices, filtered by status (paid, unpaid, overdue).", ["customer_id", "status"], False),
        ("send_invoice", "Email an invoice to the customer for payment.", ["invoice_id"], True),
        ("create_payment_link", "Generate an online payment link for a product or an amount.", ["amount", "currency", "description"], True),
        ("list_payments", "List received payments and their status.", ["customer_id", "created_after"], False),
        ("refund_payment", "Refund a payment fully or partially.", ["payment_id", "amount"], True),
        ("get_balance", "Show the available and pending balance of the Stripe account.", [], False),
        ("create_subscription", "Subscribe a customer to a monthly or yearly recurring plan.", ["customer_id", "price_id"], True),
        ("cancel_subscription", "Cancel a customer's subscription.", ["subscription_id"], True),
    ]),
    "jira": ("Jira", "Agile project management: tickets, sprints, comments.", [
        ("create_ticket", "Create a ticket (task, story or bug) in a Jira project.", ["project", "summary", "description", "issue_type"], True),
        ("get_ticket", "Show the details of a Jira ticket.", ["ticket_key"], False),
        ("list_tickets", "List the Jira tickets of a project or an assignee, filtered by status.", ["project", "assignee", "status"], False),
        ("update_ticket_status", "Change the status of a Jira ticket (to do, in progress, done).", ["ticket_key", "status"], True),
        ("assign_ticket", "Assign a Jira ticket to a team member.", ["ticket_key", "assignee"], True),
        ("add_comment", "Add a comment to a Jira ticket.", ["ticket_key", "body"], True),
        ("list_sprints", "List the sprints of a Jira board and their progress.", ["board_id", "state"], False),
        ("create_sprint", "Create a new sprint on a Jira board.", ["board_id", "name", "start_date", "end_date"], True),
    ]),
    "openweather": ("Weather", "Current weather, forecasts and air quality.", [
        ("get_current_weather", "Get the current weather (temperature, rain, wind) for a city.", ["city", "units"], False),
        ("get_forecast", "Get the weather forecast for the next days for a city.", ["city", "days"], False),
        ("get_air_quality", "Get the air quality index and pollution level of a city.", ["city"], False),
    ]),
    "google_drive": ("Google Drive", "File storage: search, folders, sharing.", [
        ("search_files", "Search files and documents in Google Drive.", ["query", "mime_type"], False),
        ("upload_file", "Upload a file to a Google Drive folder.", ["name", "content_url", "folder_id"], True),
        ("download_file", "Download the content of a Google Drive file.", ["file_id"], False),
        ("create_folder", "Create a folder in Google Drive.", ["name", "parent_id"], True),
        ("share_file", "Share a Drive file or folder with someone (view or edit access).", ["file_id", "email", "role"], True),
        ("delete_file", "Delete a file from Google Drive.", ["file_id"], True),
    ]),
}

USERS = [
    {"id": 1, "name": "Developer (GitHub, Jira, Slack)"},
    {"id": 2, "name": "Sales rep (Stripe, Gmail, Calendar)"},
    {"id": 3, "name": "Admin (all MCP servers)"},
    {"id": 4, "name": "New user (no MCP connected)"},
    {"id": 5, "name": "Writer (Notion; Drive in error, Weather disconnected)"},
]

CONNECTED = {
    1: ["github", "jira", "slack"],
    2: ["stripe", "gmail", "google_calendar"],
    3: list(SERVERS),
    5: ["notion"],
}


def build() -> dict:
    servers, tools = [], []
    for key, (label, desc, tool_list) in SERVERS.items():
        servers.append({"key": key, "label": label, "description": desc, "naming_convention": "explicit_typed", "is_native": False})
        for name, tool_desc, params, destructive in tool_list:
            tools.append(
                {
                    "mcp_key": key,
                    "tool_name": name,
                    "description": tool_desc,
                    "input_schema": {
                        "type": "object",
                        "properties": {p: {"type": "string"} for p in params},
                        "required": params[:1],
                    },
                    "is_destructive": destructive,
                }
            )
    connections = [
        {"user_id": uid, "mcp_key": key, "status": "connected"} for uid, keys in CONNECTED.items() for key in keys
    ]
    connections += [
        {"user_id": 5, "mcp_key": "google_drive", "status": "error"},
        {"user_id": 5, "mcp_key": "openweather", "status": "disconnected"},
    ]
    return {
        "_comment": "Fictitious data replacing the mcp_servers / mcp_tools / mcp_user_connections tables. "
        "Generic public MCP servers, no real data. Regenerate with: python scripts/build_mock_data.py",
        "mcp_servers": servers,
        "mcp_tools": tools,
        "users": USERS,
        "mcp_user_connections": connections,
    }


if __name__ == "__main__":
    data = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(data['mcp_servers'])} MCP servers, {len(data['mcp_tools'])} tools -> {OUT}")
