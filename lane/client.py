"""The only way a harness can talk to a model: through this lane's meter."""
import json, os, urllib.request, urllib.error

METER_URL = os.environ.get("METER_URL", "http://meter:8080")


class BudgetExhausted(Exception):
    pass


def llm(system, messages, max_tokens=4000):
    """Call the model. Returns the reply text. Raises BudgetExhausted when the lane's budget is gone."""
    body = json.dumps({"system": system, "messages": messages, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(f"{METER_URL}/v1/complete", data=body, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.loads(r.read())["text"]
    except urllib.error.HTTPError as e:
        if e.code == 402:
            raise BudgetExhausted()
        raise RuntimeError(f"meter error {e.code}: {e.read()[:300].decode(errors='replace')}")


def remaining():
    with urllib.request.urlopen(f"{METER_URL}/v1/budget", timeout=30) as r:
        return json.loads(r.read())["remaining"]