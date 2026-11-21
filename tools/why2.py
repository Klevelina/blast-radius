import ast, glob, json
REL = "sqlglot/optimizer/eliminate_joins.py"
tree = ast.parse(open("sqlglot/" + REL).read())
print("functions in the file:")
for n in ast.walk(tree):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        print(f"  {n.name}: lines {n.lineno}-{n.end_lineno}")
WANT = ["test_eliminate_joins", "test_optimize", "test_tpch", "test_optimize_special_joins"]
for f in glob.glob("raw2/*.json"):
    d = json.load(open(f))["lines"]
    for t, files in d.items():
        short = t.split("::")[-1]
        if t.startswith("tests/test_optimizer.py") and short in WANT:
            print(short, "->", sorted(files.get(REL, [])))
