#!/usr/bin/env python3
"""DRACO — The Book-Forged Code Oracle.
Flask app: home (hero + brag), library, pricing, API, MCP, SEO kit, RAG chat (SSE).
"""
import json, os, re
import requests as http
from flask import Flask, Response, jsonify, request, render_template_string, send_from_directory

import draco_core as core
from draco_core import CFG
from pages import PAGE_HOME, BASE_CSS, NAV
from pages2 import PAGE_LIBRARY, PAGE_PRICING, PAGE_API

app = Flask(__name__)

# ------------------------------------------------------------------ pages
def render(page, active):
    stats = core.get_stats()
    nav = NAV.replace("__ACTIVE__-" + active, "on")
    nav = re.sub(r"__ACTIVE__-\w+", "", nav)
    head = f"<style>{BASE_CSS}</style><nav>{nav}</nav>"
    page = page.replace("__STATS__", f"{stats['books']} books · {stats['chunks']:,} indexed passages · {stats['chars']/1e6:.0f}M chars")
    page = page.replace("__BASE__", CFG["base_url"])
    ctx = dict(books=f"{stats['books']:,}", chunks=f"{stats['chunks']:,}",
               mb=stats['chars'] // 1_000_000, free_day=CFG["anon_daily"],
               free_monthly=CFG["free_monthly"], plans=CFG["plans"], base=CFG["base_url"])
    return render_template_string(head + page, **ctx)

@app.route("/")
def home():
    return render(PAGE_HOME, "home")

@app.route("/library")
def library():
    return render(PAGE_LIBRARY, "library")

@app.route("/api/library")
def api_library():
    try:
        manifest = json.load(open(os.path.join(core.BOOKS_DIR, "manifest.json")))
    except Exception:
        manifest = []
    books = [{"id": m["id"], "title": m["title"][:90], "category": m["category"],
              "format": m["format"], "mb": round(m["bytes"] / 1e6, 1),
              "download": f"/download/{m['id']}"}
             for m in manifest if m.get("txt")]
    books.sort(key=lambda b: b["title"].lower())
    return jsonify(count=len(books), books=books)

@app.route("/download/<book_id>")
def download(book_id):
    try:
        manifest = json.load(open(os.path.join(core.BOOKS_DIR, "manifest.json")))
    except Exception:
        return jsonify(error="library offline"), 503
    m = next((x for x in manifest if x["id"] == book_id), None)
    if not m:
        return jsonify(error="unknown book"), 404
    return send_from_directory(core.BOOKS_DIR, m["source"], as_attachment=True)

@app.route("/pricing")
def pricing():
    return render(PAGE_PRICING, "pricing")

@app.route("/api")
def api_page():
    return render(PAGE_API, "api")

@app.route("/health")
def health():
    try:
        r = http.post(f"{CFG['ollama_url']}/api/generate", stream=True, timeout=4,
                      json={"model": CFG["model"], "prompt": "ping", "stream": True, "options": {"num_predict": 1}})
        llm = r.status_code == 200
    except Exception:
        llm = False
    return jsonify(status="ok", llm=llm, model=CFG["model"], **core.get_stats())

# ------------------------------------------------------------------ chat (web, SSE)
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}
    q = (data.get("q") or "").strip()
    if not q:
        return jsonify(error="Empty question."), 400
    key = data.get("api_key")
    user = None
    if key:
        user, err = core.auth_user(request)
        if err:
            return jsonify(error=err), 401
        ok, msg = core.consume(user, "chat", q[:80], core.client_ip(request))
        if not ok:
            return jsonify(error=msg), 402
    else:
        ip = core.client_ip(request)
        if not core.anon_allowed(ip):
            return jsonify(error=f"Free web limit reached ({CFG['anon_daily']}/day). "
                                 f"Sign up free at {CFG['base_url']}/api for {CFG['free_monthly']}/mo API credits."), 429

    prompt, hits = core.build_prompt(q, k=CFG.get("rag_k", 6))
    sources = [{"n": i + 1, "title": h["title"], "category": h["category"]}
               for i, h in enumerate(hits)]

    def generate():
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        try:
            for piece in core.stream_ollama(prompt):
                yield f"data: {json.dumps({'type': 'token', 'text': piece})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': f'Model offline: {e}'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/remaining")
def remaining():
    ip = core.client_ip(request)
    return jsonify(remaining=core.anon_remaining(ip), daily=CFG["anon_daily"])

# ------------------------------------------------------------------ REST API (metered)
@app.route("/api/ask", methods=["POST"])
def api_ask():
    user, err = core.auth_user(request)
    if err:
        return jsonify(error=err), 401
    q = ((request.json or {}).get("q") or "").strip()
    if not q:
        return jsonify(error="q required"), 400
    ok, msg = core.consume(user, "ask", q[:80], core.client_ip(request))
    if not ok:
        return jsonify(error=msg), 402
    prompt, hits = core.build_prompt(q, k=CFG.get("rag_k", 6))
    try:
        answer = core.ask_ollama(prompt)
    except Exception as e:
        return jsonify(error=f"Model offline: {e}"), 503
    return jsonify(question=q, answer=answer,
                   sources=[{"title": h["title"], "category": h["category"],
                             "book_id": h["book_id"], "chunk": h["chunk"]} for h in hits])

@app.route("/api/search", methods=["GET", "POST"])
def api_search():
    user, err = core.auth_user(request)
    if err:
        return jsonify(error=err), 401
    q = (request.json or {}).get("q") if request.is_json else request.args.get("q")
    q = (q or "").strip()
    if not q:
        return jsonify(error="q required"), 400
    ok, msg = core.consume(user, "search", q[:80], core.client_ip(request))
    if not ok:
        return jsonify(error=msg), 402
    hits = core.search_library(q, k=int((request.json or {}).get("k", 8) if request.is_json else request.args.get("k", 8)))
    for h in hits:
        h.pop("text", None)
    return jsonify(query=q, results=hits)

@app.route("/api/my-usage", methods=["GET", "POST"])
def my_usage():
    user, err = core.auth_user(request)
    if err:
        return jsonify(error=err), 401
    c = core.db()
    u = c.execute("SELECT credits, free_used, total_calls FROM users WHERE id=?", (user["id"],)).fetchone()
    if u["total_calls"] is None:
        c.execute("UPDATE users SET total_calls=(SELECT COUNT(*) FROM usage_log WHERE user_id=?) WHERE id=?", (user["id"], user["id"]))
        c.commit()
        u = c.execute("SELECT credits, free_used, total_calls FROM users WHERE id=?", (user["id"],)).fetchone()
    recent = [dict(r) for r in c.execute(
        "SELECT kind, detail, created_at FROM usage_log WHERE user_id=? ORDER BY id DESC LIMIT 10", (user["id"],))]
    c.close()
    return jsonify(email=user["email"], credits=u["credits"], free_used_this_month=u["free_used"],
                   free_monthly=CFG["free_monthly"], total_calls=u["total_calls"] or 0, recent=recent)

@app.route("/api/signup", methods=["POST"])
def api_signup():
    email = (request.json or {}).get("email", "")
    key, status = core.signup(email)
    if not key:
        return jsonify(error=status), 400
    return jsonify(email=email.strip().lower(), api_key=key, status=status,
                   free_monthly=CFG["free_monthly"],
                   note="Free tier active. Keep this key safe — it is shown once per signup.")

@app.route("/api/create-invoice", methods=["POST"])
def api_invoice():
    user, err = core.auth_user(request)
    if err:
        return jsonify(error=err), 401
    plan = (request.json or {}).get("plan", "")
    inv, err = core.create_invoice(user, plan)
    if err:
        return jsonify(error=err), 400
    return jsonify(invoice_id=inv["id"], amount=inv.get("amount"),
                   checkout_url=inv.get("checkoutLink") or (inv.get("checkout") or {}).get("link"))

# ------------------------------------------------------------------ BTCPay webhook
@app.route("/webhook/btcpay", methods=["POST"])
def webhook():
    body = request.get_json(silent=True) or {}
    # shared-secret check via webhook URL suffix
    ok = request.args.get("wh") == CFG["btcpay"].get("webhook_secret")
    core.handle_webhook(body, ok)
    return jsonify(status="ok")

# ------------------------------------------------------------------ SEO / agent kit
@app.route("/robots.txt")
def robots():
    ais = ("GPTBot OAI-SearchBot ChatGPT-User ClaudeBot Claude-Web anthropic-ai PerplexityBot "
           "Perplexity-User Google-Extended GoogleOther Amazonbot Applebot-Extended Bytespider "
           "cohere-ai Meta-ExternalAgent Diffbot CCBot").split()
    lines = [f"User-agent: {a}\nAllow: /" for a in ais]
    lines.append("User-agent: *\nAllow: /\nDisallow: /webhook/")
    lines.append(f"Sitemap: {CFG['base_url']}/sitemap.xml")
    return Response("\n\n".join(lines), mimetype="text/plain")

@app.route("/llms.txt")
def llms_txt():
    return Response(render_template_string(core.load_llms_txt()), mimetype="text/plain")

@app.route("/llms-full.txt")
def llms_full():
    return Response(render_template_string(core.load_llms_txt() + "\n\n" + core.load_llms_full()), mimetype="text/plain")

@app.route("/.well-known/ai-plugin.json")
def ai_plugin():
    return Response(json.dumps({
        "schema_version": "v1",
        "name_for_human": "DRACO — Book-Forged Code Oracle",
        "name_for_model": "draco",
        "description_for_human": "Coding & security answers grounded in a library of hundreds of real programming and hacking books, with citations.",
        "description_for_model": "Ask coding, systems, and security questions. Answers are RAG-grounded in DRACO's book library and include citations [n] plus a sources array with titles. Use /api/ask for full answers, /api/search to find book passages. Auth: X-API-Key header, free tier available.",
        "auth": {"type": "none"},
        "api": {"type": "openapi", "url": f"{CFG['base_url']}/openapi.json"},
        "logo_url": f"{CFG['base_url']}/static/logo.svg",
        "contact_email": "drjones@thetempleofdoom.com",
        "legal_info_url": f"{CFG['base_url']}/api"
    }, indent=1), mimetype="application/json")

@app.route("/.well-known/mcp-server.json")
def mcp_manifest():
    return Response(json.dumps({
        "$schema": "https://cdn.jsdelivr.net/npm/@modelcontextprotocol/sdk@latest/schema.json",
        "name": "com.thetempleofdoom.draco/ask",
        "description": "Coding & security oracle grounded in hundreds of real books. Ask, search, cite.",
        "homepage": CFG["base_url"],
        "remotes": [{"type": "streamable-http", "url": f"{CFG['base_url']}/mcp"}]
    }, indent=1), mimetype="application/json")

@app.route("/openapi.json")
def openapi():
    return Response(json.dumps({
        "openapi": "3.0.0",
        "info": {"title": "DRACO API", "version": "1.0",
                 "description": "RAG coding/security oracle over hundreds of real books. Free tier: signup for API key."},
        "servers": [{"url": CFG["base_url"]}],
        "paths": {
            "/api/ask": {"post": {"summary": "Ask a coding/security question (RAG + citations)",
                "requestBody": {"content": {"application/json": {"schema": {"type": "object",
                    "properties": {"q": {"type": "string"}, "api_key": {"type": "string"}},
                    "required": ["q"]}}}},
                "responses": {"200": {"description": "answer + sources"}}}},
            "/api/search": {"get": {"summary": "BM25 passage search across the library",
                "parameters": [{"name": "q", "in": "query", "required": True, "schema": {"type": "string"}},
                               {"name": "k", "in": "query", "schema": {"type": "integer", "default": 8}}],
                "responses": {"200": {"description": "passage results"}}}},
            "/api/signup": {"post": {"summary": "Get a free API key",
                "requestBody": {"content": {"application/json": {"schema": {"type": "object",
                    "properties": {"email": {"type": "string"}}, "required": ["email"]}}}},
                "responses": {"200": {"description": "api_key"}}}},
            "/api/my-usage": {"get": {"summary": "Credits + recent calls", "responses": {"200": {"description": "usage"}}}},
            "/api/create-invoice": {"post": {"summary": "Buy credits (Bitcoin via BTCPay)",
                "requestBody": {"content": {"application/json": {"schema": {"type": "object",
                    "properties": {"plan": {"type": "string", "enum": list(CFG["plans"].keys())}}}}}},
                "responses": {"200": {"description": "checkout_url"}}}}
        }
    }, indent=1), mimetype="application/json")

@app.route("/sitemap.xml")
def sitemap():
    urls = [CFG["base_url"], f"{CFG['base_url']}/library", f"{CFG['base_url']}/pricing",
            f"{CFG['base_url']}/api", f"{CFG['base_url']}/llms.txt"]
    body = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    for u in urls:
        body += f"<url><loc>{u}</loc></url>"
    body += "</urlset>"
    return Response(body, mimetype="application/xml")

# ------------------------------------------------------------------ MCP (streamable-http)
try:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("draco", host="127.0.0.1", port=CFG.get("mcp_port", 8012),
                  streamable_http_path="/mcp")

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
        hits = core.search_library(query, k=k)
        if not hits:
            return "No passages matched."
        return "\n\n".join(f"[{h['title']} · {h['category']} · score {h['score']}]\n{h['text'][:600]}" for h in hits)

    @mcp.tool()
    def draco_status() -> str:
        """DRACO health + library size."""
        s = core.get_stats()
        return (f"DRACO {CFG['model']} · {s['books']} books · {s['chunks']} passages · "
                f"API: {CFG['base_url']}/api · MCP: {CFG['base_url']}/mcp")

    from starlette.applications import Starlette
    starlette_app = mcp.streamable_http_app()
    app.mount("/mcp", starlette_app)
    MCP_OK = True
except Exception as _e:  # MCP optional at runtime
    MCP_OK = False
    MCP_ERR = str(_e)

@app.route("/mcp-info")
def mcp_info():
    return jsonify(mcp=MCP_OK, error=MCP_ERR if not MCP_OK else None,
                   url=f"{CFG['base_url']}/mcp")

# ------------------------------------------------------------------ static
@app.route("/static/logo.svg")
def logo():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
           '<rect width="64" height="64" rx="12" fill="%230b0e14"/>'
           '<path d="M32 8 L50 16 V34 C50 46 42 54 32 58 C22 54 14 46 14 34 V16 Z" '
           'fill="none" stroke="%%23e8b64c" stroke-width="3"/>'
           '<text x="32" y="40" font-size="26" text-anchor="middle" fill="%%23e8b64c" '
           'font-family="monospace" font-weight="bold">D</text></svg>')
    return Response(svg.replace("%23", "#"), mimetype="image/svg+xml")

# ------------------------------------------------------------------ main
if __name__ == "__main__":
    print(f"DRACO starting · MCP={'ok' if MCP_OK else 'FAILED: ' + MCP_ERR}")
    app.run(host="127.0.0.1", port=CFG["port"], threaded=True)
