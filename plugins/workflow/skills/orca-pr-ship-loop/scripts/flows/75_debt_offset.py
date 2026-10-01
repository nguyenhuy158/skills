# ruff: noqa: F821
"""Flow `debt_offset`: Debt Offset disbursement (bù trừ công nợ) created from the Disbursements menu for a customer and a
vendor that have unpaid bill/invoice pairs -> save generates one offset line per pair -> TO CHECK by the customer's
Operations Manager (fin_ops) -> CONFIRM by the user who confirmed most debt offsets (prod: minh@) -> Confirmed.
Matches prod: of 110 debt offsets, TO CHECK came from OM / Senior BO, CONFIRM from minh@ (88) and never via REVIEWED.

Each run offsets the open pairs of one customer/vendor couple (paired bills already in an active offset are skipped)."""

import datetime as dt

MENU_ACTION = "farmnet_sale_order.action_view_accountant_disbursements"
DO_CONFIRMER = CONFIRMER.replace(
    " order by u.id limit 1",
    " order by (select count(*) from mail_tracking_value v join mail_message m on m.id = v.mail_message_id"
    " join sale_disbursement d on d.id = m.res_id and m.model = 'sale.disbursement' and d.type = 'debt_offset'"
    " where v.create_uid = u.id and v.new_value_char = 'Confirmed') desc, u.id limit 1",
)
OPEN_PAIR = (
    "from sale_order so join purchase_order po on po.sale_id = so.id"
    " join account_move bill on bill.purchase_id = po.id and bill.move_type = 'in_invoice' and bill.state = 'posted'"
    " join account_move inv on inv.stock_picking_id = bill.stock_picking_id and inv.move_type = 'out_invoice'"
    " and inv.state = 'posted' where so.state = 'sale' and so.type = 'sale'"
    " and coalesce(inv.total_outstanding_amount, 0) + coalesce(inv.total_remaining_repayment_amount, 0) > 0"
    " and coalesce(bill.total_remaining_disbursement_amount, 0) > 0"
    " and not exists (select 1 from sale_disbursement_invoice_line l join sale_disbursement d on d.id = l.disbursement_id"
    " where l.bill_id = bill.id and d.state not in ('cancel', 'refused'))"
    " and not exists (select 1 from sale_disbursement d where d.bill_id = bill.id"
    " and d.state not in ('disbursed', 'paid', 'cancel', 'refused'))"
    " and not exists (select 1 from sale_disbursement d where d.sale_id = so.id"
    " and d.type in ('customer_advance', 'vendor_advance') and d.state in ('draft', 'to_review', 'to_check', 'confirmed', 'approve'))"
)


def plan_debt_offset(db, params):
    customer, vendor = params.get("customer"), params.get("vendor")
    where = f"so.partner_id = {int(customer)} and po.partner_id = {int(vendor)}" if customer and vendor else "true"
    customer_id, vendor_id, pairs, company = fetch(
        db,
        f"select so.partner_id, po.partner_id, count(*), min(so.company_id) {OPEN_PAIR} and {where}"
        " and exists (select 1 from res_partner c where c.id = so.partner_id and c.is_company and c.fin_ops is not null"
        " and not coalesce(c.is_suspended_cooperation, false))"
        " and exists (select 1 from res_partner r where r.parent_id = so.partner_id and r.active)"
        " and exists (select 1 from res_partner r where r.parent_id = po.partner_id and r.active)"
        " and exists (select 1 from res_partner_bank b where b.partner_id = so.partner_id and b.allow_out_payment)"
        " and not exists (select 1 from sale_order so2 join purchase_order po2 on po2.sale_id = so2.id"
        " join account_move b2 on b2.purchase_id = po2.id and b2.move_type = 'in_invoice' and b2.state = 'posted'"
        " join sale_disbursement d2 on d2.bill_id = b2.id and d2.state not in ('disbursed', 'paid', 'cancel', 'refused')"
        " and d2.type not in ('debt_offset', 'debt_transfer', 'factoring')"
        " where so2.partner_id = so.partner_id and po2.partner_id = po.partner_id)"
        " group by 1, 2 having count(distinct so.company_id) = 1 order by 3 desc, 1 desc limit 1",
        "a customer/vendor couple with unpaid bill-invoice pairs whose bill still has money to disburse",
    )
    cust, om, om_name = fetch(
        db,
        "select c.name, om.login, omp.name from res_partner c"
        f" join res_users om on om.id = c.fin_ops join res_partner omp on omp.id = om.partner_id where c.id = {customer_id}",
        f"Operations Manager (fin_ops) of customer {customer_id}",
    )
    (vend,) = fetch(db, f"select name from res_partner where id = {vendor_id}", f"vendor {vendor_id}")
    (company_name,) = fetch(db, f"select name from res_company where id = {company}", f"company {company}")
    (sign,) = fetch(
        db,
        "select sp.name from sale_disbursement d join res_users su on su.id = d.sign_person join res_partner sp"
        " on sp.id = su.partner_id where d.type = 'debt_offset' and sp.is_sign order by d.id desc limit 1",
        "a sign person used on debt offsets",
    )
    cust_rep = partner_contact(db, customer_id)[1]
    vend_rep = partner_contact(db, vendor_id)[1]
    confirmer, confirmer_name = fetch(db, DO_CONFIRMER, "a user with the disbursement approve right")
    bank_id, bank_acc = partner_bank(db, customer_id)
    company = company_name
    vendor_bank = one(
        db,
        "select b.acc_number from res_partner_bank b where b.partner_id = {0} and b.allow_out_payment"
        " and b.approval_state = 'approved' order by (select count(*) from sale_disbursement d where d.supplier_bank_id = b.id)"
        " desc, b.id desc limit 1".format(int(vendor_id)),
    )
    vendor_bank_acc = vendor_bank[0] if vendor_bank else None
    return {
        "customer_id": int(customer_id),
        "customer_name": cust,
        "customer_rep": cust_rep,
        "customer_bank_id": int(bank_id),
        "customer_bank_acc": bank_acc,
        "vendor_id": int(vendor_id),
        "vendor_name": vend,
        "vendor_rep": vend_rep,
        "vendor_bank_acc": vendor_bank_acc,
        "sign_person_name": sign,
        "company_name": company,
        "open_pairs": int(pairs),
        "biz_ops": om,
        "biz_ops_name": om_name,
        "confirmer": confirmer,
        "confirmer_name": confirmer_name,
        "date": ui_date(dt.date.today()),
        "date_iso": dt.date.today().isoformat(),
    }


def step_do_customer(st):
    plan = st["plan"]
    login_admin(st)
    odoo_open(st["base"], MENU_ACTION)
    check(form_state()["id"] is None, "expected an empty new disbursement form")
    fill_select("type", "Debt Offset")
    fill_m2o("customer_id", plan["customer_name"])
    fill_m2o("customer_representative_id", plan["customer_rep"])
    fill_m2o("customer_bank_id", plan["customer_bank_acc"])
    _expect_value("customer_id", plan["customer_name"])
    _expect_value("customer_bank_id", plan["customer_bank_acc"])
    return [f"UI  new Debt Offset: customer {plan['customer_name']}, representative, bank set (not saved yet)"]


def step_do_vendor(st):
    plan = st["plan"]
    check(form_state()["id"] is None and plan["customer_name"].lower() in _value("customer_id").lower(),
          "the unsaved debt offset from do_customer is no longer on screen")
    fill_m2o("supplier_id", plan["vendor_name"])
    fill_m2o("vendor_representative_id", plan["vendor_rep"])
    fill_m2o("company_id", plan["company_name"])
    if plan.get("vendor_bank_acc"):
        fill_m2o("supplier_bank_id", plan["vendor_bank_acc"])
        _expect_value("supplier_bank_id", plan["vendor_bank_acc"])
    _expect_value("supplier_id", plan["vendor_name"])
    return [f"UI  vendor {plan['vendor_name']}, representative, company{', bank ' + plan['vendor_bank_acc'] if plan.get('vendor_bank_acc') else ''} set (not saved yet)"]


def step_do_save(st):
    db, plan = st["db"], st["plan"]
    check(form_state()["id"] is None and plan["vendor_name"].lower() in _value("supplier_id").lower(),
          "the unsaved debt offset from do_vendor is no longer on screen")
    fill_m2o("sign_person", plan["sign_person_name"])
    fill("disbursement_date", plan["date"])
    error = save()
    record = form_state()["id"]
    check(record, f"no DR id after save; dialog: {error or _dialog() or 'none'}")
    name, state, dr_type, customer, vendor, repay, disb_date = one(
        db,
        "select name, state, type, customer_id, supplier_id, repayment_amount, disbursement_date"
        f" from sale_disbursement where id = {record}",
    )
    check(state == "draft" and dr_type == "debt_offset", f"DR state {state} type {dr_type}, expected draft debt_offset")
    check(same_id(customer, plan["customer_id"]) and same_id(vendor, plan["vendor_id"]), f"DR parties {customer}/{vendor}")
    check(disb_date == plan["date_iso"], f"DR date {disb_date}, expected {plan['date_iso']}")
    (lines, total) = one(
        db,
        f"select count(*), coalesce(sum(debt_offset_amount), 0) from sale_disbursement_invoice_line where disbursement_id = {record}",
    )
    check(int(lines) > 0, "no offset line was generated")
    check(same_number(total, repay) and number(repay) > 0, f"repayment {repay} is not the sum of the lines {total}")
    ui_rows = js("[...document.querySelectorAll('.o_form_view div[name=disbursement_invoice_line_ids] .o_data_row')].length")
    check(ui_rows == int(lines), f"form shows {ui_rows} offset lines, DB has {lines}")
    st["ids"].update(disbursement=int(record), disbursement_name=name)
    shot = _shot(st, "debt-offset-created", ".o_form_view div[name=disbursement_invoice_line_ids]", must_show=(name,))
    return [
        f"DB  DR {name} id={record} type=debt_offset state=draft · {lines} offset line(s) · repayment={repay}",
        f"SHOT {shot}",
        f"EXPECT breadcrumb {name}; the invoice lines table shows {lines} bill/invoice row(s); no error dialog",
    ]


register(
    "debt_offset",
    "Debt Offset DR from the Disbursements menu -> offset lines generated on save -> TO CHECK (customer OM, fin_ops)"
    " -> CONFIRM (the usual debt offset confirmer) -> Confirmed",
    "[customer=<id> vendor=<id>] (default: the couple with the most unpaid bill-invoice pairs; representatives, sign"
    " person and company are copied from the latest debt offset; the vendor's approved bank is set when it has one)",
    plan_debt_offset,
    [
        ("do_customer", step_do_customer),
        ("do_vendor", step_do_vendor),
        ("do_save", step_do_save),
        ("dr_to_check", step_dr_to_check),
        ("dr_confirm", step_dr_confirm),
        ("finish", step_finish(DR, final="confirmed")),
    ],
)
