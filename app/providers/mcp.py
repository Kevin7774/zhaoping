from __future__ import annotations


class MCPProviderProtocol:
    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        raise NotImplementedError
