import ast, json, collections

tests = json.load(open("sample/tests.json"))["tests"]
dur = {t["id"]: t["seconds"] for t in tests}
found = {}
for path in ["tests/test_optimizer.py", "tests/test_executor.py"]:
    tree = ast.parse(open("sqlglot/" + path).read())
    for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
        methods = {m.name: m for m in cls.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))}
        uses = {}
        calls = {}
        for name, m in methods.items():
            src = ast.unparse(m)
            uses[name] = "pool" in src.lower() or "ProcessPool" in src
            calls[name] = {n.func.attr for n in ast.walk(m)
                           if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                           and isinstance(n.func.value, ast.Name) and n.func.value.id in ("self", "cls")}
        changed = True
        while changed:
            changed = False
            for name in methods:
                if not uses[name] and any(uses.get(c) for c in calls[name]):
                    uses[name] = True
                    changed = True
        for name, u in uses.items():
            if u and name.startswith("test"):
                tid = f"{path}::{cls.name}::{name}"
                found[tid] = dur.get(tid)
print("pool-using tests:", len(found))
tot = collections.Counter()
for tid, s in sorted(found.items(), key=lambda kv: -(kv[1] or 0)):
    tot[tid.split("::")[0]] += s or 0
    print(f"  {s if s is not None else 'NA':>7}  {tid}")
print("seconds by file:", dict(tot), "| total:", round(sum(tot.values()), 1))
json.dump(sorted(found), open("data/pool.json", "w"))
