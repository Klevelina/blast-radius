import builtins, io, json, os, sys
import coverage, pytest

ROOT = os.path.abspath(".")
out, args = sys.argv[1], sys.argv[2:]
state = {"cur": None}
fixtures = {}

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
    def __init__(self, cov): self.cov = cov
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        state["cur"] = item.nodeid
        self.cov.switch_context(item.nodeid)
        yield
        state["cur"] = None
        self.cov.switch_context("")

cov = coverage.Coverage(source_pkgs=["sqlglot"], data_file=out + ".cov")
cov.start()
rc = pytest.main(["-q", "-p", "no:cacheprovider", *args], plugins=[Plugin(cov)])
cov.stop(); cov.save()
with open(out + ".fx.json", "w") as fh:
    json.dump({k: sorted(v) for k, v in fixtures.items()}, fh)
print("shard", out, "exit", rc, file=sys.stderr)
