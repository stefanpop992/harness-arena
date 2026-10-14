"""Tests the lane's evolution loop end to end with a scripted fake model (no Docker, no keys).

The fake model answers correctly only when the system prompt contains 'EDGE CASES'.
The fake meter charges tokens by text length, so a shorter prompt costs fewer tokens.

  gen 0  seed harness                        -> 0/52                    -> baseline
  gen 1  harness with a syntax error         -> must be DISCARDED
  gen 2  prompt with EDGE CASES              -> 52/52                   -> must be KEPT (more correct)
  gen 3  prompt without it                   -> 0/52                    -> must be REVERTED (less correct)
  gen 4  SHORTER prompt with EDGE CASES      -> 52/52, fewer tokens     -> must be KEPT (cheaper)
  gen 5  much LONGER prompt with EDGE CASES  -> 52/52, more tokens      -> must be REVERTED (dearer)
  gen 6  budget runs out                     -> must stop cleanly on the gen 4 harness
"""
import json, os, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference_solutions import REF  # noqa: E402

state = {"spent": 0, "evolves": 0}
BUDGET = 10_000_000

GOOD_PROMPT = "You are a careful Python programmer. Check EDGE CASES, every single one. Reply with one ```python block."
BAD_PROMPT = "You are a Python programmer. Reply with one ```python block."
SHORT_PROMPT = "Check EDGE CASES. One ```python block."
LONG_PROMPT = GOOD_PROMPT + "\n" + "Be thorough. " * 300


def fake_model(system, user):
    if system.startswith("You are improving"):
        state["evolves"] += 1
        n = state["evolves"]
        if n == 1:
            return "Plan: break it.\n=== FILE: harness.py ===\ndef solve(task, llm)\n    return ''\n=== END ==="
        prompt = {2: GOOD_PROMPT, 3: BAD_PROMPT, 4: SHORT_PROMPT, 5: LONG_PROMPT}[n]
        return f"Plan: try prompt variant {n}.\n=== FILE: prompt.md ===\n{prompt}\n=== END ==="
    entry = user.split("named `")[1].split("`")[0]
    if "EDGE CASES" in system:
        return f"```python\n{REF[entry]}\n```"
    return "```python\ndef nope():\n    pass\n```"


class Meter(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("content-length", str(len(b))); self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send(200, {"remaining": BUDGET - state["spent"]})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["content-length"])))
        system, user = req["system"], req["messages"][0]["content"]
        if system.startswith("You are improving") and state["evolves"] >= 5:
            return self._send(402, {"error": "budget_exhausted"})  # budget "runs out" before evolve 6
        text = fake_model(system, user)
        inp, out = (len(system) + len(user)) // 4, len(text) // 4
        state["spent"] += inp + out
        self._send(200, {"text": text, "usage": {"input": inp, "output": out}, "remaining": BUDGET - state["spent"]})


def main():
    tmp = tempfile.mkdtemp()
    subprocess.run([sys.executable, os.path.join(ROOT, "tasks", "build_tasks.py")], check=True, capture_output=True)
    grader = subprocess.Popen([sys.executable, os.path.join(ROOT, "grader", "grader.py")],
                              env={**os.environ, "TASK_DIR": os.path.join(ROOT, "tasks"),
                                   "DATA_DIR": os.path.join(tmp, "grader"), "GRADER_ADMIN_TOKEN": "x", "PORT": "18091"})
    meter = ThreadingHTTPServer(("127.0.0.1", 18081), Meter)
    threading.Thread(target=meter.serve_forever, daemon=True).start()
    for _ in range(50):
        try:
            urllib.request.urlopen("http://127.0.0.1:18091/tasks", timeout=1); break
        except Exception:
            time.sleep(0.1)
    try:
        p = subprocess.run([sys.executable, os.path.join(ROOT, "lane", "run.py")], capture_output=True, text=True,
                           timeout=300, env={**os.environ, "LANE": "test", "WORK_DIR": os.path.join(tmp, "work"),
                                             "METER_URL": "http://127.0.0.1:18081",
                                             "GRADER_URL": "http://127.0.0.1:18091"})
        print(p.stdout); print(p.stderr[-2000:]) if p.returncode else None
    finally:
        grader.terminate(); meter.shutdown()

    work = os.path.join(tmp, "work")
    hist = [json.loads(l) for l in open(os.path.join(work, "state", "history.jsonl"))]
    prompt = open(os.path.join(work, "harness", "prompt.md")).read()
    gitlog = subprocess.run(["git", "-C", os.path.join(work, "harness"), "log", "--all", "--oneline"],
                            capture_output=True, text=True).stdout
    best_tag = subprocess.run(["git", "-C", os.path.join(work, "harness"), "rev-parse", "best"],
                              capture_output=True, text=True).stdout.strip()
    by_gen = {h["gen"]: h for h in hist}

    checks = [
        ("gen 0 seed scores 0", by_gen[0]["passed"] == 0 and by_gen[0]["total"] == 52),
        ("gen 1 broken harness discarded", by_gen[1]["passed"] is None and not by_gen[1]["kept"]),
        ("gen 2 more correct -> kept", by_gen[2]["passed"] == 52 and by_gen[2]["kept"]),
        ("gen 3 less correct -> reverted", by_gen[3]["passed"] == 0 and not by_gen[3]["kept"]),
        ("gen 4 equally correct, cheaper -> kept",
         by_gen[4]["passed"] == 52 and by_gen[4]["score_tokens"] < by_gen[2]["score_tokens"] and by_gen[4]["kept"]),
        ("gen 5 equally correct, dearer -> reverted",
         by_gen[5]["passed"] == 52 and by_gen[5]["score_tokens"] > by_gen[4]["score_tokens"] and not by_gen[5]["kept"]),
        ("final harness is the gen 4 version", prompt.strip() == SHORT_PROMPT),
        ("'best' tag points at gen 4", best_tag == by_gen[4]["commit"]),
        ("stopped on budget, DONE written", os.path.exists(os.path.join(work, "state", "DONE"))
         and "budget exhausted" in p.stdout),
        ("every candidate is in git history", gitlog.count("candidate") == 4),
    ]
    print("tokens to solve the 6 tasks, per gen:",
          {g: h.get("score_tokens") for g, h in by_gen.items()})
    print("git history:\n" + gitlog)
    fails = 0
    for name, ok in checks:
        print(("  PASS " if ok else "  FAIL ") + name)
        fails += not ok
    print(f"\n{'ALL CHECKS PASSED' if not fails else f'{fails} CHECK(S) FAILED'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()