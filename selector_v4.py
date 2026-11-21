"""Coverage-based selector v3 (function spans, wide fallback, fixture map)."""
import bisect, gzip, json, os, re, sys
from pathlib import Path

DATA = Path(os.environ.get("DATA_DIR", "/data"))
MAP = Path(os.environ.get("MAP", Path(__file__).parent / "data" / "map4.json.gz"))
FXWIDE = os.environ.get("FXWIDE") == "1"
WORKER_COST_MS, MAX_WORKERS = 2000, 8
POOLMAP = Path(os.environ.get("POOLMAP", Path(__file__).parent / "data" / "pool.json"))
CORE_STEMS = {"base", "dialect", "python", "duckdb", "__init__"}
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
ODD = ("new file mode", "deleted file mode", "rename ", "similarity ",
       "GIT binary patch", "Binary files", "old mode", "new mode")
HELPERS = ("conftest.py", "helpers.py", "__init__.py")
SPECIFIC = ("sqlglot/dialects/", "sqlglot/parsers/", "sqlglot/generators/", "sqlglot/typing/")


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
    i = 0
    while i < len(lines):
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
            a = int(m.group(1))
            oc = int(m.group(2)) if m.group(2) is not None else 1
            nc = int(m.group(4)) if m.group(4) is not None else 1
            o = a + 1 if oc == 0 else a
            block = None
            while (oc > 0 or nc > 0) and i < len(lines):
                t = lines[i]
                i += 1
                if t.startswith("-"):
                    if block:
                        cur["ins"].append(tuple(block)); block = None
                    cur["dels"].append((o, t[1:])); o += 1; oc -= 1
                elif t.startswith("+"):
                    if block is None:
                        block = [o - 1, o, []]
                    block[2].append(t[1:]); nc -= 1
                elif t.startswith("\\"):
                    pass
                else:
                    if block:
                        cur["ins"].append(tuple(block)); block = None
                    o += 1; oc -= 1; nc -= 1
            if block:
                cur["ins"].append(tuple(block))
        else:
            i += 1
    return files


def main():
    tests = json.loads((DATA / "tests.json").read_text())["tests"]
    durs = {t["number"]: round(t["seconds"] * 1000) for t in tests}
    num_by_id = {t["id"]: t["number"] for t in tests}
    file_by_num = {t["number"]: t["file"] for t in tests}
    by_file = {}
    for t in tests:
        by_file.setdefault(t["file"], set()).add(t["number"])
    ALL = set(durs)
    SLOW = {num_by_id[i] for i in SLOW_IDS if i in num_by_id}
    EXTRA = {num_by_id[i] for i in EXTRA_IDS if i in num_by_id}
    pool_ids = []
    POOL = {num_by_id[i] for i in pool_ids if i in num_by_id and not i.startswith("tests/test_executor.py")}
    POOL_EXEC = {num_by_id[i] for i in pool_ids if i in num_by_id and i.startswith("tests/test_executor.py")}

    with gzip.open(MAP, "rt") as fh:
        M = json.load(fh)
    tnum = [num_by_id.get(x) for x in M["tests"]]
    ALWAYS = {num_by_id[i] for i in M.get("always", []) if i in num_by_id}
    ALWAYS |= {n for n in ALL if n not in {x for x in tnum if x is not None}}
    SETS = [frozenset(tnum[j] for j in s if tnum[j] is not None) for s in M["sets"]]
    for F in M["files"].values():
        F["_starts"] = [s[0] for s in F["spans"]]

    def find_span(F, ln):
        if not F:
            return None
        i = bisect.bisect_right(F["_starts"], ln) - 1
        if i >= 0 and ln <= F["spans"][i][1]:
            return i
        return None

    def file_all(F):
        return SETS[F["all"]] if F else frozenset()

    def source_selection(F, f):
        sel, wide = set(), False
        for ln, text in f["dels"]:
            t = text.strip()
            if not t or t.startswith("#"):
                continue
            i = find_span(F, ln)
            if i is not None:
                sel |= SETS[F["spans"][i][2]]
                continue
            if F and str(ln) in F["outer"]:
                sel |= SETS[F["outer"][str(ln)]]
            else:
                wide = True
        for a, b, texts in f["ins"]:
            code = [x.strip() for x in texts if x.strip() and not x.strip().startswith("#")]
            if not code:
                continue
            ia, ib = find_span(F, a), find_span(F, b)
            for i in (ia, ib):
                if i is not None:
                    sel |= SETS[F["spans"][i][2]]
            if ia is not None and ia == ib:
                continue
            if code[0].startswith(("def ", "async def ", "@", "class ")):
                sel |= file_all(F)
                continue
            got = [F["outer"][str(x)] for x in (a, b) if F and str(x) in F["outer"]]
            if got:
                for g in got:
                    sel |= SETS[g]
                continue
            wide = True
        return sel, wide

    total = 0
    for patch in sorted((DATA / "commits").glob("*.patch")):
        sel, reasons, touches_src = set(), [], False
        for f in parse_patch(patch.read_text(errors="replace")):
            p = f["path"]
            if f["odd"]:
                sel = set(ALL); reasons.append("odd:" + p); break
            if p.startswith("sqlglot/") and p.endswith(".py"):
                touches_src = True
                F = M["files"].get(p)
                s, wide = source_selection(F, f)
                sel |= s
                real = any(t.strip() and not t.strip().startswith("#") for _, t in f["dels"]) or \
                    any(x.strip() and not x.strip().startswith("#") for _, _, ts in f["ins"] for x in ts)
                if real:
                    sel |= ALWAYS
                if wide:
                    if p.startswith(SPECIFIC):
                        sel |= (ALL - SLOW) | (SLOW & file_all(F))
                    else:
                        sel |= ALL
                    reasons.append("wide:" + p)
            elif p.startswith("tests/fixtures/"):
                idx = M["fixtures"].get(p)
                if idx is None:
                    sel |= ALL; reasons.append("fixture?:" + p)
                else:
                    s = {tnum[j] for j in idx if tnum[j] is not None}
                    if FXWIDE:
                        for n in list(s):
                            s |= by_file[file_by_num[n]]
                    sel |= s
            elif p.startswith("tests/") and p.endswith(".py"):
                if os.path.basename(p) in HELPERS or p == "tests/dialects/test_dialect.py" \
                        or p not in by_file:
                    sel |= ALL; reasons.append("testhelper:" + p)
                else:
                    sel |= by_file[p]
            elif p.endswith(".md") or p.startswith("docs/"):
                pass
            else:
                sel |= ALL; reasons.append("other:" + p)
        if touches_src:
            sel |= EXTRA
        cost, ws = best_split({n: durs[n] for n in sel})
        total += cost
        print(json.dumps({"commit": patch.stem, "workers": ws}))
        print(f"{patch.stem} n={len(sel)} cost={cost/1000:.1f}s {' '.join(reasons)}", file=sys.stderr)
    print(f"sum of costs {total/1000:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
