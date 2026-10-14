"""Final run, inside the lane container, after evolution has ended.

Solves the HIDDEN tasks with two versions of this lane's harness:
  seed - the starting harness (gen 0), identical for both lanes
  best - the harness evolution ended on (tag 'best')
Each version solves every task REPEATS times, because model output varies between runs.

This script only WRITES code. It never sees the hidden tests and has no grader password;
grading happens outside the container in score_final.py.

  in : /work/final_tasks.json      hidden task prompts (no tests), written by score_final.py
  out: /work/final_solutions.json  [{version, repeat, task_id, code, tokens, error}]
"""
import json, os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from client import remaining, BudgetExhausted  # noqa: E402

LANE = os.environ.get("LANE", "lane")
WORK = os.environ.get("WORK_DIR", "/work")
REPEATS = int(os.environ.get("REPEATS", "3"))
TASK_TIMEOUT = int(os.environ.get("TASK_TIMEOUT", "600"))
HARNESS = os.path.join(WORK, "harness")


def log(msg):
    print(f"[{LANE} final {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def git(*args):
    return subprocess.run(["git", "-C", HARNESS, *args], capture_output=True, text=True, check=True).stdout.strip()


def export(ref, dest):
    """Copy the harness files as they were at `ref` into dest (without touching the repo)."""
    archive = subprocess.run(["git", "-C", HARNESS, "archive", ref], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", dest], input=archive, check=True)


def solve(harness_dir, task):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(task, f)
    before = remaining()
    try:
        p = subprocess.run([sys.executable, os.path.join(HERE, "worker.py"), harness_dir, f.name],
                           capture_output=True, text=True, timeout=TASK_TIMEOUT)
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except subprocess.TimeoutExpired:
        out = {"error": f"harness timed out after {TASK_TIMEOUT}s"}
    except Exception as e:
        out = {"error": f"harness crashed: {e}"}
    finally:
        os.unlink(f.name)
    if out.get("error") == "budget_exhausted":
        raise BudgetExhausted()
    return out.get("code", ""), before - remaining(), out.get("error")


def main():
    with open(os.path.join(WORK, "final_tasks.json")) as f:
        tasks = json.load(f)
    versions = {"seed": git("rev-list", "--max-parents=0", "best"), "best": git("rev-parse", "best")}
    log(f"{len(tasks)} hidden tasks x {REPEATS} repeats; seed={versions['seed'][:8]} best={versions['best'][:8]}; "
        f"budget {remaining()} tokens")

    solutions, out_path = [], os.path.join(WORK, "final_solutions.json")
    try:
        for version, ref in versions.items():
            with tempfile.TemporaryDirectory() as d:
                export(ref, d)
                for rep in range(1, REPEATS + 1):
                    for t in tasks:
                        code, tokens, error = solve(d, t)
                        solutions.append({"version": version, "repeat": rep, "task_id": t["id"],
                                          "code": code, "tokens": tokens, "error": error})
                    log(f"{version} repeat {rep}/{REPEATS} done")
    except BudgetExhausted:
        log("budget exhausted - results are incomplete")
    with open(out_path, "w") as f:
        json.dump(solutions, f)
    log(f"wrote {len(solutions)} solutions")


if __name__ == "__main__":
    main()