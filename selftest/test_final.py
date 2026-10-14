"""Tests the final scoring pipeline (lane/final.py + score_final.py grading) without Docker or keys.

Two fake lanes, each with a harness git repo like the one evolution leaves behind:
  lane "good": seed = plain prompt, best = prompt with 'EDGE CASES'  -> the fake model then answers correctly
  lane "flat": seed = plain prompt, best = same plain prompt          -> evolution found nothing
Expected: good/best passes all 54 hidden tests, everything else passes 0, and "good" wins.
Also checks the tie-break (equal tests -> fewer tokens wins) and that final.py never sees hidden tests.
"""
import json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from reference_solutions import REF  # noqa: E402
import score_final  # noqa: E402

spent = {"n": 0}
seen_prompts = []


class Meter(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("content-length", str(len(b))); self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send(200, {"remaining": 10_000_000 - spent["n"]})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["content-length"])))
        system, user = req["system"], req["messages"][0]["content"]
        seen_prompts.append(user)
        entry = user.split("named `")[1].split("`")[0]
        text = f"```python\n{REF[entry]}\n```" if "EDGE CASES" in system else "```python\ndef nope(): pass\n```"
        spent["n"] += (len(system) + len(user) + len(text)) // 4
        self._send(200, {"text": text, "usage": {}, "remaining": 10_000_000 - spent["n"]})


def make_lane(work, best_prompt):
    h = os.path.join(work, "harness")
    shutil.copytree(os.path.join(ROOT, "lane", "seed"), h)
    g = lambda *a: subprocess.run(["git", "-C", h, *a], check=True, capture_output=True)
    g("init", "-q"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    g("add", "-A"); g("commit", "-qm", "gen 0: seed harness")
    with open(os.path.join(h, "prompt.md"), "w") as f:
        f.write(best_prompt)
    g("add", "-A"); g("commit", "-q", "--allow-empty", "-m", "gen 1 candidate"); g("tag", "best")
    with open(os.path.join(ROOT, "tasks", "heldout.json")) as f:
        specs = [{"id": t["id"], "entry": t["entry"], "prompt": t["prompt"], "n_tests": len(t["tests"])}
                 for t in json.load(f)]
    with open(os.path.join(work, "final_tasks.json"), "w") as f:
        json.dump(specs, f)


def main():
    tmp = tempfile.mkdtemp()
    subprocess.run([sys.executable, os.path.join(ROOT, "tasks", "build_tasks.py")], check=True, capture_output=True)
    grader = subprocess.Popen([sys.executable, os.path.join(ROOT, "grader", "grader.py")],
                              env={**os.environ, "TASK_DIR": os.path.join(ROOT, "tasks"),
                                   "DATA_DIR": os.path.join(tmp, "grader"), "GRADER_ADMIN_TOKEN": "tok", "PORT": "18092"})
    meter = ThreadingHTTPServer(("127.0.0.1", 18082), Meter)
    threading.Thread(target=meter.serve_forever, daemon=True).start()
    for _ in range(50):
        try:
            urllib.request.urlopen("http://127.0.0.1:18092/tasks", timeout=1); break
        except Exception:
            time.sleep(0.1)

    seed_prompt = open(os.path.join(ROOT, "lane", "seed", "prompt.md")).read()
    lanes = {"good": "Check EDGE CASES. Reply with one ```python block.\n", "flat": seed_prompt}
    results = {}
    with open(os.path.join(ROOT, "tasks", "heldout.json")) as f:
        tasks = json.load(f)
    score_final.GRADER = "http://127.0.0.1:18092"
    try:
        for lane, best_prompt in lanes.items():
            work = os.path.join(tmp, lane)
            os.makedirs(work)
            make_lane(work, best_prompt)
            p = subprocess.run([sys.executable, os.path.join(ROOT, "lane", "final.py")], capture_output=True, text=True,
                               timeout=300, env={**os.environ, "LANE": lane, "WORK_DIR": work, "REPEATS": "2",
                                                 "METER_URL": "http://127.0.0.1:18082"})
            print(p.stdout, p.stderr[-1500:] if p.returncode else "")
            with open(os.path.join(work, "final_solutions.json")) as f:
                results[lane] = score_final.grade_lane("tok", json.load(f), tasks)
            head = subprocess.run(["git", "-C", os.path.join(work, "harness"), "status", "--porcelain"],
                                  capture_output=True, text=True).stdout
            results[lane]["_repo_untouched"] = head == ""
    finally:
        grader.terminate(); meter.shutdown()

    score_final.LANES = ["good", "flat"]
    md = score_final.report(results, {"good": "fake", "flat": "fake"})
    print(md)
    g, f = results["good"], results["flat"]
    tie = {"good": {"best": {"passed_mean": 10, "tokens_mean": 500}},
           "flat": {"best": {"passed_mean": 10, "tokens_mean": 400}}}
    test_code_markers = ["assert ", "_r = "]
    checks = [
        ("good/seed passes 0 hidden tests", g["seed"]["passed_mean"] == 0),
        ("good/best passes all 54 hidden tests", g["best"]["passed_mean"] == 54 and g["best"]["total"] == 54),
        ("flat/best passes 0 (evolution found nothing)", f["best"]["passed_mean"] == 0),
        ("2 repeats each, complete", g["best"]["repeats"] == 2 and g["best"]["complete"] and f["seed"]["complete"]),
        ("tokens measured", g["best"]["tokens_mean"] > 0 and g["seed"]["tokens_mean"] > 0),
        ("winner is 'good' on tests passed", score_final.winner(results) == ("good", "more hidden tests passed")),
        ("tie-break: equal tests -> fewer tokens wins",
         score_final.winner(tie) == ("flat", "same tests passed, fewer tokens")),
        ("final.py never saw hidden test code", not any(m in p for p in seen_prompts for m in test_code_markers)),
        ("harness repo left untouched", g["_repo_untouched"] and f["_repo_untouched"]),
        ("report names the winner", "**Winner: good**" in md),
    ]
    fails = 0
    for name, ok in checks:
        print(("  PASS " if ok else "  FAIL ") + name)
        fails += not ok
    print(f"\n{'ALL CHECKS PASSED' if not fails else f'{fails} CHECK(S) FAILED'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()