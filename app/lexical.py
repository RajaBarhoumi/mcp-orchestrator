"""Keyword search (BM25) over the tool texts, and explicit server mentions.

Embeddings capture meaning but give little weight to the one word that settles a
question: a product name ("Notion", "Dropbox") or a distinctive term ("newsletter",
"VAT", "transcript"). Two complementary keyword signals fix that:

- `BM25Index`: classic keyword relevance, turned into a bounded boost added to the
  semantic score of each tool (see `lexical_boost`);
- `find_mentions`: servers explicitly named in the message ("on Slack", "#general",
  "in the Drive"), which restrict routing to those servers.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "for", "with", "by", "from", "as", "is",
    "are", "be", "it", "its", "this", "that", "these", "those", "my", "our", "your", "me", "we", "you",
    "i", "do", "does", "did", "can", "could", "please", "what", "which", "who", "how", "when", "where",
    "all", "any", "some", "into", "about", "s", "t", "parameters",
}

# BM25 parameters (standard values) and saturation of the boost: raw / (raw + K) is in [0, 1).
_K1, _B, _SATURATION = 1.2, 0.75, 5.0


def tokenize(text: str) -> list[str]:
    """Lowercase words without stopwords, with a light plural stemming ("invoices" -> "invoice")."""
    out = []
    for word in _WORD.findall(text.lower().replace("_", " ")):
        if word in _STOPWORDS:
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        out.append(word)
    return out


class BM25Index:
    def __init__(self, documents: dict[str, str]):
        """`documents`: {tool namespaced name: embedded text}."""
        self._docs = {name: Counter(tokenize(text)) for name, text in documents.items()}
        self._lengths = {name: sum(tf.values()) for name, tf in self._docs.items()}
        self._avg_length = (sum(self._lengths.values()) / len(self._lengths)) if self._lengths else 0.0
        df = Counter(term for tf in self._docs.values() for term in tf)
        n = len(self._docs)
        self._idf = {term: math.log(1 + (n - count + 0.5) / (count + 0.5)) for term, count in df.items()}

    def scores(self, query: str) -> dict[str, float]:
        """Raw BM25 score of every tool sharing at least one term with the query."""
        terms = set(tokenize(query)) & self._idf.keys()
        out: dict[str, float] = {}
        if not terms:
            return out
        for name, tf in self._docs.items():
            score = 0.0
            norm = _K1 * (1 - _B + _B * self._lengths[name] / self._avg_length)
            for term in terms:
                freq = tf.get(term)
                if freq:
                    score += self._idf[term] * freq * (_K1 + 1) / (freq + norm)
            if score:
                out[name] = score
        return out


def lexical_boost(raw_score: float) -> float:
    """Map a raw BM25 score to [0, 1): one rare matching word gives about 0.5."""
    return raw_score / (raw_score + _SATURATION)


# Product conventions that name a server without saying its name.
_SLACK_CHANNEL = re.compile(r"(?<![\w&])#[a-z][a-z0-9_-]+", re.IGNORECASE)  # "#general", never "#1001"
_ISSUE_KEY = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")  # "PROJ-12"
_ISSUE_WORD = re.compile(r"\b(ticket|issue|story|bug|epic)s?\b", re.IGNORECASE)


def find_mentions(query: str, servers) -> set[str]:
    """Keys of the servers explicitly designated by the message.

    A server is designated by one of its aliases (product names, whole words only), or by a
    product convention: a Slack channel ("#general"), or a Jira-style key next to an issue
    word ("ticket PROJ-12"; "invoice INV-2031" alone does not count).
    """
    text = query.lower()
    found = set()
    keys = set()
    for server in servers:
        keys.add(server.key)
        for alias in server.aliases:
            if re.search(rf"(?<![\w-]){re.escape(alias)}(?![\w-])", text):
                found.add(server.key)
                break
    if "slack" in keys and _SLACK_CHANNEL.search(query):
        found.add("slack")
    if "jira" in keys and _ISSUE_KEY.search(query) and _ISSUE_WORD.search(query):
        found.add("jira")
    return found
