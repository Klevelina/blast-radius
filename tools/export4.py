import ast, bisect, glob, gzip, json, os, sys

ROOT = os.path.abspath("sqlglot")
OUT = sys.argv[1]
test_ids, tid = [], {}
def tix(c):
    if c not in tid:
        tid[c] = len(test_ids); test_ids.append(c)
    return tid[c]

per_file, always, n = {}, [], 0
for f in sorted(glob.glob("raw3/t*.json")):
    d = json.load(open(f))
    n += 1
    ti = tix(d["node"])
    if d["status"] != "ok" or not d["lines"]:
        always.append(d["node"])
    for rel, lines in d["lines"].items():
        per_file.setdefault(rel, {})[ti] = lines

sets, set_list = {}, []
def sid(s):
    k = tuple(sorted(s))
    if k not in sets:
        sets[k] = len(set_list); set_list.append(list(k))
    return sets[k]

def outer_spans(path):
    tree = ast.parse(open(os.path.join(ROOT, path), encoding="utf-8").read())
    spans = []
    def visit(node):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                spans.append((min([ch.lineno] + [x.lineno for x in ch.decorator_list]), ch.end_lineno))
            else:
                visit(ch)
    visit(tree)
    spans.sort()
    return spans

files_out = {}
for rel, by_test in per_file.items():
    try:
        spans = outer_spans(rel)
    except Exception as e:
        print("ast failed", rel, e, file=sys.stderr)
        spans = []
    starts = [s for s, _ in spans]
    span_sets = [set() for _ in spans]
    outer = {}
    for t, lines in by_test.items():
        for ln in lines:
            i = bisect.bisect_right(starts, ln) - 1
            if i >= 0 and ln <= spans[i][1]:
                span_sets[i].add(t)
            else:
                outer.setdefault(ln, set()).add(t)
    files_out[rel] = {
        "all": sid(set(by_test)),
        "spans": [[s, e, sid(ss)] for (s, e), ss in zip(spans, span_sets)],
        "outer": {str(k): sid(v) for k, v in outer.items()},
    }

with gzip.open(OUT, "wt") as fh:
    json.dump({"tests": test_ids, "sets": set_list, "files": files_out, "always": always},
              fh, separators=(",", ":"))
print("tests", len(test_ids), "files", len(files_out), "always", len(always), file=sys.stderr)
