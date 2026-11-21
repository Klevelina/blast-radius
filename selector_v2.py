"""Coverage-based selector (draft). Falls back to the full suite when unsure."""
import gzip, json, os, re, sys
from pathlib import Path

DATA = Path(os.environ.get("DATA_DIR", "/data"))
MAP = Path(os.environ.get("MAP", Path(__file__).parent / "data" / "map.json.gz"))
WORKER_COST_MS, MAX_WORKERS = 2000, 8


def best_split(durs):
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
    return best[1]


def parse_patch(text):
    """-> list of file dicts with the changed OLD line numbers."""
    out, cur, lines, i = [], None, text.split("\n"), 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("diff --git"):
            m = re.match(r"diff --git a/(\S+) b/(\S+)", l)
            cur = {"path": m.group(1) if m else "?", "lines": set(), "odd": m is None}
            out.append(cur)
        elif cur is not None and (l.startswith(("new file mode", "deleted file mode",
                "rename ", "similarity ", "GIT binary patch", "Binary files"))):
            cur["odd"] = True
        elif cur is not None and l.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", l)
            if not m:
                cur["odd"] = True
                i += 1
                continue
            o = int(m.group(1))
            oc = int(m.group(2)) if m.group(2) is not None else 1
            nc = int(m.group(4)) if m.group(4) is not None else 1
            i += 1
            while (oc > 0 or nc > 0) and i < len(lines):
                t = lines[i]
                if t.startswith("-"):
                    cur["lines"].add(o); o += 1; oc -= 1
                elif t.startswith("+"):
                    cur["lines"].update((o - 1, o)); nc -= 1   # anchor to old neighbours
                elif t.startswith("\\"):
                    pass
                else:
                    o += 1; oc -= 1; nc -= 1
                i += 1
            continue
        i += 1
    return out


def main():
    tests = json.loads((DATA / "tests.json").read_text())["tests"]
    durs = {t["number"]: round(t["seconds"] * 1000) for t in tests}
    num_by_id = {t["id"]: t["number"] for t in tests}
    ALL = set(durs)
    EXTRA_IDS = [
        "tests/dialects/test_dialect.py::TestDialect::test_lazy_load",
        "tests/test_sqlglotc.py::TestSQLGlotC::test_build_removes_obsolete_extensions",
        "tests/test_sqlglotc.py::TestSQLGlotC::test_dry_run_preserves_obsolete_extensions",
        "tests/test_sqlglotc.py::TestSQLGlotC::test_editable_install_removes_obsolete_extensions",
        "tests/test_typing.py::TestTyping::test_no_redundant_expression_metadata",
    ]
    EXTRA = {num_by_id[i] for i in EXTRA_IDS if i in num_by_id}
    by_file = {}
    for t in tests:
        by_file.setdefault(t["file"], set()).add(t["number"])

    with gzip.open(MAP, "rt") as fh:
        M = json.load(fh)
    tnum = [num_by_id.get(x) for x in M["tests"]]      # map index -> test number
    sets = [{tnum[j] for j in s if tnum[j] is not None} for s in M["sets"]]
    file_all = {}

    def all_of(path):
        if path not in file_all:
            u = set()
            for s in {e[0] for e in M["files"][path].values()}:
                u |= sets[s]
            file_all[path] = u
        return file_all[path]

    full = best_split(durs)
    stats = {"full": 0, "empty": 0, "part": 0}
    for patch in sorted((DATA / "commits").glob("*.patch")):
        sel = set()
        pfiles = parse_patch(patch.read_text(errors="replace"))
        touches_src = any(not f["path"].endswith(".md") and not f["path"].startswith("tests/fixtures/") for f in pfiles)
        for f in pfiles:
            p = f["path"]
            if f["odd"]:
                sel = ALL; break
            if p in M["files"]:
                for ln in f["lines"]:
                    e = M["files"][p].get(str(ln))
                    if e is None:
                        continue
                    sel |= sets[e[0]]
                    if e[1]:
                        sel |= all_of(p)
            elif p.startswith("tests/fixtures/") and p in M["fixtures"]:
                sel |= {tnum[j] for j in M["fixtures"][p] if tnum[j] is not None}
            elif p.startswith("tests/") and p.endswith(".py") and \
                    os.path.basename(p) not in ("conftest.py", "helpers.py", "__init__.py") \
                    and p != "tests/dialects/test_dialect.py" and p in by_file:
                sel |= by_file[p]
            elif p.endswith(".md"):
                pass
            else:
                sel = ALL; break
        if sel or touches_src:
            sel |= EXTRA
        if sel >= ALL:
            ws = full; stats["full"] += 1
        elif not sel:
            ws = []; stats["empty"] += 1
        else:
            ws = best_split({n: durs[n] for n in sel}); stats["part"] += 1
        print(json.dumps({"commit": patch.stem, "workers": ws}))
    print(stats, file=sys.stderr)


if __name__ == "__main__":
    main()
