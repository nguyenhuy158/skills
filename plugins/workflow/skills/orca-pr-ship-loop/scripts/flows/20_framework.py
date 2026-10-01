# ruff: noqa: F821
"""Flow `framework`: create a framework agreement (Hợp Đồng Nguyên Tắc, customer or vendor side) from the
Agreements menu -> TO CHECK -> TO REVIEW (partner Credit Ops) -> approvers (account manager, fin ops; parallel)
-> Approved. Framework agreements skip the To Approval / Exception stages."""

import datetime as dt

FRAMEWORK = {"key": "framework", "model": "agreement", "action": "agreement.agreement_action", "label": "framework agreement"}
FRAMEWORK_TYPES = {"customer": "Hợp Đồng Nguyên Tắc - Khách Hàng", "vendor": "Hợp Đồng Nguyên Tắc - Nhà Cung Cấp"}
READY_PARTNER = (
    "p.is_company and p.active and p.biz_ops_2 is not null and p.account_manager is not null and p.fin_ops is not null"
    " and exists (select 1 from res_partner c where c.parent_id = p.id and c.active)"
    " and exists (select 1 from res_partner_bank b where b.partner_id = p.id and b.allow_out_payment)"
)


def plan_framework(db, params):
    side = params.get("side", "customer")
    check(side in FRAMEWORK_TYPES, f"side={side} must be customer or vendor")
    rank = "customer_rank" if side == "customer" else "supplier_rank"
    partner = params.get("partner")
    where = f"p.id = {int(partner)}" if partner else f"p.{rank} > 0"
    partner_id, partner_name, bo2_login = fetch(
        db,
        "select p.id, p.name, u.login from res_partner p join res_users u on u.id = p.biz_ops_2"
        f" where {where} and {READY_PARTNER} order by p.write_date desc limit 1",
        f"a {side} company with Credit Ops, account manager, fin ops, a contact and a payable bank",
    )
    type_name = FRAMEWORK_TYPES[side]
    fw_type = type_id(db, type_name)
    company_id, company_name = fetch(
        db,
        "select c.id, c.name from res_company c order by (c.id in (select company_id from agreement"
        f" where partner_id = {partner_id})) desc, c.id limit 1",
        "a company",
    )
    sign_id, sign_name = fetch(
        db,
        "select a.sign_person, sp.name from agreement a join res_users u on u.id = a.sign_person"
        f" join res_partner sp on sp.id = u.partner_id where a.agreement_type_id = {fw_type}"
        f" and sp.is_sign order by (a.partner_id = {partner_id}) desc, a.id desc limit 1",
        f"a sign person used on {type_name} agreements",
    )
    contact = partner_contact(db, partner_id)
    bank = partner_bank(db, partner_id)
    today = dt.date.today()
    return {
        "side": side,
        "partner_id": int(partner_id),
        "partner_name": partner_name,
        "biz_ops_2": bo2_login,
        "type_name": type_name,
        "type_id": fw_type,
        "company_id": int(company_id),
        "company_name": company_name,
        "contact_id": int(contact[0]),
        "contact_name": contact[1],
        "bank_id": int(bank[0]),
        "bank_acc": bank[1],
        "sign_person_id": int(sign_id),
        "sign_person_name": sign_name,
        "signature_date": ui_date(today),
        "signature_iso": today.isoformat(),
        "expiration_date": ui_date(today + dt.timedelta(days=365)),
        "expiration_iso": (today + dt.timedelta(days=365)).isoformat(),
    }


def step_fw_header(st):
    plan = st["plan"]
    login_admin(st)
    odoo_open(st["base"], FRAMEWORK["action"])
    check(form_state()["id"] is None, "expected an empty new agreement form")
    fill_m2o("partner_id", plan["partner_name"])
    fill_m2o("agreement_type_id", plan["type_name"])
    fill_m2o("company_id", plan["company_name"])
    _expect_value("partner_id", plan["partner_name"])
    _expect_value("agreement_type_id", plan["type_name"])
    _expect_value("company_id", plan["company_name"])
    return ["UI  new agreement: partner, framework type, company set (not saved yet)"]


def step_fw_details(st):
    plan = st["plan"]
    check(
        form_state()["id"] is None and plan["partner_name"].lower() in _value("partner_id").lower(),
        "the unsaved agreement from fw_header is no longer on screen",
    )
    fill_m2o("partner_contact_id", plan["contact_name"])
    fill_m2o("partner_bank_id", plan["bank_acc"])
    fill("signature_date", plan["signature_date"])
    fill("expiration_date", plan["expiration_date"])
    fill_m2o("sign_person", plan["sign_person_name"])
    _expect_value("partner_contact_id", plan["contact_name"])
    _expect_value("partner_bank_id", plan["bank_acc"])
    _expect_value("signature_date", plan["signature_date"])
    _expect_value("expiration_date", plan["expiration_date"])
    _expect_value("sign_person", plan["sign_person_name"])
    return ["UI  contact, bank, signature/expiration dates, sign person set (not saved yet)"]


def step_fw_save(st):
    db, plan = st["db"], st["plan"]
    error = save()
    record = form_state()["id"]
    check(record, f"no record id after save; dialog: {error or _dialog() or 'none'}")
    row = one(
        db,
        "select name, stage, partner_id, agreement_type_id, company_id, partner_contact_id, partner_bank_id, sign_person,"
        f" signature_date, expiration_date, is_template, origin from agreement where id = {record}",
    )
    name, stage, partner, type_found, company, contact, bank, sign, signed, expires, template, origin = row
    check(stage == "new", f"agreement stage {stage}, expected new")
    check(same_id(partner, plan["partner_id"]), f"partner {partner}, expected {plan['partner_id']}")
    check(same_id(type_found, plan["type_id"]), f"type {type_found}, expected {plan['type_id']}")
    check(same_id(company, plan["company_id"]), f"company {company}, expected {plan['company_id']}")
    check(same_id(contact, plan["contact_id"]), f"contact {contact or 'NULL'}, expected {plan['contact_id']}")
    check(same_id(bank, plan["bank_id"]), f"bank {bank or 'NULL'}, expected {plan['bank_id']}")
    check(same_id(sign, plan["sign_person_id"]), f"sign person {sign or 'NULL'}, expected {plan['sign_person_id']}")
    check(signed == plan["signature_iso"], f"signature date {signed or 'NULL'}, expected {plan['signature_iso']}")
    check(expires == plan["expiration_iso"], f"expiration date {expires or 'NULL'}, expected {plan['expiration_iso']}")
    check(template == "t", "the agreement is not a template (framework) agreement")
    st["ids"].update(framework=int(record), framework_name=name)
    shot = _shot(st, "framework-created")
    return [
        f"DB  agreement {name} id={record} stage=new type={plan['type_name']} origin={origin or '-'}"
        f" partner={plan['partner_name']} contact={plan['contact_name']} bank={plan['bank_acc']}",
        f"SHOT {shot}",
        f"EXPECT breadcrumb {name}; statusbar current stage NEW; Type {plan['type_name']}; Partner {plan['partner_name']};"
        f" Bank {plan['bank_acc']}; no error dialog",
    ]


register(
    "framework",
    "framework agreement (Hợp Đồng Nguyên Tắc) created from the Agreements menu -> TO CHECK -> TO REVIEW -> Approved",
    "[side=customer|vendor] [partner=<id>] (default: the most recently edited company with Credit Ops, account"
    " manager, fin ops, a contact and a payable bank)",
    plan_framework,
    [
        ("fw_header", step_fw_header),
        ("fw_details", step_fw_details),
        ("fw_save", step_fw_save),
        ("to_check", step_to_check(FRAMEWORK)),
        ("to_review", step_to_review(FRAMEWORK, "action_authorize_to_review", actor_biz_ops_2(FRAMEWORK))),
        ("approve", step_approve("approve", FRAMEWORK)),
        ("finish", step_finish(FRAMEWORK, chatter="The agreement has been approved")),
    ],
)
