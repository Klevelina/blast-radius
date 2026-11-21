cd /work/sqlglot
A='tests/test_optimizer.py::TestOptimizer::test_optimize_special_joins'
B='tests/test_optimizer.py::TestOptimizer::test_eliminate_joins'
python - <<'PY'
import coverage
c = coverage.Coverage(data_file=None); c.start(); c.stop()
try: print("default core:", c._collector.tracer_name())
except Exception as e: print("core name unavailable:", e)
PY
run() {
  label="$1"; shift
  env "$@" python ../tools/shard2.py /tmp/x "$A" "$B" >/dev/null 2>&1
  python - "$label" <<'PY'
import json, sys
r = json.load(open("/tmp/x.json"))["lines"]
out = []
for t, files in r.items():
    out.append(f'{t.split("::")[-1]}={len(files.get("sqlglot/optimizer/eliminate_joins.py", []))}')
print(f"{sys.argv[1]:12}", " ".join(out))
PY
}
run default   X=1
run ctrace    COVERAGE_CORE=ctrace
run pytrace   COVERAGE_CORE=pytrace
run sysmon    COVERAGE_CORE=sysmon
run restart   RESTART=1
