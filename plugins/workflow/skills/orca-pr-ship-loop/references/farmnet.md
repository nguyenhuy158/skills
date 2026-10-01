# FarmNet — Techcoop-vn/farmnet with Orca

Repo: `/Users/huyntq/Documents/techcoop/farmnet-github`. Odoo 16, ~30 custom modules in `src/`,
running in Docker. `AGENTS.md` at the repo root is the authority on coding rules.

## Ground Rules

- Prefix every CLI command run via bash with `rtk` (`rtk proxy make`, `rtk git`, `rtk proxy gh`, etc.).
- Never use `sed`, `mkdir`, `touch`, `rm`, `cp`, `echo >file` for file operations; use built-in tools.
- Orca binary path: `/Applications/Orca.app/Contents/Resources/bin/orca`.

---

## Step 1 — Worktree & Orca Card Setup

```bash
rtk proxy make worktree BRANCH=feature/<kebab-case-description>
```

Path lands at `.claude/worktrees/<slug>`.

Register status in Orca:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" worktree set \
  --worktree active \
  --workspace-status in-progress \
  --comment "Developing FarmNet feature" --json
```

If Odoo stack is needed for testing (clone and wt-up exceed 30 s → run each as a supervised process, e.g.
`hub start name=<slug>-clone application=rtk args=["proxy","make","wt-db-clone",…] cwd=<worktree> pty=false`,
then continue with other work until its exit notice):
```bash
rtk proxy make wt-db-clone FNP_DB_CONTAINER=dev-postgres DB_HOST=localhost DB_PORT=5432 DB_PASSWORD=farmnet
rtk proxy make wt-up DB_PASSWORD=farmnet
rtk proxy make wt-proxy
# login_as_any_user is installed by dev/module-upgrade.sh during wt-up (PR #1263): nothing to do by hand
```

### Root DB freshness (Step 1.3)

Root source is `farmnet_service` on the container the main checkout uses (`dev-postgres`, port 5432).

```bash
rtk docker exec dev-postgres psql -U farmnet_service -d farmnet_service -tAc \
  "SELECT max(write_date) FROM sale_order UNION ALL SELECT max(write_date) FROM account_move"
```
Newest value older than 2 days → ask the user: use stale data, or sync the root first
(`farmnet-dokploy-dev-restore` / snapshot restore is the user's call, never the agent's).

### Repo layout rules (self-review, Step 2.4)

- Wizard views live **next to the wizard model**: `src/<module>/wizard/<name>.xml` (31 files in the repo follow
  this; the 3 in `farmnet_planning/views/` are legacy — do not add more).
- When moving files with the edit tool's `MV`, give the destination **including the worktree prefix**
  (`.claude/worktrees/<slug>/src/...`); a bare `src/...` lands in the main checkout.

### DB clone traps

- **ALWAYS clone from `dev-postgres`** (the main checkout's DB). `make wt-db-clone` does NOT read the root
  `dev/.env`: `Makefile:61` hardcodes `FNP_DB_CONTAINER ?= fnp-db-1` (stale, ~2 weeks behind) and the new
  worktree's `dev/.env` has `DB_HOST=db`. Bare `make wt-db-clone` = stale data. Use exactly:
  `rtk make wt-db-clone FNP_DB_CONTAINER=dev-postgres DB_HOST=localhost DB_PORT=5432 DB_PASSWORD=farmnet`
  (`DB_PASSWORD=odoo` fails auth; read the real one with `docker inspect dev-postgres` → `POSTGRES_PASSWORD`).
  Freshness check (1.3) and clone MUST hit the same container.
- `server closed the connection unexpectedly` mid-clone → Docker/OrbStack died; `orb start`, then rerun.
- `wt-up` needs `DB_PASSWORD=farmnet` as a make argument, not an env prefix.
- **Downgrade guard** (`N module(s) are older in this image than in the database — refusing to auto -u`,
  container restart loop). Cause is usually a branch that is behind `origin/main` while the root DB already
  runs newer `main` code. Fix in this order:
  1. `rtk git fetch origin` and compare each `DOWNGRADE:` module's version in `origin/main:src/<m>/__manifest__.py`
     with the DB value (`ir_module_module.latest_version`).
  2. `origin/main` has the DB's version and the branch is behind (`git rev-list --count HEAD..origin/main` > 0)
     → `rtk git rebase origin/main`, rerun lint, `rtk git push --force-with-lease` (standing user approval for
     this case only; never plain `--force`), then `make wt-down` + `make wt-up`.
  3. Branch already contains `origin/main` (count = 0) → the root DB came from another branch, rebase cannot help.
     **Ask the user**: (a) start without touching the schema — add `ALLOW_DOWNGRADE_UPDATE=1` next to
     `SKIP_BOOTSTRAP_UPGRADE=1` in the worktree `dev/.env` (gitignored); both are needed because
     `entrypoint.py` checks the downgrade guard before `SKIP_BOOTSTRAP_UPGRADE`; or (b) restore/sync the root DB.
- **Before `make upgrade`, read the Odoo log first** — the dev container's `module_auto_update` upgrades changed
  modules by itself on start, and a parallel `-u` deadlocks on `ir_module_module`.
  1. `rtk docker logs --tail 40 <project>-odoo-1` and check `ir_module_module.latest_version` for the module.
  2. Log still shows `loading <module>/...` / `Registry` not loaded → **the server is upgrading**: start a readiness
     watcher (`hub start name=<slug>-ready application=sh args=["-c","until curl -sf <url>/web/login >/dev/null;
     do sleep 3; done; echo READY"]`) and keep working. Do not start `make upgrade`.
  3. Server up (HTTP 200) and `latest_version` already equals the manifest → upgrade done; skip `make upgrade`.
  4. Server up but the version is still old → only now run `make upgrade MODULE=<m>` as a supervised process.


### UI login on a worktree (Step 2.2) — no need to ask the user

1. Log in yourself with `admin` / `admin` on the worktree host via `browser-use` (local clone DB only).
2. Switch to the user the scenario needs with the repo's **`login_as_any_user`** module — `make wt-up` installs it
   on the clone automatically (PR #1263). A worktree branched before that: merge `origin/main` or install it once
   from Apps; never run `odoo -i` beside the running server (parallel update deadlocks `ir_module_module`).
3. `admin/admin` rejected → reset the accounts on the root DB: from the **main checkout** run
   `rtk make clickodoo SCRIPT=/odoo/migration/change-default-lang.py`, then re-clone the worktree DB
   (`make wt-db-clone …`), restart the stack, retry step 1.
4. Take the step 2.2 screenshots while testing; continue the loop without waiting on the user.
5. `browser-use` gotchas seen on Odoo:
   - Headless agent Chrome: `new_tab` opens its own window, so the Odoo webclient renders without `activate_tab`.
     If a frame looks stale, reload the tab and wait for the element.
   - Navigate with `/web#action=<xmlid|id>&model=...&view_type=...` (Odoo 16, no `/odoo/...` routes; a bare
     `#model=` URL falls back to Discuss). Select fields by `div[name=<field>] input` — ids like `#name_1` change
     on re-render. The Save button only shows once a field is dirty: blur (Tab) first.
   - Screenshot helper: `screenshot(path)` / `capture_screenshot(path=...)`.
   - New/changed JS/SCSS not applied → open with `?debug=assets` and reload bypassing cache
     (`cdp("Network.setCacheDisabled", cacheDisabled=True)`, `cdp("Page.reload", ignoreCache=True)`).
   - Many2one in a dialog: type into its input + dispatch `input`, then click the dropdown item by box center.
   - Dates are typed `dd/mm/yyyy` (admin lang `%d/%m/%Y`); `mm/dd` is silently cleared on blur.
   - **After a reboot** every `http://<wt>.localhost` refuses to connect: the nix caddy service starts with
     `~/.config/caddy/Caddyfile` (not the worktree sites) and its automatic-HTTPS redirect on :80 gets cached by
     Chrome, which then keeps going to `https://…` (`ERR_CONNECTION_REFUSED`). Fix: `rtk proxy make wt-proxy` in any
     worktree (reloads `.claude/caddy/Caddyfile` with all sites), then clear the agent Chrome HTTP cache once
     (`cdp("Network.enable")`, `cdp("Network.clearBrowserCache")`; cookies stay).

### Odoo helpers (preloaded in every `browser-use` call)

`~/.config/browser-harness/agent-workspace/agent_helpers.py` — one call per business step; use them instead of
hand-rolled `js` + `click_at_xy`. Each call ≤ 30 s: split long flows over several `BU_NAME=<same> browser-use` calls.

| Helper | Does |
|---|---|
| `odoo_login(base)` | log in admin/admin unless already in |
| `odoo_open(base, action, id=None, view_type="form", model=None)` | open `/web#action=…` and wait for a freshly mounted view of that record (`id=None` = new record); the previous view never counts. `wait_view(view_type, error, record_id=None)` waits the same way after a click that opens a view |
| `fill(field, value)` / `fill_m2o(field, text, pick=None)` / `fill_select(field, label)` | type a field (+Tab) / many2one: waits for a stable result list, clicks the item containing `pick or text` (never Create/Search More), checks the input shows it, retries 3×, then raises (type full names: a short text can match another partner) / selection `<select>`: picks the option whose label contains `label` |
| `line_add("order_line")`, `line_fill(col, val, m2o=True/False)` | add + fill a one2many row (`product_template_id`, `vendor_id`, `product_uom_qty`, `purchase_price`) |
| `save()`, `click_btn("action_confirm")` | save and wait until stored (new record: until it has an id) / header button by `name`, waits until Odoo re-enables the buttons (call finished); both return dialog/notification text. `click_btn` reloads the form when the stage does not re-render |
| `odoo_errors()`, `dialog_click("SWITCH ANYWAY")` | read / answer the open dialog |
| `form_state()` | `{stage, buttons, id}` of the open form (`id: None` = a new, unsaved form) |
| `switch_user(login)`, `switch_user("admin")` | act as a user via login_as_any_user's JSON routes (`/switch/users` exact login match, `/switch/user`, `/switch/admin`), then reload the open record once: ~2 s per switch (clicking the systray panel took 8–10 s). Always impersonates from admin (returns to admin first), because the module records the current user as the admin to return to whenever that user may switch too |

### Scripted UI flows (`flow-step`, default for Step 2.2 data flows)

`scripts/flow-step` + `scripts/flows/*.py` (one file per flow, `00_core.py` = engine) drive every agreement, disbursement
and payment request flow found in the code as predefined steps (< 25 s each). Every step checks the page (DOM) and the
DB (read-only SQL) and saves checkpoint screenshots with an `EXPECT` line; the first failed check saves
`fail-<step>.png` and the run refuses to continue. `flow-step flows` lists the flows with their params and steps.
One call also runs the following light step (`*_reviewed`, `pr_bank`, `finish`, `purchase_approved`,
`customer_mirror`) or another `approve` round when it has used < 10 s (`CHAIN_SECONDS`), so it may print several
`STEP … OK` blocks; `NEXT` is always the step after the last one run. An Odoo error/warning dialog fails the step
at once with its text instead of waiting for the 25 s alarm.
All `flows/*.py` load into **one namespace** (alphabetical): a module-level name reused by a later file silently
replaces the earlier one (a `KINDS` in `80_collection_notice.py` once broke `debt` init). Prefix flow-specific
constants (`NOTICE_KINDS`, `DO_CONFIRMER`).

Whole suite without an agent (regression check, benchmark): `flow-step suite <root-dir> base=… db=…` runs the default
variants (every flow except `so`, which needs `"so customer=… vendor=… product=… qty=… price=…"`) as a supervised
process (`hub start`) in **4 parallel lanes** (`DEFAULT_LANES` in `flow-suite.py`; a lane keeps dependent variants
and variants that may pick the same records together: agreements · debt/DR/offset · return/PR · notices), one
`PASS|FAIL` line per variant, then `SUITE DONE x/y` (exit 0 only when all passed; ~6 min parallel vs ~12 min one by
one). Variants given on the command line run one after the other. Watch it live in an Orca terminal:
`orca terminal create --title "Flow progress" --command "flow-step progress <root-dir>"`. A suite answers "does the
code still work"; screenshots are only judged by a `flow-runner` agent run.

Every run opens its tab in its **own browser context** (`Target.createBrowserContext`, disposed at the end), so its
Odoo session and `switch_user` never leak into another run. Every `_shot` is a DOM gate: it fails the step when an
error/warning dialog is open, and create steps pass `must_show=(record name, partner, key values…)` which must be in
the page text or a visible input value before the screenshot is taken.

Blind tests of `flow-runner` (2026-09-30, bug planted in the worktree, runner given only the skill): a silent
server-side bug (TO CHECK doing nothing) was caught at once, by the step's DB check. A UI-only change was **not**:
Haiku marked every screenshot `ok` while silently skipping 2 of 7 EXPECT items and even logging `no error dialog =>
NOT VISIBLE`. Treat the screenshot verdict as a hint, never as the gate: anything that must hold on screen belongs
in the step as a DOM check (`_expect_value`, `_stage_ui`, `_dialog`), like `dr_save` now does for source, kind, bill
and stage. Planted bugs must be reverted in the same session (`git status` clean, module upgraded back).

| flow | drives | verified 2026-09-30 |
|---|---|---|
| `so` | SO with a vendor line → confirm → sale agreement approved; the paired purchase agreement follows (approvals cascade, it is never approved on its own form). `sale_type=` / `purchase_type=` for Phân Bón / Nông Sản / Thủy Sản (types are always picked by hand) | S08577–S08580 (Đơn hàng), S08583 (Phân Bón) |
| `framework` | HĐNT created from the Agreements menu → TO CHECK → TO REVIEW → approvers → Approved; `side=customer\|vendor`, `partner=` | CP17845 (customer), CP17854 (vendor) |
| `active` | Reviewed framework agreement → Administrator uploads a signed PDF (CDP `DOM.setFileInputFiles` on the Signed Attachment input) → document TO CHECK (partner Biz Ops) → APPROVE (partner Credit Ops) → TO ACTIVE (agreement `user_id`) → Active. Default: newest Reviewed HĐNT without SO whose signed document is missing (a `framework` run leaves one); `agreement=` | CP17890 |
| `appendix` | appendix with an 'Appendix Delivery Date' line on an approved sale agreement → Reviewed; writes `sale_order.appendix_commitment_date` | PL01701 |
| `appendix_active` | Reviewed appendix → Administrator uploads a signed PDF (Signed Document) → document TO CHECK (partner Biz Ops) → APPROVE (partner Credit Ops) → ACTIVE (partner Biz Ops) → Active. Default: newest Reviewed appendix with a missing signed document (an `appendix` run leaves one); `appendix=` | PL01706 |
| `collection_notice` | Collection notices, `kind=collection` (quá hạn, `round=1\|2\|3`) · `kind=obligation` (nghĩa vụ bảo lãnh, `round=1\|2`, Guarantee picked by the guarantor's name) · `kind=settlement` (tất toán, one round): created by the customer's Biz Ops (round 2/3 set Previous Collection = the customer's newest Done notice of the same kind and the round before, picked by its display name `[template] dd/mm/yyyy`) → TO CHECK (pulls the overdue disbursed DR lines) → signed PDF → document TO CHECK (Biz Ops) → APPROVE (Credit Ops) → DONE (Credit Ops) → Done. Actors match prod. Default round 1: customer with the most overdue disbursed DRs; round 2/3: customer with the newest Done notice of the round before, so rounds in a row chain on one customer; `customer=` | DPD01282–84 (collection 1→2→3), DPD01285–86 (obligation 1→2), DPD01287 (settlement), ĐẠI KIM, 21 DR lines each |
| `debt` | SO type Factoring / Transfer → agreement typed by code → creditor's AM TO REVIEW → region manager + email list → Approved → DR confirmed; `kind=factoring\|transfer`. Creditor comes from the view `debt.sale.customer` (menu Debt Sale Customer; same rules as the save validation); both kinds take the creditor's invoice pairs as source lines when it has some, else its debt transfer DRs | CP17846 (transfer), CP17870 (factoring, 3 pairs) |
| `payment_request` | an existing request (they are only created by code: CKHD by cron, early payment discount by the Monday cron, refund from bank transactions) driven by each role: Biz Ops picks the customer bank when empty → TO CHECK (Biz Ops; early: Senior BO) → REVIEWED when the bank is new (Credit Ops) → CONFIRM (ops) → Confirmed; starts at the request's current state. Selection skips requests TO CHECK would refuse: settlement (latest paid DR `farmlink_paid_date`) after the discount deadline (`appendix_discount_date` or SO `discount_date`), and CKHD whose invoice has an overdue DR without an active request. `domain=`, `state=`, `request=`, `new_bank=1` (takes a Draft request, resets its customer bank to `approval_state=new` on the `wt_*` clone, then requires the REVIEWED branch) | PR027978, PR029889 (bank picked), PR030396 (from To check), PR030935 (early), PR029767 (REVIEWED, bank 2380) |
| `disbursement` | Trade/Input/Invest DR from the SO Disbursements smart button (Trade/Input for a posted bill; Invest needs an approved sale agreement and takes `amount=`) → TO CHECK (Biz Ops) → REVIEWED if the bank is new (Credit Ops) → CONFIRM (ops) → Confirmed; Approved/Disbursed/Paid come from FarmLink. `type=`, `kind=`, `new_bank=1` (resets the supplier bank to `approval_state=new` on the `wt_*` clone, then requires the REVIEWED branch) | DR044477–78 (trade), DR044480 (invest), DR044499 (REVIEWED, bank 651) |
| `debt_offset` | Debt Offset DR from the Disbursements menu for a customer/vendor couple → one offset line per unpaid bill-invoice pair generated on save (every pair of the couple: couples with a bill still under an open non-offset DR are skipped, TO CHECK would refuse them), repayment = their sum, vendor's approved bank set → TO CHECK by the customer's OM (`fin_ops`) → CONFIRM by the top debt offset confirmer (minh@) → Confirmed. Actors match prod (110 offsets: OM/Senior BO TO CHECK, minh@ 88 CONFIRM, never REVIEWED). The REVIEWED branch is not driven: the customer's Credit Ops cannot open a DR without SO (rule `[Disbursement] 3`), so a new vendor bank would leave it stuck in To review | DR044483 (27 lines), DR044502 (OM → minh@) |
| `return` | RETURN on a done DS picking → vendor + customer return agreements → vendor one approved, customer one mirrors | CP17847 / CP17848 |

- Not covered by `flow-step`: OEM trading/processing (own scripts below, need the PR #649 branch); stage Active of
  sale/purchase agreements (same document steps, not scripted yet); PR refund — **cannot be driven**:
  the bank transaction REFUND button ends in `_action_refund` raising "Refund action is not implemented yet.", so no
  refund request can be created from the UI (only prod data or code creates them); Approved/Disbursed/Paid of PR and
  DR (FarmLink events only).
- Data-consuming (each run uses up one record, `init` fails fast when none is left): `debt` one creditor of the
  `debt_sale_customer` view (its sellable invoice pairs; the view drops the creditor once a confirmed debt SO holds them,
  but not while that SO is still draft, so two debt SOs can hold the same pairs); `return` one
  DS picking; `payment_request` one request; `disbursement` one bill (trade/input) or room on one PO (invest);
  `debt_offset` the open pairs of one customer/vendor couple.

Dispatch the **`flow-runner`** agent (source `<skill-dir>/agents/flow-runner.md`, symlinked into
`~/.omp/agent/agents/`: Haiku 4.5, thinking off, only `bash` +
`read`) with the two commands:
```text
rtk proxy <skill-dir>/scripts/flow-step init <run-dir> flow=<name> base=http://<container>.localhost db=<wt db> [params]
rtk proxy <skill-dir>/scripts/flow-step <run-dir> <step>   # <step> = the last NEXT line; until FLOW DONE / FLOW STOPPED
```
A wrong `<step>` exits 2 without running anything (it also keeps consecutive calls distinct for tool-loop guards).
Never pipe `flow-step` into `head`/`tail`: the closed pipe kills the step mid-way and the run is marked failed.

Script time per flow (2026-09-30, all 10 in a row ≈ 8 min, after `switch_user` moved to the JSON routes): `so` 103 s,
`framework` 55–63 s, `appendix` 45 s, `debt` 66 s, `return` 50 s, `payment_request` 15 s, `disbursement` 28–29 s,
`debt_offset` 41 s. With `flow-runner` add ~1–1.5 min of Haiku turns + screenshot reads per flow; measured on `so`
before that change: 179–206 s / 21 turns / $0.14–0.16 (Opus by hand with the helpers: 367 s / 40 turns / $1.40).
`init` on an existing run dir resumes it at the next step (refuses a stopped, interrupted or finished run): when
`flow-runner` dies on a provider error between steps (seen once: Haiku emitted a 760-char tool name → Anthropic 400),
dispatch a new `flow-runner` with the same commands. Runs on one host may go in parallel (own browser context each),
but never point two runs at the same record (same flow + same data pick): the second one finds it already moved.

### Recipe: customer → SO with vendor → confirm → agreement approved (manual; what flow `so` does)

Verified 2026-09-29 on clones: ~13 min / 85 turns / $2.80 before the helpers (S08575 / CP17833), 7.5 min / 54 turns /
$1.94 with them (S08574 / CP17832). Check every step with **both** the screenshot (what the user sees) and read-only
SQL (what is stored) — see step 6.
1. **Pick a realistic combo** from a recent confirmed SO (same customer, vendor, product, purchase price):
   ```sql
   SELECT s.partner_id, l.vendor_id, l.product_id, l.purchase_price
   FROM sale_order_line l JOIN sale_order s ON s.id = l.order_id
   WHERE s.state = 'sale' AND l.vendor_id IS NOT NULL ORDER BY s.id DESC LIMIT 5;
   ```
2. **New SO**: `odoo_open(B, "sale.action_quotations_with_onboarding")`. Header: customer, company FARMNET,
   payment terms, effective/delivery dates (dd/mm/yyyy), order profit, sign person. Line: product, qty,
   **`vendor_id` (mandatory — no vendor = FarmNet sells itself, wrong for this flow)**, `purchase_price`. `save()`.
   Saving creates the draft RFQ (smart button "1 Purchase") and the sale agreement (button HDMB/ĐH).
3. **Agreements must be complete before confirm** or `action_confirm` raises
   `Partner Bank in agreement CPxxxxx is required` / `Partner Contact in agreement CPxxxxx is required`:
   - sale agreement: partner bank, type `[Sale] Đơn hàng bán`, framework agreement (customer's `reviewed` one), exp. date;
   - purchase agreement: contact, bank, type `[Purchase] Đơn hàng mua`, framework agreement, exp. date.
4. `click_btn("action_confirm")` → SO `sale`, PO `purchase`, agreements New → **To Check**.
5. **Approve** (agreement form `odoo_open(B, "agreement.agreement_action", <id>, model="agreement")`):
   - To Check → To Review: the customer's `biz_ops_2` user (`res_partner.biz_ops_2` → `res_users.login`)
     clicks TO REVIEW (`action_authorize_to_review`); admin cannot (`_can_act_for`).
   - Then each waiting approver clicks APPROVE, in order:
     ```sql
     SELECT ap.approval_stage, ap.approval_role, ap.status, u.login FROM agreement_approver ap
     JOIN res_users u ON u.id = ap.user_id WHERE ap.agreement_id = <id> ORDER BY ap.sequence, ap.id;
     ```
     Stages seen: to_review (Checker) → to_approval (Approval) or exception (several Approvals) → `reviewed` (UI "Approved").
   - Other users only see their own partners' agreements: open the record as admin first, then `switch_user`.
   - Finish with `switch_user("admin")`.
6. Verify each checkpoint on both sides — screenshot (read it back) **and** SQL on the same record:

   | Checkpoint | UI (screenshot) | DB (read-only SQL) |
   |---|---|---|
   | SO line | Vendor column filled on the line, qty, purchase/unit price | `sale_order_line.vendor_id` set, `purchase_price` |
   | SO confirmed | header status **Sales Order**, smart buttons HDMB/ĐH + 1 Purchase | `sale_order.state='sale'`, PO `state='purchase'` for that vendor |
   | Each approval | stage badge moves (To Check → To Review → … ), acting user in the top bar | `agreement.stage`, `agreement_approver.status` for that user |
   | Done | stage badge **Approved**, chatter "The agreement has been approved", back as Administrator | `agreement.stage='reviewed'` |

   Take evidence shots at these checkpoints (not after every click); use `form_state()` / `odoo_errors()` for quick
   non-visual reads in between.

### Recipe: OEM Processing (QT2 / QT1) full flow — `scripts/oem_processing_e2e.py`

Both OEM scripts now run the full approval chain (shared `scripts/oem_e2e_approval.py`, needs env `DB=<wt db>` and
`login_as_any_user` installed): fill the agreement (type Đơn hàng mua/bán, contact, bank, framework HĐNT, expiration),
CONFIRM the order (PO `action_confirm_oem`, SO `action_confirm`) → agreement To Check, project AM TO REVIEW (`action_account_manager_to_review`),
then each waiting approver APPROVE via `switch_user` (OM in To Review → CEO in Exception) → Approved, checked in UI + DB.
Every optional field is attempted; the log prints `filled:` / `not editable here:`. Customer Reference must be unique
and Vendor Reference must keep its prefix. Verified 2026-09-30: projects 40 (Trading), 41 (QT2), 42 (QT1), ~7.5 min.
`OEM_SCENARIO=qt1_stock` runs the stock flow (Consumption Plan filled, no customer line, no SO); default is QT2.
All three flows (Trading, QT2, QT1) verified 2026-09-30 after merging origin/main (projects 32 / 33 / 34).
Every vendor row needs a Payment Term and the project needs Payment Terms, else TO CHECK is blocked.

Verified 2026-09-30 on PR #649 (project 21 / P08299 / S08581). Same run/env contract as the Trading script, plus:
- Needs an **active oem.bom** for the finished product (create it in `odoo shell`: `oem.bom.create({product_id,
  vendor_id=<processor>, line_ids})` then `action_active()`). The processor is read-only on the project and comes
  from the BOM; the BOM dropdown is filtered by the finished product and searches the **reference** (`BOM0…`), not
  the label.
- Steps: project (finished product → BOM → qty, sale price, fee, payment terms, QT2 sale line, vendor, material
  purchase price on the prefilled material row) → TO CHECK → TO REVIEW → REVIEWED → ACTIVE → PO → SO.
- Then by hand, same as Trading: Partner Contact + Bank on both agreements, PO **CONFIRM** (`action_confirm_oem`),
  SO CONFIRM, approvals as biz_ops_2 → Checker → Approval (`odoo shell` + `with_user`).
- Trap: the order's partner turns read-only as soon as the prefilled lines arrive, so `fill_m2o`'s last click can
  raise `not found: div[name=partner_id] input` although the partner is set; the scripts accept that case.

### Recipe: OEM Trading full flow (project → SO/PO → agreement flow 3) — one command

Verified 2026-09-29 on PR #649 (PD-2026-002 / P08327 / S08574 / CP17833). The UI part is scripted:
`scripts/oem_trading_e2e.py` (preloaded helpers only, ~4 min → supervised process, not a bash job):
```text
hub start name=pr<N>-e2e application=sh cwd=<worktree> pty=false args=["-c",
  "BASE=http://<container>.localhost OEM_SHOTS=/tmp/pr-shots/<slug>/e2e BU_NAME=pr<N>-e2e
   browser-use < <skill-dir>/scripts/oem_trading_e2e.py"]
```
`mkdir -p` the `OEM_SHOTS` dir first. Output: `STEP 01-project … 08-so`, `IDS {...}`, then `RESULT: OK` or
`RESULT: FAIL <step> | <dialog text>` (+ `<step>.png`). Defaults match the clone data: product `Tips`, customer
`CAO NAM`, vendor `ĐỒNG GIAO` (override with `OEM_PRODUCT` / `OEM_CUSTOMER` / `OEM_VENDOR` / `OEM_AM` / `OEM_TERM`).

| Step | UI action | Expect |
|---|---|---|
| 01 | new project, OEM Type = Trading, AM, dates, product / customer / purchase / vendor lines, save | Draft, **SO 0 · PO 0** (project creates no documents) |
| 02–05 | TO CHECK → TO REVIEW → MARK REVIEWED (wizard) → ACTIVATE (wizard, conclusion `"approved"`) | Active; header MARK DONE · CANCEL · ALLOCATE |
| 06 | ALLOCATE → add allocation (product, customer, qty 10) | row with unit price from the product summary |
| 07 | PO smart button → CREATE → vendor → Dropship Address → save | lines copied (qty, **price ≠ 0**), `type=oem`, agreement auto-created |
| 08 | SO smart button → CREATE → customer → Payment Terms → save | lines copied, price from allocation, agreement auto-created |

Then by hand (not scripted — shared agreement recipe above):
1. Agreement of the SO: set Partner Contact + Partner Bank (`action_validate` requires them), confirm the SO
   → agreement **To Check**. Since 2026-09-30 OEM agreements have no OEM type: pick the standard Type
   (`Đơn hàng bán` / `Đơn hàng mua`) like a normal SO/PO, or confirm fails with `Agreement Type is required`.
2. Approvals as the real users (`switch_user`, or `odoo shell` + `with_user(...)` when login_as_any_user is not
   installed): biz_ops_2 → `action_authorize_to_review`, then each `waiting` approver → `action_approve`.
   Green flow ends `reviewed` without the CEO exception step (flow 3).
3. SQL check in one query:
   ```sql
   SELECT o.name, o.state, o.type, a.name, a.oem_project_id, t.name, a.stage,
          (SELECT string_agg(product_uom_qty||'@'||price_unit, ',') FROM sale_order_line WHERE order_id=o.id)
   FROM sale_order o JOIN agreement a ON a.id=o.agreement_id LEFT JOIN agreement_type t ON t.id=a.agreement_type_id
   WHERE o.oem_project_id=<project id>;   -- same with purchase_order / purchase_order_line.product_qty
   ```

Traps found on this flow:
- **Stale error dialog blocks every later click** after a failed action; a hash-only `goto_url` keeps it. Close it
  (`dialog_click("OK")`) or reload with `Page.navigate` to `/web?reload=1#…` before judging the next result.
- Section III purchase lines have **no vendor** in the UI (vendor lives in the second table); prefill must treat
  vendorless lines as belonging to every project vendor, or the PO comes out empty.
- SO/PO line `price_unit` is recomputed from the pricelist after an onchange copies it → re-apply the copied price.
- Selection fields are `<select>`: set `.value` + `change` (`set_select` in the script); wizard selections store a
  JSON-quoted key (`"approved"`).
- **Never edit `src/` while the E2E runs**: the dev container auto-reloads Odoo on file changes and the run dies
  with `Connection lost. Trying to reconnect...`. Commit first, then start the run.
- Saving a PO/SO is slow (the agreement hook commits); wait for the form to get an id before navigating away,
  or the next step opens the project mid-save and misses its smart buttons.
- Editable list: `fill()` ends with Tab; Tab out of the last cell adds an empty row → "Invalid fields" on save.
  Fill the last column first. Right after a state change the header re-renders: retry a button click once.
- PO RFQ shows no Confirm button on FarmNet (normal POs too) — not an OEM bug.
- `create_or_update_agreement` calls `cr.commit()`: in tests wrap order creation with
  `patch.object(type(self.env.cr), "commit", lambda cursor: None)` or the test savepoint dies and every later test
  fails with `InFailedSqlTransaction`. RPC-created SOs in tests also need `partner_invoice_id`/`partner_shipping_id`.

### Isolated tests

```bash
rtk make test-fresh MODULE=<module>
```
Log: `<worktree>/tmp-test-fresh-<timestamp>-<module>.log`. Grep it for
`tests when loading database` → must read `0 failed, 0 error(s) of N tests`.
gRPC `Connection refused` errors in the log are expected (no local gRPC) and are not failures.
Common fixture errors: `product.product` needs `categ_id` + `uom_id`; `sale.order` needs `company_id`.

### Self-review hot spots

- `agreement.action_approve` is overridden in `farmnet_debt` and `farmnet_return`, both drop `super()`'s return
  value and neither depends on `farmnet_planning`: never return an action from it; raise, or add a button method.
- Agreement API controllers (`agreement/controllers/agreement.py`, `sale_order.py`) call `action_approve()` and
  ignore the result.

---

## Step 2 — Gate & browser-use Smoke Test

1. Local code gate:
```bash
rtk proxy ruff check src/
rtk proxy ruff format --check src/
rtk proxy xmllint --noout src/<module>/views/<template>.xml
```

2. Smoke test Odoo form/views with the **`browser-use` CLI only** (no other browser):
```bash
BU_NAME=pr<N>-smoke browser-use <<'PY'
t = new_tab("http://<container-slug>.localhost/web")
wait_for_load()
print(t, page_info())
PY
```
Agent Chrome down (port 9223) → run `agent-chrome`; still down → ask the user with `/tmp/agent-chrome.log`.
Local Odoo login wall → `admin/admin` (Step 2.2 above). Never type the user's own credentials.

---

## Step 3 — Visual Diff & Commit

1. Inspect changed files in Orca editor diff:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" file open-changed --mode diff
```

2. Commit & push:
Write message to scratchpad with trailer:
```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```
Run `rtk git commit -F <file>` and push.
`dev/` is gitignored but some files in it are tracked (`dev/compose*.yml`, `dev/module-upgrade.sh`): stage them
with plain `git add -u -- dev/<file>` — `rtk git add` refuses ("paths are ignored") even for tracked files.
New files under `dev/` need `git add -f`.

3. Open PR:
```bash
rtk proxy gh pr create --base main --head <branch> \
  --title "<type>: <description>" --body-file <scratchpad>/pr-body.md
```
Update Orca card:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" worktree set \
  --worktree active \
  --comment "PR #<N> opened, awaiting bot reviews & CI" --json
```

---

## Step 4 & 6 — Watchers (user tab + agent hub process)

1. User's tab in Orca (humans watch it; the agent does not read it):
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" terminal create \
  --worktree active \
  --title "CI-Watcher" \
  --command "rtk proxy gh pr checks <N> --watch" --json
```

2. Agent's watcher — also updates the Orca card, so no manual `worktree set` while checks run:
```text
hub start name=pr<N>-ci application=bash cwd=<worktree> pty=false
  args=["/Users/huyntq/.omp/agent/managed-skills/orca-pr-ship-loop/scripts/pr-watch.sh", "<N>", "<worktree>", "45"]
```
Exit notice → `hub logs name=pr<N>-ci lines=6` → `RESULT: GREEN 9/9` (seen on PR #1263: 3 log lines, no polls).
Jenkins (`ci/*`, `continuous-integration/jenkins/pr-head`) usually settles in 5–10 min.

---

## Step 7 — Human Merge Gate

When CI is 100% green and reviews addressed:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" worktree set \
  --worktree active \
  --workspace-status in-review \
  --comment "CI Green ✅ Ready for Human Merge" --json
```

---

## Step 8 — Teardown

After merge confirmed:
1. Check squash diff — patch-id of the squash commit must equal the branch's (see SKILL.md 8.1; a plain
   `git diff <merge_sha> <branch>` shows every PR merged to main after the branch point):
```bash
cd /Users/huyntq/Documents/techcoop/farmnet-github
M=<merge_sha>; B=<branch>
git diff $M^ $M | git patch-id --stable; git diff $(git merge-base $B $M^) $B | git patch-id --stable
```
2. Tear down Docker stack & filestore:
```bash
rtk proxy make wt-destroy
```
3. Close all Orca terminals in this worktree:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" terminal close --worktree active --all --json
```
4. Remove worktree and Orca workspace card:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" worktree rm --worktree active --force --json
rtk git -C /Users/huyntq/Documents/techcoop/farmnet-github branch -D <branch>
rtk git -C /Users/huyntq/Documents/techcoop/farmnet-github fetch origin --prune
```

## Step 9 — Plane Sync

PR merged → Plane task **In Progress**. **Done** only when a released tag contains the PR (`release-tag` skill).
