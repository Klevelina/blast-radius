cd /work/sqlglot
SP=$(python -c "import site;print(site.getsitepackages()[0])")
echo "import coverage; coverage.process_startup()" > "$SP/zz_cov.pth"
exec python ../tools/pertest.py
