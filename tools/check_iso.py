import coverage
import sqlglot.optimizer.eliminate_joins as m
print("module file:", m.__file__)
d = coverage.CoverageData(basename="/tmp/iso.cov")
d.read()
print("measured files:", len(d.measured_files()))
for f in d.measured_files():
    if f.endswith("eliminate_joins.py"):
        print(f, "lines recorded:", len(d.lines(f)))
