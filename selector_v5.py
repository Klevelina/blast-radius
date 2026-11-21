"""Coverage-based selector v5: line-level lookup of the changed lines."""
import bisect
import gzip
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("DATA_DIR", "/data"))
MAP = Path(os.environ.get("MAP", HERE / "data" / "map5.json.gz"))
WORKER_COST_MS, MAX_WORKERS = 2000, 8
SLOW_IDS = [
    "tests/test_parser.py::TestParser::test_max_nodes",
    "tests/test_executor.py::TestExecutor::test_execute_tpcds",
    "tests/test_generator.py::TestGenerator::test_generator_memory",
]
EXTRA_IDS = [
    "tests/dialects/test_dialect.py::TestDialect::test_lazy_load",
    "tests/test_sqlglotc.py::TestSQLGlotC::test_build_removes_obsolete_extensions",
    "tests/test_sqlglotc.py::TestSQLGlotC::test_dry_run_preserves_obsolete_extensions",
    "tests/test_sqlglotc.py::TestSQLGlotC::test_editable_install_removes_obsolete_extensions",
    "tests/test_typing.py::TestTyping::test_no_redundant_expression_metadata",
]
DOC_TEST_FILE = "tests/test_docs.py"
ODD = ("new file mode", "deleted file mode", "rename ", "similarity ",
       "GIT binary patch", "Binary files", "old mode", "new mode")
HELPERS = ("conftest.py", "helpers.py", "__init__.py")
SPECIFIC = ("sqlglot/dialects/", "sqlglot/parsers/", "sqlglot/generators/", "sqlglot/typing/")
DEFLIKE = ("def ", "async def ", "@", "class ")
FLOW = re.compile(r"\b(if|elif|else|while|and|or|not|is|in|for|try|except|with|assert|lambda)\b|[=!<>]=|[<>]|\?")


def best_split(durs):
    if not durs:
        return 0, []
    items = sorted(durs.items(), key=lambda kv: -kv[1])
    best = None
    for k in range(1, MAX_WORKERS + 1):
        ws, loads = [[] for _ in range(k)], [0] * k
        for n, ms in items:
            i = loads.index(min(loads))
            ws[i].append(n)
            loads[i] += ms
        cost = max(loads) + WORKER_COST_MS * k
        if best is None or cost < best[0]:
            best = (cost, ws)
    return best


def parse_patch(text):
    files, cur = [], None
    lines = text.split("\n")
    i, n = 0, len(lines)
    while i < n:
        l = lines[i]
        if l.startswith("diff --git"):
            m = re.match(r"diff --git a/(\S+) b/(\S+)", l)
            cur = {"path": m.group(1) if m else "?", "dels": [], "ins": [], "odd": m is None}
            files.append(cur)
            i += 1
        elif cur is not None and l.startswith(ODD):
            cur["odd"] = True
            i += 1
        elif cur is not None and l.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", l)
            i += 1
            if not m:
                cur["odd"] = True
                continue
            a0 = int(m.group(1))
            oc = int(m.group(2)) if m.group(2) is not None else 1
            nc = int(m.group(4)) if m.group(4) is not None else 1
            o = a0 + 1 if oc == 0 else a0
            block, prev_del = None, False
            while (oc > 0 or nc > 0) and i < n:
                t = lines[i]
                i += 1
                if t.startswith("-"):
                    if block is not None:
                        cur["ins"].append(tuple(block))
                        block = None
                    cur["dels"].append((o, t[1:]))
                    o += 1
                    oc -= 1
                    prev_del = True
                elif t.startswith("+"):
                    if block is None:
                        block = [o - 1, o, [], prev_del]
                    block[2].append(t[1:])
                    nc -= 1
                elif t.startswith("\\"):
                    pass
                else:
                    if block is not None:
                        cur["ins"].append(tuple(block))
                        block = None
                    o += 1
                    oc -= 1
                    nc -= 1
                    prev_del = False
            if block is not None:
                cur["ins"].append(tuple(block))
        else:
            i += 1
    return files


def main():
    tests = json.loads((DATA / "tests.json").read_text())["tests"]
    durs = {t["number"]: round(t["seconds"] * 1000) for t in tests}
    num_by_id = {t["id"]: t["number"] for t in tests}
    by_file = {}
    for t in tests:
        by_file.setdefault(t["file"], set()).add(t["number"])
    ALLNUM = set(durs)

    with gzip.open(MAP, "rt") as fh:
        M = json.load(fh)
    ids = M["tests"]
    idx_of = {x: j for j, x in enumerate(ids)}
    tnum = [num_by_id.get(x) for x in ids]
    FULL = (1 << len(ids)) - 1
    mapped = {x for x in tnum if x is not None}
    ALWAYS = {num_by_id[i] for i in M.get("always", []) if i in num_by_id} | (ALLNUM - mapped)
    EXTRA = {num_by_id[i] for i in EXTRA_IDS if i in num_by_id}
    DOCTESTS = by_file.get(DOC_TEST_FILE, set())
    SLOWMASK = 0
    for i in SLOW_IDS:
        if i in idx_of:
            SLOWMASK |= 1 << idx_of[i]
    hexsets = M["sets"]
    cache = {}

    def S(k):
        v = cache.get(k)
        if v is None:
            v = cache[k] = int(hexsets[k], 16)
        return v

    def nums(mask):
        if mask == FULL:
            return set(mapped)
        out = set()
        while mask:
            low = mask & -mask
            num = tnum[low.bit_length() - 1]
            mask ^= low
            if num is not None:
                out.add(num)
        return out

    def get_file(p):
        F = M["files"].get(p)
        if F is not None and "_sp" not in F:
            F["_sp"] = [s[0] for s in F["spans"]]
            F["_mls"] = F["ml"][0::2]
            F["_st"] = set(F["st"])
        return F

    def find_span(F, ln):
        if F is None:
            return None
        i = bisect.bisect_right(F["_sp"], ln) - 1
        if i >= 0 and ln <= F["spans"][i][1]:
            return i
        return None

    def region_of(F, ln):
        if F is None:
            return None
        ml = F["ml"]
        i = bisect.bisect_right(F["_mls"], ln) - 1
        for k in range(i, max(i - 3, -1), -1):
            if ml[2 * k] <= ln <= ml[2 * k + 1]:
                return ml[2 * k], ml[2 * k + 1]
        if ln in F["_st"]:
            return ln, ln
        return None

    def rng(F, a, b):
        rl, rs = F["rl"], F["rs"]
        m = 0
        for k in range(bisect.bisect_left(rl, a), bisect.bisect_right(rl, b)):
            m |= S(rs[k])
        return m

    def in_doc(F, ln):
        d = F["doc"]
        for k in range(0, len(d), 2):
            if d[k] <= ln <= d[k + 1]:
                return True
        return False

    def source_selection(F, f):
        mask, wide, doc = 0, False, False
        if F is None:
            return 0, True, False
        for ln, text in f["dels"]:
            t = text.strip()
            if not t or t.startswith("#"):
                continue
            if in_doc(F, ln):
                doc = True
            i = find_span(F, ln)
            if i is not None and (FLOW.search(t) or t.startswith(("return", "yield", "raise"))):
                mask |= S(F["spans"][i][2])
                continue
            r = region_of(F, ln)
            if r is not None:
                m = rng(F, r[0], r[1])
                if m == 0 and i is not None:
                    m = S(F["spans"][i][2])
                mask |= m
                continue
            if i is not None:
                mask |= S(F["spans"][i][2])
                continue
            wide = True
        for a, b, texts, repl in f["ins"]:
            code = [x for x in texts if x.strip() and not x.strip().startswith("#")]
            if not code:
                continue
            if in_doc(F, a) or in_doc(F, b):
                doc = True
            first = code[0].lstrip()
            if first.startswith(DEFLIKE):
                mask |= S(F["all"])
                continue
            if repl:
                continue
            if len(code[0]) == len(first):
                mask |= S(F["all"])
                continue
            ra, rb = region_of(F, a), region_of(F, b)
            if ra is not None and ra == rb and ra[1] > ra[0]:
                mask |= rng(F, ra[0], ra[1])
                continue
            ia, ib = find_span(F, a), find_span(F, b)
            got = False
            for i in (ia, ib):
                if i is not None:
                    mask |= S(F["spans"][i][2])
                    got = True
            if ia is not None and ia == ib:
                continue
            for x, i in ((a, ia), (b, ib)):
                if i is None:
                    r = region_of(F, x)
                    if r is not None:
                        mask |= rng(F, r[0], r[1])
                        got = True
            if not got:
                wide = True
        return mask, wide, doc

    total = 0
    for patch in sorted((DATA / "commits").glob("*.patch")):
        msk, extra, reasons = 0, set(), []
        touches_src = real_src = docflag = False
        for f in parse_patch(patch.read_text(errors="replace")):
            p = f["path"]
            if f["odd"]:
                msk, extra = FULL, set(ALLNUM)
                reasons.append("odd:" + p)
                break
            if p.startswith("sqlglot/") and p.endswith(".py"):
                touches_src = True
                F = get_file(p)
                m, wide, doc = source_selection(F, f)
                real = any(t.strip() and not t.strip().startswith("#") for _, t in f["dels"]) or \
                    any(x.strip() and not x.strip().startswith("#")
                        for _, _, ts, _r in f["ins"] for x in ts)
                real_src = real_src or real
                docflag = docflag or doc
                msk |= m
                if wide:
                    if p.startswith(SPECIFIC):
                        fall = S(F["all"]) if F is not None else 0
                        msk |= (FULL & ~SLOWMASK) | (SLOWMASK & fall)
                    else:
                        msk, extra = FULL, set(ALLNUM)
                    reasons.append("wide:" + p)
            elif p.startswith("tests/fixtures/"):
                k = M["fixtures"].get(p)
                if k is None:
                    msk, extra = FULL, set(ALLNUM)
                    reasons.append("fixture?:" + p)
                else:
                    msk |= S(k)
            elif p.startswith("tests/") and p.endswith(".py"):
                if os.path.basename(p) in HELPERS or p == "tests/dialects/test_dialect.py" \
                        or p not in by_file:
                    msk, extra = FULL, set(ALLNUM)
                    reasons.append("testhelper:" + p)
                else:
                    extra |= by_file[p]
            elif p.endswith(".md") or p.startswith("docs/"):
                pass
            else:
                msk, extra = FULL, set(ALLNUM)
                reasons.append("other:" + p)
        if real_src:
            extra |= ALWAYS
        if touches_src:
            extra |= EXTRA
        if docflag:
            extra |= DOCTESTS
        sel = nums(msk) | extra
        cost, ws = best_split({n: durs[n] for n in sel})
        total += cost
        print(json.dumps({"commit": patch.stem, "workers": ws}))
        print(f"{patch.stem} n={len(sel)} cost={cost / 1000:.1f}s {' '.join(reasons)}", file=sys.stderr)
    print(f"sum of costs {total / 1000:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
