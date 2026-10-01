# FarmNet OEM Processing end-to-end UI run (OEM_SCENARIO=qt2_sale_order default, or qt1_stock: no customer, no SO) on a worktree clone, built on the preloaded agent_helpers.
# Needs an active oem.bom for OEM_PRODUCT (default "Tips"); OEM_BOM searches its reference (default "BOM0").
# ~4 min -> run as a supervised process, never a bash job:
#   hub start name=pr<N>-e2e application=sh cwd=<worktree> pty=false args=["-c",
#     "BASE=http://<container>.localhost BU_NAME=pr<N>-e2e browser-use < <skill-dir>/scripts/oem_processing_e2e.py"]
# Env (search texts, all optional): OEM_AM, OEM_BOM, OEM_PROCESSOR, OEM_CUSTOMER, OEM_VENDOR, OEM_DROPSHIP, OEM_TERM;
# OEM_SHOTS=<dir> saves one PNG per step. Output: "STEP <n>" lines, then "RESULT: OK" or "RESULT: FAIL <step> | <error>".
import json
import os
import time

B = os.environ["BASE"]
AM = os.environ.get("OEM_AM", "a")
BOM = os.environ.get("OEM_BOM", "BOM0")
PROCESSOR = os.environ.get("OEM_PROCESSOR", "PHƯỚC LONG")
CUSTOMER = os.environ.get("OEM_CUSTOMER", "CAO NAM")
VENDOR = os.environ.get("OEM_VENDOR", "ĐỒNG GIAO")
DROPSHIP = os.environ.get("OEM_DROPSHIP", "Administrator")
TERM = os.environ.get("OEM_TERM", "30 Days")
SHOTS = os.environ.get("OEM_SHOTS")
SCENARIO = os.environ.get("OEM_SCENARIO", "qt2_sale_order")
ACTION = "farmnet_oem_project.oem_project_action"
ids = {}
PURCHASE_TYPE = os.environ.get("OEM_PURCHASE_TYPE", "Đơn hàng mua")
SALE_TYPE = os.environ.get("OEM_SALE_TYPE", "Đơn hàng bán")


def set_select(field, value, scope=".o_form_view"):
    """Odoo <select>: plain fields store the raw key, wizard fields a JSON-quoted key ('"approved"')."""
    js(f"""(()=>{{const s=document.querySelector({json.dumps(f"{scope} div[name={field}] select")});
      s.value=[...s.options].find(o=>o.value==={json.dumps(value)}||o.value==={json.dumps(json.dumps(value))}).value;
      s.dispatchEvent(new Event('change',{{bubbles:true}}));}})()""")
    time.sleep(1)


def step(name, fn):
    print("STEP", name, flush=True)
    err = fn() or odoo_errors()
    if SHOTS:
        screenshot(f"{SHOTS}/{name}.png")
    if err:
        print("RESULT: FAIL", name, "|", err[:400], flush=True)
        raise SystemExit(1)
    print("  ok", form_state(), flush=True)


def open_project():
    odoo_open(B, ACTION, ids["project"], model="oem.project")


def new_project():
    odoo_open(B, ACTION, model="oem.project")
    set_select("oem_type", "processing")
    set_select("scenario", SCENARIO)
    fill_m2o("account_manager_id", AM)
    fill("start_date", "01/10/2026")
    fill("end_date", "31/10/2026")
    fill_m2o("finished_product_id", os.environ.get("OEM_PRODUCT", "Tips"))
    fill_m2o("bom_id", BOM)
    time.sleep(1.5)
    fill("finished_product_quantity", 100)
    fill("sale_price", 1000)
    fill("processing_fee_per_unit", 100)
    fill_m2o("payment_terms", "30", pick=TERM)
    if SCENARIO == "qt1_stock":
        fill("consumption_plan", "E2E: sell from stock within 30 days")
    if SCENARIO == "qt2_sale_order":
        line_add("sale_line_ids")
        line_fill("customer_id", CUSTOMER, field="sale_line_ids", m2o=True)
        line_fill("quantity", 100, field="sale_line_ids", m2o=False)
        line_fill("unit_price", 1000, field="sale_line_ids", m2o=False)
    line_add("vendor_line_ids")
    line_fill("vendor_id", VENDOR, field="vendor_line_ids", m2o=True)
    rows = ".o_form_view div[name=vendor_line_ids] tr.o_data_row"
    for index in range(js(f"document.querySelectorAll({json.dumps(rows)}).length")):
        # BOM suppliers are prefilled as vendor rows; every row needs a payment term to pass To Check.
        click(f"{rows}:nth-child({index + 1}) td[name=payment_term_id]")
        time.sleep(0.6)
        fill_m2o("payment_term_id", "30", pick=TERM, scope=f"{rows}.o_selected_row")
    click(".o_form_view div[name=material_line_ids] tr.o_data_row td[name=unit_price]")
    time.sleep(0.8)
    fill("unit_price", 300, scope=".o_form_view div[name=material_line_ids] tr.o_selected_row")
    err = save()
    ids["project"] = form_state()["id"]
    return err or (None if ids["project"] else "project not saved (required field missing?)")


def wizard(button, conclusion=None):
    confirm = ".modal button[name=action_confirm]"
    for _ in range(4):
        odoo_wait()
        click(f".o_form_view button[name={button}]")
        for _ in range(10):
            if js(f"!!document.querySelector({json.dumps(confirm)})"):
                break
            time.sleep(0.3)
        else:
            continue
        break
    fill_optional([
        ("operations_manager_note", "E2E OM review note", False),
        ("approval_note", "E2E CEO approval note", False),
    ], scope=".modal")
    if conclusion:
        set_select("approval_conclusion", conclusion, scope=".modal")
    click(confirm)
    time.sleep(1.5)
    odoo_wait()


def order(button, partner, extra):
    open_project()
    click_btn(button)
    click(".o_list_button_add")
    for _ in range(40):
        if js("!!document.querySelector('.o_form_view div[name=partner_id] input')"):
            break
        time.sleep(0.5)
    try:
        fill_m2o("partner_id", partner)
    except LookupError:
        # The partner turns read-only once the prefilled lines arrive; that means it was set.
        if partner.lower() not in js("document.querySelector('.o_form_view div[name=partner_id]').innerText").lower():
            raise
    time.sleep(1.5)
    rows = js(
        "[...document.querySelectorAll('.o_form_view div[name=order_line] tr.o_data_row')]"
        ".map(r=>r.innerText.replace(/\\s+/g,' ').trim())"
    )
    print("  prefilled lines:", rows, flush=True)
    if not rows:
        return "prefill failed: no order lines"
    extra()
    err = save()
    for _ in range(60):
        if err or form_state()["id"]:
            break
        time.sleep(0.5)
        err = odoo_errors()
    return err or (None if form_state()["id"] else "order not saved after 30 s")


def po_extra():
    fill_m2o("dest_address_id", DROPSHIP)
    fill_optional([
        ("effective_date", "01/10/2026", False),
        ("date_planned", "15/10/2026", False),
        ("notes", "E2E OEM purchase order: all fields filled by the script", False),
    ])


def so_extra():
    fill_optional([
        ("payment_term_id", TERM, True),
        ("client_order_ref", f"E2E-{int(time.time())}", False),
        ("partner_representative_id", "a", True),
        ("effective_date", "01/10/2026", False),
        ("validity_date", "31/10/2026", False),
        ("commitment_date", "15/10/2026", False),
        ("reference", "E2E-REF", False),
        ("note", "E2E OEM sale order: all fields filled by the script", False),
    ])


exec(open(os.path.expanduser("~/.omp/agent/managed-skills/orca-pr-ship-loop/scripts/oem_e2e_approval.py")).read())

TAB = new_tab(f"{B}/web")
try:
    try:
        odoo_login(B)
    except TimeoutError:
        odoo_login(B)
    step("01-project", new_project)
    step("02-to-check", lambda: click_btn("action_to_check"))
    step("03-to-review", lambda: click_btn("action_to_review"))
    step("04-reviewed", lambda: wizard("action_mark_reviewed"))
    step("05-active", lambda: wizard("action_activate", "approved"))
    step("06-po", lambda: order("action_open_purchase_orders", VENDOR, po_extra))
    ids["po"] = form_state()["id"]
    if SCENARIO == "qt2_sale_order":
        step("07-so", lambda: order("action_open_sale_orders", CUSTOMER, so_extra))
        ids["so"] = form_state()["id"]
    approval_flow("po", "purchase.order", ids["po"], "purchase.purchase_rfq", "action_confirm_oem", PURCHASE_TYPE)
    if SCENARIO == "qt2_sale_order":
        approval_flow("so", "sale.order", ids["so"], "sale.action_orders", "action_confirm", SALE_TYPE)
    print("IDS", json.dumps(ids), flush=True)
    print("RESULT: OK", flush=True)
finally:
    close_tab(TAB)
