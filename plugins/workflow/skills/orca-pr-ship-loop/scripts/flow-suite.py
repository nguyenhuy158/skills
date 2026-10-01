"""Run flow variants without an agent (called by `flow-step suite`).

usage: flow-suite.py <root-dir> base=<url> db=<wt db> [variant ...]
  variant = "<flow> [param=value ...]" (one shell word each).
  No variant given: the DEFAULT lanes run in parallel (each run has its own browser context = own Odoo session);
  variants inside a lane run one after the other. Variants given on the command line run one after the other.
Each variant gets its own run dir <root-dir>/<NN>-<flow>; one result line per variant, then SUITE DONE.
Exit 0 when every variant passed, 1 otherwise.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time

FLOW_STEP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flow-step")
# A lane holds variants that depend on each other (framework -> active, appendix -> appendix_active, notice rounds)
# or may pick the same records (debt / disbursement / debt_offset share bill-invoice pairs).
DEFAULT_LANES = [
    ["framework side=customer", "active", "appendix", "appendix_active"],
    ["debt kind=transfer", "debt kind=factoring", "disbursement", "disbursement new_bank=1", "debt_offset"],
    ["return", "payment_request", "payment_request domain=early_payment_discount", "payment_request new_bank=1"],
    [
        "collection_notice round=1",
        "collection_notice round=2",
        "collection_notice round=3",
        "collection_notice kind=obligation",
        "collection_notice kind=obligation round=2",
        "collection_notice kind=settlement",
    ],
]
LOCK = threading.Lock()
RESULTS = []


def run_variant(run_dir, spec, common):
    started = time.time()
    out = subprocess.run([FLOW_STEP, "init", run_dir, f"flow={spec[0]}", *common, *spec[1:]], capture_output=True, text=True)
    step = re.findall(r"^NEXT (\S+)", out.stdout, re.M)
    if not step:
        return False, (out.stdout + out.stderr).strip().splitlines()[-1:] or ["init failed"], started
    while step:
        proc = subprocess.run([FLOW_STEP, run_dir, step[-1]], capture_output=True, text=True)
        if proc.returncode:
            reason = [line for line in proc.stdout.splitlines() if "FAILED" in line or "TIMED OUT" in line]
            return False, reason or proc.stdout.strip().splitlines()[-1:], started
        step = re.findall(r"^NEXT (\S+)", proc.stdout, re.M)
    return True, [], started


def run_lane(root, lane, common):
    for index, spec in lane:
        run_dir = os.path.join(root, f"{index:02d}-{spec[0]}")
        ok, reason, started = run_variant(run_dir, spec, common)
        state_path = os.path.join(run_dir, "state.json")
        browser = sum(e["secs"] for e in json.load(open(state_path))["log"]) if os.path.exists(state_path) else 0
        with LOCK:
            RESULTS.append(ok)
            label = " ".join(spec)
            print(f"{'PASS' if ok else 'FAIL'} {label:<45} {time.time() - started:5.0f}s wall {browser:5.0f}s browser  {run_dir}", flush=True)
            for line in reason:
                print(f"     {line}", flush=True)


def main():
    root, args = sys.argv[1], sys.argv[2:]
    common = [a for a in args if a.startswith(("base=", "db="))]
    given = [shlex.split(a) for a in args if not a.startswith(("base=", "db="))]
    lanes_specs = [given] if given else [[shlex.split(v) for v in lane] for lane in DEFAULT_LANES]
    numbered, index = [], 0
    for lane in lanes_specs:
        numbered.append([])
        for spec in lane:
            index += 1
            numbered[-1].append((index, spec))
    os.makedirs(root, exist_ok=True)
    started = time.time()
    threads = [threading.Thread(target=run_lane, args=(root, lane, common)) for lane in numbered]
    for thread in threads:
        thread.start()
        time.sleep(3)
    for thread in threads:
        thread.join()
    print(f"SUITE DONE {sum(RESULTS)}/{index} passed in {time.time() - started:.0f}s ({len(threads)} lane(s))")
    sys.exit(0 if sum(RESULTS) == index else 1)


main()
