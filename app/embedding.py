"""L2-normalized embeddings (dot product = cosine similarity).

Provider selected by `settings.EMBEDDING_PROVIDER`:
- "local"  -> sentence-transformers (`EMBEDDING_MODEL_NAME`), no API call;
- "openai" -> OpenAI embeddings API (`OPENAI_EMBEDDING_MODEL`).
"""

from __future__ import annotations

import numpy as np

from app.config import settings

# Known output sizes: avoids loading the model just to learn its dimension.
_KNOWN_DIMS: dict[str, int] = {
    "all-MiniLM-L6-v2": 384,
    "paraphrase-multilingual-MiniLM-L12-v2": 384,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
}

# Lazy singletons: created on first real use, not at import time.
_local_model = None
_openai_client = None
_dim_cache: int | None = None


def _get_local_model():
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer

        _local_model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
    return _local_model


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY, max_retries=settings.OPENAI_MAX_RETRIES)
    return _openai_client


def _normalize_l2(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0  # avoid dividing a zero vector by zero
    return vectors / norms


def embed_batch(texts: list[str]) -> np.ndarray:
    """List of texts -> float32 matrix (N, dim), L2-normalized."""
    if not texts:
        return np.empty((0, get_embedding_dim()), dtype=np.float32)

    if settings.EMBEDDING_PROVIDER == "local":
        vectors = _get_local_model().encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return vectors.astype(np.float32)

    if settings.EMBEDDING_PROVIDER == "openai":
        response = _get_openai_client().embeddings.create(model=settings.OPENAI_EMBEDDING_MODEL, input=texts)
        vectors = np.array([item.embedding for item in response.data], dtype=np.float32)
        return _normalize_l2(vectors)

    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {settings.EMBEDDING_PROVIDER!r} (expected 'local' or 'openai')")


def embed(text: str) -> np.ndarray:
    return embed_batch([text])[0]


def get_active_model_name() -> str:
    return settings.EMBEDDING_MODEL_NAME if settings.EMBEDDING_PROVIDER == "local" else settings.OPENAI_EMBEDDING_MODEL


def get_embedding_dim() -> int:
    global _dim_cache
    if _dim_cache is None:
        name = get_active_model_name()
        _dim_cache = _KNOWN_DIMS[name] if name in _KNOWN_DIMS else int(embed("dimension probe").shape[0])
    return _dim_cache
