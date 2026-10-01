# ruff: noqa: F821
"""Flow `payment_request`: take an existing payment request (they are only created by code: CKHD by cron, early payment
discount by the Monday cron, refunds from bank transactions) and drive it with the user of each role:
Draft -> (Biz Ops picks the customer bank when empty) -> TO CHECK (customer Biz Ops; early discount: Senior BO)
-> To review -> REVIEWED when the bank is not approved yet (customer Credit Ops) -> CONFIRM (ops with confirm right)
-> Confirmed. Approved / Paid only come back from FarmLink. A request already in To review / To check starts at that step.

Each run consumes one request."""

DOMAINS = {
    "market_development": {"label": "Payment Discount (CKHD)", "to_check": "biz_ops"},
    "early_payment_discount": {"label": "Early Payment Discount", "to_check": "senior_bo"},
    "payment_refund": {"label": "Refund", "to_check": "biz_ops"},
}
PR = {
    "key": "payment_request",
    "model": "payment.request",
    "action": "farmnet_payment_request.payment_request_action",
    "label": "payment request",
}


def _group_user(db, *groups, what):
    """First active non-admin user in every (module, group) given."""
    conds = " ".join(
        "and exists (select 1 from res_groups_users_rel r join ir_model_data d on d.res_id = r.gid and d.model = 'res.groups'"
        f" where r.uid = u.id and d.module = '{module}' and d.name = '{name}')"
        for module, name in groups
    )
    return fetch(
        db,
        "select u.login, up.name from res_users u join res_partner up on up.id = u.partner_id where u.active"
        f" and u.login not in ('admin', 'farmlink@techcoop.vn') {conds} order by u.id limit 1",
        what,
    )


def plan_payment_request(db, params):
    domain = params.get("domain", "market_development")
    check(domain in DOMAINS, f"domain={domain} must be one of {', '.join(DOMAINS)}")
    state = params.get("state") or ("draft" if params.get("new_bank") == "1" else None)
    request = params.get("request")
    where = f"pr.id = {int(request)}" if request else f"pr.domain = '{domain}'"
    if state:
        where += f" and pr.state = '{state}'"
    row = fetch(
        db,
        "select pr.id, pr.name, pr.state, pr.domain, round(pr.payment_amount), coalesce(pr.customer_bank::text, '-'),"
        " coalesce(b.approval_state, '-'), c.id, c.name, bo.login, bop.name, bo2.login, bo2p.name"
        " from payment_request pr join res_partner c on c.id = pr.customer_id"
        " join res_users bo on bo.id = c.biz_ops join res_partner bop on bop.id = bo.partner_id"
        " join res_users bo2 on bo2.id = c.biz_ops_2 join res_partner bo2p on bo2p.id = bo2.partner_id"
        " left join res_partner_bank b on b.id = pr.customer_bank left join account_move inv on inv.id = pr.invoice_id"
        f" where {where} and pr.state in ('draft', 'to_review', 'to_check')"
        " and pr.payment_date between current_date - 7 and current_date + 7"
        " and (pr.domain <> 'market_development' or inv.payment_state = 'paid')"
        " and (pr.payment_amount > 0 or pr.domain = 'early_payment_discount')"
        " and not coalesce(c.is_suspended_cooperation, false)"
        " and not coalesce((select max(d.farmlink_paid_date)::date from sale_disbursement d"
        " where d.invoice_id = pr.invoice_id and d.state = 'paid')"
        " > coalesce(pr.appendix_discount_date, (select so.discount_date from sale_order so where so.id = pr.sale_id)), false)"
        " and (pr.domain <> 'market_development' or not exists (select 1 from sale_disbursement d"
        " left join payment_request r on r.id = d.payment_request_id"
        " where d.state <> 'cancel' and (d.invoice_id = pr.invoice_id or d.id in (select l.disbursement_id"
        " from sale_disbursement_invoice_line l where l.invoice_id = pr.invoice_id))"
        " and (r.id is null or r.state in ('cancelled', 'refused'))"
        " and ((d.type = 'debt_offset' and d.state in ('disbursed', 'paid'))"
        " or (d.state = 'paid' and d.due_date is not null and coalesce(d.farmlink_paid_date::date, d.due_date) > d.due_date)"
        " or (d.state = 'disbursed' and d.due_date < current_date))))"
        " order by pr.payment_date desc, pr.id desc limit 1",
        f"a {domain} request in Draft / To review / To check with payment date within ±7 days"
        + (f" in state {state}" if state else ""),
    )
    pr_id, name, pr_state, domain, amount, bank, bank_state, cust_id, customer, bo, bo_name, bo2, bo2_name = row
    bank = "" if bank == "-" else bank
    bank_state = "" if bank_state == "-" else bank_state
    bank_acc = None
    if not bank:
        pick_id, bank_acc = partner_bank(db, cust_id)
    if params.get("new_bank") == "1":
        check(db.startswith("wt_"), f"new_bank=1 edits data: only on a worktree clone db (wt_*), not {db}")
        check(pr_state == "draft", f"new_bank=1 needs a Draft request (TO CHECK decides the branch), {name} is {pr_state}")
        sql(db, f"update res_partner_bank set approval_state = 'new' where id = {int(bank or pick_id)}")
        bank_state = "new" if bank else bank_state
    if DOMAINS[domain]["to_check"] == "senior_bo":
        checker, checker_name = _group_user(
            db, ("farmnet_sale_order", "restrict_for_senior_bo"), ("farmnet_payment_request", "restrict_for_admin"),
            what="a Senior BO who can see every payment request",
        )
    else:
        checker, checker_name = bo, bo_name
    confirmer, confirmer_name = _group_user(
        db, ("farmnet_payment_request", "action_confirm"), ("farmnet_payment_request", "restrict_for_admin"),
        what="a user with the payment request confirm right",
    )
    return {
        "domain": domain,
        "domain_label": DOMAINS[domain]["label"],
        "request_name": name,
        "start_state": pr_state,
        "amount": amount,
        "customer_name": customer,
        "bank": "set" if bank else "empty",
        "bank_state": bank_state or "-",
        "bank_to_pick": bank_acc,
        "biz_ops": bo,
        "biz_ops_name": bo_name,
        "checker": checker,
        "checker_name": checker_name,
        "credit_ops": bo2,
        "credit_ops_name": bo2_name,
        "confirmer": confirmer,
        "confirmer_name": confirmer_name,
        "new_bank": params.get("new_bank") == "1",
        "ids": {"payment_request": int(pr_id)},
    }


def step_pr_open(st):
    plan = st["plan"]
    login_admin(st)
    open_target(st, PR)
    label = expect_state(st, PR, plan["start_state"])
    shot = _shot(st, "payment-request-start", must_show=(plan["request_name"], plan["customer_name"]))
    return [
        f"DB  {plan['request_name']} ({plan['domain_label']}) state={plan['start_state']} amount={plan['amount']}"
        f" bank={plan['bank']} ({plan['bank_state']})",
        f"SHOT {shot}",
        f"EXPECT {plan['request_name']}: statusbar current stage {label}; customer {plan['customer_name']}",
    ]


def step_pr_bank(st):
    plan = st["plan"]
    if not plan["bank_to_pick"] or target_state(st, PR) != "draft":
        return ["DB  customer bank already set: nothing to pick"]
    open_target(st, PR)
    as_user(st, PR, plan["biz_ops"], plan["biz_ops_name"])
    fill_m2o("customer_bank", plan["bank_to_pick"])
    error = save()
    (bank,) = one(st["db"], f"select coalesce(customer_bank::text, '') from payment_request where id = {target_id(st, PR)}")
    check(bank, f"customer bank not saved by {plan['biz_ops']}; dialog: {error or _dialog() or 'none'}")
    (approval,) = one(st["db"], f"select coalesce(approval_state, '-') from res_partner_bank where id = {bank}")
    return [f"DB  customer_bank={plan['bank_to_pick']} (approval {approval}) picked by {plan['biz_ops']}"]


def step_pr_to_check(st):
    plan = st["plan"]
    if target_state(st, PR) != "draft":
        return [f"DB  already {target_state(st, PR)}: TO CHECK not needed"]
    open_target(st, PR)
    as_user(st, PR, plan["checker"], plan["checker_name"])
    check("action_to_check" in _buttons(), f"no TO CHECK button for {plan['checker']}; buttons {form_state()['buttons']}")
    error = click_btn("action_to_check")
    state = target_state(st, PR)
    check(state in ("to_check", "to_review", "paid"),
          f"state {state} after TO CHECK by {plan['checker']}; dialog: {error or _dialog() or 'none'}")
    check(state == "to_review" or not plan.get("new_bank"), f"new_bank=1 but the request went to {state}, expected to_review")
    label = expect_state(st, PR, state)
    shot = _shot(st, "payment-request-to-check")
    return [
        f"DB  {plan['request_name']} state={state} (TO CHECK by {plan['checker']})",
        f"SHOT {shot}",
        f"EXPECT {plan['checker_name']} in the top bar; statusbar current stage {label}; no error dialog",
    ]


def step_pr_reviewed(st):
    plan = st["plan"]
    if target_state(st, PR) != "to_review":
        return [f"DB  state {target_state(st, PR)}: no REVIEWED step needed"]
    open_target(st, PR)
    as_user(st, PR, plan["credit_ops"], plan["credit_ops_name"])
    check("action_to_reviewed" in _buttons(), f"no REVIEWED button for {plan['credit_ops']}; buttons {form_state()['buttons']}")
    error = click_btn("action_to_reviewed")
    label = expect_state(st, PR, "to_check", f"; dialog: {error or _dialog() or 'none'}")
    (approval,) = one(
        st["db"],
        "select coalesce(b.approval_state, '-') from payment_request pr join res_partner_bank b on b.id = pr.customer_bank"
        f" where pr.id = {target_id(st, PR)}",
    )
    shot = _shot(st, "payment-request-reviewed")
    return [
        f"DB  {plan['request_name']} state=to_check after REVIEWED by {plan['credit_ops']} · bank approval={approval}",
        f"SHOT {shot}",
        f"EXPECT {plan['credit_ops_name']} in the top bar; statusbar current stage {label}",
    ]


def step_pr_confirm(st):
    plan = st["plan"]
    state = target_state(st, PR)
    if state == "paid":
        return ["DB  zero amount: moved straight to Paid, nothing to confirm"]
    check(state == "to_check", f"state {state} before CONFIRM, expected to_check")
    open_target(st, PR)
    as_user(st, PR, plan["confirmer"], plan["confirmer_name"])
    check("action_confirm" in _buttons(), f"no CONFIRM button for {plan['confirmer']}; buttons {form_state()['buttons']}")
    error = click_btn("action_confirm")
    label = expect_state(st, PR, "confirmed", f"; dialog: {error or _dialog() or 'none'}")
    login, source = one(
        st["db"],
        "select u.login, coalesce(pr.source_id::text, '') from payment_request pr left join res_users u on u.id = pr.confirmed_uid"
        f" where pr.id = {target_id(st, PR)}",
    )
    check(login == plan["confirmer"], f"confirmed_uid is {login}, expected {plan['confirmer']}")
    shot = _shot(st, "payment-request-confirmed")
    return [
        f"DB  {plan['request_name']} state=confirmed confirmed_uid={login} source_id={source or '-'}",
        f"SHOT {shot}",
        f"EXPECT {plan['confirmer_name']} in the top bar; statusbar current stage {label}; no error dialog",
    ]


def step_pr_finish(st):
    final = "paid" if target_state(st, PR) == "paid" else "confirmed"
    return step_finish(PR, final=final)(st)


register(
    "payment_request",
    "existing payment request (CKHD / early payment discount / refund) driven by each role: bank pick + TO CHECK"
    " -> REVIEWED when the bank is new -> CONFIRM -> Confirmed",
    "[domain=market_development|early_payment_discount|payment_refund] [state=draft|to_review|to_check]"
    " [request=<id>] [new_bank=1] (default: the newest actionable request of that domain with payment date within ±7"
    " days; each run consumes one request; new_bank=1 takes a Draft request and resets its customer bank to"
    " approval_state=new on the wt_* clone to drive the REVIEWED branch)",
    plan_payment_request,
    [
        ("pr_open", step_pr_open),
        ("pr_bank", step_pr_bank),
        ("pr_to_check", step_pr_to_check),
        ("pr_reviewed", step_pr_reviewed),
        ("pr_confirm", step_pr_confirm),
        ("finish", step_pr_finish),
    ],
)
