#!/usr/bin/env python3
"""draco index build — chunk all extracted book text and build a BM25 index.
Run on the CT after ingest.py:  python3 build_index.py [--books /opt/books]
Output: /opt/books/index/chunks.json + index.pkl   (book_count.json = stats)
"""
import argparse, json, os, pickle, re, time

BOOKS_DIR = "/opt/books"
INDEX_DIR = os.path.join(BOOKS_DIR, "index")
CHUNK_TOKENS, CHUNK_OVERLAP = 300, 60

def chunk_text(text, size=CHUNK_TOKENS, overlap=CHUNK_OVERLAP):
    words = text.split()
    if len(words) <= size:
        return [" ".join(words)] if words else []
    out = []
    step = size - overlap
    for i in range(0, len(words), step):
        c = words[i:i + size]
        if len(c) >= 40:
            out.append(" ".join(c))
        if i + size >= len(words):
            break
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--books", default=BOOKS_DIR)
    a = ap.parse_args()
    books_dir = a.books
    index_dir = os.path.join(books_dir, "index")
    os.makedirs(index_dir, exist_ok=True)

    from rank_bm25 import BM25Okapi
    from nltk.stem import SnowballStemmer

    t0 = time.time()
    manifest = json.load(open(os.path.join(books_dir, "manifest.json")))
    usable = [m for m in manifest if m.get("txt")]
    print(f"index: {len(usable)} usable books from manifest", flush=True)

    stemmer = SnowballStemmer("english")
    stop = set("""a an and are as at be by for from has have he her his how i in is it its of on or she that the this to was were what when where which who will with you your our we they them not no but can could should would may might must do does did done if then than into over under about after before between during through against without within""".split())

    def toks(s):
        return [stemmer.stem(w) for w in re.findall(r"[a-z0-9_#+.-]{2,}", s.lower()) if w not in stop]

    chunk_records, texts = [], []
    CAP = 400  # max chunks indexed per book (≈480 pages) — keeps the fit inside 8GB
    for m in usable:
        try:
            raw = open(os.path.join(books_dir, "text", m["txt"]), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for j, ch in enumerate(chunk_text(raw)[:CAP]):
            chunk_records.append({"book": m["id"], "chunk": j})
            texts.append(ch)
    print(f"index: {len(texts)} chunks from {len(usable)} books", flush=True)

    print("index: tokenizing...", flush=True)
    corpus = [toks(t) for t in texts]
    print("index: fitting BM25...", flush=True)
    bm25 = BM25Okapi(corpus)

    with open(os.path.join(index_dir, "chunks.json"), "w") as f:
        json.dump(chunk_records, f)
    with open(os.path.join(index_dir, "index.pkl"), "wb") as f:
        pickle.dump({"bm25": bm25, "texts": texts}, f, protocol=4)

    stats = {"books": len(usable), "chunks": len(texts),
             "chars": sum(m["chars"] for m in usable), "built": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.join(books_dir, "book_count.json"), "w") as f:
        json.dump(stats, f)
    print(f"index DONE: {stats} in {time.time()-t0:.0f}s", flush=True)

if __name__ == "__main__":
    main()
