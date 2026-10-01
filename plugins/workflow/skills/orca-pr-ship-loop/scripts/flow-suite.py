"""Run flow variants back to back without an agent (called by `flow-step suite`).

usage: flow-suite.py <root-dir> base=<url> db=<wt db> [variant ...]
  variant = "<flow> [param=value ...]" (one shell word each); none = DEFAULT below.
Each variant gets its own run dir <root-dir>/<NN>-<flow>; one result line per variant, then SUITE DONE.
Exit 0 when every variant passed, 1 otherwise.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import time

FLOW_STEP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flow-step")
DEFAULT = [
    "framework side=customer",
    "active",
    "appendix",
    "appendix_active",
    "debt kind=transfer",
    "debt kind=factoring",
    "return",
    "payment_request",
    "payment_request domain=early_payment_discount",
    "payment_request new_bank=1",
    "disbursement",
    "disbursement new_bank=1",
    "debt_offset",
    "collection_notice round=1",
    "collection_notice round=2",
    "collection_notice round=3",
    "collection_notice kind=obligation",
    "collection_notice kind=obligation round=2",
    "collection_notice kind=settlement",
]


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


def main():
    root, args = sys.argv[1], sys.argv[2:]
    common = [a for a in args if a.startswith(("base=", "db="))]
    variants = [shlex.split(a) for a in args if not a.startswith(("base=", "db="))] or [shlex.split(v) for v in DEFAULT]
    os.makedirs(root, exist_ok=True)
    suite_started, passed = time.time(), 0
    for index, spec in enumerate(variants, 1):
        run_dir = os.path.join(root, f"{index:02d}-{spec[0]}")
        ok, reason, started = run_variant(run_dir, spec, common)
        state_path = os.path.join(run_dir, "state.json")
        browser = sum(e["secs"] for e in json.load(open(state_path))["log"]) if os.path.exists(state_path) else 0
        passed += ok
        label = " ".join(spec)
        print(f"{'PASS' if ok else 'FAIL'} {label:<45} {time.time() - started:5.0f}s wall {browser:5.0f}s browser  {run_dir}", flush=True)
        for line in reason:
            print(f"     {line}", flush=True)
    print(f"SUITE DONE {passed}/{len(variants)} passed in {time.time() - suite_started:.0f}s")
    sys.exit(0 if passed == len(variants) else 1)


main()
