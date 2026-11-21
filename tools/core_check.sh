cd /work/sqlglot
python -c 'import coverage; print("coverage", coverage.__version__)'
A='tests/test_optimizer.py::TestOptimizer::test_optimize_special_joins'
B='tests/test_optimizer.py::TestOptimizer::test_eliminate_joins'
echo "== default core"
python ../tools/shard.py /tmp/t_default "$A" "$B" >/dev/null 2>&1
python ../tools/check_raw.py /tmp/t_default.cov
echo "== COVERAGE_CORE=ctrace"
COVERAGE_CORE=ctrace python ../tools/shard.py /tmp/t_ctrace "$A" "$B" >/dev/null 2>&1
python ../tools/check_raw.py /tmp/t_ctrace.cov
