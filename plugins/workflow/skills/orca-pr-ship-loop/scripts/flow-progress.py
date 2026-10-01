"""Live view of the runs under a directory (called by `flow-step progress <root-dir>`): one line per run dir with
flow, steps done/total, browser seconds and the current step or result; refreshes every 2 s until Ctrl-C."""

import glob
import json
import os
import sys
import time

FLOW_DIR = os.environ["FLOW_DIR"]
root = sys.argv[1]
ns = {}
for path in sorted(glob.glob(os.path.join(FLOW_DIR, "*.py"))):
    exec(compile(open(path).read(), path, "exec"), ns)
steps = {name: [step for step, _ in flow["steps"]] for name, flow in ns["FLOWS"].items()}


def row(run_dir):
    st = json.load(open(os.path.join(run_dir, "state.json")))
    done, total = len(set(st["done"])), len(steps.get(st["flow"], []))
    secs = sum(e["secs"] for e in st["log"])
    if st.get("failed"):
        status = "\033[31mFAIL\033[0m " + st["failed"][:100]
    elif not st.get("next"):
        status = "\033[32mPASS\033[0m"
    else:
        status = f"\033[33m▶ {st.get('running') or st['next']}\033[0m"
    return f"{os.path.basename(run_dir):<28} {done:>2}/{total:<2} {secs:>5.0f}s  {status}"


while True:
    dirs = sorted(os.path.dirname(p) for p in glob.glob(os.path.join(root, "*", "state.json")))
    if os.path.exists(os.path.join(root, "state.json")):
        dirs = [root]
    lines = []
    for run_dir in dirs:
        try:
            lines.append(row(run_dir))
        except (OSError, ValueError, KeyError):
            continue
    print(f"\033[2J\033[H{root}  {time.strftime('%H:%M:%S')}\n" + "\n".join(lines or ["(no run yet)"]), flush=True)
    time.sleep(2)
