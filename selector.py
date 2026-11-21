"""Run every test, split across the cheapest number of workers (1 to 8)."""

import json
import os
import sys
from pathlib import Path

DATA = Path(os.environ.get("DATA_DIR", "/data"))
WORKER_COST_MS = 2000
MAX_WORKERS = 8


def best_split(durations_ms):
    items = sorted(durations_ms.items(), key=lambda kv: -kv[1])
    best_cost, best_workers = None, []
    for k in range(1, MAX_WORKERS + 1):
        workers = [[] for _ in range(k)]
        loads = [0] * k
        for number, ms in items:
            i = loads.index(min(loads))
            workers[i].append(number)
            loads[i] += ms
        cost = max(loads) + WORKER_COST_MS * k
        if best_cost is None or cost < best_cost:
            best_cost, best_workers = cost, workers
    return best_workers


def main():
    tests = json.loads((DATA / "tests.json").read_text())["tests"]
    durations = {t["number"]: round(t["seconds"] * 1000) for t in tests}
    workers = best_split(durations)
    for patch in sorted((DATA / "commits").glob("*.patch")):
        print(json.dumps({"commit": patch.stem, "workers": workers}))
    print(f"selected {len(tests)} tests on every commit", file=sys.stderr)


if __name__ == "__main__":
    main()
