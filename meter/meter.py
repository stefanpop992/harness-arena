"""Token meter: the ONLY component that holds an API key.

Each lane (claude / openai) gets its own meter with its own budget. The lane
container has no internet access and no key; every model call goes through here,
so the budget can't be bypassed.

API (one endpoint, provider-neutral):
  POST /v1/complete  {"system": str, "messages": [{"role","content"}], "max_tokens": int}
    -> 200 {"text": str, "usage": {"input": n, "output": n}, "remaining": n}
    -> 402 {"error": "budget_exhausted", "remaining": 0}
  GET  /v1/budget    -> {"budget": n, "spent": n, "remaining": n, "calls": n}

Env: PROVIDER=anthropic|openai|mock, API_KEY, MODEL, TOKEN_BUDGET, DATA_DIR
Stdlib only, so the image needs nothing beyond python.
"""
import json, os, threading, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROVIDER = os.environ.get("PROVIDER", "mock")
API_KEY = os.environ.get("API_KEY", "")
MODEL = os.environ.get("MODEL", "")
BUDGET = int(os.environ.get("TOKEN_BUDGET", "2000000"))
DATA_DIR = os.environ.get("DATA_DIR", "/data")
MAX_OUT = int(os.environ.get("MAX_OUTPUT_TOKENS", "8000"))

os.makedirs(DATA_DIR, exist_ok=True)
LEDGER = os.path.join(DATA_DIR, "ledger.jsonl")
lock = threading.Lock()
state = {"spent": 0, "calls": 0}

# Resume spend after a restart so a crash can't reset the budget.
if os.path.exists(LEDGER):
    with open(LEDGER) as f:
        for line in f:
            r = json.loads(line)
            state["spent"] += r["input"] + r["output"]
            state["calls"] += 1


def _post(url, headers, body, timeout=600):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def call_anthropic(system, messages, max_tokens):
    d = _post("https://api.anthropic.com/v1/messages",
              {"x-api-key": API_KEY, "anthropic-version": "2023-06-01",
               "content-type": "application/json"},
              {"model": MODEL, "system": system, "messages": messages, "max_tokens": max_tokens})
    text = "".join(b.get("text", "") for b in d["content"] if b["type"] == "text")
    u = d["usage"]
    inp = u["input_tokens"] + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
    return text, inp, u["output_tokens"]


def call_openai(system, messages, max_tokens):
    msgs = ([{"role": "system", "content": system}] if system else []) + messages
    d = _post("https://api.openai.com/v1/chat/completions",
              {"Authorization": f"Bearer {API_KEY}", "content-type": "application/json"},
              {"model": MODEL, "messages": msgs, "max_completion_tokens": max_tokens})
    u = d["usage"]
    # completion_tokens includes hidden reasoning tokens -> they count against budget.
    return d["choices"][0]["message"]["content"] or "", u["prompt_tokens"], u["completion_tokens"]


def call_mock(system, messages, max_tokens):
    inp = (len(system) + sum(len(m["content"]) for m in messages)) // 4
    return "```python\ndef f():\n    return 1\n```", inp, 20


CALL = {"anthropic": call_anthropic, "openai": call_openai, "mock": call_mock}[PROVIDER]


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/v1/budget":
            with lock:
                self._send(200, {"provider": PROVIDER, "model": MODEL, "budget": BUDGET,
                                 "spent": state["spent"], "remaining": max(0, BUDGET - state["spent"]),
                                 "calls": state["calls"]})
        else:
            self._send(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/v1/complete":
            return self._send(404, {"error": "not_found"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
            system = str(req.get("system", ""))
            messages = [{"role": m["role"], "content": str(m["content"])} for m in req["messages"]]
            max_tokens = int(req.get("max_tokens", 4000))
        except Exception as e:
            return self._send(400, {"error": f"bad_request: {e}"})

        with lock:
            remaining = BUDGET - state["spent"]
        if remaining <= 0:
            return self._send(402, {"error": "budget_exhausted", "remaining": 0})
        max_tokens = max(1, min(max_tokens, MAX_OUT, remaining))

        t0 = time.time()
        try:
            text, inp, out = CALL(system, messages, max_tokens)
        except urllib.error.HTTPError as e:
            return self._send(502, {"error": f"provider_http_{e.code}", "detail": e.read()[:500].decode(errors="replace")})
        except Exception as e:
            return self._send(502, {"error": f"provider_error: {e}"})

        with lock:
            state["spent"] += inp + out
            state["calls"] += 1
            remaining = max(0, BUDGET - state["spent"])
            with open(LEDGER, "a") as f:
                f.write(json.dumps({"t": t0, "secs": round(time.time() - t0, 2), "input": inp,
                                    "output": out, "remaining": remaining}) + "\n")
        self._send(200, {"text": text, "usage": {"input": inp, "output": out}, "remaining": remaining})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"meter: provider={PROVIDER} model={MODEL} budget={BUDGET} spent={state['spent']} port={port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
