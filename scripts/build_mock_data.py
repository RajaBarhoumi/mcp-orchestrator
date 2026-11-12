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

# Second wave: business servers that overlap with the core ones on purpose (tasks in Jira, Asana
# and Trello; invoices in Stripe and QuickBooks; files in Drive and Dropbox; meetings in Calendar
# and Zoom). This is what makes routing hard as a catalog grows.
EXTRA_SERVERS = {
    "hubspot": ("HubSpot", "CRM: contacts, companies, deals, calls, follow-ups.", [
        ("list_contacts", "List CRM contacts, filtered by owner, company or lifecycle stage.", ["owner", "company", "stage"], False),
        ("get_contact", "Show a contact's details and activity timeline.", ["contact_id"], False),
        ("create_contact", "Add a new contact (lead) to the CRM.", ["email", "first_name", "last_name", "company"], True),
        ("update_contact", "Update a contact's properties (phone, stage, owner).", ["contact_id", "properties"], True),
        ("list_companies", "List the companies (accounts) in the CRM.", ["industry", "owner"], False),
        ("list_deals", "List sales deals in the pipeline, filtered by stage or owner.", ["stage", "owner", "closing_before"], False),
        ("create_deal", "Create a new sales deal (opportunity) for a contact or company.", ["name", "amount", "stage", "contact_id"], True),
        ("update_deal_stage", "Move a deal to another pipeline stage (qualified, proposal, won, lost).", ["deal_id", "stage"], True),
        ("log_call", "Log a phone call with a contact and its outcome.", ["contact_id", "outcome", "notes"], True),
        ("list_calls", "List logged sales calls and their outcomes over a period.", ["owner", "since"], False),
        ("list_overdue_follow_ups", "List contacts whose follow-up call or email is overdue (people not called back).", ["owner", "since"], False),
        ("create_task", "Create a sales follow-up task (call back, send a proposal) for a contact.", ["contact_id", "title", "due_date"], True),
        ("add_note", "Add a note to a contact or deal record.", ["record_id", "body"], True),
        ("get_pipeline_report", "Show the sales pipeline value and conversion rate by stage.", ["period"], False),
    ]),
    "zendesk": ("Zendesk", "Customer support: tickets, replies, satisfaction, macros.", [
        ("list_tickets", "List customer support tickets, filtered by status, priority or assignee.", ["status", "priority", "assignee"], False),
        ("get_ticket", "Show a support ticket with its conversation.", ["ticket_id"], False),
        ("create_ticket", "Open a support ticket for a customer request or complaint.", ["requester_email", "subject", "description", "priority"], True),
        ("reply_to_ticket", "Send a public reply to the customer on a support ticket.", ["ticket_id", "body"], True),
        ("add_internal_note", "Add a private note on a support ticket, visible only to agents.", ["ticket_id", "body"], True),
        ("update_ticket_status", "Change a support ticket status (open, pending, solved).", ["ticket_id", "status"], True),
        ("assign_ticket", "Assign a support ticket to an agent or group.", ["ticket_id", "assignee"], True),
        ("merge_tickets", "Merge duplicate support tickets into one.", ["source_ticket_id", "target_ticket_id"], True),
        ("search_tickets", "Search support tickets by keyword or customer.", ["query"], False),
        ("list_macros", "List canned reply templates (macros) for support agents.", ["category"], False),
        ("apply_macro", "Apply a canned reply template to a support ticket.", ["ticket_id", "macro_id"], True),
        ("get_satisfaction_scores", "Show customer satisfaction (CSAT) scores over a period.", ["period"], False),
    ]),
    "shopify": ("Shopify", "Online store: products, orders, inventory, discounts, customers.", [
        ("list_products", "List the products of the online store.", ["collection", "status"], False),
        ("get_product", "Show a product's details, variants and price.", ["product_id"], False),
        ("create_product", "Add a new product to the online store.", ["title", "price", "description", "images"], True),
        ("update_product_price", "Change the price of a product or variant.", ["product_id", "price"], True),
        ("update_inventory", "Set the stock quantity of a product variant.", ["variant_id", "quantity", "location"], True),
        ("list_orders", "List customer orders of the store, filtered by status or date.", ["status", "since", "customer"], False),
        ("get_order", "Show a store order with items, shipping and payment status.", ["order_id"], False),
        ("fulfill_order", "Mark a store order as shipped with a tracking number.", ["order_id", "tracking_number", "carrier"], True),
        ("cancel_order", "Cancel a customer order in the store.", ["order_id", "reason"], True),
        ("refund_order", "Refund a store order fully or partially.", ["order_id", "amount"], True),
        ("create_discount_code", "Create a discount or promo code for the store.", ["code", "percentage", "expires_at"], True),
        ("list_customers", "List the store's customers and their order count.", ["since", "min_orders"], False),
        ("get_sales_report", "Show store sales, revenue and best-selling products over a period.", ["period"], False),
        ("list_low_stock_products", "List products that are low in stock or sold out.", ["threshold"], False),
    ]),
    "quickbooks": ("QuickBooks", "Accounting: invoices, bills, expenses, reports, tax.", [
        ("list_invoices", "List accounting invoices, filtered by customer or status (open, overdue, paid).", ["customer", "status"], False),
        ("create_invoice", "Create an accounting invoice for a customer.", ["customer", "lines", "due_date"], True),
        ("record_payment", "Record a customer payment received against an invoice.", ["invoice_id", "amount", "date"], True),
        ("list_bills", "List supplier bills to pay, filtered by vendor or due date.", ["vendor", "due_before"], False),
        ("pay_bill", "Pay a supplier bill from a bank account.", ["bill_id", "account", "amount"], True),
        ("create_expense", "Record a business expense with its category and receipt.", ["amount", "category", "vendor", "receipt_url"], True),
        ("list_expenses", "List business expenses by category or period.", ["category", "since"], False),
        ("get_profit_and_loss", "Show the profit and loss statement for a period.", ["period"], False),
        ("get_balance_sheet", "Show the balance sheet at a date.", ["date"], False),
        ("get_cash_flow", "Show the cash flow statement for a period.", ["period"], False),
        ("list_vendors", "List suppliers (vendors) and what the company owes them.", ["status"], False),
        ("get_tax_summary", "Show the sales tax (VAT) collected and owed for a period.", ["period"], False),
    ]),
    "asana": ("Asana", "Team work management: projects, tasks, sections, workload.", [
        ("list_projects", "List the team's Asana projects.", ["team", "archived"], False),
        ("create_project", "Create a new Asana project for a team.", ["name", "team", "template"], True),
        ("list_tasks", "List Asana tasks of a project or assignee, filtered by due date.", ["project", "assignee", "due_before"], False),
        ("create_task", "Create a task in an Asana project with an assignee and due date.", ["project", "name", "assignee", "due_date"], True),
        ("complete_task", "Mark an Asana task as complete.", ["task_id"], True),
        ("update_task", "Change an Asana task's assignee, due date or description.", ["task_id", "assignee", "due_date"], True),
        ("add_comment", "Comment on an Asana task.", ["task_id", "text"], True),
        ("move_task_to_section", "Move an Asana task to another section of the board.", ["task_id", "section"], True),
        ("list_overdue_tasks", "List Asana tasks that are past their due date.", ["project", "assignee"], False),
        ("get_workload", "Show how many tasks each team member has this week.", ["team"], False),
    ]),
    "google_sheets": ("Google Sheets", "Spreadsheets: read, write, append rows, formulas.", [
        ("list_spreadsheets", "List the spreadsheets the user can access.", ["query"], False),
        ("create_spreadsheet", "Create a new spreadsheet.", ["title", "sheets"], True),
        ("read_range", "Read the values of a cell range in a spreadsheet.", ["spreadsheet_id", "range"], False),
        ("update_range", "Write values into a cell range of a spreadsheet.", ["spreadsheet_id", "range", "values"], True),
        ("append_rows", "Append new rows at the end of a spreadsheet table.", ["spreadsheet_id", "sheet", "rows"], True),
        ("add_sheet", "Add a new tab (sheet) to a spreadsheet.", ["spreadsheet_id", "title"], True),
        ("clear_range", "Erase the values of a cell range.", ["spreadsheet_id", "range"], True),
        ("create_chart", "Create a chart from a range of spreadsheet data.", ["spreadsheet_id", "range", "chart_type"], True),
        ("search_rows", "Find spreadsheet rows matching a value in a column.", ["spreadsheet_id", "column", "value"], False),
        ("share_spreadsheet", "Share a spreadsheet with someone (view or edit).", ["spreadsheet_id", "email", "role"], True),
    ]),
    "zoom": ("Zoom", "Video meetings: schedule, recordings, transcripts, webinars.", [
        ("list_meetings", "List upcoming Zoom video meetings.", ["from_date", "to_date"], False),
        ("create_meeting", "Schedule a Zoom video meeting and get its join link.", ["topic", "start_time", "duration_minutes", "invitees"], True),
        ("update_meeting", "Change the time or topic of a Zoom meeting.", ["meeting_id", "start_time", "topic"], True),
        ("delete_meeting", "Cancel a Zoom meeting.", ["meeting_id"], True),
        ("list_recordings", "List the cloud recordings of past Zoom meetings.", ["from_date"], False),
        ("get_transcript", "Get the transcript of a recorded Zoom meeting.", ["meeting_id"], False),
        ("get_meeting_summary", "Get the AI summary and action items of a past Zoom meeting.", ["meeting_id"], False),
        ("create_webinar", "Schedule a Zoom webinar with a registration page.", ["topic", "start_time", "duration_minutes"], True),
    ]),
    "mailchimp": ("Mailchimp", "Email marketing: audiences, campaigns, newsletters, reports.", [
        ("list_audiences", "List the email marketing audiences (mailing lists).", [], False),
        ("add_subscriber", "Add a subscriber to an email marketing audience.", ["audience_id", "email", "tags"], True),
        ("unsubscribe_member", "Unsubscribe someone from a mailing list.", ["audience_id", "email"], True),
        ("list_campaigns", "List email marketing campaigns and their status.", ["status"], False),
        ("create_campaign", "Create a newsletter or email marketing campaign draft.", ["audience_id", "subject", "content"], True),
        ("send_test_email", "Send a test version of a campaign to an address.", ["campaign_id", "email"], True),
        ("schedule_campaign", "Schedule an email marketing campaign for a date and time.", ["campaign_id", "send_at"], True),
        ("send_campaign", "Send an email marketing campaign to its whole audience now.", ["campaign_id"], True),
        ("get_campaign_report", "Show a campaign's open rate, click rate and unsubscribes.", ["campaign_id"], False),
        ("create_segment", "Create an audience segment from subscriber tags or activity.", ["audience_id", "name", "conditions"], True),
    ]),
    "twilio": ("Twilio", "Phone and SMS: text messages, calls, phone numbers.", [
        ("send_sms", "Send an SMS text message to a phone number.", ["to", "body"], True),
        ("list_messages", "List sent and received SMS text messages.", ["to", "since"], False),
        ("make_call", "Place an automated phone call that plays a message.", ["to", "message"], True),
        ("list_calls", "List incoming and outgoing phone calls and their duration.", ["since"], False),
        ("list_phone_numbers", "List the phone numbers owned by the account.", [], False),
        ("lookup_phone_number", "Check a phone number's carrier and line type.", ["phone_number"], False),
    ]),
    "dropbox": ("Dropbox", "File storage and sharing: files, folders, shared links.", [
        ("search_files", "Search files and folders in Dropbox.", ["query"], False),
        ("list_folder", "List the contents of a Dropbox folder.", ["path"], False),
        ("upload_file", "Upload a file to Dropbox.", ["path", "content_url"], True),
        ("download_file", "Download a file from Dropbox.", ["path"], False),
        ("create_folder", "Create a folder in Dropbox.", ["path"], True),
        ("create_shared_link", "Create a shareable link to a Dropbox file or folder.", ["path", "expires_at"], True),
        ("move_file", "Move or rename a file in Dropbox.", ["from_path", "to_path"], True),
        ("delete_file", "Delete a file or folder from Dropbox.", ["path"], True),
    ]),
    "docusign": ("DocuSign", "Electronic signatures: envelopes, templates, signing status.", [
        ("send_envelope", "Send a document (contract) to be signed electronically.", ["document_url", "signer_email", "subject"], True),
        ("list_envelopes", "List documents sent for signature and their status.", ["status", "since"], False),
        ("get_envelope_status", "Check whether a document has been signed, and by whom.", ["envelope_id"], False),
        ("void_envelope", "Cancel (void) a document sent for signature.", ["envelope_id", "reason"], True),
        ("resend_envelope", "Send a signature reminder for a document still unsigned.", ["envelope_id"], True),
        ("list_templates", "List reusable contract templates for signature.", ["query"], False),
        ("download_signed_document", "Download the completed signed document.", ["envelope_id"], False),
    ]),
    "google_maps": ("Google Maps", "Places, directions, travel time, geocoding.", [
        ("search_places", "Find places (restaurants, shops, offices) near a location.", ["query", "location", "radius"], False),
        ("get_directions", "Get driving, walking or transit directions between two places.", ["origin", "destination", "mode"], False),
        ("get_travel_time", "Estimate the travel time between two addresses.", ["origin", "destination", "departure_time"], False),
        ("geocode_address", "Convert a street address into GPS coordinates.", ["address"], False),
        ("reverse_geocode", "Find the street address of GPS coordinates.", ["latitude", "longitude"], False),
        ("get_place_details", "Show a place's opening hours, phone number and rating.", ["place_id"], False),
    ]),
    "trello": ("Trello", "Kanban boards: boards, lists, cards, checklists.", [
        ("list_boards", "List the user's Trello boards.", [], False),
        ("create_board", "Create a new Trello board.", ["name", "workspace"], True),
        ("list_cards", "List the cards of a Trello board or list.", ["board", "list"], False),
        ("create_card", "Add a card to a list on a Trello board.", ["board", "list", "name", "due_date"], True),
        ("move_card", "Move a Trello card to another list (e.g. from Doing to Done).", ["card_id", "list"], True),
        ("update_card", "Change a Trello card's title, description or due date.", ["card_id", "name", "due_date"], True),
        ("add_checklist", "Add a checklist to a Trello card.", ["card_id", "title", "items"], True),
        ("add_label", "Add a colored label to a Trello card.", ["card_id", "label"], True),
        ("assign_member", "Assign a member to a Trello card.", ["card_id", "member"], True),
        ("archive_card", "Archive a Trello card.", ["card_id"], True),
    ]),
}

# Product names that explicitly designate a server in a message. Default: the lowercase label.
# Only product names, never generic nouns ("weather", "calendar", "drive" alone would also match
# "drive from Lyon to Grenoble"): a mention restricts routing to the server.
ALIASES = {
    "openweather": ["openweather"],
    "google_drive": ["google drive", "the drive", "my drive", "shared drive"],
}

EXTRA_USERS = [{"id": 6, "name": "Support lead (Zendesk, Shopify, Twilio, Mailchimp)"}]

EXTRA_CONNECTED = {
    1: ["trello"],
    2: ["hubspot", "quickbooks", "docusign", "zoom"],
    3: list(EXTRA_SERVERS),
    5: ["google_sheets"],
    6: ["zendesk", "shopify", "twilio", "mailchimp"],
}


def build(core_only: bool = False) -> dict:
    """Full catalog (core + extra servers), or the original core catalog for comparisons."""
    catalog = dict(SERVERS) if core_only else {**SERVERS, **EXTRA_SERVERS}
    connected = {uid: list(keys) for uid, keys in CONNECTED.items()}
    users = list(USERS)
    if not core_only:
        users += EXTRA_USERS
        for uid, keys in EXTRA_CONNECTED.items():
            connected.setdefault(uid, []).extend(keys)

    servers, tools = [], []
    for key, (label, desc, tool_list) in catalog.items():
        servers.append(
            {
                "key": key,
                "label": label,
                "description": desc,
                "aliases": ALIASES.get(key, [label.lower()]),
                "naming_convention": "explicit_typed",
                "is_native": False,
            }
        )
        for name, tool_desc, params, destructive in tool_list:
            tools.append(
                {
                    "mcp_key": key,
                    "tool_name": name,
                    "description": tool_desc,
                    "input_schema": {
                        "type": "object",
                        "properties": {p: {"type": "string"} for p in params},
                        # list_* parameters are optional filters; other tools need their first parameter.
                        "required": [] if name.startswith("list_") else params[:1],
                    },
                    "is_destructive": destructive,
                }
            )
    connections = [
        {"user_id": uid, "mcp_key": key, "status": "connected"} for uid, keys in connected.items() for key in keys
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
        "users": users,
        "mcp_user_connections": connections,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--core-only", action="store_true", help="only the 9 core servers (73 tools), for comparisons")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    data = build(core_only=args.core_only)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(data['mcp_servers'])} MCP servers, {len(data['mcp_tools'])} tools -> {out}")
