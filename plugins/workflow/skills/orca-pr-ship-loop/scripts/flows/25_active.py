# ruff: noqa: F821
"""Signed-document steps shared by several flows (upload PDF -> TO CHECK -> APPROVE) and flow `active`:
an approved (Reviewed) framework agreement goes Active: Administrator uploads the signed PDF -> TO CHECK of the
document by the partner's Biz Ops -> APPROVE by the partner's Credit Ops -> TO ACTIVE by the agreement's responsible
user (agreement.user_id) -> Active.

A signed-document target is a record target (see 00_core) plus "doc": {"field", "rel", "col"}: the many2many field
holding the PDF, its relation table and the column pointing at the record."""

ACTIVE = {
    "key": "agreement",
    "model": "agreement",
    "action": "agreement.agreement_action",
    "label": "agreement",
    "doc": {"field": "signed_attachment_ids", "rel": "agreement_signed_attachment_rel", "col": "agreement_id"},
}
PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
)


def in_group(alias, module, name):
    """SQL condition: user `alias` belongs to group module.name."""
    return (
        "exists (select 1 from res_groups_users_rel r join ir_model_data d on d.res_id = r.gid and d.model = 'res.groups'"
        f" where r.uid = {alias}.id and d.module = '{module}' and d.name = '{name}')"
    )


def signed_doc(st, target):
    """(number of signed PDFs, signed_attachment_state) of the target record."""
    doc, table = target["doc"], TABLES[target["model"]]["table"]
    count, state = one(
        st["db"],
        f"select (select count(*) from {doc['rel']} r where r.{doc['col']} = t.id),"
        f" coalesce(t.signed_attachment_state, 'missing') from {table} t where t.id = {target_id(st, target)}",
    )
    return int(count), state


def step_doc_upload(target, as_login=None):
    """Upload a one-page PDF into the signed-document field (as admin, or as_login(st) -> (login, name)) and save."""

    def run(st):
        field = target["doc"]["field"]
        login_admin(st)
        open_target(st, target)
        if as_login:
            as_user(st, target, *as_login(st))
        pdf = os.path.join(st["dir"], "signed-document.pdf")
        with open(pdf, "wb") as fh:
            fh.write(PDF)
        root = cdp("DOM.getDocument", depth=1)["root"]["nodeId"]
        node = cdp("DOM.querySelector", nodeId=root, selector=f".o_form_view div[name={field}] input[type=file]")
        check(node.get("nodeId"), f"no file input on the {field} field")
        cdp("DOM.setFileInputFiles", nodeId=node["nodeId"], files=[pdf])
        shown = f"!!document.querySelector('.o_form_view div[name={field}] .o_attachment')"
        for _ in range(40):
            if js(shown):
                break
            time.sleep(0.25)
        check(js(shown), f"the uploaded PDF does not show on the form; dialog: {_dialog() or 'none'}")
        error = save()
        count, state = signed_doc(st, target)
        check(count >= 1 and state == "missing", f"signed documents {count}, state {state}; dialog: {error or _dialog() or 'none'}")
        check("signed-document.pdf" in js(f"(document.querySelector('.o_form_view div[name={field}]')||{{}}).innerText||''"),
              "signed-document.pdf is not listed on the saved form")
        shot = _shot(st, f"{target['key']}-document-uploaded", f"div[name={field}]")
        return [
            f"DB  {target['label']} id={target_id(st, target)}: {count} signed document(s), document state=missing",
            f"SHOT {shot}",
            "EXPECT signed-document.pdf listed in the signed document field; document Status MISSING; TO CHECK button",
        ]

    return run


def step_doc_action(target, button, actor, want, label):
    """actor(st) -> (login, name) clicks the document `button`; the document state must become `want`."""

    def run(st):
        login, name = actor(st)
        open_target(st, target)
        as_user(st, target, login, name)
        check(js(f"!!document.querySelector('.o_form_view button[name={button}]')"), f"no {button} button for {login}")
        error = click_btn(button)
        _, state = signed_doc(st, target)
        check(state == want, f"document state {state}, expected {want}; dialog: {error or _dialog() or 'none'}")
        shown = js("(document.querySelector('.o_form_view div[name=signed_attachment_state]')||{}).innerText||''").strip()
        names = one(
            st["db"],
            "select string_agg(v.value, '|') from ir_model_fields_selection s join ir_model_fields f on f.id = s.field_id,"
            f" jsonb_each_text(s.name) v where f.model = '{target['model']}' and f.name = 'signed_attachment_state'"
            f" and s.value = '{want}'",
        )[0].upper().split("|")
        check(shown.upper() in names, f"document Status shows {shown!r}, expected one of {names}")
        shot = _shot(st, f"{target['key']}-document-{want}", f"div[name={target['doc']['field']}]")
        return [
            f"DB  {target['label']} id={target_id(st, target)}: document state={want} (by {login})",
            f"SHOT {shot}",
            f"EXPECT {name} in the top bar; document Status {label}; no error dialog",
        ]

    return run


def step_state_button(target, button, actor, want):
    """actor(st) -> (login, name) clicks a header `button`; the record state must become `want` (DB + statusbar)."""

    def run(st):
        login, name = actor(st)
        open_target(st, target)
        as_user(st, target, login, name)
        check(button in _buttons(), f"no {button} button for {login}; buttons {form_state()['buttons']}")
        error = click_btn(button)
        label = expect_state(st, target, want, f"; dialog: {error or _dialog() or 'none'}")
        shot = _shot(st, f"{target['key']}-{want}")
        return [
            f"DB  {target['label']} id={target_id(st, target)} state={want} ({button} by {login})",
            f"SHOT {shot}",
            f"EXPECT {name} in the top bar; statusbar current stage {label}; no error dialog",
        ]

    return run


def plan_active(db, params):
    agreement = params.get("agreement")
    where = f"a.id = {int(agreement)}" if agreement else "t.name like 'Hợp Đồng Nguyên Tắc%'"
    row = fetch(
        db,
        "select a.id, a.name, bo.login, bop.name, bo2.login, bo2p.name, own.login, ownp.name"
        " from agreement a join agreement_type t on t.id = a.agreement_type_id join res_partner p on p.id = a.partner_id"
        " join res_users bo on bo.id = p.biz_ops join res_partner bop on bop.id = bo.partner_id"
        " join res_users bo2 on bo2.id = p.biz_ops_2 join res_partner bo2p on bo2p.id = bo2.partner_id"
        " join res_users own on own.id = a.user_id join res_partner ownp on ownp.id = own.partner_id"
        f" where {where} and a.stage = 'reviewed' and coalesce(a.signed_attachment_state, 'missing') = 'missing'"
        " and t.name not like '%Đơn hàng mua%' and bo.active and bo2.active and own.active"
        " and not exists (select 1 from sale_order s where s.agreement_id = a.id)"
        f" and {in_group('bo', 'farmnet_documents', 'restrict_for_bo')}"
        f" and {in_group('bo2', 'farmnet_documents', 'restrict_for_bo2')}"
        f" and {in_group('own', 'agreement', 'user')}"
        " order by a.id desc limit 1",
        "a Reviewed framework agreement without sale order and with a missing signed document, whose partner Biz Ops /"
        " Credit Ops and responsible user hold the document and agreement rights",
    )
    agreement_id, name, bo, bo_name, bo2, bo2_name, owner, owner_name = row
    return {
        "agreement_name": name,
        "biz_ops": bo,
        "biz_ops_name": bo_name,
        "credit_ops": bo2,
        "credit_ops_name": bo2_name,
        "owner": owner,
        "owner_name": owner_name,
        "ids": {"agreement": int(agreement_id)},
    }


def plan_actor(role):
    """Actor callback reading (login, name) from plan[role] / plan[role + '_name']."""
    return lambda st: (st["plan"][role], st["plan"][f"{role}_name"])


register(
    "active",
    "Reviewed framework agreement -> signed PDF uploaded -> document TO CHECK (Biz Ops) -> APPROVE (Credit Ops)"
    " -> TO ACTIVE (responsible user) -> Active",
    "[agreement=<Reviewed framework agreement id>] (default: the newest one without sale order whose signed document"
    " is missing; each run activates one agreement, e.g. the one a `framework` run just approved)",
    plan_active,
    [
        ("act_upload", step_doc_upload(ACTIVE)),
        ("act_lock", step_doc_action(ACTIVE, "action_lock_signed_attachment", plan_actor("biz_ops"), "pending", "PENDING")),
        ("act_approve", step_doc_action(ACTIVE, "action_approve_signed_attachment", plan_actor("credit_ops"), "completed", "COMPLETED")),
        ("act_active", step_state_button(ACTIVE, "action_to_active", plan_actor("owner"), "active")),
        ("finish", step_finish(ACTIVE, final="active")),
    ],
)
