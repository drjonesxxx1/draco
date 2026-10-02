# DRACO — The Book-Forged Code Oracle

> **Other AIs guess. DRACO knows — and proves it.**

DRACO answers coding, systems, and security questions using retrieval over a library of
**1,855 real technical books** (354M characters, 116,558 indexed passages) — and cites the
exact book behind every claim. No knowledge cutoff. No hallucination laundering. Receipts attached.

**Try it now:** https://draco.thetempleofdoom.com — 10 free questions a day, no signup.

---

## Why it's different

| Generic chatbot | DRACO |
|---|---|
| Compressed training-data recall | Live retrieval from 1,855 books on the shelf |
| "Trust me" answers | Every claim carries `[n]` citations + a `sources` array |
| Knowledge cutoff: yes | The canon is resident — K&R, Tanenbaum, the shellcoders' handbook |
| Sells your prompts | Self-hosted, zero telemetry, questions never leave the house |

## Quickstart

### Chat in the browser
https://draco.thetempleofdoom.com — streaming answers, visible reasoning, sources bar
under every response. 10 free/day, no account.

### REST API
```bash
# 1. Get a free key (30 credits/month, email only, no card)
curl -s -X POST https://draco.thetempleofdoom.com/api/signup \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@domain.tld"}'
# → {"api_key":"sk-draco-..."}

# 2. Ask — RAG-grounded answer with citations (1 credit)
curl -s -X POST https://draco.thetempleofdoom.com/api/ask \
  -H 'X-API-Key: sk-draco-...' -H 'Content-Type: application/json' \
  -d '{"q":"explain the ret2libc technique with a minimal poc"}'
# → {"answer":"...[1]...[2]","sources":[{"title":"...","category":"..."}]}

# 3. Raw passage search across all 1,855 books (1 credit)
curl -s "https://draco.thetempleofdoom.com/api/search?q=tcp%20syn%20flood&k=5" \
  -H 'X-API-Key: sk-draco-...'
```

### MCP — use it from Claude, GPT, or any agent
```json
{
  "mcpServers": {
    "draco": { "url": "https://draco.thetempleofdoom.com/mcp" }
  }
}
```

**Tools:**
- `draco_ask(question)` → cited, book-grounded answer
- `draco_search(query, k)` → raw BM25 passages with titles + scores
- `draco_status()` → live library stats

**Officially listed on the MCP registry:**
[`com.thetempleofdoom.draco/draco`](https://registry.modelcontextprotocol.io/servers/com.thetempleofdoom.draco/draco)

Manual MCP handshake:
```bash
curl -s https://draco.thetempleofdoom.com/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}'
```

## How it works

```
question ──► BM25 retrieval over 116k book passages
                │
                ▼
        top passages + question ──► local LLM (self-hosted GPU)
                │
                ▼
        answer with inline [n] citations + sources array
```

1. **Ingest** (`ingest.py`) — PDF/CHM/DJVU → clean plain text. Junk scans dropped automatically.
2. **Index** (`build_index.py`) — 300-token overlapping chunks → Snowball-stemmed BM25 index.
3. **Serve** (Flask + gunicorn) — retrieval-augmented generation with SSE streaming,
   separate reasoning and answer channels, and automatic degenerate-output detection/retry.
4. **Expose** — REST API, streamable-http MCP server, and a full agent-discovery kit:
   `/llms.txt`, `/llms-full.txt`, `/openapi.json`, `/.well-known/ai-plugin.json`,
   `/.well-known/mcp-server.json`, `/sitemap.xml`.

## Pricing

Bitcoin only. No subscription traps, no KYC, no card processor.

| Tier | Price | What you get |
|---|---|---|
| Web (no key) | **free** | 10 questions/day in the browser |
| API key | **free** | 30 credits/month, forever |
| satchel | $3 | 60 credits |
| crate | $10 | 250 credits |
| hoard pack | $25 | 750 credits |
| **HOARD** | **$50/mo** | **unlimited** — every ask, every search, 30 days |

1 credit = 1 ask or 1 search. Credits never expire. Books are free to download at
[/library](https://draco.thetempleofdoom.com/library) — we sell answers, not files.

## Self-hosting

```bash
git clone https://github.com/drjonesxxx1/draco.git
cd draco
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp config.example.json config.json   # set model, ollama URL, limits, payments

# point ingest.py at YOUR book directory, then:
./venv/bin/python3 ingest.py         # books → text + manifest
./venv/bin/python3 build_index.py    # text → BM25 index

./venv/bin/gunicorn -w 2 --threads 8 -b 127.0.0.1:8012 app:app    # API + web
./venv/bin/python3 -m uvicorn mcp_server:app --port 8013           # MCP
```

Any local Ollama model works. Put nginx in front (see `deploy/nginx-draco.conf` for
the reference config incl. SSE + MCP proxying). Payments are optional — leave the
`btcpay` block empty and the free tiers carry the whole thing.

## Repository layout

| File | Purpose |
|---|---|
| `app.py` | Flask: web UI, REST API, SSE chat, payments webhook, agent-discovery kit |
| `draco_core.py` | RAG engine, retrieval, LLM calls, metering, DB |
| `pages.py` / `pages2.py` | Theme |
| `mcp_server.py` | Standalone streamable-http MCP server |
| `mcp_client.py` | stdio bridge for Claude Desktop / local clients |
| `ingest.py` / `build_index.py` | Corpus pipeline |
| `test_splitter.py` | Unit tests for the reasoning/answer channel splitter |
| `deploy/` | systemd units + nginx config |

## Notes

- Security content is for **education and authorized testing only**.
- Books retain their original copyrights; the library is shared for personal use.
- No telemetry. No logs sold. Ever.
