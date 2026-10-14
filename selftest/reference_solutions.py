"""Reference solutions. Used only by selftest to prove every task is solvable and every test is right.
Never mounted into a lane."""

REF = {}

REF["roman_to_int"] = '''
def int_to_roman(n):
    vals = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),(50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s; n -= v
    return out
def roman_to_int(s):
    m = {"I":1,"V":5,"X":10,"L":50,"C":100,"D":500,"M":1000}
    if not s or any(c not in m for c in s):
        raise ValueError(s)
    total = 0
    for i, c in enumerate(s):
        v = m[c]
        total += -v if i + 1 < len(s) and m[s[i+1]] > v else v
    if not 1 <= total <= 3999 or int_to_roman(total) != s:
        raise ValueError(s)
    return total
'''

REF["parse_duration"] = '''
import re
def parse_duration(s):
    m = re.fullmatch(r"(?:(\\d+)d)?(?:(\\d+)h)?(?:(\\d+)m)?(?:(\\d+)s)?", s)
    if not s or not m:
        raise ValueError(s)
    d, h, mi, se = (int(x) if x else 0 for x in m.groups())
    return d*86400 + h*3600 + mi*60 + se
'''

REF["merge_intervals"] = '''
def merge_intervals(intervals):
    out = []
    for a, b in sorted([list(x) for x in intervals]):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out
'''

REF["eval_rpn"] = '''
def eval_rpn(tokens):
    st = []
    for t in tokens:
        if t in "+-*/" and len(t) == 1:
            if len(st) < 2:
                raise ValueError("too few operands")
            b, a = st.pop(), st.pop()
            if t == "+": st.append(a + b)
            elif t == "-": st.append(a - b)
            elif t == "*": st.append(a * b)
            else:
                if b == 0: raise ZeroDivisionError
                q = abs(a) // abs(b)
                st.append(q if (a >= 0) == (b >= 0) else -q)
        else:
            st.append(int(t))
    if len(st) != 1:
        raise ValueError("malformed")
    return st[0]
'''

REF["wrap_text"] = '''
def wrap_text(text, width):
    if width < 1:
        raise ValueError(width)
    lines, cur = [], ""
    for w in text.split():
        if len(w) > width:
            if cur:
                lines.append(cur)
            while len(w) > width:
                lines.append(w[:width]); w = w[width:]
            cur = w
        elif not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines
'''

REF["semver_compare"] = '''
import re
_P = re.compile(r"(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)(?:-([0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*))?(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?")
def _parse(v):
    m = _P.fullmatch(v)
    if not m:
        raise ValueError(v)
    pre = m.group(4).split(".") if m.group(4) else []
    for p in pre:
        if p.isdigit() and len(p) > 1 and p[0] == "0":
            raise ValueError(v)
    return tuple(int(x) for x in m.group(1, 2, 3)), pre
def _cmp(a, b):
    return (a > b) - (a < b)
def semver_compare(a, b):
    (ca, pa), (cb, pb) = _parse(a), _parse(b)
    if ca != cb:
        return _cmp(ca, cb)
    if not pa or not pb:
        return _cmp(not pa, not pb)
    for x, y in zip(pa, pb):
        if x == y: continue
        xd, yd = x.isdigit(), y.isdigit()
        if xd and yd: return _cmp(int(x), int(y))
        if xd != yd: return -1 if xd else 1
        return _cmp(x, y)
    return _cmp(len(pa), len(pb))
'''

REF["int_to_roman"] = '''
def int_to_roman(n):
    if not 1 <= n <= 3999:
        raise ValueError(n)
    vals = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),(50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s; n -= v
    return out
'''

REF["calc"] = '''
import re
def calc(expr):
    toks = re.findall(r"\\d+\\.\\d*|\\.\\d+|\\d+|[-+*/()]|\\S", expr)
    pos = 0
    def peek():
        return toks[pos] if pos < len(toks) else None
    def take():
        nonlocal pos
        t = peek(); pos += 1; return t
    def expr_():
        v = term()
        while peek() in ("+", "-"):
            v = v + term() if take() == "+" else v - term()
        return v
    def term():
        v = factor()
        while peek() in ("*", "/"):
            op = take(); r = factor()
            if op == "*": v *= r
            else:
                if r == 0: raise ZeroDivisionError
                v /= r
        return v
    def factor():
        t = take()
        if t == "-": return -factor()
        if t == "+": return factor()
        if t == "(":
            v = expr_()
            if take() != ")": raise ValueError("unclosed")
            return v
        if t is None or not re.fullmatch(r"\\d+\\.\\d*|\\.\\d+|\\d+", t): raise ValueError(t)
        return float(t)
    v = expr_()
    if pos != len(toks): raise ValueError("trailing")
    return v
'''

REF["topo_sort"] = '''
import heapq
def topo_sort(deps):
    nodes = set(deps) | {d for v in deps.values() for d in v}
    indeg = {n: 0 for n in nodes}; out = {n: [] for n in nodes}
    for n, ds in deps.items():
        for d in set(ds):
            indeg[n] += 1; out[d].append(n)
    h = [n for n in nodes if indeg[n] == 0]; heapq.heapify(h); res = []
    while h:
        n = heapq.heappop(h); res.append(n)
        for m in out[n]:
            indeg[m] -= 1
            if indeg[m] == 0: heapq.heappush(h, m)
    if len(res) != len(nodes): raise ValueError("cycle")
    return res
'''

REF["normalize_path"] = '''
def normalize_path(p):
    absolute = p.startswith("/")
    st = []
    for part in p.split("/"):
        if part in ("", "."): continue
        if part == "..":
            if st and st[-1] != "..": st.pop()
            elif not absolute: st.append("..")
        else:
            st.append(part)
    if absolute: return "/" + "/".join(st)
    return "/".join(st) or "."
'''

REF["parse_csv_line"] = '''
def parse_csv_line(line):
    out, i, n = [], 0, len(line)
    while True:
        if i < n and line[i] == '"':
            i += 1; buf = []
            while True:
                if i >= n: raise ValueError("unterminated")
                if line[i] == '"':
                    if i + 1 < n and line[i+1] == '"': buf.append('"'); i += 2; continue
                    i += 1; break
                buf.append(line[i]); i += 1
            out.append("".join(buf))
            if i < n and line[i] != ",": raise ValueError("text after quote")
        else:
            j = line.find(",", i)
            j = n if j == -1 else j
            out.append(line[i:j]); i = j
        if i >= n: return out
        i += 1
'''

REF["next_business_day"] = '''
import datetime as _dt
def next_business_day(date, holidays=()):
    d = _dt.date.fromisoformat(date); hs = set(holidays)
    while True:
        d += _dt.timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in hs: return d.isoformat()
'''
