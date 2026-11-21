import ast, bisect, glob, gzip, json, os, sys

ROOT = os.path.abspath("sqlglot")
OUT = sys.argv[1]
test_ids, tid = [], {}
def tix(c):
    if c not in tid:
        tid[c] = len(test_ids); test_ids.append(c)
    return tid[c]

per_file = {}    # rel -> {test idx: sorted lines}
fx = {}
for f in sorted(glob.glob("raw2/*.json")):
    d = json.load(open(f))
    for t, files in d["lines"].items():
        ti = tix(t)
        for rel, lines in files.items():
            if lines:
                per_file.setdefault(rel, {})[ti] = lines
    for rel, ts in d["fx"].items():
        fx.setdefault(rel, set()).update(tix(t) for t in ts)

sets, set_list = {}, []
def sid(s):
    k = tuple(sorted(s))
    if k not in sets:
        sets[k] = len(set_list); set_list.append(list(k))
    return sets[k]

def outer_spans(path):
    src = open(os.path.join(ROOT, path), encoding="utf-8").read()
    tree = ast.parse(src)
    spans = []
    def visit(node, in_class):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = min([ch.lineno] + [x.lineno for x in ch.decorator_list])
                spans.append((start, ch.end_lineno))
            elif isinstance(ch, ast.ClassDef):
                visit(ch, True)
            else:
                visit(ch, in_class)
    visit(tree, False)
    spans.sort()
    return spans

files_out = {}
for rel, by_test in per_file.items():
    union = set()
    for ti in by_test:
        union.add(ti)
    try:
        spans = outer_spans(rel)
    except Exception as e:
        print("ast failed", rel, e, file=sys.stderr)
        spans = []
    starts = [s for s, _ in spans]
    span_sets = [set() for _ in spans]
    for ti, lines in by_test.items():
        for ln in lines:
            i = bisect.bisect_right(starts, ln) - 1
            if i >= 0 and ln <= spans[i][1]:
                span_sets[i].add(ti)
    files_out[rel] = {
        "all": sid(union),
        "spans": [[s, e, sid(ss)] for (s, e), ss in zip(spans, span_sets)],
    }

fx_out = {k: sorted(v) for k, v in fx.items()}
with gzip.open(OUT, "wt") as fh:
    json.dump({"tests": test_ids, "sets": set_list, "files": files_out, "fixtures": fx_out},
              fh, separators=(",", ":"))
print("tests", len(test_ids), "files", len(files_out), "fixtures", len(fx_out), file=sys.stderr)
