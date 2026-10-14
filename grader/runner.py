"""Runs one submission against its tests in a fresh interpreter. Prints one JSON line."""
import io, json, signal, sys, contextlib

real_stdout = sys.stdout


class TestTimeout(Exception):
    pass


def _alarm(*_):
    raise TestTimeout("test exceeded 3s")


def short(e):
    msg = f"{type(e).__name__}: {e}"
    return msg[:300]


def main():
    with open(sys.argv[1]) as f:
        p = json.load(f)
    signal.signal(signal.SIGALRM, _alarm)
    sink = io.StringIO()
    ns = {"__name__": "submission"}
    results = []
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            signal.alarm(5)
            exec(compile(p["code"], "submission.py", "exec"), ns)
            signal.alarm(0)
    except BaseException as e:
        signal.alarm(0)
        err = "submission failed to load: " + short(e)
        results = [{"test": t["name"], "ok": False, "error": err} for t in p["tests"]]
    else:
        for t in p["tests"]:
            env = dict(ns)
            try:
                with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                    signal.alarm(3)
                    exec(t["code"], env)
                    signal.alarm(0)
                results.append({"test": t["name"], "ok": True, "error": None})
            except BaseException as e:
                signal.alarm(0)
                results.append({"test": t["name"], "ok": False, "error": short(e)})
    real_stdout.write(json.dumps({"results": results}) + "\n")


if __name__ == "__main__":
    main()
