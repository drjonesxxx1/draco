#!/usr/bin/env python3
"""draco core — RAG engine + monetization for DRACO (coding & hacking book oracle)."""
import json, os, pickle, re, sqlite3, threading, time, secrets

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BOOKS_DIR = "/opt/books"
DB_PATH = os.path.join(APP_DIR, "draco.db")

def load_config():
    with open(os.path.join(APP_DIR, "config.json")) as f:
        return json.load(f)

CFG = load_config()

# ---------------------------------------------------------------- database
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    api_key VARCHAR(64) UNIQUE NOT NULL,
    credits INTEGER DEFAULT 0,
    free_used INTEGER DEFAULT 0,
    is_admin INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    api_key VARCHAR(64),
    ip VARCHAR(64),
    kind VARCHAR(32),
    detail VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    invoice_id VARCHAR(128) UNIQUE,
    amount_usd REAL,
    credits INTEGER,
    status VARCHAR(32) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    settled_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS anon_usage (
    ip VARCHAR(64) PRIMARY KEY,
    day VARCHAR(16),
    count INTEGER DEFAULT 0
);
"""

def db():
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.executescript(SCHEMA)
    c.execute("INSERT OR IGNORE INTO users (email, api_key, credits, is_admin) VALUES (?,?,?,1)",
              ("admin@draco.local", CFG["admin_key"], 999999))
    c.commit()
    c.close()

init_db()  # module level: runs under gunicorn too

# ---------------------------------------------------------------- library index
_lock = threading.Lock()
_idx = None

def get_index():
    global _idx
    with _lock:
        if _idx is None:
            with open(os.path.join(BOOKS_DIR, "index", "index.pkl"), "rb") as f:
                _idx = pickle.load(f)
            with open(os.path.join(BOOKS_DIR, "index", "chunks.json")) as f:
                _idx["chunks"] = json.load(f)
            with open(os.path.join(BOOKS_DIR, "manifest.json")) as f:
                manifest = json.load(f)
            _idx["books"] = {m["id"]: m for m in manifest}
        return _idx

def get_stats():
    try:
        with open(os.path.join(BOOKS_DIR, "book_count.json")) as f:
            return json.load(f)
    except Exception:
        return {"books": 0, "chunks": 0, "chars": 0}

_STEM = None
def _stemmer():
    global _STEM
    if _STEM is None:
        from nltk.stem import SnowballStemmer
        _STEM = SnowballStemmer("english")
    return _STEM

_STOP = set("""a an and are as at be by for from has have he her his how i in is it its of on or she that the this to was were what when where which who will with you your our we they them them not no but can could should would may might must do does did done if then than into over under about after before between during through against without within""".split())

def toks(s):
    st = _stemmer()
    return [st.stem(w) for w in re.findall(r"[a-z0-9_#+.-]{2,}", s.lower()) if w not in _STOP]

def search_library(query, k=6):
    idx = get_index()
    scores = idx["bm25"].get_scores(toks(query))
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    out = []
    for i in order:
        if scores[i] <= 0:
            continue
        rec = idx["chunks"][i]
        book = idx["books"].get(rec["book"], {})
        out.append({"score": round(float(scores[i]), 2), "book_id": rec["book"],
                    "title": book.get("title", "?"), "category": book.get("category", "?"),
                    "chunk": rec["chunk"], "text": idx["texts"][i]})
    return out

# ---------------------------------------------------------------- RAG prompt
SYSTEM = (
    "You are DRACO, a master coding and security tutor. You answer ONLY from the "
    "book excerpts provided. Cite sources inline as [n]. If the excerpts do not "
    "contain the answer, say so and answer from general expertise, marked "
    "(general knowledge). Be precise, technical, and give working code. "
    "Answer directly with no reasoning preamble and no meta commentary."
)

def build_prompt(question, k=6):
    hits = search_library(question, k=k)
    if hits:
        blocks = []
        for n, h in enumerate(hits, 1):
            blocks.append(f"[{n}] {h['title']} ({h['category']})\n{h['text'][:1400]}")
        ctx = "\n\n".join(blocks)
        prompt = f"{SYSTEM}\n\nBOOK EXCERPTS:\n{ctx}\n\nQUESTION: {question}\n\nANSWER (cite [n]):"
    else:
        prompt = f"{SYSTEM}\n\n(No book excerpts matched — answer from general expertise, marked.)\n\nQUESTION: {question}\n\nANSWER:"
    return prompt, hits

# ---------------------------------------------------------------- ollama
import requests as http

def strip_cot(text):
    text = re.sub(r"(?s)<think>.*?</think>", "", text)
    if "</think>" in text:
        text = text.split("</think>")[-1]
    if "<think>" in text:  # unbalanced opener: keep what follows
        text = text.split("<think>")[-1]
    return text.strip()

def ask_ollama(prompt):
    r = http.post(f"{CFG['ollama_url']}/api/generate",
                  json={"model": CFG["model"], "prompt": prompt, "stream": False,
                        "options": {"temperature": 0.4, "num_predict": 700,
                                    "num_ctx": CFG.get("num_ctx", 8192)}},
                  timeout=180)
    r.raise_for_status()
    return strip_cot(r.json().get("response", ""))

class CoTFilter:
    """Streaming filter that drops <think>...</think> blocks token-by-token."""
    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self):
        self.buf, self.in_think = "", False

    def feed(self, s):
        self.buf += s
        out = ""
        while True:
            if self.in_think:
                i = self.buf.find(self.CLOSE)
                if i == -1:
                    keep = min(len(self.buf), len(self.CLOSE) - 1)
                    self.buf = self.buf[-keep:] if keep else ""
                    return out
                self.in_think = False
                self.buf = self.buf[i + len(self.CLOSE):]
            else:
                i_open = self.buf.find(self.OPEN)
                i_close = self.buf.find(self.CLOSE)
                # close-tag with no open-tag seen: drop the CoT preamble wholesale
                if i_close != -1 and (i_open == -1 or i_close < i_open):
                    self.buf = self.buf[i_close + len(self.CLOSE):]
                    self.in_think = False
                    continue
                if i_open == -1:
                    keep = min(len(self.buf), max(len(self.OPEN), len(self.CLOSE)) - 1)
                    cut = len(self.buf) - keep
                    out += self.buf[:cut]
                    self.buf = self.buf[cut:]
                    return out
                out += self.buf[:i_open]
                self.in_think = True
                self.buf = self.buf[i_open + len(self.OPEN):]

    def flush(self):
        out, self.buf = ("" if self.in_think else self.buf), ""
        return out

def stream_ollama(prompt):
    r = http.post(f"{CFG['ollama_url']}/api/generate",
                  json={"model": CFG["model"], "prompt": prompt, "stream": True,
                        "options": {"temperature": 0.4, "num_predict": 700,
                                    "num_ctx": CFG.get("num_ctx", 8192)}},
                  timeout=(5, None), stream=True)
    flt = CoTFilter()
    for line in r.iter_lines():
        if line:
            tok = json.loads(line).get("response", "")
            if tok:
                piece = flt.feed(tok)
                if piece:
                    yield piece
    tail = flt.flush()
    if tail:
        yield tail

# ---------------------------------------------------------------- auth + metering
def auth_user(req):
    key = req.headers.get("X-API-Key") or (req.json or {}).get("api_key") if req.is_json else req.headers.get("X-API-Key")
    if not key:
        return None, "API key required (X-API-Key header or api_key field)."
    c = db()
    u = c.execute("SELECT * FROM users WHERE api_key=?", (key,)).fetchone()
    c.close()
    if not u:
        return None, "Invalid API key."
    return dict(u), None

def consume(user, kind, detail="", ip=""):
    c = db()
    if user and not user.get("is_admin"):
        cur = c.execute("SELECT credits, free_used FROM users WHERE id=?", (user["id"],)).fetchone()
        row = c.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        month = time.strftime("%Y-%m")
        if row["free_used"] < CFG["free_monthly"]:
            c.execute("UPDATE users SET free_used=free_used+1, last_used_at=CURRENT_TIMESTAMP WHERE id=?", (user["id"],))
        elif row["credits"] > 0:
            c.execute("UPDATE users SET credits=credits-1, last_used_at=CURRENT_TIMESTAMP WHERE id=?", (user["id"],))
        else:
            c.close()
            return False, "Out of credits. Free tier: %d/mo. Buy more at %s/pricing" % (
                CFG["free_monthly"], CFG["base_url"])
        c.execute("INSERT INTO usage_log (user_id, api_key, ip, kind, detail) VALUES (?,?,?,?,?)",
                  (user["id"], user["api_key"], ip, kind, detail[:200]))
    else:
        c.execute("INSERT INTO usage_log (api_key, ip, kind, detail) VALUES (?,?,?,?)",
                  (user["api_key"] if user else None, ip, kind, detail[:200]))
    c.commit()
    c.close()
    return True, "ok"

def anon_allowed(ip):
    """10 chat messages per IP per day from the web UI."""
    day = time.strftime("%Y-%m-%d")
    c = db()
    row = c.execute("SELECT * FROM anon_usage WHERE ip=?", (ip,)).fetchone()
    if not row or row["day"] != day:
        c.execute("INSERT OR REPLACE INTO anon_usage (ip, day, count) VALUES (?,?,0)", (ip, day))
        c.commit()
        c.close()
        return True
    ok = row["count"] < CFG["anon_daily"]
    if ok:
        c.execute("UPDATE anon_usage SET count=count+1 WHERE ip=?", (ip,))
        c.commit()
    c.close()
    return ok

def anon_remaining(ip):
    day = time.strftime("%Y-%m-%d")
    c = db()
    row = c.execute("SELECT * FROM anon_usage WHERE ip=? AND day=?", (ip, day)).fetchone()
    c.close()
    used = row["count"] if row else 0
    return max(0, CFG["anon_daily"] - used)

def client_ip(req):
    return (req.headers.get("CF-Connecting-IP") or req.headers.get("X-Forwarded-For", req.remote_addr or "?")).split(",")[0].strip()

def signup(email):
    email = email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return None, "Valid email required."
    key = "sk-draco-" + secrets.token_hex(20)
    c = db()
    try:
        c.execute("INSERT INTO users (email, api_key) VALUES (?,?)", (email, key))
        c.commit()
    except sqlite3.IntegrityError:
        c.rollback()
        row = c.execute("SELECT api_key FROM users WHERE email=?", (email,)).fetchone()
        c.close()
        return row["api_key"], "existing"
    c.close()
    return key, "new"

# ---------------------------------------------------------------- llms.txt content
def load_llms_txt():
    s = get_stats()
    plans = ", ".join(f"{name}: ${p['usd']} = {p['credits']} credits" for name, p in CFG["plans"].items())
    return f"""# DRACO — The Book-Forged Code Oracle

> DRACO answers coding, Linux, systems, and security questions with answers grounded
> (RAG, BM25) in a private library of {s['books']} real technical books — programming
> languages, kernels, networks, exploitation, red-team tradecraft — {s['chunks']:,}
> indexed passages, {s['chars']/1e6:.0f}M characters. Every answer cites the books it
> came from as [n] with a sources array. Talk to it in the browser, call the REST API,
> or summon it as an MCP tool from any agent.

## Core endpoints
- POST {CFG['base_url']}/api/ask — body {{"q": "...", "api_key": "..."}} → {{"answer", "sources[]"}} (RAG + citations)
- GET {CFG['base_url']}/api/search?q=...&k=8 — BM25 passage search across all books (header X-API-Key)
- POST {CFG['base_url']}/api/signup — body {{"email": "..."}} → free API key ({CFG['free_monthly']} credits/month)
- GET {CFG['base_url']}/api/my-usage — credits and recent calls (header X-API-Key)
- POST {CFG['base_url']}/api/create-invoice — body {{"plan": "..."}} → BTCPay checkout_url (Bitcoin only)
- GET {CFG['base_url']}/health — liveness + model + library stats

## MCP (streamable-http)
- {CFG['base_url']}/mcp — tools: draco_ask(question), draco_search(query,k), draco_status()

## Web UI
- {CFG['base_url']}/ — homepage + live chat (no key needed, {CFG['anon_daily']}/day per IP)
- {CFG['base_url']}/library — the book collection
- {CFG['base_url']}/pricing — {plans}
- {CFG['base_url']}/api — signup + curl examples

## Auth
- X-API-Key header (or api_key JSON field). Free tier: signup with email.
- Admin/wholesale: contact drjones@thetempleofdoom.com.

## Model
- {CFG['model']} on bare-metal Ollama · retrieval: BM25, {CFG.get('rag_k',6)} passages/answer
"""


def load_llms_full():
    return load_llms_txt() + """
## Example: ask with curl
    curl -s -X POST {b}/api/ask -H 'Content-Type: application/json' \\
      -d '{{"q": "How does a buffer overflow exploit get written?", "api_key": "sk-draco-..."}}'

## Example: search passages
    curl -s "{b}/api/search?q=port+scanning+with+nmap&k=5" -H 'X-API-Key: sk-draco-...'

## Example: MCP initialize
    POST {b}/mcp  Accept: application/json, text/event-stream
    {{"jsonrpc":"2.0","id":1,"method":"initialize","params":{{"protocolVersion":"2025-03-26",
      "capabilities":{{}},"clientInfo":{{"name":"agent","version":"1"}}}}}}

## Policy
- Answers cite books [n]; unmatched questions are marked (general knowledge).
- Security content is for education and authorized testing.
""".format(b=CFG["base_url"])

# ---------------------------------------------------------------- BTCPay
def create_invoice(user, plan):
    plans = CFG["plans"]
    if plan not in plans:
        return None, "Unknown plan."
    p = plans[plan]
    b = CFG["btcpay"]
    if not b.get("store_id"):
        return None, "Payments temporarily offline."
    try:
        r = http.post(f"{b['url']}/api/v1/stores/{b['store_id']}/invoices",
                      headers={"Authorization": f"token {b['api_key']}"},
                      json={"amount": str(p["usd"]), "currency": "USD",
                            "metadata": {"userId": user["id"], "credits": p["credits"],
                                         "orderId": f"draco-{user['id']}-{int(time.time())}"},
                            "checkout": {"redirectURL": f"{CFG['base_url']}/pricing"}},
                      timeout=20, verify=False)
        r.raise_for_status()
        inv = r.json()
    except Exception as e:
        return None, f"Invoice error: {e}"
    c = db()
    c.execute("INSERT INTO payments (user_id, invoice_id, amount_usd, credits) VALUES (?,?,?,?)",
              (user["id"], inv["id"], p["usd"], p["credits"]))
    c.commit()
    c.close()
    return inv, None

def handle_webhook(body, header_sig_ok):
    if not header_sig_ok:
        return False
    etype = body.get("type", "")
    invoice_id = body.get("invoiceId", "")
    if etype not in ("InvoiceSettled", "InvoiceProcessing"):
        return True
    c = db()
    p = c.execute("SELECT * FROM payments WHERE invoice_id=?", (invoice_id,)).fetchone()
    if not p:
        c.close()
        return True
    if etype == "InvoiceSettled":
        c.execute("UPDATE payments SET status='settled', settled_at=CURRENT_TIMESTAMP WHERE invoice_id=?", (invoice_id,))
        c.execute("UPDATE users SET credits=credits+? WHERE id=?", (p["credits"], p["user_id"]))
    else:
        c.execute("UPDATE payments SET status='processing' WHERE invoice_id=?", (invoice_id,))
    c.commit()
    c.close()
    return True
