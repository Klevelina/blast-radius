import glob, sys, coverage
def show(path):
    d = coverage.CoverageData(basename=path); d.read()
    for fn in d.measured_files():
        if fn.endswith("optimizer/eliminate_joins.py"):
            per = {}
            for ln, cs in d.contexts_by_lineno(fn).items():
                for c in cs:
                    per[c] = per.get(c, 0) + 1
            print(path, "| contexts:", len(per), "| import-time lines:", per.get("", 0))
            for c, n in sorted(per.items()):
                if c and ("eliminate_joins" in c or "tpcds" in c or "test_optimize" in c):
                    print("    ", n, c)
for p in sys.argv[1:]:
    for f in sorted(glob.glob(p)):
        show(f)
