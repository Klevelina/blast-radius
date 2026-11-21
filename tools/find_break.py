import concurrent.futures as cf, subprocess, sys, coverage
TARGET = "tests/test_optimizer.py::TestOptimizer::test_eliminate_joins"
FILE = "tests/test_optimizer.py"

def recorded(out):
    d = coverage.CoverageData(basename=out + ".cov")
    d.read()
    n = 0
    for fn in d.measured_files():
        if fn.endswith("optimizer/eliminate_joins.py"):
            for ln, cs in d.contexts_by_lineno(fn).items():
                if TARGET in cs:
                    n += 1
    return n

def run(args, out):
    subprocess.run([sys.executable, "../tools/shard.py", out, *args],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
    return recorded(out)

col = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q",
                      "-p", "no:cacheprovider", FILE],
                     capture_output=True, text=True).stdout
ids = [l.strip() for l in col.splitlines() if "::" in l and l.strip() != TARGET]
print("tests to try:", len(ids), flush=True)
print("whole file, lines recorded for target:", run([FILE], "/tmp/whole"), flush=True)

def pair(item):
    i, t = item
    return t, run([t, TARGET], f"/tmp/p{i}")

with cf.ThreadPoolExecutor(4) as ex:
    for t, n in ex.map(pair, enumerate(ids)):
        if n == 0:
            print("BREAKS:", t, flush=True)
print("done", flush=True)
