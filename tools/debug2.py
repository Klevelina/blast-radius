import gzip, json, re, sys
from pathlib import Path
M = json.load(gzip.open("data/map.json.gz", "rt"))
tests = json.load(open("sample/tests.json"))["tests"]
by_num = {t["number"]: t["id"] for t in tests}
idx = {t: i for i, t in enumerate(M["tests"])}
ans = json.load(open("sample/answers.json"))["commits"]
touched = {}
for path, lines in M["files"].items():
    for ln, e in lines.items():
        for j in M["sets"][e[0]]:
            d = touched.setdefault(j, {})
            d[path] = d.get(path, 0) + 1
for cid in sys.argv[1:]:
    text = Path(f"sample/commits/{cid}.patch").read_text()
    changed = re.findall(r"^\+\+\+ b/(\S+)", text, re.M)
    stems = {Path(p).stem for p in changed}
    print("==", cid, changed)
    for n in ans[cid]["failing"]:
        tid = by_num[n]
        j = idx.get(tid)
        if j is None:
            print("  NOT IN MAP", tid)
            continue
        d = touched.get(j, {})
        hit = {p: c for p, c in d.items() if p in changed}
        fam = sorted(p for p in d if Path(p).stem in stems)
        print(f"  {tid}\n    files={len(d)} lines={sum(d.values())} changed_file_lines={hit} same_stem={fam}")
