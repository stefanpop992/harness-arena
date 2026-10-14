"""Self-test for the foundation. Runs grader + a mock meter as local processes (no Docker, no keys).

Checks:
  1. every reference solution scores 100% on its task (tests are correct and passable)
  2. plausible-but-naive solutions fail the traps (tests actually discriminate)
  3. lanes cannot reach heldout tasks; admin endpoints reject missing tokens
  4. the meter enforces its budget, refuses at zero, and survives a restart without resetting spend
"""
import json, os, subprocess, sys, tempfile, time, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reference_solutions import REF  # noqa: E402

ADMIN = "selftest-admin"
fails = 0


def ok(cond, msg):
    global fails
    print(("  PASS " if cond else "  FAIL ") + msg)
    fails += 0 if cond else 1


def http(method, url, body=None, headers=None):
    req = urllib.request.Request(url, method=method, headers={"content-type": "application/json", **(headers or {})},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def wait(url):
    for _ in range(50):
        try:
            urllib.request.urlopen(url, timeout=1); return
        except urllib.error.HTTPError:
            return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"{url} never came up")


def start(script, env):
    return subprocess.Popen([sys.executable, script], env={**os.environ, **env})


NAIVE = {  # (task, code, test names it should fail)
    "eval_rpn": ("""
def eval_rpn(tokens):
    st = []
    for t in tokens:
        if t in '+-*/':
            b, a = st.pop(), st.pop()
            st.append({'+': a+b, '-': a-b, '*': a*b, '/': a//b if b else 1//b}[t])
        else:
            st.append(int(t))
    return st[0]
""", {"negative_division_truncates_toward_zero", "rejects_leftover_operands"}),
    "normalize_path": ("import posixpath\ndef normalize_path(p):\n    return posixpath.normpath(p)\n",
                       {"leading_double_slash"}),
    "parse_csv_line": ("import csv\ndef parse_csv_line(line):\n    return next(csv.reader([line])) if line else ['']\n",
                       {"rejects_text_after_quote"}),
}


def main():
    tmp = tempfile.mkdtemp()
    subprocess.run([sys.executable, os.path.join(ROOT, "tasks", "build_tasks.py")], check=True)

    g = start(os.path.join(ROOT, "grader", "grader.py"),
              {"TASK_DIR": os.path.join(ROOT, "tasks"), "DATA_DIR": os.path.join(tmp, "grader"),
               "GRADER_ADMIN_TOKEN": ADMIN, "PORT": "18090"})
    meter_env = {"PROVIDER": "mock", "TOKEN_BUDGET": "1000", "DATA_DIR": os.path.join(tmp, "meter"), "PORT": "18080"}
    m = start(os.path.join(ROOT, "meter", "meter.py"), meter_env)
    try:
        wait("http://127.0.0.1:18090/tasks"); wait("http://127.0.0.1:18080/v1/budget")
        G, M, A = "http://127.0.0.1:18090", "http://127.0.0.1:18080", {"X-Admin-Token": ADMIN}

        print("1. reference solutions score 100%")
        for split in ("train", "heldout"):
            _, specs = http("GET", f"{G}/admin/tasks?split={split}", headers=A)
            for s in specs:
                _, r = http("POST", f"{G}/admin/grade", {"task_id": s["id"], "code": REF[s["id"]], "split": split}, A)
                ok(r["passed"] == r["total"], f"{split}/{s['id']}: {r['passed']}/{r['total']} {r['failures'] or ''}")

        print("2. naive solutions hit the traps")
        for tid, (code, must_fail) in NAIVE.items():
            split = "train" if tid == "eval_rpn" else "heldout"
            _, r = http("POST", f"{G}/admin/grade", {"task_id": tid, "code": code, "split": split}, A)
            failed = {f["test"] for f in r["failures"]}
            ok(must_fail <= failed and r["passed"] > 0, f"{tid}: {r['passed']}/{r['total']}, failed {sorted(failed)}")
        _, r = http("POST", f"{G}/grade", {"task_id": "eval_rpn", "code": "while True: pass"})
        ok(r["passed"] == 0, f"infinite loop is contained: {r['failures'][0]['error']}")
        _, r = http("POST", f"{G}/grade", {"task_id": "eval_rpn", "code": "import sys; sys.exit(0)"})
        ok(r["passed"] == 0, f"sys.exit is contained: {r['failures'][0]['error']}")

        print("3. isolation")
        _, specs = http("GET", f"{G}/tasks")
        ok({s["id"] for s in specs} == {"roman_to_int", "parse_duration", "merge_intervals", "eval_rpn", "wrap_text", "semver_compare"}
           and all("tests" not in s for s in specs), "lane sees train prompts only, no tests")
        code, _ = http("POST", f"{G}/grade", {"task_id": "calc", "code": REF["calc"]})
        ok(code == 404, f"lane grading a heldout task -> {code}")
        code, _ = http("POST", f"{G}/admin/grade", {"task_id": "calc", "code": "", "split": "heldout"})
        ok(code == 403, f"admin grade without token -> {code}")
        code, _ = http("GET", f"{G}/admin/tasks?split=heldout", headers={"X-Admin-Token": "wrong"})
        ok(code == 403, f"admin tasks with wrong token -> {code}")

        print("4. meter budget")
        statuses, msg = [], {"system": "x" * 400, "messages": [{"role": "user", "content": "hi"}]}
        for _ in range(20):
            c, _ = http("POST", f"{M}/v1/complete", msg)
            statuses.append(c)
            if c == 402: break
        _, b = http("GET", f"{M}/v1/budget")
        ok(statuses[-1] == 402 and b["remaining"] == 0, f"refuses once spent: {len(statuses)-1} calls then 402, spent={b['spent']}")
        m.terminate(); m.wait()
        m = start(os.path.join(ROOT, "meter", "meter.py"), meter_env)
        wait(f"{M}/v1/budget")
        c, _ = http("POST", f"{M}/v1/complete", msg)
        ok(c == 402, f"restart does not reset budget -> {c}")
    finally:
        g.terminate(); m.terminate()

    print(f"\n{'ALL CHECKS PASSED' if not fails else f'{fails} CHECK(S) FAILED'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
