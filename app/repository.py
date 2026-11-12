"""Access to MCP data from the mock data file (no database).

Replaces the `mcp_servers`, `mcp_tools` and `mcp_user_connections` tables of a
database. The JSON file is reloaded automatically when it changes on disk
(mtime), so the mock data can be edited without restarting the server.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings


@dataclass(frozen=True)
class McpServer:
    key: str
    label: str
    description: str = ""
    naming_convention: str = "unknown"
    is_native: bool = False
    # Product names that explicitly designate this server in a message ("notion", "google drive").
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class McpTool:
    mcp_key: str
    tool_name: str
    description: str
    input_schema: dict = field(default_factory=dict)
    is_destructive: bool = False


@dataclass(frozen=True)
class McpUserConnection:
    user_id: int
    mcp_key: str
    status: str  # "connected" | "error" | "disconnected"


def normalize_mcp_key(mcp_key: str) -> str:
    return mcp_key.strip().lower()


class MockRepository:
    def __init__(self, path: str | Path | None = None):
        self._path = Path(path or settings.MOCK_DATA_PATH)
        self._lock = threading.Lock()
        self._mtime: float | None = None
        self._data: dict = {}

    def _ensure_loaded(self) -> dict:
        with self._lock:
            mtime = self._path.stat().st_mtime
            if mtime != self._mtime:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
                self._mtime = mtime
            return self._data

    def list_servers(self) -> list[McpServer]:
        return [
            McpServer(
                key=s["key"],
                label=s.get("label", s["key"]),
                description=s.get("description", ""),
                naming_convention=s.get("naming_convention", "unknown"),
                is_native=bool(s.get("is_native", False)),
                # Default alias: the product label ("Google Drive" -> "google drive").
                aliases=tuple(a.lower() for a in s.get("aliases") or [s.get("label", s["key"])]),
            )
            for s in self._ensure_loaded().get("mcp_servers", [])
        ]

    def list_tools(self, mcp_key: str | None = None) -> list[McpTool]:
        wanted = normalize_mcp_key(mcp_key) if mcp_key else None
        return [
            McpTool(
                mcp_key=t["mcp_key"],
                tool_name=t["tool_name"],
                description=t.get("description") or "",
                input_schema=t.get("input_schema") or {},
                is_destructive=bool(t.get("is_destructive", False)),
            )
            for t in self._ensure_loaded().get("mcp_tools", [])
            if wanted is None or normalize_mcp_key(t["mcp_key"]) == wanted
        ]

    def list_users(self) -> list[dict]:
        return list(self._ensure_loaded().get("users", []))

    def list_connections(self, user_id: int) -> list[McpUserConnection]:
        return [
            McpUserConnection(user_id=c["user_id"], mcp_key=c["mcp_key"], status=c["status"])
            for c in self._ensure_loaded().get("mcp_user_connections", [])
            if c["user_id"] == user_id
        ]

    def get_allowed_mcps(self, user_id: int) -> list[str]:
        """Native MCPs UNION the MCPs the user is `connected` to.

        'error' and 'disconnected' mean "not allowed", exactly like a missing row.
        """
        keys = {normalize_mcp_key(s.key) for s in self.list_servers() if s.is_native}
        keys |= {
            normalize_mcp_key(c.mcp_key) for c in self.list_connections(user_id) if c.status == "connected"
        }
        return sorted(keys)


repository = MockRepository()
