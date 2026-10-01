# ruff: noqa: F821
"""Flow `return`: RETURN on a done dropship picking (DS/…) creates the return picking plus the vendor return agreement
(Hợp đồng trả hàng NCC) and the customer return agreement (Hợp đồng trả hàng KH) -> TO CHECK -> TO REVIEW
(vendor Credit Ops) -> approvers -> Approved on the vendor agreement; the customer agreement mirrors every stage.

Each run consumes one picking (a picking can be returned once)."""

import time

VENDOR_RETURN = {
    "key": "vendor_return",
    "model": "agreement",
    "action": "farmnet_return.return_agreement_action",
    "label": "vendor return agreement",
}
CUSTOMER_RETURN = {
    "key": "customer_return",
    "model": "agreement",
    "action": "farmnet_return.return_agreement_action",
    "label": "customer return agreement",
}
PICKING_ACTION = "stock.action_picking_tree_all"
STALE_JS = "document.querySelectorAll('.o_action_manager > *').forEach(e=>e.setAttribute('data-bu-stale','1'))"


def plan_return(db, params):
    picking = params.get("picking")
    where = f"p.id = {int(picking)}" if picking else "true"
    row = fetch(
        db,
        "select p.id, p.name, so.name, v.id, v.name, ub.login, c.name, bill.name from stock_picking p"
        " join sale_order so on so.id = p.sale_id join purchase_order po on po.id = p.purchase_id"
        " join res_partner v on v.id = p.partner_id join res_users ub on ub.id = v.biz_ops_2"
        " join res_partner c on c.id = so.partner_id"
        " join lateral (select m.name, m.amount_total, coalesce(m.total_disbursement_amount, 0) paid from account_move m"
        " where m.stock_picking_id = p.id and m.move_type = 'in_invoice' and m.state = 'posted'"
        " order by m.date desc, m.name desc, m.id desc limit 1) bill on true"
        f" where {where} and p.state = 'done' and p.name like '%DS%' and p.create_date >= '2025-01-01'"
        " and not coalesce(p.have_return, false) and p.vendor_return_agreement_id is null and p.source_id is null"
        " and so.agreement_id is not null and po.agreement_id is not null and bill.amount_total > bill.paid"
        " and exists (select 1 from agreement_approver ap where ap.agreement_id = so.agreement_id)"
        " and not exists (select 1 from sale_disbursement d where d.sale_id = so.id"
        " and d.state not in ('disbursed', 'paid', 'refused', 'cancel'))"
        " order by p.id desc limit 1",
        "a done dropship picking (from 2025, never returned) with an unpaid vendor bill, no open disbursement and a"
        " vendor with Credit Ops",
    )
    picking_id, picking_name, so_name, vendor_id, vendor_name, vendor_bo2, customer_name, bill_name = row
    return {
        "picking_name": picking_name,
        "so_name": so_name,
        "vendor_id": int(vendor_id),
        "vendor_name": vendor_name,
        "vendor_biz_ops_2": vendor_bo2,
        "customer_name": customer_name,
        "bill_name": bill_name,
        "ids": {"picking": int(picking_id)},
    }


def step_ret_create(st):
    db, plan, ids = st["db"], st["plan"], st["ids"]
    login_admin(st)
    odoo_open(st["base"], PICKING_ACTION, ids["picking"], model="stock.picking")
    check(_stage_ui() == "DONE", f"picking statusbar shows {_stage_ui()!r}, expected DONE")
    button = js(
        "([...document.querySelectorAll('.o_form_view .o_statusbar_buttons button')]"
        ".find(b=>b.offsetParent&&b.innerText.trim().toUpperCase()==='RETURN')||{}).getAttribute?.('name')"
    )
    check(button, f"no RETURN button on {plan['picking_name']}; buttons {form_state()['buttons']}")
    click(f'.o_form_view .o_statusbar_buttons button[name="{button}"]')
    for _ in range(30):
        if js("!!document.querySelector('.modal div[name=product_return_moves] .o_data_row')") or _dialog():
            break
        time.sleep(0.25)
    rows = js("[...document.querySelectorAll('.modal div[name=product_return_moves] .o_data_row')].map(r=>r.innerText.replace(/\\s+/g,' ').trim())") or []
    check(rows, f"the return wizard shows no product line; dialog: {_dialog()[:300] or 'none'}")
    js(STALE_JS)
    click(".modal button[name=create_returns]")
    wait_view("form", "no form opened after confirming the return")
    check(not _dialog(), f"dialog after confirming the return: {_dialog()[:300]}")
    ret = one(
        db,
        "select id, name, state, vendor_return_agreement_id, customer_return_agreement_id from stock_picking"
        f" where source_id = {ids['picking']} order by id desc limit 1",
    )
    check(ret, f"no return picking was created for {plan['picking_name']}")
    ret_id, ret_name, ret_state, vendor_agr, customer_agr = ret
    check(vendor_agr and customer_agr, f"return picking {ret_name} is missing its return agreements")
    (returned,) = one(db, f"select coalesce(have_return, false) from stock_picking where id = {ids['picking']}")
    check(returned == "t", f"{plan['picking_name']} is not marked as returned")
    agreements = {
        found_id: (name, stage, type_name)
        for found_id, name, stage, type_name in sql(
            db,
            "select a.id, a.name, a.stage, t.name from agreement a join agreement_type t on t.id = a.agreement_type_id"
            f" where a.id in ({vendor_agr}, {customer_agr})",
        )
    }
    check(agreements.get(vendor_agr, ("", "", ""))[2] == "Hợp đồng trả hàng NCC", f"vendor return agreement {agreements.get(vendor_agr)}")
    check(agreements.get(customer_agr, ("", "", ""))[2] == "Hợp đồng trả hàng KH", f"customer return agreement {agreements.get(customer_agr)}")
    for found_id, (name, stage, _type) in agreements.items():
        check(stage == "new", f"return agreement {name} stage {stage}, expected new")
    wrapper = one(db, f"select id, state from stock_picking_wrapper where return_stock_picking_id = {ret_id}")
    check(wrapper, f"no return wrapper for {ret_name}")
    ids.update(
        return_picking=int(ret_id),
        return_picking_name=ret_name,
        vendor_return=int(vendor_agr),
        vendor_return_name=agreements[vendor_agr][0],
        customer_return=int(customer_agr),
        customer_return_name=agreements[customer_agr][0],
        wrapper=int(wrapper[0]),
    )
    shot = _shot(st, "return-created", ".o_form_view")
    return [
        f"UI  wizard lines: {' ## '.join(rows)[:200]}",
        f"DB  return picking {ret_name} id={ret_id} state={ret_state} · vendor return {agreements[vendor_agr][0]}"
        f" id={vendor_agr} · customer return {agreements[customer_agr][0]} id={customer_agr} (both stage new)"
        f" · wrapper id={wrapper[0]} state={wrapper[1]}",
        f"SHOT {shot}",
        f"EXPECT the return wrapper form opened after confirming (return of {plan['picking_name']}); no error dialog",
    ]


def _return_checks(st):
    db, ids = st["db"], st["ids"]
    customer_stage = target_state(st, CUSTOMER_RETURN)
    check(customer_stage == "reviewed", f"customer return agreement stage {customer_stage}, expected reviewed (mirrors the vendor one)")
    (picking_state,) = one(db, f"select state from stock_picking where id = {ids['return_picking']}")
    return [f"DB  {ids['customer_return_name']} stage=reviewed (mirrored) · return picking {ids['return_picking_name']} state={picking_state}"]


register(
    "return",
    "dropship return: RETURN on a done DS picking -> vendor + customer return agreements -> vendor agreement approved"
    " (the customer one mirrors it)",
    "[picking=<done DS picking id>] (default: the newest done DS picking from 2025 never returned, with an unpaid vendor"
    " bill, no open disbursement and a vendor with Credit Ops; each run consumes one picking)",
    plan_return,
    [
        ("ret_create", step_ret_create),
        ("to_check", step_to_check(VENDOR_RETURN)),
        ("to_review", step_to_review(VENDOR_RETURN, "action_authorize_to_review", actor_biz_ops_2(VENDOR_RETURN))),
        ("approve", step_approve("approve", VENDOR_RETURN)),
        ("finish", step_finish(VENDOR_RETURN, chatter="The agreement has been approved", extra=_return_checks)),
        ("customer_mirror", step_show_state(CUSTOMER_RETURN, "reviewed", "customer-return-approved")),
    ],
)
