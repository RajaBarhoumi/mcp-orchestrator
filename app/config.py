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


settings = Settings()
