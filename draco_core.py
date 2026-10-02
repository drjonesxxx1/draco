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
    total_calls INTEGER DEFAULT 0,
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
    try:  # in-place migration for DBs created before total_calls existed
        c.execute("SELECT total_calls FROM users LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE users ADD COLUMN total_calls INTEGER DEFAULT 0")
        c.commit()
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

def build_prompt(question, k=None):
    """RAG prompt. PROMPT BUDGET RULE: all prompts must land in the same size class
    (~600 tok). vornith (linear-attn+MTP hybrid) corrupts when one resident instance
    receives mixed tiny/long prompts; uniform bounded prompts are proven stable."""
    k = k or CFG.get("rag_k", 2)
    k = min(k, 3)  # hard cap: 3 x 1200-char excerpts ~= clean-zone prompt
    hits = search_library(question, k=k)
    if hits:
        blocks = []
        for n, h in enumerate(hits, 1):
            blocks.append(f"[{n}] {h['title']} ({h['category']})\n{h['text'][:1200]}")
        ctx = "\n\n".join(blocks)
        prompt = f"{SYSTEM}\n\nBOOK EXCERPTS:\n{ctx}\n\nQUESTION: {question}\n\nANSWER (cite [n]):"
    else:
        prompt = f"{SYSTEM}\n\n(No book excerpts matched — answer from general expertise, marked.)\n\nQUESTION: {question}\n\nANSWER:"
    return prompt, hits

# ---------------------------------------------------------------- ollama
import requests as http

OPEN, CLOSE = "<think>", "</think>"

def strip_cot(text):
    """Non-streaming: return (reasoning, answer). Handles tagged AND untagged CoT."""
    if OPEN in text:
        pre, rest = text.split(OPEN, 1)
        if CLOSE in rest:
            think, answer = rest.split(CLOSE, 1)
            return (pre + think).strip(), answer.strip()
        return "", rest.strip()  # unbalanced opener
    if CLOSE in text:  # missing opener: preamble before close is reasoning
        think, answer = text.split(CLOSE, 1)
        return think.strip(), answer.strip()
    return "", text.strip()  # no tags: answer as-is

class ThinkSplitter:
    """Streaming: yield (channel, piece) where channel is 'think' or 'answer'.
    Handles: <think>..</think>, missing opener (</think> closes), or fully untagged
    output — where meta-narration ("The user asks... Let me check the excerpts...")
    is detected by a gated prefix + per-paragraph classifier and routed to 'think',
    while real content paragraphs start the 'answer'."""
    PRE, THINK, NARR, ANSWER = range(4)
    import re as _re
    _BOLD = r"\*\*[^*\n]{1,60}\*\*"
    NARR_START = _re.compile(
        r"^\s*(?:the user|user asks|user want|let me|i need|i'll|i will|i should|"
        r"okay\b|ok,|alright|hmm\b|to answer|so i|so,|we need|looking at|"
        r"first,|step 1[:.]|" + _BOLD + r")", _re.IGNORECASE)
    NARR_CONT = _re.compile(
        r"^\s*(?:" + _BOLD +
        r"|the (?:user|excerpts?|passages?|books?|sources?|quotes?)|none of"
        r"|excerpt \[|excerpt \d|passage \d|quote \d|source \d"
        r"|there (?:is|are) no|no (?:book|passage|excerpt|relevant)"
        r"|based on (?:the|these|my)|so,?(?: i| the| this| none)"
        r"|i (?:should|will|would|need|can't|cannot|don't|do not|think|see|notice)"
        r"|to answer|as (?:the|these|per)|these (?:excerpts?|passages?|books?)"
        r"|okay\b|alright|hmm|let me|however,? (?:the|none|there)|therefore,? (?:the|i)"
        r"|in (?:short|conclusion|summary)|overall|finally,? (?:i|the))", _re.IGNORECASE)
    GATE_CHARS = 140
    GATE_MAX = 400  # hard cap: decide even without a paragraph boundary

    def __init__(self):
        self.state = self.PRE
        self.buf = ""        # scanner buffer (PRE/THINK) OR paragraph buffer (NARR)
        self.ans_buf = ""    # text held by the undecided gate
        self.gated = False   # True once answer-vs-narration has been decided

    def _emit(self, channel, s):
        return [(channel, s)] if s else []

    def _take(self, n=None):
        if n is None:
            piece, self.buf = self.buf, ""
        else:
            piece, self.buf = self.buf[:n], self.buf[n:]
        return piece

    def _gate_feed(self, s):
        """PRE-state text: hold until the start-of-answer gate can judge.
        Decides at the first paragraph boundary after GATE_CHARS (or at GATE_MAX)."""
        if self.gated:
            return self._emit("answer", s)
        self.ans_buf += s
        boundary = self.ans_buf.find("\n\n", self.GATE_CHARS)
        if boundary == -1 and len(self.ans_buf) < self.GATE_MAX:
            return []
        cut = boundary + 2 if boundary != -1 else len(self.ans_buf)
        held, self.ans_buf = self.ans_buf[:cut], self.ans_buf[cut:]
        self.gated = True
        tail, self.buf = self.buf, ""  # tail is NEWER than ans_buf; stream order = held + rest + tail
        if self.NARR_START.match(held):
            self.state = self.NARR
            out = self._emit("think", held)
            out += self._narr_feed(self.ans_buf + tail)
            self.ans_buf = ""
            return out
        self.state = self.ANSWER
        return self._emit("answer", held + self.ans_buf + tail)

    def _narr_feed(self, s):
        """NARR state: classify complete paragraphs; first content paragraph = answer."""
        self.buf += s
        out = []
        while "\n\n" in self.buf:
            para, rest = self.buf.split("\n\n", 1)
            if para.strip() and self.NARR_CONT.match(para):
                out += self._emit("think", para + "\n\n")
                self.buf = rest
            else:
                self.state = self.ANSWER
                self.gated = True
                out += self._emit("answer", self.buf)
                self.buf = ""
                return out
        return out

    def feed(self, s):
        self.buf += s
        out = []
        while True:
            if self.state == self.ANSWER:
                out += self._emit("answer", self._take())
                return out
            if self.state == self.NARR:
                out += self._narr_feed(self._take())
                if self.state == self.NARR:
                    return out
                continue
            i_open, i_close = self.buf.find(OPEN), self.buf.find(CLOSE)
            if self.state == self.PRE:
                if i_open != -1 and (i_close == -1 or i_open < i_close):
                    out += self._gate_feed(self._take(i_open))
                    self.gated = True  # tagged CoT follows; gate no longer needed
                    self.buf = self.buf[len(OPEN):]
                    self.state = self.THINK
                    continue
                if i_close != -1:  # missing opener — preamble is reasoning
                    held, self.ans_buf = self.ans_buf, ""
                    out += self._emit("think", held + self._take(i_close))
                    self.buf = self.buf[len(CLOSE):]
                    self.state = self.ANSWER
                    continue
            elif self.state == self.THINK:
                if i_close != -1:
                    held, self.ans_buf = self.ans_buf, ""  # rare held PRE text merges
                    out += self._emit("think", held + self._take(i_close))
                    self.buf = self.buf[len(CLOSE):]
                    self.state = self.ANSWER
                    continue
            # no marker found: emit all but a tag-length tail
            keep = min(len(self.buf), max(len(OPEN), len(CLOSE)) - 1)
            cut = len(self.buf) - keep
            if cut > 0:
                piece = self._take(cut)
                if self.state == self.THINK:
                    out += self._emit("think", piece)
                else:  # PRE: route through the gate
                    out += self._gate_feed(piece)
            return out

    def flush(self):
        out = []
        if self.state == self.PRE and (self.ans_buf or self.buf):
            rest = self.ans_buf + self.buf  # stream order: held text, then tail
            self.ans_buf = self.buf = ""
            if self.NARR_START.match(rest):
                self.state = self.NARR
                out += self._narr_feed(rest)  # classify paragraphs; content → answer
            else:
                out += self._emit("answer", rest)
                return out
        if self.state == self.NARR:
            residual, self.buf = self.buf, ""
            if residual.strip():
                out += self._emit("think" if self.NARR_CONT.match(residual) else "answer", residual)
            return out
        if self.buf:
            piece = self._take()
            if self.state == self.THINK:
                out += self._emit("think", piece + self.ans_buf)
                self.ans_buf = ""
            else:
                out += self._gate_feed(piece)
        if self.ans_buf:  # gate decided held text still pending
            held, self.ans_buf = self.ans_buf, ""
            out += self._emit("think" if self.NARR_START.match(held) else "answer", held)
        return out

def stream_ollama(prompt):
    """Yield (channel, piece) tuples: channel 'think' or 'answer'."""
    r = http.post(f"{CFG['ollama_url']}/api/generate",
                  json={"model": CFG["model"], "prompt": prompt, "stream": True,
                        # RESIDENT model: cold-load prefill >1k tokens CUDA-crashes on this
                        # hybrid arch. Corruption (????? output) is handled by detection +
                        # auto-reload in the app layer instead.
                        "options": {"temperature": 0.4, "num_predict": CFG.get("num_predict", 1100),
                                    "num_ctx": CFG.get("num_ctx", 8192)}},
                  timeout=(5, None), stream=True)
    sp = ThinkSplitter()
    for line in r.iter_lines():
        if line:
            tok = json.loads(line).get("response", "")
            if tok:
                for channel, piece in sp.feed(tok):
                    yield channel, piece
    for channel, piece in sp.flush():
        yield channel, piece

def ask_ollama(prompt):
    """Non-streaming RAG answer with auto-recovery: on degenerate/CUDA failure,
    unload the model, reload fresh, retry once before surfacing an error."""
    last_err = None
    for attempt in (1, 2):
        try:
            r = http.post(f"{CFG['ollama_url']}/api/generate",
                          json={"model": CFG["model"], "prompt": prompt, "stream": False,
                                "options": {"temperature": 0.4, "num_predict": CFG.get("num_predict", 1100),
                                            "num_ctx": CFG.get("num_ctx", 8192)}},
                          timeout=180)
            r.raise_for_status()
            raw = r.json().get("response", "")
            if raw and degenerate(raw):
                last_err = RuntimeError("degenerate output")
            else:
                _, answer = strip_cot(raw)
                return answer
        except http.HTTPError as e:
            last_err = e
        except Exception as e:
            last_err = e
        unload_model()  # force clean reload for the next attempt
        time.sleep(2)
    raise RuntimeError(f"model unstable after retry: {last_err}")

def degenerate(s):
    """vornith VRAM/session corruption signature: run of '?' chars."""
    s = s.strip()
    return len(s) >= 40 and s.count("?") / len(s) > 0.4

def warm_model():
    """Budget-sized heartbeat: keeps the model resident AND exercised at the canonical
    prompt size. Tiny prompts (<50 tok) on the shared instance are the corruption
    trigger, so the ping itself must be RAG-sized."""
    try:
        excerpt = ("The utility of a uniform prompt budget is that the model never "
                   "encounters a context-length distribution shift between requests. " * 9)
        prompt = (f"{SYSTEM}\n\nBOOK EXCERPTS:\n[1] Warmup Excerpt (maintenance)\n{excerpt}"
                  "\n\nQUESTION: Reply with exactly: ok\n\nANSWER (cite [n]):")
        r = http.post(f"{CFG['ollama_url']}/api/generate",
                      json={"model": CFG["model"], "prompt": prompt,
                            "stream": False, "options": {"num_predict": 4}},
                      timeout=120)
        sample = r.json().get("response", "") if r.status_code == 200 else ""
        healthy = r.status_code == 200 and not degenerate(sample)
        return healthy, sample[:120]
    except Exception as e:
        return False, str(e)[:120]

def unload_model():
    """Drop the model from VRAM so the next request reloads clean."""
    try:
        http.post(f"{CFG['ollama_url']}/api/generate",
                  json={"model": CFG["model"], "keep_alive": 0}, timeout=10)
    except Exception:
        pass

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
