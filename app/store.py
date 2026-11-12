"""FAISS vector indexes of MCP tools, one per `mcp_key`.

Per MCP: a FAISS index (IndexFlatIP = cosine on normalized vectors), parallel
metadata, raw vectors, a centroid (re-normalized mean) and a `catalog_hash`
(so only modified catalogs get re-embedded).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np

from app import embedding
from app.config import settings
from app.lexical import BM25Index, lexical_boost

_MANIFEST_FILENAME = "manifest.json"


@dataclass
class _McpEntry:
    index: faiss.IndexFlatIP
    # metadatas[i] describes the tool whose vector is at position i in `index`.
    metadatas: list[dict]
    vectors: np.ndarray
    centroid: np.ndarray
    catalog_hash: str


def _compute_centroid(vectors: np.ndarray, dim: int) -> np.ndarray:
    """Mean of the vectors, re-normalized so it stays comparable to tool scores."""
    if vectors.shape[0] == 0:
        return np.zeros(dim, dtype=np.float32)
    centroid = vectors.mean(axis=0)
    norm = np.linalg.norm(centroid)
    return (centroid / norm if norm else centroid).astype(np.float32)


class VectorStore:
    def __init__(self, index_dir: str | Path | None = None):
        self._index_dir = Path(index_dir) if index_dir is not None else Path(settings.ORCH_INDEX_DIR)
        self._entries: dict[str, _McpEntry] = {}
        self._lexical: BM25Index | None = None  # keyword index over all tools, rebuilt lazily

    def lexical_scores(self, query: str) -> dict[str, float]:
        """Keyword boost in [0, 1) for every tool sharing words with `query` (BM25, all servers)."""
        if self._lexical is None:
            self._lexical = BM25Index(
                {m["namespaced_name"]: m.get("text") or m["description"] for e in self._entries.values() for m in e.metadatas}
            )
        return {name: lexical_boost(raw) for name, raw in self._lexical.scores(query).items()}

    def replace_mcp(self, mcp_key: str, vectors: np.ndarray, metadatas: list[dict], catalog_hash: str) -> None:
        """Atomically replace the state of ONE MCP (never append to the old index)."""
        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        if vectors.shape[0] != len(metadatas):
            raise ValueError(f"replace_mcp({mcp_key!r}): {vectors.shape[0]} vectors for {len(metadatas)} metadata entries")

        dim = int(vectors.shape[1]) if vectors.shape[0] > 0 else embedding.get_embedding_dim()
        # Exact (brute-force) search: fast enough for catalogs of a few hundred tools.
        index = faiss.IndexFlatIP(dim)
        if vectors.shape[0] > 0:
            index.add(vectors)

        self._entries[mcp_key] = _McpEntry(
            index=index,
            metadatas=list(metadatas),
            vectors=vectors,
            centroid=_compute_centroid(vectors, dim),
            catalog_hash=catalog_hash,
        )
        self._lexical = None

    def remove_mcp(self, mcp_key: str) -> bool:
        """Purge an MCP from memory and disk. Idempotent: returns False if absent."""
        removed = self._entries.pop(mcp_key, None) is not None
        self._lexical = None
        mcp_dir = self._index_dir / mcp_key
        if mcp_dir.is_dir():
            shutil.rmtree(mcp_dir, ignore_errors=True)
            removed = True
        if removed:
            self.save()
        return removed

    def keys(self) -> list[str]:
        return list(self._entries)

    def get_hash(self, mcp_key: str) -> str | None:
        entry = self._entries.get(mcp_key)
        return entry.catalog_hash if entry is not None else None

    def search_centroids(self, qvec: np.ndarray) -> list[tuple[str, float]]:
        """Query <-> centroid score for EVERY indexed MCP, sorted descending.

        Includes MCPs the user is not connected to: the router needs their
        scores to suggest a connection.
        """
        qvec = np.asarray(qvec, dtype=np.float32).reshape(-1)
        scores = [(key, float(np.dot(entry.centroid, qvec))) for key, entry in self._entries.items()]
        scores.sort(key=lambda pair: pair[1], reverse=True)
        return scores

    def search_tools(self, qvec: np.ndarray, mcp_key: str, k: int) -> list[dict]:
        """Top-K tools of `mcp_key` (descending score)."""
        entry = self._entries.get(mcp_key)
        if entry is None or entry.index.ntotal == 0:
            return []
        qvec = np.ascontiguousarray(qvec, dtype=np.float32).reshape(1, -1)
        scores, indices = entry.index.search(qvec, min(k, entry.index.ntotal))
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            result = dict(entry.metadatas[idx])
            result["score"] = float(score)
            results.append(result)
        return results

    def save(self) -> None:
        self._index_dir.mkdir(parents=True, exist_ok=True)
        for mcp_key, entry in self._entries.items():
            mcp_dir = self._index_dir / mcp_key
            mcp_dir.mkdir(parents=True, exist_ok=True)
            faiss.write_index(entry.index, str(mcp_dir / "index.faiss"))
            np.save(mcp_dir / "vectors.npy", entry.vectors)
            (mcp_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "catalog_hash": entry.catalog_hash,
                        "metadatas": entry.metadatas,
                        # Model identity: an index built with another model is unusable.
                        "embedding_model": embedding.get_active_model_name(),
                        "embedding_dim": embedding.get_embedding_dim(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        (self._index_dir / _MANIFEST_FILENAME).write_text(
            json.dumps({key: entry.catalog_hash for key, entry in self._entries.items()}), encoding="utf-8"
        )

    def load(self) -> None:
        """Reload from disk; skip indexes built with a different embedding model."""
        self._entries = {}
        self._lexical = None
        if not self._index_dir.exists():
            return
        active_model = embedding.get_active_model_name()
        active_dim = embedding.get_embedding_dim()
        for mcp_dir in sorted(p for p in self._index_dir.iterdir() if p.is_dir()):
            paths = [mcp_dir / "index.faiss", mcp_dir / "vectors.npy", mcp_dir / "metadata.json"]
            if not all(p.exists() for p in paths):
                continue
            payload = json.loads(paths[2].read_text(encoding="utf-8"))
            if payload.get("embedding_model") != active_model or payload.get("embedding_dim") != active_dim:
                continue
            index = faiss.read_index(str(paths[0]))
            vectors = np.load(paths[1])
            self._entries[mcp_dir.name] = _McpEntry(
                index=index,
                metadatas=payload["metadatas"],
                vectors=vectors,
                centroid=_compute_centroid(vectors, vectors.shape[1] if vectors.shape[0] else index.d),
                catalog_hash=payload["catalog_hash"],
            )

    def stats(self) -> dict[str, dict]:
        return {key: {"tools": entry.index.ntotal, "hash": entry.catalog_hash} for key, entry in self._entries.items()}


store = VectorStore()
