cd /work/sqlglot
SP=$(python -c "import site;print(site.getsitepackages()[0])")
echo "import coverage; coverage.process_startup()" > "$SP/zz_cov.pth"
rm -rf /tmp/cc && mkdir -p /tmp/cc
export COVERAGE_PROCESS_START=/work/tools/cov.rc COVERAGE_FILE=/tmp/cc/cov
python -m pytest -q -p no:cacheprovider "tests/test_optimizer.py::TestOptimizer::test_tpch" 2>&1 | tail -3
unset COVERAGE_PROCESS_START
python - <<'PY'
import glob, coverage
parts = glob.glob("/tmp/cc/cov.*")
print("data files written:", len(parts))
d = coverage.CoverageData(basename="/tmp/cc/all")
for f in parts:
    p = coverage.CoverageData(basename=f); p.read(); d.update(p)
for fn in d.measured_files():
    if fn.endswith("optimizer/eliminate_joins.py"):
        ls = sorted(d.lines(fn) or [])
        print("eliminate_joins lines:", len(ls), "| inside _should_eliminate_join (61-77):", [l for l in ls if 61 <= l <= 77])
PY
