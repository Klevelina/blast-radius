import gzip, json, sys
from pathlib import Path
sys.path.insert(0, ".")
from selector_v2 import parse_patch

M = json.load(gzip.open("data/map.json.gz", "rt"))
tests = json.load(open("sample/tests.json"))["tests"]
num = {t["id"]: t["number"] for t in tests}
tn = [num.get(x) for x in M["tests"]]
sets = [{tn[j] for j in s if tn[j] is not None} for s in M["sets"]]
ans = json.load(open("sample/answers.json"))["commits"]

for cid in sys.argv[1:]:
    fails = set(ans[cid]["failing"])
    text = Path(f"sample/commits/{cid}.patch").read_text()
    print("=" * 70, cid, "fails:", len(fails))
    print("\n".join(text.split("\n")[:45]))
    print("-" * 70)
    for f in parse_patch(text):
        fm = M["files"].get(f["path"])
        print("file", f["path"], "| in map:", bool(fm), "| odd:", f["odd"])
        if not fm:
            continue
        union = set()
        for e in fm.values():
            union |= sets[e[0]]
        print("  file-level union covers", len(fails & union), "of", len(fails), "failing tests")
        got = set()
        for ln in sorted(f["lines"])[:30]:
            e = fm.get(str(ln))
            if e:
                got |= sets[e[0]]
                print("  line", ln, "mapped, tests:", len(sets[e[0]]), "import-time:", bool(e[1]))
            else:
                print("  line", ln, "UNMAPPED")
        print("  line-level covers", len(fails & got), "of", len(fails))
