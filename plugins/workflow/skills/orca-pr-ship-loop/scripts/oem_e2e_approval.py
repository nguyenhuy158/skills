# ruff: noqa: F821
# Shared by oem_trading_e2e.py and oem_processing_e2e.py (exec'd into the same browser-use namespace):
# fill every editable optional field, confirm the order, fill its agreement, then drive the approval chain
# project AM TO REVIEW -> each waiting approver APPROVE (switch_user) -> Approved, checked in UI + DB.
# Needs env DB=<wt database> (read-only SQL through the dev-postgres container).
import subprocess

DB = os.environ["DB"]
AGREEMENT_ACTION = "agreement.agreement_action"
MAX_APPROVALS = 8


def sql(query):
    run = subprocess.run(
        ["docker", "exec", "dev-postgres", "psql", "-U", "farmnet_service", "-d", DB, "-At", "-F", "\t", "-c", query],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if run.returncode:
        raise RuntimeError(f"SQL error: {run.stderr.strip()}")
    return [line.split("\t") for line in run.stdout.splitlines() if line]


def one(query):
    rows = sql(query)
    return rows[0] if rows else None


def editable(field, scope=".o_form_view"):
    """True when the field is on screen and has an input the user can type into."""
    sel = json.dumps(f"{scope} div[name={field}]")
    return js(
        f"(()=>{{const d=document.querySelector({sel}); if(!d||!d.getClientRects().length) return false;"
        "const i=d.querySelector('input:not([readonly]):not([disabled]),textarea:not([readonly]),select');"
        "return !!i && !d.classList.contains('o_readonly_modifier');})()"
    )


def fill_optional(values, scope=".o_form_view"):
    """Fill each (field, value, is_m2o) that is visible and editable; print what was skipped."""
    filled, skipped = [], []
    for field, value, is_m2o in values:
        if not editable(field, scope):
            skipped.append(field)
            continue
        try:
            (fill_m2o if is_m2o else fill)(field, value, scope=scope)
            filled.append(field)
        except Exception as error:
            skipped.append(f"{field} ({str(error)[:60]})")
    print("  filled:", filled, "| not editable here:", skipped, flush=True)


def buttons():
    return [button.split(":")[0] for button in form_state()["buttons"] or []]


def order_agreement(model, order_id):
    table = "purchase_order" if model == "purchase.order" else "sale_order"
    return one(f"select agreement_id from {table} where id = {order_id}")[0]


def agreement_stage(agreement_id):
    return one(f"select stage from agreement where id = {agreement_id}")[0]


def fill_agreement(agreement_id, agreement_type):
    """Open the order agreement and fill type, contact, bank, dates, signer and description."""
    odoo_open(B, AGREEMENT_ACTION, agreement_id, model="agreement")
    (partner, company) = one(f"select partner_id, company_id from agreement where id = {agreement_id}")
    domain = "purchase" if one(f"select 1 from purchase_order where agreement_id = {agreement_id}") else "sale"
    framework = one(
        f"select name from agreement where is_template and partner_id = {partner} and company_id = {company}"
        f" and domain = '{domain}' and stage in ('reviewed', 'active') order by id desc limit 1"
    )
    contact = one(f"select name from res_partner where parent_id = {partner} and active order by id desc limit 1")
    bank = one(
        f"select acc_number from res_partner_bank where partner_id = {partner} and allow_out_payment order by id desc limit 1"
    )
    values = [("agreement_type_id", agreement_type, True)]
    if contact:
        values.append(("partner_contact_id", contact[0], True))
    if bank:
        values.append(("partner_bank_id", bank[0], True))
    if framework:
        values.append(("parent_id", framework[0], True))
    values += [
        ("signature_date", "01/10/2026", False),
        ("expiration_date", "31/12/2026", False),
        ("number_origin_ref", f"E2E-{agreement_id}", False),
        ("sign_person", "Administrator", True),
        ("description", "E2E OEM agreement: all fields filled by the script", False),
    ]
    fill_optional(values)
    err = save()
    row = one(
        "select coalesce(agreement_type_id::text,''), coalesce(partner_contact_id::text,''),"
        f" coalesce(partner_bank_id::text,''), coalesce(expiration_date::text,'') from agreement where id = {agreement_id}"
    )
    print("  agreement DB (type, contact, bank, expiration):", row, flush=True)
    if not row[0]:
        return err or "agreement type not saved"
    return err


def confirm_order(model, order_id, action, button):
    odoo_open(B, action, order_id, model=model)
    if button not in buttons():
        return f"no {button} button; buttons {buttons()}"
    err = click_btn(button)
    table = "purchase_order" if model == "purchase.order" else "sale_order"
    (state,) = one(f"select state from {table} where id = {order_id}")
    stage = agreement_stage(order_agreement(model, order_id))
    print(f"  {model} {order_id} state={state} agreement stage={stage}", flush=True)
    if state not in ("purchase", "sale", "to approve"):
        return err or f"order state {state} after {button}"
    if stage != "draft":
        return err or f"agreement stage {stage}, expected draft (To Check)"
    return err


def as_user(login, agreement_id):
    switch_user(login)
    if str(form_state()["id"]) != str(agreement_id):
        odoo_open(B, AGREEMENT_ACTION, agreement_id, model="agreement")


def send_to_review(agreement_id):
    """The OEM project's AM clicks the AM TO REVIEW button (action_account_manager_to_review)."""
    odoo_open(B, AGREEMENT_ACTION, agreement_id, model="agreement")
    am = one(
        "select u.login from agreement a join oem_project p on p.id = a.oem_project_id"
        f" join res_users u on u.id = p.account_manager_id where a.id = {agreement_id}"
    )
    if not am:
        return "agreement has no OEM project AM"
    as_user(am[0], agreement_id)
    if "action_authorize_to_review" in buttons():
        return f"CO TO REVIEW button still shown to {am[0]}; buttons {buttons()}"
    if "action_account_manager_to_review" not in buttons():
        return f"no AM TO REVIEW button for {am[0]}; buttons {buttons()}"
    err = click_btn("action_account_manager_to_review")
    stage = agreement_stage(agreement_id)
    print(f"  TO REVIEW by AM {am[0]} -> {stage}", flush=True)
    return err or (None if stage in ("to_review", "exception", "reviewed") else f"stage {stage} after TO REVIEW")


def approve_all(agreement_id, shot_prefix):
    """Each waiting approver approves in sequence until the agreement is Approved (stage reviewed)."""
    for index in range(MAX_APPROVALS):
        stage = agreement_stage(agreement_id)
        if stage == "reviewed":
            switch_user("admin")
            odoo_open(B, AGREEMENT_ACTION, agreement_id, model="agreement")
            ui = (form_state()["stage"] or "").strip().upper()
            print(f"  Approved: DB stage=reviewed, statusbar {ui}", flush=True)
            return None if ui == "APPROVED" else f"statusbar shows {ui!r}, expected APPROVED"
        pending = one(
            "select ap.id, u.login, coalesce(ap.approval_role,'-') from agreement_approver ap"
            f" join res_users u on u.id = ap.user_id where ap.agreement_id = {agreement_id} and ap.status = 'waiting'"
            " order by ap.sequence, ap.id limit 1"
        )
        if not pending:
            return f"stage {stage} but no approver is waiting"
        approver_id, login, role = pending
        as_user(login, agreement_id)
        if "action_approve" not in buttons():
            return f"no APPROVE button for {login} at {stage}; buttons {buttons()}"
        err = click_btn("action_approve")
        (status,) = one(f"select status from agreement_approver where id = {approver_id}")
        print(f"  {role} {login} approved at {stage} -> {agreement_stage(agreement_id)}", flush=True)
        if SHOTS:
            screenshot(f"{SHOTS}/{shot_prefix}-approve-{index + 1}.png")
        if status != "approved":
            return err or f"approver {login} status {status}"
    return f"more than {MAX_APPROVALS} approval rounds"


def approval_flow(prefix, model, order_id, action, button, agreement_type):
    """fill agreement -> confirm order -> TO REVIEW -> approvers -> Approved, one STEP each."""
    agreement_id = order_agreement(model, order_id)
    ids[f"{prefix}_agreement"] = agreement_id
    step(f"{prefix}-agreement-fill", lambda: fill_agreement(agreement_id, agreement_type))
    step(f"{prefix}-confirm", lambda: confirm_order(model, order_id, action, button))
    step(f"{prefix}-to-review", lambda: send_to_review(agreement_id))
    step(f"{prefix}-approved", lambda: approve_all(agreement_id, prefix))
