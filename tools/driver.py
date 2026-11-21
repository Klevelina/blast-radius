import concurrent.futures as cf, glob, os, subprocess, sys, time
SLOW = ["tests/test_parser.py::TestParser::test_max_nodes",
        "tests/test_executor.py::TestExecutor::test_execute_tpcds",
        "tests/test_generator.py::TestGenerator::test_generator_memory"]
files = sorted(glob.glob("tests/**/test_*.py", recursive=True), key=os.path.getsize, reverse=True)
N = 8
chunks = [files[i::N] for i in range(N)]
jobs = [(f"slow{i}", [s]) for i, s in enumerate(SLOW)]
jobs += [(f"c{i}", c + [f"--deselect={s}" for s in SLOW]) for i, c in enumerate(chunks)]
os.makedirs("/work/raw2", exist_ok=True)
LIMIT = int(os.environ.get("JOB_TIMEOUT", "3000"))

def run(job):
    name, args = job
    t = time.time()
    try:
        r = subprocess.run([sys.executable, os.environ.get("SHARD", "../tools/shard.py"), f"/work/raw2/{name}", *args],
                           timeout=LIMIT)
        status = r.returncode
    except subprocess.TimeoutExpired:
        status = "TIMEOUT"
    print(f"{name}: {status} in {time.time()-t:.0f}s", file=sys.stderr, flush=True)
    return name, status

with cf.ThreadPoolExecutor(int(os.environ.get("POOL", "4"))) as ex:
    results = list(ex.map(run, jobs))
print(results, file=sys.stderr)
