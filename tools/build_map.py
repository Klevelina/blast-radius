"""Run sqlglot's tests once with per-test coverage contexts and fixture-open
tracking, then write a compact map. Run inside the br-dev image."""
import gzip, json, os, sys
import coverage, pytest

ROOT = os.path.abspath(".")          # the sqlglot checkout (cwd)
OUT = sys.argv[1]
state = {"cur": None}
fixtures = {}                        # relative fixture path -> set of test ids

def audit(event, args):
    if event == "open" and state["cur"] and args and isinstance(args[0], str):
        p = args[0]
        if "/tests/fixtures/" in p:
            rel = os.path.relpath(p, ROOT)
            fixtures.setdefault(rel, set()).add(state["cur"])

class Plugin:
    def __init__(self, cov):
        self.cov = cov
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        state["cur"] = item.nodeid
        self.cov.switch_context(item.nodeid)
        yield
        state["cur"] = None
        self.cov.switch_context("")

sys.addaudithook(audit)
cov = coverage.Coverage(source_pkgs=["sqlglot"], data_file="/tmp/cov.db")
cov.start()
rc = pytest.main(["tests", "-q", "-p", "no:cacheprovider"], plugins=[Plugin(cov)])
cov.stop()
cov.save()
print("pytest exit code", rc, file=sys.stderr)

data = cov.get_data()
test_ids, tid = [], {}
sets, set_list = {}, []
files = {}
for f in data.measured_files():
    rel = os.path.relpath(f, ROOT)
    lines = {}
    for ln, ctxs in data.contexts_by_lineno(f).items():
        ids = []
        for c in ctxs:
            if c:
                if c not in tid:
                    tid[c] = len(test_ids); test_ids.append(c)
                ids.append(tid[c])
        key = tuple(sorted(ids))
        if key not in sets:
            sets[key] = len(set_list); set_list.append(list(key))
        lines[ln] = [sets[key], 1 if "" in ctxs else 0]   # [set index, ran at import time]
    files[rel] = lines

fx = {}
for rel, ids in fixtures.items():
    out = []
    for c in ids:
        if c not in tid:
            tid[c] = len(test_ids); test_ids.append(c)
        out.append(tid[c])
    fx[rel] = sorted(out)

with gzip.open(OUT, "wt") as fh:
    json.dump({"tests": test_ids, "sets": set_list, "files": files, "fixtures": fx},
              fh, separators=(",", ":"))
print("wrote", OUT, file=sys.stderr)
