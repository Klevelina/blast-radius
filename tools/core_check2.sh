cd /work/sqlglot
A='tests/test_optimizer.py::TestOptimizer::test_optimize_special_joins'
B='tests/test_optimizer.py::TestOptimizer::test_eliminate_joins'
python ../tools/shard2.py /tmp/t2 "$A" "$B" >/dev/null 2>&1
python - <<'PY'
import json
r = json.load(open("/tmp/t2.json"))
for t, files in r.items():
    n = len(files.get("sqlglot/optimizer/eliminate_joins.py", []))
    print(n, "lines in eliminate_joins.py |", len(files), "files |", t.split("::")[-1])
PY
