"""Lane runner: the evolution loop. This file is fixed; the harness it evolves is not.

  generation 0: score the seed harness on the train tasks
  each generation after that:
    1. EVOLVE  - show the model its harness files + where it failed, it returns new files
    2. CHECK   - new files must compile and still define solve()
    3. SCORE   - run the new harness on all train tasks, grade them
    4. KEEP or REVERT - keep if it passes MORE tests than the best so far, or the SAME number
                        of tests using FEWER tokens; otherwise git-reset to the best
  stops when the token budget runs out or MAX_GENERATIONS is reached.

Every candidate is a git commit in /work/harness, so the whole evolution can be replayed.
The run log (/work/state/history.jsonl) lives outside the repo so reverts don't erase it.
"""
import json, os, re, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from client import llm, remaining, BudgetExhausted  # noqa: E402

LANE = os.environ.get("LANE", "lane")
GRADER = os.environ.get("GRADER_URL", "http://grader:8090")
WORK = os.environ.get("WORK_DIR", "/work")
MAX_GEN = int(os.environ.get("MAX_GENERATIONS", "20"))
TASK_TIMEOUT = int(os.environ.get("TASK_TIMEOUT", "600"))
HARNESS = os.path.join(WORK, "harness")
STATE = os.path.join(WORK, "state")
FILE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
MIN_SAVING = float(os.environ.get("MIN_SAVING", "0.15"))


def log(msg):
    print(f"[{LANE} {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def git(*args):
    return subprocess.run(["git", "-C", HARNESS, *args], capture_output=True, text=True, check=True).stdout.strip()


def http_json(method, path, body=None):
    req = urllib.request.Request(f"{GRADER}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"content-type": "application/json", "X-Lane": LANE})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def setup():
    os.makedirs(STATE, exist_ok=True)
    if not os.path.isdir(os.path.join(HARNESS, ".git")):
        subprocess.run(["cp", "-r", os.path.join(HERE, "seed"), HARNESS], check=True)
        git("init", "-q")
        git("config", "user.email", f"{LANE}@harness"), git("config", "user.name", LANE)
        git("add", "-A"), git("commit", "-qm", "gen 0: seed harness")


def score(tasks):
    """Run the current harness on every train task.
    Returns (passed, total, tokens, per-task results). tokens = what the harness spent solving them."""
    results = []
    for t in tasks:
        before = remaining()
        path = os.path.join(STATE, "task.json")
        with open(path, "w") as f:
            json.dump(t, f)
        try:
            p = subprocess.run([sys.executable, os.path.join(HERE, "worker.py"), HARNESS, path],
                               capture_output=True, text=True, timeout=TASK_TIMEOUT)
            out = json.loads(p.stdout.strip().splitlines()[-1])
        except subprocess.TimeoutExpired:
            out = {"error": f"harness timed out after {TASK_TIMEOUT}s"}
        except Exception as e:
            out = {"error": f"harness crashed: {e}"}
        if out.get("error") == "budget_exhausted":
            raise BudgetExhausted()
        if "error" in out:
            g = {"passed": 0, "total": t["n_tests"], "failures": [{"test": "*", "error": out["error"]}]}
            code = ""
        else:
            code = out["code"]
            g = http_json("POST", "/grade", {"task_id": t["id"], "code": code})
        results.append({"task_id": t["id"], "passed": g["passed"], "total": g["total"],
                        "tokens": before - remaining(), "failures": g["failures"], "code": code})
    total = sum(t["n_tests"] for t in tasks)
    passed = sum(r["passed"] for r in results)
    tokens = sum(r["tokens"] for r in results)
    return passed, total, tokens, results


def better(passed, tokens, best):
    """Correctness first; at equal correctness, clearly fewer tokens wins (small savings are noise)."""
    return passed > best["passed"] or (passed == best["passed"] and tokens <= best["tokens"] * (1 - MIN_SAVING))


def read_harness():
    files = {}
    for name in sorted(os.listdir(HARNESS)):
        p = os.path.join(HARNESS, name)
        if os.path.isfile(p):
            with open(p) as f:
                files[name] = f.read()
    return files


EVOLVE_SYSTEM = """You are improving an AI coding harness: the code and prompts that turn a task description into a working Python solution.

Objective, in priority order:
  1. pass as many tests as possible;
  2. at equal correctness, spend as few tokens as possible solving the tasks.
A new version is KEPT only if it passes more tests, or the same number of tests with at least {pct}% fewer tokens. Otherwise it is REVERTED. Token counts vary about 10% between runs of the same harness, so small savings don't count; aim for structural savings.

The harness is scored on TRAIN tasks you can see results for. The final grade comes from different, HIDDEN tasks of a similar kind (precise specs, tricky edge cases). So hardcoding train answers is worthless; only general improvements count.

Rules:
- harness.py must keep `solve(task, llm) -> str` returning Python source that defines task["entry"].
- `llm(system, messages, max_tokens)` is the only model access. Every token counts against a shared, fixed budget that also pays for this evolve step. Spend tokens where they buy accuracy.
- The harness may run Python locally (subprocess, exec) to test its own code before returning it. No internet.
- Use only the Python standard library.
- Keep notes.md updated: what you changed this generation, why, and what you learned.

Reply with a one-paragraph plan, then every file you want to create or replace, in full, in exactly this format:
=== FILE: name.py ===
<full file content>
=== END ===
Files you don't include stay as they are.""".replace("{pct}", str(round(MIN_SAVING * 100)))


def evolve_prompt(files, results, history, budget_left):
    parts = ["## Current harness files"]
    for name, content in files.items():
        parts.append(f"=== FILE: {name} ===\n{content}\n=== END ===")
    parts.append("## Score history (train tests passed)")
    for h in history:
        parts.append(f"- gen {h['gen']}: {h['passed']}/{h['total']} tests, {h.get('score_tokens')} tokens to solve, "
                     f"{'kept' if h['kept'] else 'REVERTED'}; {h.get('plan', '')[:300]}")
    parts.append("## Latest results on the current (best) harness")
    for r in results:
        line = f"### {r['task_id']}: {r['passed']}/{r['total']} tests, {r['tokens']} tokens"
        if r["failures"]:
            line += "\nFailed: " + "; ".join(f"{f['test']} ({f['error']})" for f in r["failures"])[:1500]
            line += f"\nSubmitted code:\n```python\n{r['code'][:2000]}\n```"
        parts.append(line)
    parts.append(f"## Budget\n{budget_left} tokens left for this lane (scoring + evolving).")
    return "\n\n".join(parts)


def apply_files(reply):
    written = []
    for name, content in re.findall(r"=== FILE: (.+?) ===\n(.*?)\n=== END ===", reply, re.S):
        name = name.strip()
        if not FILE_RE.match(name):
            continue
        with open(os.path.join(HARNESS, name), "w") as f:
            f.write(content + "\n")
        written.append(name)
    return written


def check_harness():
    p = subprocess.run([sys.executable, "-c", "import harness; assert callable(harness.solve)"],
                       cwd=HARNESS, capture_output=True, text=True, timeout=60)
    return p.returncode == 0, p.stderr[-800:]


def record(entry):
    with open(os.path.join(STATE, "history.jsonl"), "a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    setup()
    tasks = http_json("GET", "/tasks")
    log(f"{len(tasks)} train tasks, budget {remaining()} tokens")
    history, best, total = [], None, sum(t["n_tests"] for t in tasks)

    try:
        before = remaining()
        passed, total, tokens, results = score(tasks)
        best = {"passed": passed, "tokens": tokens, "commit": git("rev-parse", "HEAD"), "results": results}
        entry = {"gen": 0, "passed": passed, "total": total, "score_tokens": tokens, "kept": True,
                 "tokens": before - remaining(), "commit": best["commit"], "plan": "seed"}
        history.append(entry), record(entry)
        log(f"gen 0 (seed): {passed}/{total} tests, {tokens} tokens")

        for gen in range(1, MAX_GEN + 1):
            before = remaining()
            reply = llm(EVOLVE_SYSTEM, [{"role": "user", "content": evolve_prompt(
                read_harness(), best["results"], history, before)}], max_tokens=8000)
            plan = reply.split("=== FILE:")[0].strip()[:600]
            written = apply_files(reply)
            ok, err = check_harness() if written else (False, "no files returned")
            if not ok:
                git("checkout", "-q", "--", "."), git("clean", "-qfd")
                entry = {"gen": gen, "passed": None, "total": total, "kept": False,
                         "tokens": before - remaining(), "plan": f"INVALID ({err.strip()[-200:]}): {plan}"}
                history.append(entry), record(entry)
                log(f"gen {gen}: invalid harness, discarded")
                continue
            git("add", "-A"), git("commit", "-q", "--allow-empty", "-m", f"gen {gen} candidate: {plan[:200]}")
            git("tag", "-f", f"gen-{gen}")  # keeps reverted attempts reachable for the audit trail
            passed, total, tokens, results = score(tasks)
            kept = better(passed, tokens, best)
            commit = git("rev-parse", "HEAD")
            if kept:
                best = {"passed": passed, "tokens": tokens, "commit": commit, "results": results}
                git("tag", "-f", "best")
            else:
                git("reset", "-q", "--hard", best["commit"])
            entry = {"gen": gen, "passed": passed, "total": total, "score_tokens": tokens, "kept": kept,
                     "tokens": before - remaining(), "commit": commit, "files": written, "plan": plan}
            history.append(entry), record(entry)
            log(f"gen {gen}: {passed}/{total} tests, {tokens} tokens, {'KEPT' if kept else 'reverted'} "
                f"(changed {', '.join(written)})")
    except BudgetExhausted:
        log("budget exhausted")
        if best:
            git("reset", "-q", "--hard", best["commit"])

    if best:
        git("tag", "-f", "best", best["commit"])
        log(f"done. best harness: {best['passed']} train tests, {best['tokens']} tokens, "
            f"commit {best['commit'][:8]} (tag 'best')")
    with open(os.path.join(STATE, "DONE"), "w") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S"))


if __name__ == "__main__":
    main()