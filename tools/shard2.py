import builtins, io, json, os, sys
import coverage, pytest

out, args = sys.argv[1], sys.argv[2:]
ROOT = os.path.abspath(".")
lines_by_test, fixtures, state = {}, {}, {"cur": None}

_orig = builtins.open
def _open(file, *a, **k):
    c = state["cur"]
    if c and isinstance(file, (str, os.PathLike)):
        p = os.fspath(file)
        if isinstance(p, str) and "tests/fixtures/" in p:
            rel = os.path.relpath(os.path.abspath(p), ROOT)
            fixtures.setdefault(rel, set()).add(c)
    return _orig(file, *a, **k)
builtins.open = _open
io.open = _open

class Plugin:
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        state["cur"] = item.nodeid
        if os.environ.get("RESTART") and hasattr(sys, "monitoring"):
            sys.monitoring.restart_events()
        cov = coverage.Coverage(source_pkgs=["sqlglot"], data_file=None)
        cov.start()
        yield
        cov.stop()
        d = cov.get_data()
        lines_by_test[item.nodeid] = {
            os.path.relpath(f, ROOT): sorted(d.lines(f) or []) for f in d.measured_files()
        }
        state["cur"] = None

rc = pytest.main(["-q", "-p", "no:cacheprovider", *args], plugins=[Plugin()])
with _orig(out + ".json", "w") as fh:
    json.dump({"lines": lines_by_test,
               "fx": {k: sorted(v) for k, v in fixtures.items()}}, fh)
print("shard", out, "exit", rc, file=sys.stderr)