# ruff: noqa: F821
"""Flow `appendix`: add an appendix (phụ lục) with an 'Appendix Delivery Date' line to an approved sale agreement
-> TO CHECK -> TO REVIEW (partner Credit Ops) -> approvers (account manager, fin ops) -> Reviewed, which writes
the new date to sale_order.appendix_commitment_date."""

import datetime as dt
import time

PARENT = {"key": "parent", "model": "agreement", "action": "agreement.agreement_action", "label": "sale agreement"}
APPENDIX = {
    "key": "appendix",
    "model": "agreement.appendix",
    "action": "farmnet_appendix.agreement_appendix_action",
    "label": "appendix",
}
LINE_TYPE = "Appendix Delivery Date"


def plan_appendix(db, params):
    parent = params.get("agreement")
    where = f"a.id = {int(parent)}" if parent else "true"
    parent_id, parent_name, so_id, so_name, partner_id = fetch(
        db,
        "select a.id, a.name, s.id, s.name, p.id from agreement a join sale_order s on s.agreement_id = a.id"
        " join res_partner p on p.id = a.partner_id"
        f" where {where} and a.domain = 'sale' and not coalesce(a.is_template, false) and a.stage in ('reviewed', 'active')"
        " and s.state = 'sale' and s.type = 'sale' and p.biz_ops_2 is not null and p.account_manager is not null"
        " and p.fin_ops is not null and exists (select 1 from res_partner c where c.parent_id = p.id and c.active)"
        " order by a.id desc limit 1",
        "an approved sale agreement with a confirmed sale order and a partner with Credit Ops, account manager,"
        " fin ops and a contact",
    )
    (line_type,) = fetch(
        db,
        f"select id from agreement_appendix_line_type where active and name->>'en_US' = '{LINE_TYPE}'",
        f"appendix line type {LINE_TYPE}",
    )
    contact = partner_contact(db, partner_id)
    new_date = dt.date.today() + dt.timedelta(days=int(params.get("days", 21)))
    return {
        "parent_name": parent_name,
        "so_id": int(so_id),
        "so_name": so_name,
        "partner_id": int(partner_id),
        "contact_id": int(contact[0]),
        "contact_name": contact[1],
        "line_type_id": int(line_type),
        "new_date": ui_date(new_date),
        "new_date_iso": new_date.isoformat(),
        "ids": {"parent": int(parent_id)},
    }


def step_ap_create(st):
    db, plan = st["db"], st["plan"]
    login_admin(st)
    open_target(st, PARENT)
    click(".o_form_view button[name=action_view_appendix]")
    wait_view("list", "the appendix list of the agreement did not open")
    click(".o_list_button_add")
    wait_view("form", "the new appendix form did not open")
    check(form_state()["id"] is None, "expected an empty new appendix form")
    fill_m2o("partner_contact_id", plan["contact_name"])
    line_add("line_ids")
    line_fill("type_id", LINE_TYPE, field="line_ids", m2o=True)
    error = save()
    record = form_state()["id"]
    check(record, f"no appendix id after save; dialog: {error or _dialog() or 'none'}")
    row = one(
        db,
        "select a.name, a.state, a.agreement_id, a.partner_contact_id, a.origin, l.id, l.type_id, l.field_old_value"
        f" from agreement_appendix a left join agreement_appendix_line l on l.appendix_id = a.id where a.id = {record}",
    )
    name, state, parent, contact, origin, line_id, line_type, old_value = row
    check(state == "new", f"appendix state {state}, expected new")
    check(same_id(parent, target_id(st, PARENT)), f"appendix agreement {parent}, expected {target_id(st, PARENT)}")
    check(same_id(contact, plan["contact_id"]), f"appendix contact {contact or 'NULL'}, expected {plan['contact_id']}")
    check(same_id(line_type, plan["line_type_id"]), f"appendix line type {line_type or 'NULL'}, expected {plan['line_type_id']}")
    st["ids"].update(appendix=int(record), appendix_name=name, appendix_line=int(line_id))
    return [f"DB  appendix {name} id={record} state=new origin={origin} · line {LINE_TYPE} old value {old_value}"]


def step_ap_date(st):
    plan = st["plan"]
    if str(form_state()["id"]) != str(target_id(st, APPENDIX)):
        open_target(st, APPENDIX)
    click(".o_form_view div[name=line_ids] .o_data_row button[name=action_open_appendix_line_wizard]")
    for _ in range(20):
        if js("!!document.querySelector('.modal div[name=delivery_date] input')"):
            break
        time.sleep(0.25)
    fill("delivery_date", plan["new_date"], scope=".modal")
    click(".modal button[name=action_apply]")
    for _ in range(30):
        if not js("[...document.querySelectorAll('.modal')].some(m=>m.getClientRects().length)"):
            break
        time.sleep(0.25)
    check(not _dialog(), f"the delivery date wizard is still open: {_dialog()[:200]}")
    odoo_wait()
    (new_value,) = one(st["db"], f"select field_new_value from agreement_appendix_line where id = {st['ids']['appendix_line']}")
    check(new_value == plan["new_date_iso"], f"line new value {new_value or 'NULL'}, expected {plan['new_date_iso']}")
    row_text = js("(document.querySelector('.o_form_view div[name=line_ids] .o_data_row')||{}).innerText||''") or ""
    check(plan["new_date_iso"] in row_text, f"the appendix line does not show {plan['new_date_iso']}: {row_text!r}")
    check(not _dialog(), f"a dialog is still open: {_dialog()[:200]}")
    shot = _shot(st, "appendix-created", ".o_form_view div[name=line_ids]",
                 must_show=(st["ids"]["appendix_name"], LINE_TYPE, plan["new_date_iso"]))
    return [
        f"DB  appendix line {LINE_TYPE}: new value {new_value}",
        f"SHOT {shot}",
        f"EXPECT appendix {st['ids']['appendix_name']} in stage NEW; Lines table: {LINE_TYPE} with new value"
        f" {plan['new_date_iso']}; no dialog open",
    ]


def _commitment_date(st):
    plan = st["plan"]
    (found,) = one(st["db"], f"select appendix_commitment_date from sale_order where id = {plan['so_id']}")
    check(found == plan["new_date_iso"], f"{plan['so_name']} appendix_commitment_date {found or 'NULL'}, expected {plan['new_date_iso']}")
    return [f"DB  {plan['so_name']} appendix_commitment_date={found}"]


register(
    "appendix",
    "appendix with an 'Appendix Delivery Date' line on an approved sale agreement -> TO CHECK -> TO REVIEW -> Reviewed"
    " (writes sale_order.appendix_commitment_date)",
    "[agreement=<approved sale agreement id>] [days=<new date = today + days, default 21>] (default: the newest"
    " approved sale agreement whose partner has Credit Ops, account manager, fin ops and a contact)",
    plan_appendix,
    [
        ("ap_create", step_ap_create),
        ("ap_date", step_ap_date),
        ("to_check", step_to_check(APPENDIX)),
        ("to_review", step_to_review(APPENDIX, "action_to_review", actor_biz_ops_2(APPENDIX))),
        ("approve", step_approve("approve", APPENDIX)),
        ("finish", step_finish(APPENDIX, chatter="Phụ lục đã được phê duyệt", extra=_commitment_date)),
    ],
)
