#!/usr/bin/env python3
"""draco ingest — convert every book (pdf/chm/djvu/djv/txt) to plain text + manifest.
Run on the CT:  python3 ingest.py [--books /opt/books] [--workers 4]
Output: /opt/books/text/<category>/<id>.txt  +  /opt/books/manifest.json
"""
import argparse, concurrent.futures as cf, hashlib, html as htmllib, json, os, re, shutil, subprocess, sys, tempfile, traceback

BOOKS_DIR = "/opt/books"
TEXT_DIR = os.path.join(BOOKS_DIR, "text")

def slugify(name: str) -> str:
    s = re.sub(r"\.(pdf|chm|djvu|djv|txt|epub)$", "", name, flags=re.I)
    s = s.replace("&", " and ").replace("+", " plus ")
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("._")
    return s[:110] or "book"

def clean_text(t: str) -> str:
    t = t.replace("\x00", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

def html_to_text(h: str) -> str:
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h[1-6]>|</li>|</tr>", "\n", h)
    h = re.sub(r"<[^>]+>", " ", h)
    return htmllib.unescape(h)

def convert(path: str, fmt: str, out_path: str) -> tuple[int, str]:
    """Returns (n_chars, err)."""
    if fmt == "txt":
        shutil.copyfile(path, out_path)
        return os.path.getsize(out_path), ""
    if fmt == "pdf":
        r = subprocess.run(["pdftotext", "-q", "-layout", path, out_path], capture_output=True, timeout=300)
        return (os.path.getsize(out_path) if os.path.exists(out_path) else 0), (r.stderr.decode()[:200] if r.returncode else "")
    if fmt == "djvu":
        r = subprocess.run(["djvutxt", path], capture_output=True, timeout=300)
        txt = clean_text(r.stdout.decode("utf-8", "replace"))
        open(out_path, "w").write(txt)
        return len(txt), ""
    if fmt == "chm":
        tmp = tempfile.mkdtemp(prefix="chm_")
        try:
            r = subprocess.run(["extract_chmLib", path, tmp], capture_output=True, timeout=300)
            parts = []
            for root, _, files in os.walk(tmp):
                for f in sorted(files):
                    if f.lower().endswith((".html", ".htm", ".txt")):
                        try:
                            raw = open(os.path.join(root, f), "rb").read()
                            for enc in ("utf-8", "cp1252", "latin-1"):
                                try:
                                    parts.append(html_to_text(raw.decode(enc))); break
                                except UnicodeDecodeError:
                                    continue
                        except Exception:
                            pass
            txt = clean_text("\n\n".join(parts))
            open(out_path, "w").write(txt)
            return len(txt), ""
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return 0, "unsupported"

def process(task):
    path, category, books_dir, text_dir = task
    fmt = path.rsplit(".", 1)[-1].lower()
    base = slugify(os.path.basename(path))
    bid = hashlib.sha1(f"{category}/{base}".encode()).hexdigest()[:10]
    title = re.sub(r"\.(pdf|chm|djvu|djv|txt|epub)$", "", os.path.basename(path), flags=re.I)
    title = re.sub(r"[_\.]+", " ", title).strip()
    out_rel = f"{category}/{bid}_{base}.txt"
    out_abs = os.path.join(text_dir, out_rel)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    n, err = 0, ""
    try:
        n, err = convert(path, fmt, out_abs)
    except subprocess.TimeoutExpired:
        err = "timeout"
    except Exception:
        err = traceback.format_exc(limit=1).splitlines()[-1]
    if n < 200 and os.path.exists(out_abs):
        os.remove(out_abs)  # scanned/no-text junk
        n = 0
    return {"id": bid, "title": title, "category": category, "format": fmt,
            "source": os.path.relpath(path, books_dir), "txt": out_rel if n else None,
            "chars": n, "bytes": os.path.getsize(path), "err": err[:200]}

def main():
    global BOOKS_DIR, TEXT_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--books", default=BOOKS_DIR)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    BOOKS_DIR, TEXT_DIR = a.books, os.path.join(a.books, "text")
    os.makedirs(TEXT_DIR, exist_ok=True)
    tasks = []
    for root, dirs, files in os.walk(BOOKS_DIR):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "text"]
        for f in files:
            if f.startswith("._") or f == ".gitignore":
                continue
            if f.rsplit(".", 1)[-1].lower() in ("pdf", "chm", "djvu", "djv", "txt"):
                rel = os.path.relpath(os.path.join(root, f), BOOKS_DIR)
                category = rel.split(os.sep)[0]
                tasks.append((os.path.join(root, f), category, BOOKS_DIR, TEXT_DIR))
    print(f"ingest: {len(tasks)} books queued", flush=True)
    manifest, done = [], 0
    with cf.ProcessPoolExecutor(max_workers=a.workers) as ex:
        for rec in ex.map(process, tasks):
            manifest.append(rec)
            done += 1
            if done % 25 == 0 or done == len(tasks):
                ok = sum(1 for m in manifest if m["chars"])
                print(f"  {done}/{len(tasks)} converted ({ok} with text)", flush=True)
    manifest.sort(key=lambda m: (m["category"], m["title"].lower()))
    with open(os.path.join(BOOKS_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    ok = [m for m in manifest if m["chars"]]
    print(f"ingest DONE: {len(ok)}/{len(manifest)} books usable, "
          f"{sum(m['chars'] for m in ok)/1e6:.1f}M chars total", flush=True)

if __name__ == "__main__":
    main()
