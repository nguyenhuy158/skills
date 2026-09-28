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

If Odoo stack is needed for testing:
```bash
rtk proxy make wt-db-clone
rtk proxy make wt-up
rtk proxy make wt-proxy
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
  2. Log still shows `loading <module>/...` / `Registry` not loaded → **the server is upgrading: watch it**
     (poll the log / `curl /web/login` until 200, each call ≤ 30 s). Do not start `make upgrade`.
  3. Server up (HTTP 200) and `latest_version` already equals the manifest → upgrade done; skip `make upgrade`.
  4. Server up but the version is still old → only now run `make upgrade MODULE=<m>` (via `hub start`, > 30 s).


### UI login on a worktree (Step 2.2) — no need to ask the user

1. Log in yourself with `admin` / `admin` on the worktree host via `browser-use` (local clone DB only).
2. Switch to the user the scenario needs with the repo's **`login_as_any_user`** module
   (install it on the worktree DB first if `ir_module_module.state != 'installed'`).
3. `admin/admin` rejected → reset the accounts on the root DB: from the **main checkout** run
   `rtk make clickodoo SCRIPT=/odoo/migration/change-default-lang.py`, then re-clone the worktree DB
   (`make wt-db-clone …`), restart the stack, retry step 1.
4. Take the step 2.2 screenshots while testing; continue the loop without waiting on the user.
5. `browser-use` gotchas seen on Odoo:
   - Screenshots of a background tab can be a stale frame → `activate_tab(current_tab())` before `capture_screenshot`.
   - New/changed JS/SCSS not applied → open with `?debug=assets` and reload bypassing cache
     (`cdp("Network.setCacheDisabled", cacheDisabled=True)`, `cdp("Page.reload", ignoreCache=True)`).
   - Many2one in a dialog: type into its input + dispatch `input`, then click the dropdown item by box center.
   - `login_as_any_user`: POST `/switch/user` `{user_id}` then reload; back to admin via `/switch/admin`.
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
browser-use <<'PY'
new_tab("http://<container-slug>.localhost/web")
wait_for_load()
print(page_info())
PY
```
`browser-use --doctor` fails, or the daemon cannot attach → ask the user to check the `browser-use` CLI and
Chrome remote debugging (`chrome://inspect/#remote-debugging`). Login page → ask the user to sign in; never type credentials.

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

## Step 4 & 6 — Watcher Terminal & CI Status Streaming

1. Spawn dedicated watcher tab in Orca:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" terminal create \
  --worktree active \
  --title "CI-Watcher" \
  --command "rtk proxy gh pr checks <N> --watch" --json
```

2. Update card progress while checks run:
```bash
rtk proxy "/Applications/Orca.app/Contents/Resources/bin/orca" worktree set \
  --worktree active \
  --comment "CI running: 3/5 passing" --json
```

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
1. Check squash diff:
```bash
rtk git -C /Users/huyntq/Documents/techcoop/farmnet-github diff <merge_sha> origin/<branch>
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
