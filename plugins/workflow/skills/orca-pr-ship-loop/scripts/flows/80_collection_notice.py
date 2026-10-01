# ruff: noqa: F821
"""Flow `collection_notice`: Yêu cầu thanh toán công nợ quá hạn (round 1) for a customer with overdue disbursed DRs:
the customer's Biz Ops creates it and clicks TO CHECK (the overdue DR lines are pulled in) -> signed PDF uploaded ->
document TO CHECK (Biz Ops) -> APPROVE (Credit Ops) -> DONE (Credit Ops) -> Done.
Actors match prod: TO CHECK and document lock by the customer's Biz Ops, DONE and document approval by Credit Ops.

Each run creates one notice for a customer without an open (draft / to check) notice."""

CN = {
    "key": "collection_notice",
    "model": "collection.notice",
    "action": "farmnet_collection_notice.collection_notice_action",
    "label": "collection notice",
    "doc": {"field": "signed_attachment_ids", "rel": "collection_notice_signed_attachment_rel", "col": "collection_notice_id"},
}
OVERDUE_DR = "d.state = 'disbursed' and d.farmlink_outstanding > 0 and d.due_date < current_date"


ROUNDS = {"1": "1st", "2": "2nd", "3": "3rd"}
NOTICE_KINDS = {"collection": ("collection_notice", 3), "obligation": ("obligation_notice", 2), "settlement": ("settlement_notice", 1)}
GUARANTOR = (
    "(select min(gu.name) from res_partner_guarantor g join res_guarantor gu on gu.id = g.guarantor_id"
    " where g.partner_id = c.id)"
)


def plan_collection_notice(db, params):
    customer = params.get("customer")
    kind = params.get("kind", "collection")
    check(kind in NOTICE_KINDS, f"kind={kind} must be one of {', '.join(NOTICE_KINDS)}")
    ntype, max_round = NOTICE_KINDS[kind]
    rnd = params.get("round", "1")
    check(rnd in ROUNDS and int(rnd) <= max_round, f"round={rnd}: {kind} notices have rounds 1..{max_round}")
    where = f"c.id = {int(customer)}" if customer else "true"
    if kind == "obligation":
        where += f" and {GUARANTOR} is not null"
    prev = {"2": "1st", "3": "2nd"}.get(rnd)
    prev_notice = (
        "(select max(n.id) from collection_notice n join collection_notice_template t on t.id = n.template_id"
        f" where n.customer_id = c.id and n.state = 'done' and t.type = '{ntype}' and t.domain = '{prev}')"
    )
    if prev:
        where += f" and {prev_notice} is not null"
    parent_col = f"max(({prev_notice}))" if prev else "0"
    order = "order by 10 desc nulls last, count(*) desc limit 1" if prev else "order by count(*) desc, c.id desc limit 1"
    row = fetch(
        db,
        f"select c.id, c.name, d.company_id, co.name, count(*), bo.login, bop.name, bo2.login, bo2p.name, {parent_col}"
        " from sale_disbursement d join res_partner c on c.id = d.customer_id join res_company co on co.id = d.company_id"
        " join res_users bo on bo.id = c.biz_ops join res_partner bop on bop.id = bo.partner_id"
        " join res_users bo2 on bo2.id = c.biz_ops_2 join res_partner bo2p on bo2p.id = bo2.partner_id"
        f" where {where} and {OVERDUE_DR} and bo.active and bo2.active"
        f" and {in_group('bo', 'farmnet_collection_notice', 'group_collection_notice_bo')}"
        f" and {in_group('bo2', 'farmnet_collection_notice', 'group_collection_notice_co')}"
        " and exists (select 1 from res_partner r where r.parent_id = c.id and r.active)"
        " and not exists (select 1 from collection_notice n where n.customer_id = c.id and n.state in ('draft', 'to_check'))"
        f" group by c.id, c.name, d.company_id, co.name, bo.login, bop.name, bo2.login, bo2p.name {order}",
        "a customer with overdue disbursed DRs, a contact, Biz Ops / Credit Ops holding the collection notice rights"
        " and no open collection notice" + (f", plus a Done round-{int(rnd) - 1} {kind} notice" if prev else "")
        + (", plus a guarantor" if kind == "obligation" else ""),
    )
    cust_id, cust, company_id, company, overdue, bo, bo_name, bo2, bo2_name, parent_id = row
    guarantor = one(db, f"select {GUARANTOR} from res_partner c where c.id = {int(cust_id)}")[0] if kind == "obligation" else None
    parent_name, parent_label = (
        one(
            db,
            "select n.name, '[' || t.name || '] ' || to_char(n.effective_date, 'DD/MM/YYYY') from collection_notice n"
            f" join collection_notice_template t on t.id = n.template_id where n.id = {int(parent_id)}",
        )
        if prev
        else (None, None)
    )
    template, template_name = fetch(
        db,
        f"select id, name from collection_notice_template where active and type = '{ntype}'"
        f" and domain = '{ROUNDS[rnd]}' order by sequence, id limit 1",
        f"an active round-{rnd} {kind} notice template",
    )
    (signer,) = fetch(
        db,
        "select sp.name from collection_notice n join res_users su on su.id = n.signer_id join res_partner sp"
        " on sp.id = su.partner_id where sp.is_sign group by sp.name order by count(*) desc limit 1",
        "a signer used on collection notices",
    )
    return {
        "customer_id": int(cust_id),
        "customer_name": cust,
        "contact_name": partner_contact(db, cust_id)[1],
        "company_name": company,
        "overdue_drs": int(overdue),
        "template_name": template_name,
        "round": rnd,
        "kind": kind,
        "notice_type": ntype,
        "guarantor_name": guarantor,
        "parent_id": int(parent_id) if prev else None,
        "parent_name": parent_name,
        "parent_label": parent_label,
        "signer_name": signer,
        "biz_ops": bo,
        "biz_ops_name": bo_name,
        "credit_ops": bo2,
        "credit_ops_name": bo2_name,
    }


def step_cn_header(st):
    plan = st["plan"]
    login_admin(st)
    odoo_open(st["base"], CN["action"], None, model=CN["model"])
    switch_user(plan["biz_ops"])
    check(plan["biz_ops_name"].lower() in _user().lower(), f"top bar shows {_user()!r}, expected {plan['biz_ops_name']}")
    wait_view("form", "the new collection notice form did not open")
    fill_m2o("customer_id", plan["customer_name"])
    fill_m2o("contact_person_id", plan["contact_name"])
    fill_m2o("company_id", plan["company_name"])
    fill_m2o("template_id", plan["template_name"])
    _expect_value("customer_id", plan["customer_name"])
    return [f"UI  new {plan['kind']} notice: customer {plan['customer_name']}, contact, company, template set by"
            f" {plan['biz_ops']} (not saved yet)"]


def step_cn_create(st):
    plan = st["plan"]
    check(form_state()["id"] is None and plan["customer_name"].lower() in _value("customer_id").lower(),
          "the unsaved collection notice from cn_header is no longer on screen")
    if plan.get("guarantor_name"):
        fill_m2o("partner_guarantor_id", plan["guarantor_name"])
    fill_m2o("signer_id", plan["signer_name"])
    if plan.get("parent_name"):
        fill_m2o("parent_id", plan["parent_name"], pick=plan["parent_label"])
        _expect_value("parent_id", plan["parent_label"])
    error = save()
    record = form_state()["id"]
    check(record, f"no collection notice id after save; dialog: {error or _dialog() or 'none'}")
    name, state, customer, am, parent, ntype, guarantee = one(
        st["db"],
        "select name, state, customer_id, coalesce(am_id::text, '-'), coalesce(parent_id::text, '-'), type,"
        f" coalesce(partner_guarantor_id::text, '-') from collection_notice where id = {record}",
    )
    check(state == "draft" and same_id(customer, plan["customer_id"]), f"notice state {state}, customer {customer}")
    check(ntype == plan["notice_type"], f"notice type {ntype}, expected {plan['notice_type']}")
    check(not plan.get("guarantor_name") or guarantee != "-", "no guarantee saved on the obligation notice")
    check(not plan.get("parent_id") or same_id(parent, plan["parent_id"]), f"parent {parent}, expected {plan.get('parent_id')}")
    st["ids"].update(collection_notice=int(record), collection_notice_name=name)
    _expect_value("customer_id", plan["customer_name"])
    check(_stage_ui() == "DRAFT", f"statusbar shows {_stage_ui()!r}, expected DRAFT")
    shot = _shot(st, "collection-notice-created")
    return [
        f"DB  collection notice {name} (round {plan['round']}) id={record} state=draft customer={plan['customer_name']}"
        f" am_id={am} parent={plan.get('parent_name') or '-'} (created by {plan['biz_ops']})",
        f"SHOT {shot}",
        f"EXPECT breadcrumb {name}; statusbar current stage DRAFT; Customer {plan['customer_name']};"
        f" {plan['biz_ops_name']} in the top bar; no error dialog",
    ]


def step_cn_to_check(st):
    plan = st["plan"]
    lines = step_state_button(CN, "action_to_check", plan_actor("biz_ops"), "to_check")(st)
    (count,) = one(st["db"], f"select count(*) from collection_notice_line where collection_id = {target_id(st, CN)}")
    check(int(count) > 0, "TO CHECK pulled in no overdue DR line")
    ui_rows = js("[...document.querySelectorAll('.o_form_view div[name=line_ids] .o_data_row')].length")
    check(ui_rows == int(count), f"form shows {ui_rows} DR lines, DB has {count}")
    return [f"DB  {count} overdue DR line(s) pulled in (customer has {plan['overdue_drs']} overdue disbursed DRs)", *lines]


register(
    "collection_notice",
    "Collection notices (quá hạn round 1-3, nghĩa vụ bảo lãnh round 1-2, tất toán) created by the customer's Biz Ops"
    " (round 2/3 point at the customer's Done notice of the round before) -> TO CHECK (overdue DR lines) -> signed PDF"
    " -> document TO CHECK (Biz Ops) -> APPROVE (Credit Ops) -> DONE (Credit Ops)",
    "[kind=collection|obligation|settlement] [round=1|2|3] [customer=<id>] (collection: rounds 1-3; obligation"
    " (customer needs a guarantor, picked by guarantor name): rounds 1-2; settlement: round 1. Default round 1: the"
    " customer with the most overdue disbursed DRs; round 2/3: the customer with the newest Done notice of the same"
    " kind and round before, so rounds in a row stay on one customer; always Biz Ops / Credit Ops with the collection"
    " notice rights and no open notice; each run leaves one Done notice)",
    plan_collection_notice,
    [
        ("cn_header", step_cn_header),
        ("cn_create", step_cn_create),
        ("cn_to_check", step_cn_to_check),
        ("cn_upload", step_doc_upload(CN)),
        ("cn_lock", step_doc_action(CN, "action_lock_signed_attachment", plan_actor("biz_ops"), "pending", "PENDING")),
        ("cn_approve", step_doc_action(CN, "action_approve_signed_attachment", plan_actor("credit_ops"), "completed", "COMPLETED")),
        ("cn_done", step_state_button(CN, "action_done", plan_actor("credit_ops"), "done")),
        ("finish", step_finish(CN, final="done")),
    ],
)
