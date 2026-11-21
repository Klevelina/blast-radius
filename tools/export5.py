import ast, bisect, glob, gzip, json, os, sys

ROOT = os.path.abspath("sqlglot")
OUT = sys.argv[1]
OLD = sys.argv[2] if len(sys.argv) > 2 else None

test_ids, tid = [], {}
def tix(name):
    if name not in tid:
        tid[name] = len(test_ids)
        test_ids.append(name)
    return tid[name]

per_file, always = {}, []
for path in sorted(glob.glob("raw3/t*.json")):
    d = json.load(open(path))
    ti = tix(d["node"])
    if d["status"] != "ok" or not d["lines"]:
        always.append(d["node"])
    for rel, lines in d["lines"].items():
        per_file.setdefault(rel, {})[ti] = lines

sets, hexsets = {}, []
def sid(mask):
    k = sets.get(mask)
    if k is None:
        k = sets[mask] = len(hexsets)
        hexsets.append(format(mask, "x"))
    return k

COMPOUND = tuple(t for t in (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With,
                             ast.AsyncWith, ast.Try, getattr(ast, "TryStar", None)) if t)

def analyze(rel):
    tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())
    spans, single, multi, docs = [], set(), set(), []
    def region(a, b):
        if b > a:
            multi.add((a, b))
        else:
            single.add(a)
    def doc_of(node):
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            docs.append((body[0].lineno, body[0].end_lineno))
    def walk(node, in_func):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = min([ch.lineno] + [x.lineno for x in ch.decorator_list])
                region(start, max(ch.lineno, ch.body[0].lineno - 1))
                is_fn = not isinstance(ch, ast.ClassDef)
                if is_fn and not in_func:
                    spans.append((start, ch.end_lineno))
                doc_of(ch)
                walk(ch, in_func or is_fn)
            elif isinstance(ch, COMPOUND) or isinstance(ch, ast.ExceptHandler):
                region(ch.lineno, max(ch.lineno, ch.body[0].lineno - 1))
                walk(ch, in_func)
            elif isinstance(ch, ast.stmt):
                region(ch.lineno, ch.end_lineno)
    doc_of(tree)
    walk(tree, False)
    return spans, single, multi, docs

files_out = {}
for rel, by_test in sorted(per_file.items()):
    line_mask = {}
    allmask = 0
    for ti, lines in by_test.items():
        bit = 1 << ti
        allmask |= bit
        for ln in lines:
            line_mask[ln] = line_mask.get(ln, 0) | bit
    rl = sorted(line_mask)
    rs = [sid(line_mask[ln]) for ln in rl]
    try:
        spans, single, multi, docs = analyze(rel)
    except Exception as e:
        print("ast failed", rel, e, file=sys.stderr)
        spans, single, multi, docs = [], set(), set(), []
    def range_mask(a, b):
        m = 0
        for k in range(bisect.bisect_left(rl, a), bisect.bisect_right(rl, b)):
            m |= line_mask[rl[k]]
        return m
    files_out[rel] = {
        "all": sid(allmask),
        "spans": [[a, b, sid(range_mask(a, b))] for a, b in sorted(spans)],
        "rl": rl, "rs": rs,
        "st": sorted(single),
        "ml": [x for ab in sorted(multi) for x in ab],
        "doc": [x for ab in sorted(set(docs)) for x in ab],
    }

fx = {}
if OLD:
    old = json.load(gzip.open(OLD, "rt"))
    for rel, ids in old.get("fixtures", {}).items():
        m = 0
        for j in ids:
            name = old["tests"][j]
            if name in tid:
                m |= 1 << tid[name]
        fx[rel] = sid(m)

with gzip.open(OUT, "wt") as fh:
    json.dump({"tests": test_ids, "sets": hexsets, "files": files_out,
               "fixtures": fx, "always": always}, fh, separators=(",", ":"))
print("tests", len(test_ids), "files", len(files_out), "sets", len(hexsets),
      "fixtures", len(fx), "always", len(always), file=sys.stderr)
