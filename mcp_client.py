#!/usr/bin/env python3
"""DRACO stdio MCP client — bridges DRACO's remote /mcp into any stdio MCP host.

Register with Claude Desktop / Hermes:
  draco-search:
    command: python3
    args: [/path/to/mcp_client.py]
    env:
      DRACO_MCP_URL: "https://draco.thetempleofdoom.com/mcp"
"""
import asyncio, json, os, sys
import urllib.request

MCP_URL = os.environ.get("DRACO_MCP_URL", "https://draco.thetempleofdoom.com/mcp")

def rpc(method, params=None, session=None, notify=False):
    body = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        body["params"] = params
    if not notify:
        body["id"] = 1
    req = urllib.request.Request(MCP_URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json, text/event-stream",
                                          **({"mcp-session-id": session} if session else {})})
    resp = urllib.request.urlopen(req, timeout=120)
    sid = resp.headers.get("mcp-session-id")
    raw = resp.read().decode()
    if not notify:
        for line in raw.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:]), sid
        return (json.loads(raw) if raw.strip() else {}), sid
    return None, sid

def parse_sse_text(raw):
    for line in raw.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    return json.loads(raw) if raw.strip() else {}

def call_tool(name, args):
    _, sid = rpc("initialize", {"protocolVersion": "2025-03-26",
                                "capabilities": {},
                                "clientInfo": {"name": "draco-stdio", "version": "1"}})
    rpc("notifications/initialized", {}, session=sid, notify=True)
    body = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                       "params": {"name": name, "arguments": args}}).encode()
    req = urllib.request.Request(MCP_URL, data=body,
                                 headers={"Content-Type": "application/json",
                                          "Accept": "application/json, text/event-stream",
                                          "mcp-session-id": sid})
    resp = urllib.request.urlopen(req, timeout=180)
    result = parse_sse_text(resp.read().decode())
    out = result.get("result", {}).get("content", [])
    return "\n".join(c.get("text", "") for c in out if c.get("type") == "text")

async def main():
    from mcp.server import Server
    from mcp.server.stdio import stdio_server

    server = Server("draco")

    @server.tool()
    async def draco_ask(question: str) -> str:
        """Ask DRACO a coding/security question — grounded in hundreds of real books, cited."""
        return call_tool("draco_ask", {"question": question})

    @server.tool()
    async def draco_search(query: str, k: int = 8) -> str:
        """Search DRACO's book library (BM25) for passages."""
        return call_tool("draco_search", {"query": query, "k": k})

    @server.tool()
    async def draco_status() -> str:
        """DRACO health + library size."""
        return call_tool("draco_status", {})

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--direct":
        print(call_tool(sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}))
    else:
        asyncio.run(main())
