# ruff: noqa: F821
"""Core of the FarmNet UI flow runner driven by `flow-step`.

Every file in this directory is executed into one namespace: in plain python3 for `init`, inside browser-use
for the steps (js, cdp, fill, fill_m2o, save, click_btn, switch_user, ... are injected there). This file holds
the run state machine, read-only SQL, page reads and the generic agreement/appendix steps (to check, to review,
approve loop, finish); each other file registers one flow with `register(...)`.
"""

import json
import os
import re
import signal
import subprocess
import time

FLOWS = {}
STEP_SECONDS = 25
CHAIN_SECONDS = 10
LIGHT_STEPS = {"dr_reviewed", "pr_reviewed", "pr_bank", "finish", "purchase_approved", "customer_mirror"}
MAX_ROUNDS = 8
TABLES = {
    "agreement": {"table": "agreement", "state": "stage", "approver_fk": "agreement_id"},
    "agreement.appendix": {"table": "agreement_appendix", "state": "state", "approver_fk": "appendix_id"},
    "payment.request": {"table": "payment_request", "state": "state", "approver_fk": None},
    "sale.disbursement": {"table": "sale_disbursement", "state": "state", "approver_fk": None},
    "collection.notice": {"table": "collection_notice", "state": "state", "approver_fk": None},
}


class StepFailed(Exception):
    """A predefined check did not hold: the flow stops here."""


def check(condition, message):
    if not condition:
        raise StepFailed(message)


def register(name, describe, params, plan, steps):
    """steps: list of (step name, function(state) -> output lines); functions with .repeat run until they finish."""
    FLOWS[name] = {"describe": describe, "params": params, "plan": plan, "steps": steps}


def partner_bank(db, partner):
    """A payable bank account of the partner, preferring one already used on its agreements."""
    return fetch(
        db,
        f"select b.id, b.acc_number from res_partner_bank b where b.partner_id = {partner} and b.allow_out_payment"
        f" order by (b.id in (select partner_bank_id from agreement where partner_id = {partner}"
        " and partner_bank_id is not null)) desc, b.id desc limit 1",
        f"a bank account (allow out payment) of partner {partner}",
    )


def partner_contact(db, partner):
    """A contact person of the partner, preferring one already used on its agreements."""
    return fetch(
        db,
        f"select c.id, c.name from res_partner c where c.parent_id = {partner} and c.active order by (c.id in"
        f" (select partner_contact_id from agreement where partner_id = {partner} and partner_contact_id is not null))"
        " desc, c.id desc limit 1",
        f"a contact person of partner {partner}",
    )


# ---------------------------------------------------------------- SQL (read-only)


def sql(db, query):
    run = subprocess.run(
        ["docker", "exec", "dev-postgres", "psql", "-U", "farmnet_service", "-d", db, "-At", "-F", "\t", "-c", query],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if run.returncode:
        raise StepFailed(f"SQL error: {run.stderr.strip()}")
    return [line.split("\t") for line in run.stdout.splitlines() if line]


def one(db, query):
    rows = sql(db, query)
    return rows[0] if rows else None


def fetch(db, query, what):
    row = one(db, query)
    check(row and all(value != "" for value in row), f"cannot find {what}")
    return row


def number(text):
    cleaned = re.sub(r"[^\d.\-]", "", str(text or "").replace(",", ""))
    return float(cleaned) if cleaned not in ("", "-", ".") else None


def same_number(a, b):
    x, y = number(a), number(b)
    return x is not None and y is not None and abs(x - y) < 1e-6


def same_id(a, b):
    return a not in (None, "") and int(a) == int(b)


def labels(db, model, field):
    rows = sql(
        db,
        "select s.value, s.name->>'en_US' from ir_model_fields_selection s join ir_model_fields f on f.id = s.field_id"
        f" where f.model = '{model}' and f.name = '{field}' order by s.sequence",
    )
    return {value: label.upper() for value, label in rows}


def type_id(db, name):
    (found,) = fetch(db, f"select id from agreement_type where name = '{name}'", f"agreement type {name}")
    return int(found)


def ui_date(day):
    return day.strftime("%d/%m/%Y")


# ---------------------------------------------------------------- init / resume


def init(run_dir, args):
    state_path = os.path.join(os.path.abspath(run_dir), "state.json")
    if os.path.exists(state_path):
        resume(state_path)
        return
    params = dict(arg.split("=", 1) for arg in args)
    flow = params.pop("flow", None)
    check(flow in FLOWS, f"flow={flow} is not one of: {', '.join(sorted(FLOWS))}")
    db = params["db"]
    plan = FLOWS[flow]["plan"](db, params)
    plan["labels"] = {model: labels(db, model, meta["state"]) for model, meta in TABLES.items()}
    os.makedirs(run_dir, exist_ok=True)
    state = {
        "flow": flow,
        "base": params["base"].rstrip("/"),
        "db": db,
        "dir": os.path.abspath(run_dir),
        "tab": None,
        "done": [],
        "running": None,
        "failed": None,
        "last": None,
        "rounds": {},
        "next": FLOWS[flow]["steps"][0][0],
        "shot": 0,
        "log": [],
        "ids": plan.pop("ids", {}),
        "plan": plan,
    }
    write_state(state_path, state)
    print(f"INIT OK {state_path}")
    print(f"FLOW {flow}: {FLOWS[flow]['describe']}")
    for key, value in plan.items():
        if key != "labels":
            print(f"  {key} = {value}")
    print(f"NEXT {FLOWS[flow]['steps'][0][0]}")


def resume(state_path):
    """Same run dir again (e.g. the runner agent died between steps): continue where the run stopped."""
    with open(state_path) as fh:
        st = json.load(fh)
    check(not st["failed"], f"run already stopped ({st['failed']}); start a new run dir")
    check(not st["running"], f"step {st['running']} was interrupted mid-way; start a new run dir")
    remaining = pending_steps(st)
    check(remaining, "run already finished; start a new run dir")
    print(f"INIT OK (resumed) {state_path}")
    print(f"NEXT {remaining[0]}")


def write_state(path, state):
    with open(path, "w") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)


def pending_steps(st):
    return [name for name, _ in FLOWS[st["flow"]]["steps"] if name not in st["done"]]


# ---------------------------------------------------------------- page reads (browser-use only)


def _user():
    return (js("(document.querySelector('.o_user_menu')||{}).innerText||''") or "").strip()


def _value(field, scope=".o_form_view"):
    return (
        js(
            f"(()=>{{const all=[...document.querySelectorAll('{scope} div[name={field}]')];"
            " const d=all.find(e=>e.getClientRects().length)||all[0]; if(!d) return '';"
            " const i=d.querySelector('input,textarea,select');"
            " if(i&&i.tagName==='SELECT') return (i.selectedOptions[0]||{}).text||'';"
            " return (i ? i.value : d.innerText).trim();})()"
        )
        or ""
    )


def _stage_ui():
    return (form_state()["stage"] or "").strip().upper()


def _buttons():
    return [button.split(":")[0] for button in form_state()["buttons"] or []]


def _dialog():
    return (
        js(
            "[...document.querySelectorAll('.modal')].filter(m=>m.getClientRects().length)"
            ".map(m=>m.innerText.replace(/\\s+/g,' ').trim()).join(' || ')"
        )
        or ""
    )


def _expect_value(field, want, scope=".o_form_view"):
    shown = _value(field, scope)
    check(str(want).lower() in shown.lower(), f"{field} shows {shown!r}, expected {want!r}")


def _shot(st, label, scroll_to=".o_form_statusbar"):
    st["shot"] += 1
    path = os.path.join(st["dir"], f"{st['shot']:02d}-{label}.png")
    js(f"document.querySelector({json.dumps(scroll_to)})?.scrollIntoView({{block:'start'}})")
    time.sleep(0.5)
    screenshot(path)
    return path


def _ensure_tab(st):
    pages = {t["targetId"] for t in cdp("Target.getTargets")["targetInfos"] if t["type"] == "page"}
    if st.get("tab") in pages:
        switch_tab(st["tab"])
    else:
        st["tab"] = new_tab(st["base"] + "/web/login")
    cdp("Emulation.setDeviceMetricsOverride", width=1600, height=1000, deviceScaleFactor=1, mobile=False)


def _close_tab(st):
    if st.get("tab"):
        close_tab()
        st["tab"] = None


def login_admin(st):
    odoo_login(st["base"])
    check("administrator" in _user().lower(), f"expected Administrator, the top bar shows {_user()!r}")


# ---------------------------------------------------------------- generic record steps
# A target is {"key": ids key, "model": "agreement" | "agreement.appendix", "action": xmlid, "label": text}.


def target_id(st, target):
    return st["ids"][target["key"]]


def open_target(st, target):
    odoo_open(st["base"], target["action"], target_id(st, target), model=target["model"])


def target_state(st, target):
    meta = TABLES[target["model"]]
    (value,) = one(st["db"], f"select {meta['state']} from {meta['table']} where id = {target_id(st, target)}")
    return value


def state_label(st, target, value):
    return st["plan"]["labels"][target["model"]].get(value, value.upper())


def expect_state(st, target, value, detail=""):
    found = target_state(st, target)
    check(found == value, f"{target['label']} state {found}, expected {value}{detail}")
    label = state_label(st, target, value)
    check(_stage_ui() == label, f"statusbar shows {_stage_ui()!r}, expected {label}")
    return label


def as_user(st, target, login, name):
    switch_user(login)
    check(name.lower() in _user().lower(), f"top bar shows {_user()!r}, expected {name!r}")
    check(str(form_state()["id"]) == str(target_id(st, target)), f"the {target['label']} is not open as {login}")


def actor_biz_ops_2(target):
    """The partner's Credit Ops (res_partner.biz_ops_2): clicks TO REVIEW on agreements and appendices."""
    table = TABLES[target["model"]]["table"]

    def actor(st):
        return fetch(
            st["db"],
            f"select u.login, up.name from {table} r join res_partner p on p.id = r.partner_id"
            " join res_users u on u.id = p.biz_ops_2 join res_partner up on up.id = u.partner_id"
            f" where r.id = {target_id(st, target)}",
            f"Credit Ops (biz_ops_2) of the {target['label']} partner",
        )

    return actor


def step_to_check(target):
    """Administrator clicks TO CHECK on a record in stage new."""

    def run(st):
        open_target(st, target)
        check("action_to_check" in _buttons(), f"no TO CHECK button; buttons {form_state()['buttons']}")
        error = click_btn("action_to_check")
        label = expect_state(st, target, "draft", f"; dialog: {error or _dialog() or 'none'}")
        shot = _shot(st, f"{target['key']}-to-check")
        return [
            f"DB  {target['label']} id={target_id(st, target)} state=draft",
            f"SHOT {shot}",
            f"EXPECT {target['label']}: statusbar current stage {label}; Administrator in the top bar; no error dialog",
        ]

    return run


def step_show_state(target, value, name):
    """Open the record as the current user and confirm DB + statusbar show `value` (no action)."""

    def run(st):
        open_target(st, target)
        label = expect_state(st, target, value)
        shot = _shot(st, name)
        return [
            f"DB  {target['label']} id={target_id(st, target)} state={value}",
            f"SHOT {shot}",
            f"EXPECT {target['label']}: statusbar current stage {label}; Administrator in the top bar",
        ]

    return run


def step_to_review(target, button, actor):
    """Open as admin, impersonate `actor(st)` -> (login, name), click the TO REVIEW `button`."""

    def run(st):
        open_target(st, target)
        login, name = actor(st)
        as_user(st, target, login, name)
        check(button in _buttons(), f"no {button} button for {login}; buttons {form_state()['buttons']}")
        error = click_btn(button)
        label = expect_state(st, target, "to_review", f"; dialog: {error or _dialog() or 'none'}")
        shot = _shot(st, f"{target['key']}-to-review")
        return [
            f"DB  {target['label']} id={target_id(st, target)} state=to_review (by {login})",
            f"SHOT {shot}",
            f"EXPECT {name} in the top bar; statusbar current stage {label}; no error dialog",
        ]

    return run


def step_approve(name, target, final="reviewed"):
    """One waiting approver approves per call; repeats until the record reaches `final`."""
    fk = TABLES[target["model"]]["approver_fk"]

    def run(st):
        state = target_state(st, target)
        if state == final:
            st["done"].append(name)
            return [f"DB  {target['label']} already {final}, no approver left"]
        pending = one(
            st["db"],
            "select ap.id, u.login, up.name, coalesce(ap.approval_role, '-'), coalesce(ap.approval_stage, '-')"
            " from agreement_approver ap join res_users u on u.id = ap.user_id"
            " join res_partner up on up.id = u.partner_id"
            f" where ap.{fk} = {target_id(st, target)} and ap.status = 'waiting' order by ap.sequence, ap.id limit 1",
        )
        check(pending, f"{target['label']} is at {state} but no approver is waiting")
        rounds = st["rounds"]
        rounds[name] = rounds.get(name, 0) + 1
        check(rounds[name] <= MAX_ROUNDS, f"more than {MAX_ROUNDS} approval rounds on the {target['label']}")
        approver_id, login, approver_name, role, stage = pending
        as_user(st, target, login, approver_name)
        check("action_approve" in _buttons(), f"no APPROVE button for {login}; buttons {form_state()['buttons']}")
        error = click_btn("action_approve")
        (status,) = one(st["db"], f"select status from agreement_approver where id = {approver_id}")
        check(status == "approved", f"approver {login} status {status}, expected approved; dialog: {error or _dialog() or 'none'}")
        new_state = target_state(st, target)
        label = state_label(st, target, new_state)
        check(_stage_ui() == label, f"statusbar shows {_stage_ui()!r}, expected {label}")
        shot = _shot(st, f"{target['key']}-approved-by-{login.split('@')[0]}")
        if new_state == final:
            st["done"].append(name)
        return [
            f"DB  {target['label']}: {role} {login} approved at {stage} -> state={new_state}",
            f"SHOT {shot}",
            f"EXPECT {approver_name} in the top bar; statusbar current stage {label}",
        ]

    run.repeat = True
    return run


def step_finish(target, final="reviewed", chatter=None, extra=None):
    """Back to Administrator on the record: final state in DB + UI, optional chatter text and extra checks."""

    def run(st):
        switch_user("admin")
        check("administrator" in _user().lower(), f"top bar shows {_user()!r}, expected Administrator")
        if str(form_state()["id"]) != str(target_id(st, target)):
            open_target(st, target)
        label = expect_state(st, target, final)
        expect = [f"Administrator in the top bar; statusbar current stage {label}"]
        if chatter:
            present = f"document.body.innerText.includes({json.dumps(chatter)})"
            for _ in range(20):
                if js(present):
                    break
                time.sleep(0.25)
            check(js(present), f"chatter does not show {chatter!r}")
            expect.append(f"chatter shows '{chatter}'")
        lines = extra(st) if extra else []
        shot = _shot(st, f"{target['key']}-{final}")
        return [
            f"DB  {target['label']} id={target_id(st, target)} state={final}",
            *lines,
            f"SHOT {shot}",
            "EXPECT " + "; ".join(expect),
        ]

    return run


# ---------------------------------------------------------------- run one step


def _too_slow(signum, frame):
    raise StepFailed(f"step took longer than {STEP_SECONDS} s")


def _stop(state_path, st, message):
    st["failed"] = message
    st["last"] = {"step": message.split(":")[0], "ok": False}
    write_state(state_path, st)
    print(f"FLOW STOPPED: {message}")
    print("Do not continue; report this failure.")


def _chain_next(st, step, fn, call_started):
    """After `step` succeeded: the step to run in the same call, or None (keeps one call under the 25 s alarm)."""
    remaining = pending_steps(st)
    if not remaining or time.time() - call_started >= CHAIN_SECONDS:
        return None
    nxt = remaining[0]
    return nxt if nxt in LIGHT_STEPS or (nxt == step and getattr(fn, "repeat", False)) else None


def run_step(state_path):
    with open(state_path) as fh:
        st = json.load(fh)
    if st["failed"]:
        _stop(state_path, st, st["failed"])
        return
    if st["running"]:
        running, st["running"] = st["running"], None
        _stop(state_path, st, f"{running}: the previous call did not finish (killed by a timeout?)")
        return
    pending = pending_steps(st)
    if not pending:
        print("FLOW DONE")
        return
    step = pending[0]
    call_started = started = time.time()
    st["running"] = step
    try:
        signal.signal(signal.SIGALRM, _too_slow)
        signal.alarm(STEP_SECONDS)
    except ValueError:
        pass
    try:
        _ensure_tab(st)
        while step:
            fn = dict(FLOWS[st["flow"]]["steps"])[step]
            st["running"] = step
            write_state(state_path, st)
            started = time.time()
            lines = fn(st)
            if not getattr(fn, "repeat", False):
                st["done"].append(step)
            secs = round(time.time() - started, 1)
            st["last"] = {"step": step, "ok": True, "secs": secs}
            st["log"].append({"step": step, "ok": True, "secs": secs})
            print(f"STEP {step} OK ({secs}s)")
            for line in lines:
                print(line)
            step = _chain_next(st, step, fn, call_started)
        signal.alarm(0)
        remaining = pending_steps(st)
        if remaining:
            print(f"NEXT {remaining[0]}")
        else:
            _close_tab(st)
            total = round(sum(entry["secs"] for entry in st["log"]), 1)
            print(f"FLOW DONE · {len(st['log'])} steps · {total}s in the browser")
    except Exception as exc:
        signal.alarm(0)
        step = st["running"]
        secs = round(time.time() - started, 1)
        shot = os.path.join(st["dir"], f"fail-{step}.png")
        try:
            screenshot(shot)
        except Exception:
            shot = None
        try:
            _close_tab(st)
        except Exception:
            pass
        st["failed"] = f"{step}: {type(exc).__name__}: {exc}"
        st["last"] = {"step": step, "ok": False, "secs": secs}
        st["log"].append({"step": step, "ok": False, "secs": secs, "error": str(exc)})
        print(f"STEP {step} FAILED ({secs}s): {type(exc).__name__}: {exc}")
        if shot:
            print(f"SHOT {shot}")
        print("FLOW STOPPED — do not continue; report this failure.")
    finally:
        st["running"] = None
        st["next"] = (pending_steps(st) or [None])[0]
        write_state(state_path, st)
