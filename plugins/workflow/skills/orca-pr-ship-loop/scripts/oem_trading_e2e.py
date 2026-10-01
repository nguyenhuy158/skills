# FarmNet OEM Trading end-to-end UI run on a worktree clone, built on the preloaded agent_helpers
# (odoo_open, fill, fill_m2o, line_add, line_fill, save, click_btn, click, odoo_errors, form_state).
# ~4 min -> run as a supervised process, never a bash job:
#   hub start name=pr<N>-e2e application=sh cwd=<worktree> pty=false args=["-c",
#     "BASE=http://<container>.localhost BU_NAME=pr<N>-e2e browser-use < <skill-dir>/scripts/oem_trading_e2e.py"]
# Env (search texts, all optional): OEM_AM, OEM_PRODUCT, OEM_CUSTOMER, OEM_VENDOR, OEM_DROPSHIP, OEM_TERM;
# OEM_SHOTS=<dir> saves one PNG per step. Output: "STEP <n>" lines, then "RESULT: OK" or "RESULT: FAIL <step> | <error>".
import json
import os
import time

B = os.environ["BASE"]
AM = os.environ.get("OEM_AM", "a")
PRODUCT = os.environ.get("OEM_PRODUCT", "Tips")
CUSTOMER = os.environ.get("OEM_CUSTOMER", "CAO NAM")
VENDOR = os.environ.get("OEM_VENDOR", "ĐỒNG GIAO")
DROPSHIP = os.environ.get("OEM_DROPSHIP", "Administrator")
TERM = os.environ.get("OEM_TERM", "30 Days")
SHOTS = os.environ.get("OEM_SHOTS")
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
    set_select("oem_type", "trading")
    fill_m2o("account_manager_id", AM)
    fill("start_date", "01/10/2026")
    fill("end_date", "31/10/2026")
    fill_m2o("payment_terms", "30", pick=TERM)
    for field, cells in (
        ("trading_product_line_ids", [("product_id", PRODUCT, True), ("quantity", 10, False), ("unit_price", 100, False)]),
        ("trading_customer_line_ids", [("customer_id", CUSTOMER, True)]),
        ("vendor_line_ids", [("vendor_id", VENDOR, True), ("payment_term_id", TERM, True)]),
    ):
        line_add(field)
        for column, value, is_m2o in cells:
            line_fill(column, value, field=field, m2o=is_m2o)
    click(".o_form_view div[name=purchase_line_ids] tr.o_data_row td[name=unit_price]")
    time.sleep(0.8)
    fill("unit_price", 80, scope=".o_form_view div[name=purchase_line_ids] tr.o_selected_row")
    err = save()
    ids["project"] = form_state()["id"]
    return err


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


def allocate():
    click_btn("action_open_trading_allocations")
    click(".o_list_button_add")
    time.sleep(1)
    row = ".o_list_view .o_selected_row"
    fill("quantity", 10, scope=row)
    fill_m2o("product_id", PRODUCT, scope=row)
    fill_m2o("customer_id", CUSTOMER, scope=row)
    click(".o_list_button_save")
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
    prices = js("[...document.querySelectorAll('.o_form_view div[name=order_line] td[name=price_unit]')].map(e=>e.innerText.trim())")
    print("  prefilled price_unit:", prices, flush=True)
    if not prices or "0" in prices:
        return f"prefill failed: price_unit={prices}"
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
    step("06-allocate", lambda: (open_project(), allocate())[1])
    step("07-po", lambda: order("action_open_purchase_orders", VENDOR, po_extra))
    ids["po"] = form_state()["id"]
    step("08-so", lambda: order("action_open_sale_orders", CUSTOMER, so_extra))
    ids["so"] = form_state()["id"]
    approval_flow("po", "purchase.order", ids["po"], "purchase.purchase_rfq", "action_confirm_oem", PURCHASE_TYPE)
    approval_flow("so", "sale.order", ids["so"], "sale.action_orders", "action_confirm", SALE_TYPE)
    print("IDS", json.dumps(ids), flush=True)
    print("RESULT: OK", flush=True)
finally:
    close_tab(TAB)
