"""Normalization of MCP tool JSON Schemas (OpenAI function-calling compatible)."""

from __future__ import annotations

from copy import deepcopy


def normalize_input_schema(schema: dict | None) -> dict:
    """Non-object `properties` -> {}, non-list `required` -> [], missing `type` -> "object"."""
    if not schema or not isinstance(schema, dict):
        return {"type": "object", "properties": {}, "required": []}
    normalized = deepcopy(schema)
    if not isinstance(normalized.get("properties"), dict):
        normalized["properties"] = {}
    if not isinstance(normalized.get("required"), list):
        normalized["required"] = []
    if not normalized.get("type"):
        normalized["type"] = "object"
    return normalized
