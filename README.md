# DRACO — The Book-Forged Code Oracle

> The smartest coding AI you can **prove**. DRACO answers coding, Linux, systems, and
> security questions using retrieval (BM25 RAG) over **hundreds of real technical books**
> — the coding canon and the hacker's shelf — and cites the exact book behind every
> answer. Talk to it in the browser, call the REST API, or summon it as an **MCP tool**
> from Claude, GPT, or any agent.

- **Live:** https://draco.thetempleofdoom.com
- **Repo:** http://10.30.20.149:3000/drjones/draco
- **Host:** Proxmox CT 174 `draco` @ `10.30.20.12` (Debian 13, 4GB RAM / 4 cores)
- **LLM:** `ornith-1.5:9b-64k` on bare-metal Ollama @ `10.30.20.29` (nightmare, 4090S) — abliterated/heretic lineage, zero-spill resident
- **Stack:** Flask + BM25 (rank_bm25 + Snowball stem) + SSE streaming + BTCPay + MCP streamable-http

---

## Why "book-forged"

Most assistants guess. DRACO retrieves. Every question is embedded-scanned against the
full library (BM25 over stemmed tokens), the top passages are stuffed into the prompt,
and the model must cite them `[n]`. The response includes a `sources` array —
**check the receipts yourself**. That's the proof behind the homepage brag.

## Architecture

```
                    ┌────────────────────── CT 174 "draco" (10.30.20.12) ─────────────────────┐
                    │  nginx :80 ──► gunicorn :8012 (app.py + FastMCP mounted at /mcp)        │
browser ── CF tunnel│                                        │                                │
agent  ──► /mcp ────┤   /api/chat (SSE)  /api/ask  /api/search  /api/signup  /webhook/btcpay  │
                    │                                        │                                │
                    │   draco_core: BM25 index (~N chunks)   │  sqlite: users/credits/payments│
                    │        │                               │                                │
                    │   /opt/books: original pdf/chm/djvu + text/ + manifest.json + index/     │
                    └────────────────────────────────────────┼────────────────────────────────┘
                                                             ▼
                                    Ollama ornith-1.5:9b-64k @ 10.30.20.29:11434 (bare metal)
```

## The library

| Collection | Contents | Source |
|---|---|---|
| `library_linux` | The coding canon: C/C++, Python, Perl, PHP, Java, assembly, SQL, web, Unix/Linux internals, networks & security, math, Apache | `/Volumes/sanD/library linux` |
| `hackerpack` | Hacker Pro Pack: exploitation, malware, network attacks, crypto, wireless, scene classics | `/Volumes/sanD/dw stuff 3/hacking/HACKER PRO PACK books` |

**Conversion pipeline** (`ingest.py`, runs on the CT):

```
pdf   → pdftotext -layout        (poppler-utils)
chm   → extract_chmLib → walk html/txt → strip tags → unescape
djvu  → djvutxt                  (djvulibre-bin)
txt   → passthrough
then: null-strip, whitespace collapse, <200 chars = scanned junk → dropped
→ /opt/books/text/<category>/<id>_<slug>.txt + manifest.json (id/title/category/chars/…)
```

**Index** (`build_index.py`): 300-token chunks, 60 overlap → Snowball-stem → `BM25Okapi`
→ `index/index.pkl` + `chunks.json`. Rebuild = re-run both scripts; app picks up on restart.

---

## Web UI

| Route | What |
|---|---|
| `/` | Hero (the brag, with live library stats) + **chat** — 10 free questions/day/IP, streaming, sources bar under every answer |
| `/library` | The whole hoard, filterable, every book **downloadable** |
| `/pricing` | Credit packs, Bitcoin-only |
| `/api` | Key signup + copy-paste curl examples |
| `/health` | `{"status":"ok","llm":true,"model":...,"books":...,"chunks":...}` |

## REST API

Auth: `X-API-Key` header (or `api_key` JSON field). Free tier = 30 credits/month (email signup). Credits never expire.

```bash
# get a key
curl -s -X POST https://draco.thetempleofdoom.com/api/signup \
  -d '{"email":"you@domain.tld"}'
# → {"api_key":"sk-draco-..."}

# ask (RAG + citations) — 1 credit
curl -s -X POST https://draco.thetempleofdoom.com/api/ask \
  -H 'X-API-Key: sk-draco-...' -H 'Content-Type: application/json' \
  -d '{"q":"explain the ret2libc technique with a minimal poc"}'
# → {"answer":"...[1]...[2]","sources":[{"title":"...","category":"hackerpack",...}]}

# raw BM25 passage search — 1 credit
curl -s "https://draco.thetempleofdoom.com/api/search?q=tcp%20syn%20flood&k=5" \
  -H 'X-API-Key: sk-draco-...'

# usage / credits
curl -s https://draco.thetempleofdoom.com/api/my-usage -H 'X-API-Key: sk-draco-...'

# buy credits (Bitcoin via BTCPay) → checkout_url
curl -s -X POST https://draco.thetempleofdoom.com/api/create-invoice \
  -H 'X-API-Key: sk-draco-...' -d '{"plan":"crate"}'
```

| Code | Meaning |
|---|---|
| 200 | answer + sources |
| 401 | missing/invalid key |
| 402 | out of credits (free tier exhausted) |
| 429 | web anon limit (10/day) hit |
| 503 | Ollama unreachable |

## MCP — summon as a tool call

**Remote (any MCP client, zero install):**

```json
{ "mcpServers": { "draco": { "url": "https://draco.thetempleofdoom.com/mcp" } } }
```

Tools: `draco_ask(question)` → cited answer · `draco_search(query, k)` → raw passages ·
`draco_status()` → health + library stats.

Streamable-http at `/mcp`. Smoke test by hand:

```bash
curl -s https://draco.thetempleofdoom.com/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"x","version":"1"}}}'
```

**Local stdio client for your own machine** — `mcp_client.py` in this repo (talks to the
remote HTTP MCP; usable from Claude Desktop via `mcp-remote` or any stdio bridge).

Machine-readable discovery: `/llms.txt`, `/llms-full.txt`, `/openapi.json`,
`/.well-known/ai-plugin.json`, `/.well-known/mcp-server.json`, `robots.txt` (all AI crawlers allowed), `/sitemap.xml`.

## Pricing (Bitcoin only, BTCPay, no KYC)

| Tier | Price | Gets |
|---|---|---|
| Web anon | free | 10 questions/day in browser |
| Free API key | free | 30 credits/month |
| **satchel** | $3 | 60 credits |
| **crate** | $10 | 250 credits |
| **hoard** | $25 | 750 credits |

1 credit = 1 ask or 1 search. Credits never expire. Invoice webhook (`/webhook/btcpay?wh=<secret>`)
credits the key on `InvoiceSettled`. Books are always free to download — we sell answers, not files.

## Deploy runbook (CT 174)

```bash
# code push — the golden path
cd ~/draco && tar czf /tmp/d.tar.gz *.py config.json requirements.txt
scp /tmp/d.tar.gz root@10.30.20.85:/tmp/
ssh root@10.30.20.85 "pct push 174 /tmp/d.tar.gz /tmp/d.tar.gz"
ssh root@10.30.20.85 "pct exec 174 -- bash -c 'cd /opt/draco && tar xzf /tmp/d.tar.gz && systemctl restart draco'"
curl -s https://draco.thetempleofdoom.com/health

# rebuild the corpus (books → text → index) on the CT
ssh root@10.30.20.85 "pct exec 174 -- systemd-run --unit=draco-ingest \
  bash -c 'cd /opt/draco && ./venv/bin/python3 ingest.py && ./venv/bin/python3 build_index.py && systemctl restart draco'"
```

Layout on CT: `/opt/draco` (code, venv, draco.db) · `/opt/books` (books + text/ + index/) ·
services `draco.service` + `nginx` · gunicorn binds 127.0.0.1:8012.

## Verify everything (the checklist that was actually run)

```bash
curl -s https://draco.thetempleofdoom.com/health          # llm:true, books>0
curl -s https://draco.thetempleofdoom.com/llms.txt        # starts with "# DRACO"
curl -s https://draco.thetempleofdoom.com/robots.txt      # GPTBot + Allow: /
curl -s https://draco.thetempleofdoom.com/api/library | jq .count
curl -s https://draco.thetempleofdoom.com/api/search?q=nmap -H 'X-API-Key: <key>'   # hits
# MCP handshake + tools/call against /mcp
```

## Notes

- Security content is for **education and authorized testing only**.
- `config.json` carries runtime knobs (model, k, limits, plans, BTCPay) — admin key +
  BTCPay store creds live there on the CT, **never** in the repo (config.json is
  git-ignored; a sanitized `config.example.json` is tracked).
- Books retain their original copyrights; the library is shared for personal use.
