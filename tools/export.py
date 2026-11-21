import glob, gzip, json, os, sys
import coverage

ROOT = os.path.abspath("sqlglot")
OUT = sys.argv[1]
data = coverage.CoverageData(basename="/tmp/combined.cov")
for f in sorted(glob.glob("raw/*.cov")):
    part = coverage.CoverageData(basename=f)
    part.read()
    data.update(part)

test_ids, tid, sets, set_list, files = [], {}, {}, [], {}
def tix(c):
    if c not in tid:
        tid[c] = len(test_ids); test_ids.append(c)
    return tid[c]

for f in data.measured_files():
    rel = os.path.relpath(f, ROOT)
    lines = {}
    for ln, ctxs in data.contexts_by_lineno(f).items():
        key = tuple(sorted(tix(c) for c in ctxs if c))
        if key not in sets:
            sets[key] = len(set_list); set_list.append(list(key))
        lines[ln] = [sets[key], 1 if "" in ctxs else 0]
    files[rel] = lines

fx = {}
for f in glob.glob("raw/*.fx.json"):
    for rel, ids in json.load(open(f)).items():
        fx.setdefault(rel, set()).update(tix(c) for c in ids)
fx = {k: sorted(v) for k, v in fx.items()}

with gzip.open(OUT, "wt") as fh:
    json.dump({"tests": test_ids, "sets": set_list, "files": files, "fixtures": fx},
              fh, separators=(",", ":"))
print("tests", len(test_ids), "files", len(files), "fixtures", len(fx), file=sys.stderr)
