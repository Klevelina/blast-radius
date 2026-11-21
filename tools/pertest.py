import concurrent.futures as cf, glob, json, os, shutil, subprocess, sys, time
import coverage

ROOT = os.path.abspath(".")
OUTDIR = "/work/raw3"
RC = "/work/tools/cov.rc"
POOL = int(os.environ.get("POOL", "4"))
LIMIT = int(os.environ.get("TEST_TIMEOUT", "900"))
ONLY = os.environ.get("ONLY")          # substring filter, for trials

col = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "tests"],
                     capture_output=True, text=True).stdout
nodes = []
for l in col.splitlines():
    l = l.strip()
    if "::" in l and not l.startswith(("ERROR", "FAILED")):
        nodes.append(l)
nodes = list(dict.fromkeys(nodes))
if ONLY:
    nodes = [n for n in nodes if ONLY in n]
print("tests:", len(nodes), file=sys.stderr, flush=True)
os.makedirs(OUTDIR, exist_ok=True)

def run(item):
    i, node = item
    out = f"{OUTDIR}/t{i}.json"
    if os.path.exists(out):
        return node, "cached"
    d = f"/tmp/pt{i}"
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    env = dict(os.environ, COVERAGE_PROCESS_START=RC, COVERAGE_FILE=f"{d}/cov")
    status = "ok"
    try:
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", node],
                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=LIMIT)
    except subprocess.TimeoutExpired:
        status = "TIMEOUT"
    parts = glob.glob(f"{d}/cov.*")
    data = coverage.CoverageData(basename=f"{d}/all")
    for f in parts:
        p = coverage.CoverageData(basename=f)
        try:
            p.read(); data.update(p)
        except Exception:
            pass
    lines = {}
    for fn in data.measured_files():
        ls = sorted(data.lines(fn) or [])
        if ls and "/sqlglot/" in fn:
            lines[os.path.relpath(fn, ROOT)] = ls
    json.dump({"node": node, "lines": lines, "status": status}, open(out, "w"))
    shutil.rmtree(d, ignore_errors=True)
    return node, status

t0 = time.time()
done = 0
with cf.ThreadPoolExecutor(POOL) as ex:
    for node, st in ex.map(run, enumerate(nodes)):
        done += 1
        if st not in ("ok", "cached"):
            print(st, node, file=sys.stderr, flush=True)
        if done % 100 == 0:
            print(f"{done}/{len(nodes)} in {time.time()-t0:.0f}s", file=sys.stderr, flush=True)
print("finished", done, f"in {time.time()-t0:.0f}s", file=sys.stderr)
