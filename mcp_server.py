#!/usr/bin/env python3
"""DRACO MCP server — standalone streamable-http ASGI app on :8013.
Run:  uvicorn mcp_server:app --host 127.0.0.1 --port 8013   (or python3 mcp_server.py)
nginx routes /mcp here; Flask keeps :8012.
"""
import os

from mcp.server.fastmcp import FastMCP

import draco_core as core
from draco_core import CFG

MCP_PORT = int(os.environ.get("DRACO_MCP_PORT", 8013))

mcp = FastMCP("draco", host="127.0.0.1", port=MCP_PORT, streamable_http_path="/mcp")


@mcp.tool()
def draco_ask(question: str) -> str:
    """Ask DRACO a coding or security question. Answers are grounded in hundreds of
    real programming and hacking books, with [n] citations and source titles."""
    prompt, hits = core.build_prompt(question, k=CFG.get("rag_k", 6))
    try:
        answer = core.ask_ollama(prompt)
    except Exception as e:
        return f"Model offline: {e}"
    src = "\n".join(f"[{i+1}] {h['title']} ({h['category']})" for i, h in enumerate(hits))
    return f"{answer}\n\nSOURCES:\n{src}"


@mcp.tool()
def draco_search(query: str, k: int = 8) -> str:
    """Search DRACO's book library (BM25) for passages matching a topic."""
    hits = core.search_library(query, k=max(1, min(k, 25)))
    if not hits:
        return "No passages matched."
    return "\n\n".join(
        f"[{h['title']} · {h['category']} · score {h['score']}]\n{h['text'][:600]}"
        for h in hits)


@mcp.tool()
def draco_status() -> str:
    """DRACO health + library size."""
    s = core.get_stats()
    return (f"DRACO {CFG['model']} · {s['books']} books · {s['chunks']} passages · "
            f"API: {CFG['base_url']}/api · MCP: {CFG['base_url']}/mcp")


app = mcp.streamable_http_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=MCP_PORT, log_level="warning")
