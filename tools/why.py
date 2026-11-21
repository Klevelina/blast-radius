import glob, json, re, sys
from pathlib import Path

tests = json.load(open("sample/tests.json"))["tests"]
by_num = {t["number"]: t["id"] for t in tests}
ans = json.load(open("sample/answers.json"))["commits"]
sel = {}
for line in open("output.jsonl"):
    o = json.loads(line)
    sel[o["commit"]] = {n for w in o["workers"] for n in w}

rec = {}
for f in glob.glob("raw2/*.json"):
    d = json.load(open(f))["lines"]
    for t, files in d.items():
        rec[t] = {k: len(v) for k, v in files.items() if v}

for cid in sys.argv[1:]:
    text = Path(f"sample/commits/{cid}.patch").read_text()
    changed = re.findall(r"^\+\+\+ b/(\S+)", text, re.M)
    miss = [n for n in ans[cid]["failing"] if n not in sel[cid]]
    print("==", cid, changed, "| failing:", len(ans[cid]["failing"]), "| not selected:", len(miss))
    for n in miss:
        tid = by_num[n]
        r = rec.get(tid)
        if r is None:
            print("  NO RECORD AT ALL:", tid)
            continue
        hit = {p: r.get(p, 0) for p in changed}
        print(f"  {tid}\n     files={len(r)} lines={sum(r.values())} in_changed={hit}")
