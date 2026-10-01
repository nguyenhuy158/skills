# ruff: noqa: F821
"""Flow `appendix_active`: a Reviewed appendix goes Active: Administrator uploads the signed PDF (Signed Document)
-> document TO CHECK by the partner's Biz Ops -> APPROVE by the partner's Credit Ops -> ACTIVE by the partner's
Biz Ops -> Active. Uses the signed-document steps of 25_active.py.

Each run activates one appendix (default: the newest Reviewed appendix whose signed document is missing, e.g. the
one an `appendix` run just approved)."""

APPENDIX_ACTIVE = {
    "key": "appendix",
    "model": "agreement.appendix",
    "action": "farmnet_appendix.agreement_appendix_action",
    "label": "appendix",
    "doc": {"field": "source_document", "rel": "agreement_appendix_ir_attachment_rel", "col": "agreement_appendix_id"},
}


def plan_appendix_active(db, params):
    appendix = params.get("appendix")
    where = f"x.id = {int(appendix)}" if appendix else "true"
    appendix_id, name, bo, bo_name, bo2, bo2_name = fetch(
        db,
        "select x.id, x.name, bo.login, bop.name, bo2.login, bo2p.name from agreement_appendix x"
        " join res_partner p on p.id = x.partner_id"
        " join res_users bo on bo.id = p.biz_ops join res_partner bop on bop.id = bo.partner_id"
        " join res_users bo2 on bo2.id = p.biz_ops_2 join res_partner bo2p on bo2p.id = bo2.partner_id"
        f" where {where} and x.state = 'reviewed' and coalesce(x.signed_attachment_state, 'missing') = 'missing'"
        " and bo.active and bo2.active"
        f" and {in_group('bo', 'farmnet_documents', 'restrict_for_bo')} and {in_group('bo', 'agreement', 'restrict_for_bo')}"
        f" and {in_group('bo2', 'farmnet_documents', 'restrict_for_bo2')}"
        " order by x.id desc limit 1",
        "a Reviewed appendix with a missing signed document whose partner Biz Ops / Credit Ops hold the document and"
        " agreement rights",
    )
    return {
        "appendix_name": name,
        "biz_ops": bo,
        "biz_ops_name": bo_name,
        "credit_ops": bo2,
        "credit_ops_name": bo2_name,
        "ids": {"appendix": int(appendix_id)},
    }


register(
    "appendix_active",
    "Reviewed appendix -> signed PDF uploaded -> document TO CHECK (Biz Ops) -> APPROVE (Credit Ops) -> ACTIVE"
    " (Biz Ops) -> Active",
    "[appendix=<Reviewed appendix id>] (default: the newest one whose signed document is missing; each run"
    " activates one appendix, e.g. the one an `appendix` run just approved)",
    plan_appendix_active,
    [
        ("apa_upload", step_doc_upload(APPENDIX_ACTIVE)),
        ("apa_lock", step_doc_action(APPENDIX_ACTIVE, "action_lock_signed_attachment", plan_actor("biz_ops"), "pending", "PENDING")),
        ("apa_approve", step_doc_action(APPENDIX_ACTIVE, "action_approve_signed_attachment", plan_actor("credit_ops"), "completed", "COMPLETED")),
        ("apa_active", step_state_button(APPENDIX_ACTIVE, "action_active", plan_actor("biz_ops"), "active")),
        ("finish", step_finish(APPENDIX_ACTIVE, final="active")),
    ],
)
