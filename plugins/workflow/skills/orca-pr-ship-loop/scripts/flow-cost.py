"""Token / cost summary of flow-runner agent runs (called by `flow-step cost <agent-name> [...]`).

Reads the newest ~/.omp/agent/sessions/**/<agent-name>.jsonl (the subagent transcript written by the harness) and sums
the per-turn `usage` blocks. Agent-free runs (`flow-step suite`, `flow-step <run-dir> <step>` by hand) cost $0.
"""

import glob
import json
import os
import sys

KEYS = ("input", "output", "cacheRead", "cacheWrite")


def summary(name):
    paths = glob.glob(os.path.expanduser(f"~/.omp/agent/sessions/**/{name}.jsonl"), recursive=True)
    if not paths:
        return None
    path = max(paths, key=os.path.getmtime)
    tokens, cost, turns, models, first, last = dict.fromkeys(KEYS, 0), 0.0, 0, set(), None, None
    for line in open(path):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        stamp = entry.get("timestamp")
        first, last = first or stamp, stamp or last
        message = entry.get("message") or {}
        usage = message.get("usage")
        if not usage:
            continue
        turns += 1
        models.add(message.get("model") or "?")
        for key in KEYS:
            tokens[key] += usage.get(key, 0) or 0
        cost += (usage.get("cost") or {}).get("total", 0) or 0
    return {"path": path, "turns": turns, "models": sorted(models), "tokens": tokens, "cost": cost, "first": first, "last": last}


def main():
    names = sys.argv[1:]
    if not names:
        sys.exit("usage: flow-step cost <agent-name> [...]   (agent-free suite runs cost $0)")
    grand = 0.0
    for name in names:
        s = summary(name)
        if not s:
            print(f"COST {name}: no session transcript found")
            continue
        t = s["tokens"]
        grand += s["cost"]
        print(
            f"COST {name}: ${s['cost']:.4f} · {s['turns']} model turns · {', '.join(s['models'])} · tokens in {t['input']:,}"
            f" / out {t['output']:,} / cache read {t['cacheRead']:,} / cache write {t['cacheWrite']:,}"
            f" (total {sum(t.values()):,})"
        )
    if len(names) > 1:
        print(f"COST TOTAL ${grand:.4f} for {len(names)} agent run(s)")


main()
