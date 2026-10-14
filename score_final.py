"""Final score: who built the better self-evolving harness? Run on the host after both lanes are done.

  python3 score_final.py               # full run: solve the hidden tasks, then grade
  python3 score_final.py --grade-only  # only grade solutions that were already written

1. Stops the evolution meters and starts fresh "final" meters (new ledger, same budget per lane),
   so the final run isn't starved by whatever evolution spent.
2. In each lane container, final.py solves the HIDDEN tasks with the seed harness and the
   evolved 'best' harness, REPEATS times each. The container gets task prompts only - no tests,
   no grader password.
3. Here on the host, a local grader (grader.py, plain Python, no Docker) grades every solution
   against the hidden tests. The grader container sits only on sealed networks, so it can't be
   reached from the host - and doesn't need to be.
4. Prints the result and writes runs/results.json and runs/results.md.

Winner: the 'best' harness that passes more hidden tests on average; if equal, fewer tokens on average.
"""
import json, os, secrets, subprocess, sys, time, urllib.request
from statistics import mean

ROOT = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(ROOT, "runs")
LANES = ["claude", "openai"]
GRADER = "http://127.0.0.1:18190"   # local grader started by start_local_grader()
REPEATS = os.environ.get("REPEATS", "3")


def read_env():
    env = {}
    with open(os.path.join(ROOT, ".env")) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def start_local_grader():
    """Start grader.py on the host with a one-off admin token. Returns (process, token)."""
    token = secrets.token_hex(16)
    data = os.path.join(RUNS, "grader-final")
    os.makedirs(data, exist_ok=True)
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "grader", "grader.py")],
                            env={**os.environ, "TASK_DIR": os.path.join(ROOT, "tasks"), "DATA_DIR": data,
                                 "GRADER_ADMIN_TOKEN": token, "PORT": GRADER.rsplit(":", 1)[1]})
    for _ in range(100):
        try:
            urllib.request.urlopen(f"{GRADER}/tasks", timeout=1)
            return proc, token
        except Exception:
            time.sleep(0.1)
    proc.terminate()
    sys.exit("local grader did not start")


def admin_grade(token, task_id, code):
    req = urllib.request.Request(f"{GRADER}/admin/grade", method="POST",
                                 data=json.dumps({"task_id": task_id, "code": code, "split": "heldout"}).encode(),
                                 headers={"content-type": "application/json", "X-Admin-Token": token,
                                          "X-Lane": "final-scorer"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def grade_lane(token, solutions, tasks):
    """Grade one lane's solutions. Returns {version: summary} with per-task detail."""
    n_tests = {t["id"]: len(t["tests"]) for t in tasks}
    total = sum(n_tests.values())
    out = {}
    for version in ("seed", "best"):
        rows = [s for s in solutions if s["version"] == version]
        reps = sorted({s["repeat"] for s in rows})
        per_rep, per_task = [], {t: [] for t in n_tests}
        for rep in reps:
            passed = tokens = 0
            for s in (s for s in rows if s["repeat"] == rep):
                g = admin_grade(token, s["task_id"], s["code"]) if s["code"] else {"passed": 0}
                passed += g["passed"]
                tokens += s["tokens"]
                per_task[s["task_id"]].append(g["passed"])
            per_rep.append({"passed": passed, "tokens": tokens})
        complete = len(rows) == len(reps) * len(n_tests) and len(reps) > 0
        out[version] = {
            "total": total, "repeats": len(reps), "complete": complete,
            "passed_mean": round(mean(r["passed"] for r in per_rep), 2) if per_rep else 0,
            "passed_each": [r["passed"] for r in per_rep],
            "tokens_mean": round(mean(r["tokens"] for r in per_rep)) if per_rep else 0,
            "per_task": {t: f"{round(mean(v), 1) if v else 0}/{n_tests[t]}" for t, v in per_task.items()},
        }
    return out


def winner(results):
    a, b = (results[l]["best"] for l in LANES)
    if a["passed_mean"] != b["passed_mean"]:
        return (LANES[0] if a["passed_mean"] > b["passed_mean"] else LANES[1]), "more hidden tests passed"
    if a["tokens_mean"] != b["tokens_mean"]:
        return (LANES[0] if a["tokens_mean"] < b["tokens_mean"] else LANES[1]), "same tests passed, fewer tokens"
    return None, "exact tie"


def report(results, models):
    w, why = winner(results)
    lines = ["# Final result: hidden tasks", "",
             "| Lane | Model | Harness | Hidden tests passed (mean) | Each repeat | Tokens (mean) |",
             "|---|---|---|---|---|---|"]
    for lane in LANES:
        for v in ("seed", "best"):
            r = results[lane][v]
            flag = "" if r["complete"] else " (incomplete: budget ran out)"
            lines.append(f"| {lane} | {models[lane]} | {v} | {r['passed_mean']}/{r['total']}{flag} | "
                         f"{r['passed_each']} | {r['tokens_mean']} |")
    lines += ["", "## What evolution changed (best minus seed)", ""]
    for lane in LANES:
        s, b = results[lane]["seed"], results[lane]["best"]
        dt = b["tokens_mean"] - s["tokens_mean"]
        pct = f" ({dt / s['tokens_mean'] * 100:+.0f}%)" if s["tokens_mean"] else ""
        lines.append(f"- **{lane}**: tests {b['passed_mean'] - s['passed_mean']:+.2f}, tokens {dt:+d}{pct}")
    lines += ["", "## Per task (best harness, mean tests passed)", "", "| Task | " + " | ".join(LANES) + " |",
              "|---|" + "---|" * len(LANES)]
    for t in results[LANES[0]]["best"]["per_task"]:
        lines.append(f"| {t} | " + " | ".join(results[l]["best"]["per_task"][t] for l in LANES) + " |")
    lines += ["", f"**Winner: {w}** ({why})." if w else f"**No winner** ({why})."]
    return "\n".join(lines)


def compose(*args, env=None):
    subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True, env={**os.environ, **(env or {})})


def main():
    env = read_env()
    with open(os.path.join(ROOT, "tasks", "heldout.json")) as f:
        tasks = json.load(f)

    if "--grade-only" not in sys.argv:
        for lane in LANES:
            if not os.path.exists(os.path.join(RUNS, lane, "work", "state", "DONE")):
                sys.exit(f"lane '{lane}' hasn't finished evolving yet (no runs/{lane}/work/state/DONE)")
        phase = {"PHASE": "final", "REPEATS": REPEATS}
        compose("down")
        for lane in LANES:
            os.makedirs(os.path.join(RUNS, lane, "meter-final"), exist_ok=True)
            specs = [{"id": t["id"], "entry": t["entry"], "prompt": t["prompt"], "n_tests": len(t["tests"])}
                     for t in tasks]
            with open(os.path.join(RUNS, lane, "work", "final_tasks.json"), "w") as f:
                json.dump(specs, f)
            compose("run", "--rm", "-e", f"REPEATS={REPEATS}", f"lane-{lane}", "python", "-u", "final.py", env=phase)
        compose("down", env=phase)

    proc, token = start_local_grader()
    try:
        results = {}
        for lane in LANES:
            path = os.path.join(RUNS, lane, "work", "final_solutions.json")
            if not os.path.exists(path):
                sys.exit(f"no solutions for '{lane}' yet ({path}) - run without --grade-only first")
            with open(path) as f:
                results[lane] = grade_lane(token, json.load(f), tasks)
    finally:
        proc.terminate()

    models = {"claude": env.get("CLAUDE_MODEL", "?"), "openai": env.get("OPENAI_MODEL", "?")}
    md = report(results, models)
    with open(os.path.join(RUNS, "results.json"), "w") as f:
        json.dump({"models": models, "results": results}, f, indent=1)
    with open(os.path.join(RUNS, "results.md"), "w") as f:
        f.write(md + "\n")
    print("\n" + md)


if __name__ == "__main__":
    main()
