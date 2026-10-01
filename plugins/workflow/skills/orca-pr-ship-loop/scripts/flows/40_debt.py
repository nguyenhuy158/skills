# ruff: noqa: F821
"""Flow `debt`: sale order of type Factoring (Hợp đồng bán nợ) or Transfer (Hợp đồng chuyển nợ) -> save generates
the source lines and the agreement (type set by code) -> confirm -> TO REVIEW by the creditor's account manager ->
region manager, then the debt approval email list -> Approved, which creates the factoring / debt transfer DR.

Each run consumes the creditor's open debt (factoring: its approved/disbursed debt transfer DRs; transfer: its
open customer invoices), so a clone supports only as many runs as there are such creditors."""

import datetime as dt
import time

SO_ACTION = "sale.action_quotations_with_onboarding"
DEBT = {"key": "agreement", "model": "agreement", "action": "farmnet_debt.transfer_agreement_action", "label": "debt agreement"}
KINDS = {
    "factoring": {
        "label": "Factoring",
        "agreement_type": "Hợp đồng bán nợ",
        "disbursement": "factoring",
    },
    "transfer": {
        "label": "Transfer",
        "agreement_type": "Hợp đồng chuyển nợ",
        "disbursement": "debt_transfer",
    },
}


def plan_debt(db, params):
    kind = params.get("kind", "factoring")
    check(kind in KINDS, f"kind={kind} must be factoring or transfer")
    spec = KINDS[kind]
    company_id, company_name = fetch(db, "select id, name from res_company order by id limit 1", "a company")
    creditor = params.get("creditor")
    where = f"p.id = {int(creditor)}" if creditor else "true"
    creditor_id, creditor_name, am_login = fetch(
        db,
        "select p.id, p.name, u.login from debt_sale_customer v join res_partner p on p.id = v.customer_id"
        f" join res_users u on u.id = p.account_manager where {where} and v.company_id = {company_id}"
        " and p.is_company and p.active order by v.sellable_amount desc limit 1",
        "a creditor in the Debt Sale Customer view (farmnet_debt.debt_sale_customer: sellable pairs, no bill left"
        " to disburse) with an account manager",
    )
    customer = params.get("customer")
    customer_where = f"p.id = {int(customer)}" if customer else f"p.id <> {creditor_id}"
    customer_id, customer_name = fetch(
        db,
        f"select p.id, p.name from res_partner p where {customer_where} and p.is_company and p.active"
        " and exists (select 1 from res_partner c where c.parent_id = p.id and c.active)"
        f" order by (select count(*) from sale_order s where s.partner_id = p.id and s.type = '{kind}') desc, p.id desc limit 1",
        f"a customer company with a contact person for {kind}",
    )
    contact = partner_contact(db, customer_id)
    today = dt.date.today()
    return {
        "kind": kind,
        "kind_label": spec["label"],
        "agreement_type": spec["agreement_type"],
        "creditor_id": int(creditor_id),
        "creditor_name": creditor_name,
        "creditor_am": am_login,
        "customer_id": int(customer_id),
        "customer_name": customer_name,
        "contact_id": int(contact[0]),
        "contact_name": contact[1],
        "company_id": int(company_id),
        "company_name": company_name,
        "effective_date": ui_date(today),
    }


def _open_debt_tab():
    js("[...document.querySelectorAll('.o_form_view .o_notebook .nav-link')].find(e=>e.innerText.trim()==='Debt Transfer')?.click()")
    for _ in range(20):
        if js("!!document.querySelector('.o_form_view div[name=partner_representative_id]')"):
            return
        time.sleep(0.25)
    raise StepFailed("the Debt Transfer tab did not open")


def step_debt_header(st):
    plan = st["plan"]
    login_admin(st)
    odoo_open(st["base"], SO_ACTION)
    check(form_state()["id"] is None, "expected an empty new quotation form")
    fill_select("type", plan["kind_label"])
    fill_m2o("creditor_id", plan["creditor_name"])
    fill_m2o("company_id", plan["company_name"])
    fill("contract_effective_date", plan["effective_date"])
    _expect_value("type", plan["kind_label"])
    _expect_value("creditor_id", plan["creditor_name"])
    _expect_value("company_id", plan["company_name"])
    _expect_value("contract_effective_date", plan["effective_date"])
    return [f"UI  new quotation: type {plan['kind_label']}, creditor, company, effective date set (not saved yet)"]


def step_debt_customer(st):
    plan = st["plan"]
    check(
        form_state()["id"] is None and plan["creditor_name"].lower() in _value("creditor_id").lower(),
        "the unsaved quotation from debt_header is no longer on screen",
    )
    _open_debt_tab()
    kind = js("((document.querySelector('.o_form_view div[name=recipient_kind] input:checked')||{}).closest?.('.o_radio_item')||{}).innerText||''")
    check("company" in (kind or "").lower(), f"recipient kind is {kind!r}, expected Company")
    fill_m2o("partner_id", plan["customer_name"])
    fill_m2o("partner_representative_id", plan["contact_name"])
    _expect_value("partner_id", plan["customer_name"])
    _expect_value("partner_representative_id", plan["contact_name"])
    term = _value("payment_term_id")
    check(term, "no payment term after picking the customer")
    return [f"UI  recipient Company: {plan['customer_name']} · representative {plan['contact_name']} · payment term {term}"]


def step_debt_save(st):
    db, plan = st["db"], st["plan"]
    spec = KINDS[plan["kind"]]
    error = save()
    so_id = form_state()["id"]
    check(so_id, f"no record id after save; dialog: {error or _dialog() or 'none'}")
    name, state, so_type, creditor, partner, representative, agreement = one(
        db,
        "select name, state, type, creditor_id, partner_id, partner_representative_id, agreement_id"
        f" from sale_order where id = {so_id}",
    )
    check(state == "draft", f"sale order state {state}, expected draft")
    check(so_type == plan["kind"], f"sale order type {so_type}, expected {plan['kind']}")
    check(same_id(creditor, plan["creditor_id"]), f"creditor {creditor}, expected {plan['creditor_id']}")
    check(same_id(partner, plan["customer_id"]), f"customer {partner}, expected {plan['customer_id']}")
    check(same_id(representative, plan["contact_id"]), f"representative {representative or 'NULL'}, expected {plan['contact_id']}")
    check(agreement, "the sale order has no agreement after saving")
    agreement_name, stage, type_name, contact = one(
        db,
        "select a.name, a.stage, t.name, a.partner_contact_id from agreement a left join agreement_type t"
        f" on t.id = a.agreement_type_id where a.id = {agreement}",
    )
    check(type_name == spec["agreement_type"], f"agreement type {type_name or 'NULL'}, expected {spec['agreement_type']}")
    check(stage == "new", f"agreement stage {stage}, expected new")
    check(contact, "the agreement has no representative (partner contact)")
    (sources,) = one(
        db,
        f"select (select count(*) from sale_invoice_transfer_line where parent_id = {so_id})"
        f" + (select count(*) from sale_disbursement_factoring_line where parent_id = {so_id})",
    )
    check(int(sources) > 0, f"no source line (invoice pair or disbursement) was generated for {name}")
    (order_lines,) = one(db, f"select count(*) from sale_order_line where order_id = {so_id} and display_type is null")
    check(int(order_lines) >= 1, f"no order line was generated for {name}")
    st["ids"].update(so=int(so_id), so_name=name, agreement=int(agreement), agreement_name=agreement_name)
    _open_debt_tab()
    shot = _shot(st, "debt-so-saved", ".o_form_view .o_notebook", must_show=(name, plan["customer_name"], plan["contact_name"]))
    return [
        f"DB  sale_order {so_id} {name} type={so_type} state=draft · {sources} source line(s) · agreement {agreement_name}"
        f" id={agreement} type={type_name} stage=new",
        f"SHOT {shot}",
        f"EXPECT breadcrumb {name}; Debt Transfer tab: Customer {plan['customer_name']}, Customer Representative"
        f" {plan['contact_name']}, at least one source line; no error dialog",
    ]


def step_debt_confirm(st):
    db, ids = st["db"], st["ids"]
    odoo_open(st["base"], SO_ACTION, ids["so"], model="sale.order")
    check("action_confirm" in _buttons(), f"no CONFIRM button; buttons {form_state()['buttons']}")
    error = click_btn("action_confirm")
    (so_state,) = one(db, f"select state from sale_order where id = {ids['so']}")
    check(so_state == "sale", f"sale order state {so_state}, expected sale; dialog: {error or _dialog() or 'none'}")
    stage = target_state(st, DEBT)
    check(stage == "draft", f"agreement stage {stage}, expected draft (To Check)")
    check(_stage_ui() == "SALES ORDER", f"statusbar shows {_stage_ui()!r}, expected SALES ORDER")
    shot = _shot(st, "debt-so-confirmed")
    return [
        f"DB  {ids['so_name']} state=sale · {ids['agreement_name']} stage=draft",
        f"SHOT {shot}",
        f"EXPECT {ids['so_name']}: statusbar current stage SALES ORDER; no error dialog",
    ]


def actor_creditor_am(st):
    return fetch(
        st["db"],
        "select u.login, up.name from sale_order so join res_partner cr on cr.id = so.creditor_id"
        " join res_users u on u.id = cr.account_manager join res_partner up on up.id = u.partner_id"
        f" where so.id = {st['ids']['so']}",
        "the creditor's account manager",
    )


def _disbursement(st):
    spec = KINDS[st["plan"]["kind"]]
    row = one(
        st["db"],
        f"select id, name, state from sale_disbursement where sale_id = {st['ids']['so']} and type = '{spec['disbursement']}'"
        " order by id desc limit 1",
    )
    check(row, f"no {spec['disbursement']} disbursement was created for {st['ids']['so_name']}")
    check(row[2] == "confirmed", f"disbursement {row[1]} state {row[2]}, expected confirmed")
    return [f"DB  disbursement {row[1]} id={row[0]} type={spec['disbursement']} state={row[2]}"]


register(
    "debt",
    "sale order of type Factoring (Hợp đồng bán nợ) or Transfer (Hợp đồng chuyển nợ) -> confirm -> agreement approved"
    " -> factoring / debt transfer disbursement created",
    "[kind=factoring|transfer] [creditor=<id>] [customer=<id>] (default: a creditor with open debt for that kind and the"
    " customer company most used on such orders; each run consumes the creditor's open debt)",
    plan_debt,
    [
        ("debt_header", step_debt_header),
        ("debt_customer", step_debt_customer),
        ("debt_save", step_debt_save),
        ("debt_confirm", step_debt_confirm),
        ("to_check", step_show_state(DEBT, "draft", "debt-agreement-to-check")),
        ("to_review", step_to_review(DEBT, "action_account_manager_to_review", actor_creditor_am)),
        ("approve", step_approve("approve", DEBT)),
        ("finish", step_finish(DEBT, chatter="The agreement has been approved", extra=_disbursement)),
    ],
)
