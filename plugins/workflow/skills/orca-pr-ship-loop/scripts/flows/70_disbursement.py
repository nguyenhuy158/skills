# ruff: noqa: F821
"""Flow `disbursement`: Trade (or Input) disbursement request (DR) created from the sale order's Disbursements smart
button for a posted vendor bill -> TO CHECK by the customer's Biz Ops -> (bank not approved yet: To review -> REVIEWED by
the customer's Credit Ops) -> CONFIRM by an ops user with the disbursement approve right -> Confirmed.
Approve / Disbursed / Paid only come back from FarmLink.

Each run disburses one bill (a bill with an open DR is skipped)."""

import datetime as dt

SO_ACTION = "sale.action_quotations_with_onboarding"
DR = {
    "key": "disbursement",
    "model": "sale.disbursement",
    "action": "farmnet_sale_order.action_view_accountant_disbursements",
    "label": "disbursement",
}
CONFIRMER = (
    "select u.login, up.name from res_users u join res_partner up on up.id = u.partner_id where u.active"
    " and u.login not in ('admin', 'farmlink@techcoop.vn')"
    " and exists (select 1 from res_groups_users_rel r join ir_model_data d on d.res_id = r.gid and d.model = 'res.groups'"
    " where r.uid = u.id and d.module = 'farmnet_sale_order' and d.name = 'disbursement_approve')"
    " and exists (select 1 from res_groups_users_rel r join ir_model_data d on d.res_id = r.gid and d.model = 'res.groups'"
    " where r.uid = u.id and d.module = 'farmnet_sale_order' and d.name = 'sale_disbursement_restrict_for_admin')"
    " order by u.id limit 1"
)
TYPES = {"trade": "Trade", "input": "Input", "invest": "Invest"}
BILL_SQL = (
    "select so.id, so.name, so.company_id, po.name, bill.id, bill.name, bill.ref, bo.login, bop.name, bo2.login, bo2p.name, pb.id"
    " from account_move bill join purchase_order po on po.id = bill.purchase_id and po.state = 'purchase'"
    " join sale_order so on so.id = po.sale_id and so.state = 'sale' and so.type = 'sale'"
    " join account_move inv on inv.stock_picking_id = bill.stock_picking_id and inv.move_type = 'out_invoice'"
    " and inv.state = 'posted' join stock_picking sp on sp.id = bill.stock_picking_id"
    " join agreement pag on pag.id = po.agreement_id join res_partner_bank pb on pb.id = pag.partner_bank_id"
    " and pb.allow_out_payment join res_partner c on c.id = so.partner_id"
    " join res_users bo on bo.id = c.biz_ops join res_partner bop on bop.id = bo.partner_id"
    " join res_users bo2 on bo2.id = c.biz_ops_2 join res_partner bo2p on bo2p.id = bo2.partner_id"
    " where {where} and bill.move_type = 'in_invoice' and bill.state = 'posted' and bill.ref is not null"
    " and not coalesce(sp.have_return, false) and not coalesce(c.is_suspended_cooperation, false)"
    " and (select count(*) from purchase_order p2 where p2.sale_id = so.id) = 1"
    " and not exists (select 1 from sale_disbursement d where d.bill_id = bill.id and d.state not in ('refused', 'cancel'))"
    " and not exists (select 1 from sale_disbursement_invoice_line l join sale_disbursement d on d.id = l.disbursement_id"
    " where l.bill_id = bill.id and d.state not in ('refused', 'cancel'))"
    " order by bill.id desc limit 1"
)
INVEST_SQL = (
    "select so.id, so.name, so.company_id, po.name, '-', '-', '-', bo.login, bop.name, bo2.login, bo2p.name, pb.id"
    " from sale_order so join agreement sag on sag.id = so.agreement_id and sag.stage in ('reviewed', 'active')"
    " join purchase_order po on po.sale_id = so.id and po.state = 'purchase'"
    " join agreement pag on pag.id = po.agreement_id join res_partner_bank pb on pb.id = pag.partner_bank_id"
    " and pb.allow_out_payment join res_partner c on c.id = so.partner_id"
    " join res_users bo on bo.id = c.biz_ops join res_partner bop on bop.id = bo.partner_id"
    " join res_users bo2 on bo2.id = c.biz_ops_2 join res_partner bo2p on bo2p.id = bo2.partner_id"
    " where {where} and so.state = 'sale' and so.type = 'sale' and not coalesce(c.is_suspended_cooperation, false)"
    " and po.amount_total - coalesce((select sum(d.disbursement_amount) from sale_disbursement d where d.purchase_id = po.id"
    " and d.state not in ('refused', 'cancel')), 0) >= {amount}"
    " and (select count(*) from purchase_order p2 where p2.sale_id = so.id) = 1 order by so.id desc limit 1"
)


def plan_disbursement(db, params):
    kind_type = params.get("type", "trade")
    check(kind_type in TYPES, f"type={kind_type} must be one of {', '.join(TYPES)}")
    so = params.get("so")
    where = f"so.id = {int(so)}" if so else "true"
    invest = kind_type == "invest"
    row = fetch(
        db,
        (INVEST_SQL if invest else BILL_SQL).format(where=where, amount=float(params.get("amount", "50000000"))),
        "a confirmed single-PO sale order with an approved sale agreement and room left on its purchase amount" if invest
        else "a posted vendor bill of a confirmed sale order (single PO, paired customer invoice, no open DR, no return)",
    )
    so_id, so_name, company, po_name, bill_id, bill_name, bill_ref, bo, bo_name, bo2, bo2_name, bank_id = row
    if params.get("new_bank") == "1":
        check(db.startswith("wt_"), f"new_bank=1 edits data: only on a worktree clone db (wt_*), not {db}")
        sql(db, f"update res_partner_bank set approval_state = 'new' where id = {int(bank_id)}")
    source_id, source_name = fetch(
        db,
        "select s.id, s.name->>'en_US' from sale_disbursement_source s left join sale_disbursement d on d.source_id = s.id"
        f" and d.create_date > now() - interval '90 days' where s.company_id = {company} or s.company_id is null"
        " group by s.id order by count(d.id) desc, s.id limit 1",
        f"a disbursement source for company {company}",
    )
    confirmer, confirmer_name = fetch(db, CONFIRMER, "a user with the disbursement approve right")
    kind_label = params.get("kind", "Old")
    (kind_value,) = fetch(
        db,
        "select s.value from ir_model_fields_selection s join ir_model_fields f on f.id = s.field_id"
        f" where f.model = 'sale.disbursement' and f.name = 'kind' and s.name->>'en_US' = '{kind_label}'",
        f"disbursement kind {kind_label}",
    )
    return {
        "type": kind_type,
        "type_label": TYPES[kind_type],
        "kind_label": kind_label,
        "kind_value": kind_value,
        "so_name": so_name,
        "po_name": po_name,
        "bill_id": int(bill_id) if not invest else None,
        "bill_name": bill_name if not invest else None,
        "bill_ref": bill_ref if not invest else None,
        "amount": params.get("amount", "50000000") if invest else None,
        "supplier_bank_id": int(bank_id),
        "new_bank": params.get("new_bank") == "1",
        "source_id": int(source_id),
        "source_name": source_name,
        "biz_ops": bo,
        "biz_ops_name": bo_name,
        "credit_ops": bo2,
        "credit_ops_name": bo2_name,
        "confirmer": confirmer,
        "confirmer_name": confirmer_name,
        "date": ui_date(dt.date.today()),
        "date_iso": dt.date.today().isoformat(),
        "ids": {"so": int(so_id)},
    }


def step_dr_form(st):
    plan = st["plan"]
    login_admin(st)
    odoo_open(st["base"], SO_ACTION, st["ids"]["so"], model="sale.order")
    click(".o_form_view button[name=action_view_disbursement]")
    wait_view("list", "the disbursement list of the sale order did not open")
    click(".o_list_button_add")
    wait_view("form", "the new disbursement form did not open")
    check(form_state()["id"] is None, "expected an empty new disbursement form")
    fill_select("type", plan["type_label"])
    check(plan["po_name"].split(" ")[0] in _value("purchase_id"), f"purchase order shows {_value('purchase_id')!r}, expected {plan['po_name']}")
    if plan["bill_ref"]:
        fill_m2o("bill_id", plan["bill_name"], pick=plan["bill_ref"])
        _expect_value("bill_id", plan["bill_ref"])
        check(_value("invoice_id"), "no customer invoice was paired with the bill")
        return [f"UI  new {plan['type_label']} DR: {plan['po_name']} · bill {plan['bill_ref']} · invoice {_value('invoice_id')}"]
    check(_value("supplier_bank_id"), "no supplier bank prefilled for the invest DR")
    return [f"UI  new {plan['type_label']} DR: {plan['po_name']} · supplier bank {_value('supplier_bank_id')}"]


def step_dr_save(st):
    db, plan = st["db"], st["plan"]
    check(form_state()["id"] is None and plan["type_label"] in _value("type"), "the unsaved DR from dr_form is no longer on screen")
    fill("disbursement_date", plan["date"])
    if plan["amount"]:
        fill("disbursement_amount", plan["amount"])
    fill_select("kind", plan["kind_label"])
    fill_m2o("source_id", plan["source_name"])
    error = save()
    record = form_state()["id"]
    check(record, f"no DR id after save; dialog: {error or _dialog() or 'none'}")
    name, state, dr_type, bill, invoice, amount, repay, disb_date, source, created_from, kind = one(
        db,
        "select name, state, type, bill_id, invoice_id, disbursement_amount, repayment_amount, disbursement_date, source_id,"
        f" created_from, kind from sale_disbursement where id = {record}",
    )
    check(kind == plan["kind_value"], f"DR kind {kind}, expected {plan['kind_value']} ({plan['kind_label']})")
    check(state == "draft", f"DR state {state}, expected draft")
    check(dr_type == plan["type"], f"DR type {dr_type}, expected {plan['type']}")
    if plan["bill_id"]:
        check(same_id(bill, plan["bill_id"]), f"DR bill {bill}, expected {plan['bill_id']}")
        check(invoice, "the DR has no customer invoice")
    else:
        check(same_number(amount, plan["amount"]), f"DR amount {amount}, expected {plan['amount']}")
    check(number(amount) and number(amount) > 0, f"DR amount {amount}")
    check(disb_date == plan["date_iso"], f"DR date {disb_date}, expected {plan['date_iso']}")
    check(same_id(source, plan["source_id"]), f"DR source {source}, expected {plan['source_id']}")
    st["ids"].update(disbursement=int(record), disbursement_name=name)
    _expect_value("source_id", plan["source_name"])
    _expect_value("kind", plan["kind_label"])
    if plan["bill_ref"]:
        _expect_value("bill_id", plan["bill_ref"])
    check(_stage_ui() == "DRAFT", f"statusbar shows {_stage_ui()!r}, expected DRAFT")
    shot = _shot(st, "disbursement-created")
    return [
        f"DB  DR {name} id={record} type={dr_type} kind={kind} state=draft created_from={created_from} amount={amount}"
        f" repayment={repay} date={disb_date} source={plan['source_name']}",
        f"SHOT {shot}",
        f"EXPECT breadcrumb {name}; statusbar current stage DRAFT; Type {plan['type_label']};"
        + (f" bill {plan['bill_ref']};" if plan["bill_ref"] else f" Disbursement Amount {plan['amount']};")
        + f" Disbursement Type {plan['kind_label']}; Payment Source {plan['source_name']}; no error dialog",
    ]


def step_dr_to_check(st):
    plan = st["plan"]
    open_target(st, DR)
    as_user(st, DR, plan["biz_ops"], plan["biz_ops_name"])
    check("action_to_check" in _buttons(), f"no TO CHECK button for {plan['biz_ops']}; buttons {form_state()['buttons']}")
    error = click_btn("action_to_check")
    state = target_state(st, DR)
    check(state in ("to_check", "to_review"), f"DR state {state}, expected to_check or to_review; dialog: {error or _dialog() or 'none'}")
    check(state == "to_review" or not plan.get("new_bank"), f"new_bank=1 but DR went to {state}, expected to_review")
    label = expect_state(st, DR, state)
    shot = _shot(st, "disbursement-to-check")
    return [
        f"DB  {st['ids']['disbursement_name']} state={state} (by {plan['biz_ops']})",
        f"SHOT {shot}",
        f"EXPECT {plan['biz_ops_name']} in the top bar; statusbar current stage {label}; no error dialog",
    ]


def step_dr_reviewed(st):
    plan = st["plan"]
    if target_state(st, DR) == "to_check":
        return ["DB  supplier bank already approved: no REVIEWED step needed"]
    open_target(st, DR)
    as_user(st, DR, plan["credit_ops"], plan["credit_ops_name"])
    check("action_to_reviewed" in _buttons(), f"no REVIEWED button for {plan['credit_ops']}; buttons {form_state()['buttons']}")
    error = click_btn("action_to_reviewed")
    label = expect_state(st, DR, "to_check", f"; dialog: {error or _dialog() or 'none'}")
    shot = _shot(st, "disbursement-reviewed")
    return [
        f"DB  {st['ids']['disbursement_name']} state=to_check after REVIEWED by {plan['credit_ops']}",
        f"SHOT {shot}",
        f"EXPECT {plan['credit_ops_name']} in the top bar; statusbar current stage {label}",
    ]


def step_dr_confirm(st):
    plan = st["plan"]
    open_target(st, DR)
    as_user(st, DR, plan["confirmer"], plan["confirmer_name"])
    check("action_confirm" in _buttons(), f"no CONFIRM button for {plan['confirmer']}; buttons {form_state()['buttons']}")
    error = click_btn("action_confirm")
    label = expect_state(st, DR, "confirmed", f"; dialog: {error or _dialog() or 'none'}")
    login, outstanding = one(
        st["db"],
        "select u.login, d.farmlink_outstanding from sale_disbursement d left join res_users u on u.id = d.confirm_uid"
        f" where d.id = {target_id(st, DR)}",
    )
    check(login == plan["confirmer"], f"confirm_uid is {login}, expected {plan['confirmer']}")
    shot = _shot(st, "disbursement-confirmed")
    return [
        f"DB  {st['ids']['disbursement_name']} state=confirmed confirm_uid={login} farmlink_outstanding={outstanding}",
        f"SHOT {shot}",
        f"EXPECT {plan['confirmer_name']} in the top bar; statusbar current stage {label}; no error dialog",
    ]


register(
    "disbursement",
    "Trade / Input disbursement request from the sale order smart button -> TO CHECK (customer Biz Ops) -> REVIEWED if"
    " the bank is new (Credit Ops) -> CONFIRM (ops) -> Confirmed",
    "[type=trade|input] [kind=<Old|New|Fast|Early|…>] [so=<sale order id>] [new_bank=1] (default: trade, Old, the"
    " newest posted vendor bill of a confirmed single-PO sale order with a paired invoice and no open DR; each run uses"
    " one bill; new_bank=1 resets the supplier bank to approval_state=new on the wt_* clone to drive the REVIEWED branch)",
    plan_disbursement,
    [
        ("dr_form", step_dr_form),
        ("dr_save", step_dr_save),
        ("dr_to_check", step_dr_to_check),
        ("dr_reviewed", step_dr_reviewed),
        ("dr_confirm", step_dr_confirm),
        ("finish", step_finish(DR, final="confirmed")),
    ],
)
