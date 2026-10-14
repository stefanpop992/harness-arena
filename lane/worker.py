"""Runs one harness on one task in its own process, so a broken or hanging harness can't kill the lane.

Usage: python worker.py <harness_dir> <task.json>   -> prints {"code": ...} or {"error": ...}
"""
import json, os, sys, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from client import llm, BudgetExhausted  # noqa: E402


def main():
    harness_dir, task_path = sys.argv[1], sys.argv[2]
    with open(task_path) as f:
        task = json.load(f)
    sys.path.insert(0, harness_dir)
    os.chdir(harness_dir)
    out = sys.stdout
    sys.stdout = sys.stderr  # harness prints go to stderr, not into our result
    try:
        import harness
        code = harness.solve(task, llm)
        out.write(json.dumps({"code": str(code)}) + "\n")
    except BudgetExhausted:
        out.write(json.dumps({"error": "budget_exhausted"}) + "\n")
    except BaseException:
        out.write(json.dumps({"error": traceback.format_exc()[-1500:]}) + "\n")


if __name__ == "__main__":
    main()