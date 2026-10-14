"""Grader: runs submitted code against hidden tests.

Lanes see only the TRAIN split (task prompts, and per-test pass/fail feedback).
The HELDOUT split is never shown to lanes and can only be graded with the admin
token, which only the final scorer has. That is what stops a harness from
"evolving" by memorising answers: improvement only counts if it transfers.

API:
  GET  /tasks                       -> train task specs (id, prompt, entry) - no tests
  POST /grade {task_id, code}       -> {passed, total, failures:[{test, error}]}   (train only)
  POST /admin/grade {task_id, code, split}  header X-Admin-Token  -> full result, any split
  GET  /admin/tasks?split=heldout   header X-Admin-Token  -> specs for that split
"""
import json, os, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

TASK_DIR = os.environ.get("TASK_DIR", "/tasks")
DATA_DIR = os.environ.get("DATA_DIR", "/data")
ADMIN = os.environ.get("GRADER_ADMIN_TOKEN", "")
os.makedirs(DATA_DIR, exist_ok=True)
lock = threading.Lock()

SPLITS = {}
for split in ("train", "heldout"):
    with open(os.path.join(TASK_DIR, f"{split}.json")) as f:
        SPLITS[split] = {t["id"]: t for t in json.load(f)}

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runner.py")


def spec(t):
    return {"id": t["id"], "entry": t["entry"], "prompt": t["prompt"]}


def grade(task, code):
    with tempfile.TemporaryDirectory() as d:
        payload = os.path.join(d, "payload.json")
        with open(payload, "w") as f:
            json.dump({"code": code, "tests": task["tests"]}, f)
        try:
            p = subprocess.run([sys.executable, "-I", RUNNER, payload], capture_output=True,
                               text=True, timeout=30, cwd=d)
            res = json.loads(p.stdout.strip().splitlines()[-1])
        except subprocess.TimeoutExpired:
            res = {"results": [{"test": t["name"], "ok": False, "error": "timeout (30s total)"} for t in task["tests"]]}
        except Exception as e:
            res = {"results": [{"test": t["name"], "ok": False, "error": f"runner crashed: {e}"} for t in task["tests"]]}
    results = res["results"]
    return {"task_id": task["id"], "passed": sum(r["ok"] for r in results), "total": len(results),
            "failures": [{"test": r["test"], "error": r["error"]} for r in results if not r["ok"]]}


def log(lane, split, result):
    with lock, open(os.path.join(DATA_DIR, "grades.jsonl"), "a") as f:
        f.write(json.dumps({"t": time.time(), "lane": lane, "split": split, "task_id": result["task_id"],
                            "passed": result["passed"], "total": result["total"]}) + "\n")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _admin(self):
        return bool(ADMIN) and self.headers.get("X-Admin-Token") == ADMIN

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/tasks":
            return self._send(200, [spec(t) for t in SPLITS["train"].values()])
        if u.path == "/admin/tasks":
            if not self._admin():
                return self._send(403, {"error": "forbidden"})
            split = parse_qs(u.query).get("split", ["heldout"])[0]
            return self._send(200, [spec(t) for t in SPLITS[split].values()])
        self._send(404, {"error": "not_found"})

    def do_POST(self):
        u = urlparse(self.path)
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
        except Exception:
            return self._send(400, {"error": "bad_json"})
        lane = self.headers.get("X-Lane", "unknown")
        if u.path == "/grade":
            split = "train"
        elif u.path == "/admin/grade":
            if not self._admin():
                return self._send(403, {"error": "forbidden"})
            split = req.get("split", "heldout")
        else:
            return self._send(404, {"error": "not_found"})
        task = SPLITS[split].get(req.get("task_id"))
        if task is None:
            return self._send(404, {"error": f"unknown task in {split}"})
        result = grade(task, str(req.get("code", "")))
        log(lane, split, result)
        self._send(200, result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8090"))
    print(f"grader: train={len(SPLITS['train'])} heldout={len(SPLITS['heldout'])} port={port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
