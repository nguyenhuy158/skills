# ruff: noqa: F821
"""Flow `so`: sale order with a vendor line -> confirm -> sale agreement approved; the paired purchase agreement
follows it (approvals cascade from the sale agreement, it can never be approved on its own form)."""

import datetime as dt

SO_ACTION = "sale.action_quotations_with_onboarding"
SALE = {"key": "sale_agreement", "model": "agreement", "action": "agreement.agreement_action", "label": "sale agreement"}
PURCHASE = {
    "key": "purchase_agreement",
    "model": "agreement",
    "action": "agreement.agreement_action",
    "label": "purchase agreement",
}


def _framework(db, partner, company, domain, required):
    row = one(
        db,
        f"select id, name from agreement where is_template and partner_id = {partner} and company_id = {company}"
        f" and domain = '{domain}' and stage in ('reviewed', 'active') order by id desc limit 1",
    )
    check(row or not required, f"partner {partner} has no approved framework agreement ({domain})")
    return row


def plan_so(db, params):
    customer, vendor, product = int(params["customer"]), int(params["vendor"]), int(params["product"])
    sale_type = params.get("sale_type", "Đơn hàng bán")
    purchase_type = params.get("purchase_type", "Đơn hàng mua")
    customer_name, biz_ops_login, biz_ops_name = fetch(
        db,
        "select p.name, u.login, bp.name from res_partner p join res_users u on u.id = p.biz_ops_2"
        f" join res_partner bp on bp.id = u.partner_id where p.id = {customer}",
        f"customer {customer} with a Credit Ops (biz_ops_2) user",
    )
    (vendor_name,) = fetch(db, f"select name from res_partner where id = {vendor}", f"vendor {vendor}")
    (product_name,) = fetch(
        db,
        "select coalesce(t.name->>'en_US', t.name->>'vi_VN') from product_product p"
        f" join product_template t on t.id = p.product_tmpl_id where p.id = {product}",
        f"product {product}",
    )
    header = one(
        db,
        "select s.company_id, c.name, s.payment_term_id, coalesce(t.name->>'en_US', t.name->>'vi_VN'), s.order_profit,"
        " s.sign_person, sp.name, s.partner_representative_id, r.name"
        " from sale_order s join res_company c on c.id = s.company_id"
        " join account_payment_term t on t.id = s.payment_term_id"
        " join res_users su on su.id = s.sign_person join res_partner sp on sp.id = su.partner_id"
        " left join res_partner r on r.id = s.partner_representative_id"
        f" where s.partner_id = {customer} and s.state = 'sale' and s.type = 'sale' order by s.id desc limit 1",
    )
    check(header, f"cannot find a confirmed sale order of customer {customer} with payment term and sign person")
    company_id, company_name, term_id, term_name, profit, sign_id, sign_name, rep_id, rep_name = header
    sale_type_id, purchase_type_id = type_id(db, sale_type), type_id(db, purchase_type)
    (sale_needs_fw,) = one(db, f"select coalesce(framework_agreement_required, false) from agreement_type where id = {sale_type_id}")
    (purchase_needs_fw,) = one(db, f"select coalesce(framework_agreement_required, false) from agreement_type where id = {purchase_type_id}")
    cust_bank = partner_bank(db, customer)
    vendor_bank = partner_bank(db, vendor)
    vendor_contact = partner_contact(db, vendor)
    cust_contact = (rep_id, rep_name) if rep_id else partner_contact(db, customer)
    cust_fw = _framework(db, customer, company_id, "sale", sale_needs_fw == "t")
    vendor_fw = _framework(db, vendor, company_id, "purchase", purchase_needs_fw == "t")
    today = dt.date.today()
    return {
        "customer_id": customer,
        "customer_name": customer_name,
        "biz_ops_login": biz_ops_login,
        "biz_ops_name": biz_ops_name,
        "vendor_id": vendor,
        "vendor_name": vendor_name,
        "product_id": product,
        "product_name": product_name,
        "qty": params["qty"],
        "price": params["price"],
        "company_id": int(company_id),
        "company_name": company_name,
        "payment_term_id": int(term_id),
        "payment_term": term_name,
        "order_profit": profit,
        "sign_person_id": int(sign_id),
        "sign_person_name": sign_name,
        "rep_id": int(rep_id) if rep_id else None,
        "rep_name": rep_name or None,
        "sale_type": sale_type,
        "sale_type_id": sale_type_id,
        "purchase_type": purchase_type,
        "purchase_type_id": purchase_type_id,
        "cust_bank_id": int(cust_bank[0]),
        "cust_bank_acc": cust_bank[1],
        "cust_framework_id": int(cust_fw[0]) if cust_fw else None,
        "cust_framework_name": cust_fw[1] if cust_fw else None,
        "cust_contact_id": int(cust_contact[0]),
        "cust_contact_name": cust_contact[1],
        "vendor_contact_id": int(vendor_contact[0]),
        "vendor_contact_name": vendor_contact[1],
        "vendor_bank_id": int(vendor_bank[0]),
        "vendor_bank_acc": vendor_bank[1],
        "vendor_framework_id": int(vendor_fw[0]) if vendor_fw else None,
        "vendor_framework_name": vendor_fw[1] if vendor_fw else None,
        "date_effective": ui_date(today),
        "date_commitment": ui_date(today + dt.timedelta(days=7)),
        "date_expiration": f"31/12/{today.year}",
        "expiration_iso": f"{today.year}-12-31",
    }


def _editing_row():
    return js(
        "(()=>{const r=document.querySelector('.o_form_view div[name=order_line] .o_selected_row'); if(!r) return null;"
        " return Object.fromEntries([...r.querySelectorAll('td[name]')].map(td=>[td.getAttribute('name'),"
        " (td.querySelector('input') ? td.querySelector('input').value : td.innerText).trim()]));})()"
    )


def step_so_header(st):
    plan = st["plan"]
    login_admin(st)
    odoo_open(st["base"], SO_ACTION)
    check(form_state()["id"] is None, "expected an empty new quotation form")
    fill_m2o("partner_id", plan["customer_name"])
    fill_m2o("company_id", plan["company_name"])
    fill_m2o("payment_term_id", plan["payment_term"])
    _expect_value("partner_id", plan["customer_name"])
    _expect_value("company_id", plan["company_name"])
    _expect_value("payment_term_id", plan["payment_term"])
    return ["UI  new quotation: customer, company, payment term set (not saved yet)"]


def step_so_details(st):
    plan = st["plan"]
    check(
        form_state()["id"] is None and plan["customer_name"].lower() in _value("partner_id").lower(),
        "the unsaved quotation from so_header is no longer on screen",
    )
    fill("contract_effective_date", plan["date_effective"])
    fill("commitment_date", plan["date_commitment"])
    fill("order_profit", plan["order_profit"])
    fill_m2o("sign_person", plan["sign_person_name"])
    if plan["rep_name"]:
        fill_m2o("partner_representative_id", plan["rep_name"])
    _expect_value("contract_effective_date", plan["date_effective"])
    _expect_value("commitment_date", plan["date_commitment"])
    _expect_value("sign_person", plan["sign_person_name"])
    if plan["rep_name"]:
        _expect_value("partner_representative_id", plan["rep_name"])
    check(same_number(_value("order_profit"), plan["order_profit"]), f"order_profit shows {_value('order_profit')!r}")
    return ["UI  dates, order profit, sign person, representative set (not saved yet)"]


def step_so_line(st):
    plan = st["plan"]
    check(form_state()["id"] is None, "the unsaved quotation is no longer on screen")
    line_add("order_line")
    line_fill("product_template_id", plan["product_name"], m2o=True)
    line_fill("vendor_id", plan["vendor_name"], m2o=True)
    line_fill("product_uom_qty", plan["qty"])
    line_fill("purchase_price", plan["price"])
    row = _editing_row()
    check(row, "no order line in edition after filling it")
    check(plan["product_name"].lower() in row.get("product_template_id", "").lower(), f"line product shows {row.get('product_template_id')!r}")
    check(plan["vendor_name"].lower() in row.get("vendor_id", "").lower(), f"line vendor shows {row.get('vendor_id')!r}")
    check(same_number(row.get("product_uom_qty"), plan["qty"]), f"line quantity shows {row.get('product_uom_qty')!r}")
    check(same_number(row.get("purchase_price"), plan["price"]), f"line purchase price shows {row.get('purchase_price')!r}")
    return [
        f"UI  line: {row.get('product_template_id')} · vendor {row.get('vendor_id')} · qty {row.get('product_uom_qty')}"
        f" · purchase price {row.get('purchase_price')}"
    ]


def step_so_save(st):
    db, plan = st["db"], st["plan"]
    error = save()
    so_id = form_state()["id"]
    check(so_id, f"no record id after save; dialog: {error or _dialog() or 'none'}")
    name, state, partner, company, term, sign, rep, profit, agreement = one(
        db,
        "select name, state, partner_id, company_id, payment_term_id, sign_person, partner_representative_id,"
        f" order_profit, agreement_id from sale_order where id = {so_id}",
    )
    check(state == "draft", f"sale order state {state}, expected draft")
    check(same_id(partner, plan["customer_id"]), f"sale order customer {partner}, expected {plan['customer_id']}")
    check(same_id(company, plan["company_id"]), f"sale order company {company}, expected {plan['company_id']}")
    check(same_id(term, plan["payment_term_id"]), f"payment term {term}, expected {plan['payment_term_id']}")
    check(same_id(sign, plan["sign_person_id"]), f"sign person {sign}, expected {plan['sign_person_id']}")
    if plan["rep_id"]:
        check(same_id(rep, plan["rep_id"]), f"representative {rep}, expected {plan['rep_id']}")
    check(same_number(profit, plan["order_profit"]), f"order profit {profit}, expected {plan['order_profit']}")
    check(agreement, "the sale order has no sale agreement after saving")
    lines = sql(
        db,
        "select id, product_id, vendor_id, product_uom_qty, purchase_price from sale_order_line"
        f" where order_id = {so_id} and display_type is null",
    )
    check(len(lines) == 1, f"expected 1 order line, found {len(lines)}")
    line_id, product, vendor, qty, price = lines[0]
    check(same_id(vendor, plan["vendor_id"]), f"line vendor_id={vendor or 'NULL'}, expected {plan['vendor_id']}")
    check(same_id(product, plan["product_id"]), f"line product {product}, expected {plan['product_id']}")
    check(same_number(qty, plan["qty"]), f"line quantity {qty}, expected {plan['qty']}")
    check(same_number(price, plan["price"]), f"line purchase price {price}, expected {plan['price']}")
    po = one(db, f"select id, name, state, partner_id, agreement_id from purchase_order where origin = '{name}' order by id desc limit 1")
    check(po, f"no purchase order with origin {name}")
    check(same_id(po[3], plan["vendor_id"]), f"purchase order vendor {po[3]}, expected {plan['vendor_id']}")
    check(po[4], f"purchase order {po[1]} has no purchase agreement")
    (sale_agreement_name,) = one(db, f"select name from agreement where id = {agreement}")
    (purchase_agreement_name,) = one(db, f"select name from agreement where id = {po[4]}")
    st["ids"].update(
        so=int(so_id),
        so_name=name,
        line=int(line_id),
        sale_agreement=int(agreement),
        sale_agreement_name=sale_agreement_name,
        po=int(po[0]),
        po_name=po[1],
        purchase_agreement=int(po[4]),
        purchase_agreement_name=purchase_agreement_name,
    )
    row_text = (
        js(
            "[...document.querySelectorAll('.o_form_view div[name=order_line] .o_data_row')]"
            ".map(r=>r.innerText.replace(/\\s+/g,' ')).join(' || ')"
        )
        or ""
    )
    check(plan["vendor_name"].lower() in row_text.lower(), f"the saved order line does not show the vendor: {row_text[:200]!r}")
    shot = _shot(st, "so-line-vendor", ".o_form_view div[name=order_line]")
    return [
        f"DB  sale_order {so_id} {name} state=draft · line {line_id} vendor_id={vendor} qty={qty} purchase_price={price}",
        f"DB  purchase order {po[1]} id={po[0]} state={po[2]} · sale agreement {sale_agreement_name} id={agreement}"
        f" · purchase agreement {purchase_agreement_name} id={po[4]}",
        f"SHOT {shot}",
        f"EXPECT breadcrumb {name}; Order Lines table has one line {plan['product_name']} whose Vendor column shows"
        f" {plan['vendor_name']}, quantity {plan['qty']}, purchase price {plan['price']}; no error dialog",
    ]


def _fill_order_agreement(st, target, fields):
    """Open the order agreement and fill contact/bank/type/framework/expiration; returns the DB row after save."""
    plan = st["plan"]
    open_target(st, target)
    for field, text in fields:
        fill_m2o(field, text)
    fill("expiration_date", plan["date_expiration"])
    error = save()
    row = one(
        st["db"],
        "select partner_contact_id, partner_bank_id, agreement_type_id, parent_id, expiration_date"
        f" from agreement where id = {target_id(st, target)}",
    )
    return row, f"; dialog: {error or 'none'}"


def step_sale_agreement_fill(st):
    plan, ids = st["plan"], st["ids"]
    fields = [
        ("agreement_type_id", plan["sale_type"]),
        ("partner_contact_id", plan["cust_contact_name"]),
        ("partner_bank_id", plan["cust_bank_acc"]),
    ]
    if plan["cust_framework_name"]:
        fields.append(("parent_id", plan["cust_framework_name"]))
    (contact, bank, type_found, parent, expiration), detail = _fill_order_agreement(st, SALE, fields)
    check(same_id(type_found, plan["sale_type_id"]), f"sale agreement type {type_found or 'NULL'}, expected {plan['sale_type_id']}{detail}")
    check(same_id(contact, plan["cust_contact_id"]), f"sale agreement contact {contact or 'NULL'}, expected {plan['cust_contact_id']}{detail}")
    check(same_id(bank, plan["cust_bank_id"]), f"sale agreement bank {bank or 'NULL'}, expected {plan['cust_bank_id']}{detail}")
    if plan["cust_framework_id"]:
        check(same_id(parent, plan["cust_framework_id"]), f"framework {parent or 'NULL'}, expected {plan['cust_framework_id']}{detail}")
    check(expiration == plan["expiration_iso"], f"expiration {expiration or 'NULL'}, expected {plan['expiration_iso']}{detail}")
    return [
        f"DB  sale agreement {ids['sale_agreement_name']}: type {plan['sale_type']}, contact {plan['cust_contact_name']},"
        f" bank {plan['cust_bank_acc']}, framework {plan['cust_framework_name'] or '-'}, expires {plan['expiration_iso']}"
    ]


def step_purchase_agreement_fill(st):
    plan, ids = st["plan"], st["ids"]
    fields = [
        ("agreement_type_id", plan["purchase_type"]),
        ("partner_contact_id", plan["vendor_contact_name"]),
        ("partner_bank_id", plan["vendor_bank_acc"]),
    ]
    if plan["vendor_framework_name"]:
        fields.append(("parent_id", plan["vendor_framework_name"]))
    (contact, bank, type_found, parent, expiration), detail = _fill_order_agreement(st, PURCHASE, fields)
    check(same_id(contact, plan["vendor_contact_id"]), f"purchase agreement contact {contact or 'NULL'}, expected {plan['vendor_contact_id']}{detail}")
    check(same_id(bank, plan["vendor_bank_id"]), f"purchase agreement bank {bank or 'NULL'}, expected {plan['vendor_bank_id']}{detail}")
    check(same_id(type_found, plan["purchase_type_id"]), f"purchase agreement type {type_found or 'NULL'}, expected {plan['purchase_type_id']}{detail}")
    if plan["vendor_framework_id"]:
        check(same_id(parent, plan["vendor_framework_id"]), f"framework {parent or 'NULL'}, expected {plan['vendor_framework_id']}{detail}")
    check(expiration == plan["expiration_iso"], f"expiration {expiration or 'NULL'}, expected {plan['expiration_iso']}{detail}")
    return [
        f"DB  purchase agreement {ids['purchase_agreement_name']}: contact {plan['vendor_contact_name']},"
        f" bank {plan['vendor_bank_acc']}, type {plan['purchase_type']}, framework {plan['vendor_framework_name'] or '-'}"
    ]


def step_so_confirm(st):
    db, ids = st["db"], st["ids"]
    odoo_open(st["base"], SO_ACTION, ids["so"], model="sale.order")
    check("action_confirm" in _buttons(), f"no CONFIRM button; buttons {form_state()['buttons']}")
    error = click_btn("action_confirm")
    (so_state,) = one(db, f"select state from sale_order where id = {ids['so']}")
    check(so_state == "sale", f"sale order state {so_state}, expected sale; dialog: {error or _dialog() or 'none'}")
    (po_state,) = one(db, f"select state from purchase_order where id = {ids['po']}")
    check(po_state == "purchase", f"purchase order state {po_state}, expected purchase")
    for target in (SALE, PURCHASE):
        found = target_state(st, target)
        check(found == "draft", f"{target['label']} stage {found}, expected draft (To Check)")
    check(_stage_ui() == "SALES ORDER", f"statusbar shows {_stage_ui()!r}, expected SALES ORDER")
    shot = _shot(st, "so-confirmed")
    return [
        f"DB  {ids['so_name']} state=sale · {ids['po_name']} state=purchase · both agreements stage=draft",
        f"SHOT {shot}",
        f"EXPECT {ids['so_name']}: statusbar current stage SALES ORDER; smart buttons include 1 Purchase; no error dialog",
    ]


def _so_summary(st):
    ids, plan = st["ids"], st["plan"]
    so_state, po_state = one(
        st["db"],
        f"select s.state, p.state from sale_order s, purchase_order p where s.id = {ids['so']} and p.id = {ids['po']}",
    )
    return [
        f"DB  {ids['so_name']} id={ids['so']} state={so_state} · line {ids['line']} vendor_id={plan['vendor_id']}"
        f" · {ids['po_name']} id={ids['po']} state={po_state}"
    ]


register(
    "so",
    "sale order with a vendor line -> confirm -> sale agreement approved (the purchase agreement follows)",
    "customer=<id> vendor=<id> product=<id> qty=<n> price=<n> [sale_type=<agreement type>] [purchase_type=<agreement type>]"
    " (types are picked by hand: default Đơn hàng bán / Đơn hàng mua; also Hợp Đồng Bán/Mua Phân Bón,"
    " Hợp đồng mua bán Nông Sản / Thủy Sản - Khách hàng / Nhà cung cấp)",
    plan_so,
    [
        ("so_header", step_so_header),
        ("so_details", step_so_details),
        ("so_line", step_so_line),
        ("so_save", step_so_save),
        ("sale_agreement_fill", step_sale_agreement_fill),
        ("purchase_agreement_fill", step_purchase_agreement_fill),
        ("so_confirm", step_so_confirm),
        ("to_check", step_show_state(SALE, "draft", "agreement-to-check")),
        ("to_review", step_to_review(SALE, "action_authorize_to_review", actor_biz_ops_2(SALE))),
        ("approve", step_approve("approve", SALE)),
        ("finish", step_finish(SALE, chatter="The agreement has been approved", extra=_so_summary)),
        ("purchase_approved", step_show_state(PURCHASE, "reviewed", "purchase-agreement-approved")),
    ],
)
