"""Orchestrator configuration (environment variables / .env file)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_APP_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Data source (replaces a database).
    MOCK_DATA_PATH: str = str(_APP_DIR / "data" / "mock_data.json")

    # Embeddings: "local" (sentence-transformers) or "openai".
    EMBEDDING_PROVIDER: str = "local"
    # Multilingual model: handles English and other languages.
    EMBEDDING_MODEL_NAME: str = "paraphrase-multilingual-MiniLM-L12-v2"
    OPENAI_API_KEY: str | None = None
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_MAX_RETRIES: int = 2

    # FAISS indexes persisted on disk (one sub-folder per mcp_key).
    ORCH_INDEX_DIR: str = "./data/orchestrator"

    # Routing thresholds (see `scripts/evaluate.py --sweep` to recalibrate them).
    THRESHOLD_MCP: float = 0.20
    THRESHOLD_TOOL: float = 0.28
    # A NON-connected MCP is only suggested if one of its TOOLS exceeds this threshold.
    THRESHOLD_SUGGEST: float = 0.40
    MAX_SUGGESTED_MCPS: int = 1
    # "what is X", "why can't you" -> forces direct_answer.
    KNOWLEDGE_GUARD_ENABLED: bool = True

    # Routing improvements (each can be switched off; scripts/ablation.py measures them).
    # Prefix every embedded tool text with its server name ("Zendesk. get ticket ...").
    # OFF by default: measured with this embedding model, it does not help (light version) or hurts
    # (with the domain description), see reports/ablation.md. Kept to re-test with other models.
    SERVER_CONTEXT_IN_TOOL_TEXT: bool = False
    # Also add the server's domain description ("Zendesk. Customer support: tickets, ... get ticket").
    SERVER_CONTEXT_INCLUDE_DOMAIN: bool = True
    # A server named in the message ("in Notion", "on Slack", "#general") restricts routing to it.
    EXPLICIT_MENTION_ENABLED: bool = True
    # Tool threshold inside an explicitly named server (the mention is evidence in itself).
    THRESHOLD_TOOL_MENTIONED: float = 0.20
    # Keyword (BM25) boost added to the semantic score of a tool; 0 disables keyword search.
    LEXICAL_WEIGHT: float = 0.15


settings = Settings()
