# Hard limits (ask first, every time)

- Git: never `commit --amend` or `push --force`/`--force-with-lease`, never push to `main`/`master`, never `gh pr merge`/`close` unless the user asked for that exact action in this conversation. Follow-up changes are new commits.
- Production: never write to production — `odoo-prod` MCP writes/`execute_method`, prod hosts, prod databases, Dokploy prod deploys, release tags — without an explicit go-ahead naming the action. Read-only queries are fine.
- Data: never drop or truncate a database, delete a filestore, or run `rm -rf` outside a path you created in this task, without confirmation.
- Secrets: never print, paste or commit `.env` values, API keys or passwords; reference them by variable name.
- Nested agents: when launching `omp` from bash inside Orca, unset `ORCA_TERMINAL_HANDLE` and `ORCA_PANE_KEY` (`env -u ORCA_TERMINAL_HANDLE -u ORCA_PANE_KEY omp ...`) so the child does not rename the parent's tab.

# Browser automation

- Use the `browser-use` CLI only (read `skill://browser-use` for helpers). Never agent-browser, Playwright/Puppeteer, Orca's embedded browser, or the omp `browser` eval object.
- It drives one shared headless agent Chrome: CDP `http://127.0.0.1:9223`, profile `~/.chrome-agent`, already logged in to GitHub, Plane and the Odoo envs. It is preconfigured; never launch another Chrome, profile or debug port. If it is down, run `agent-chrome` once; still down → stop and report the exact error.
- Every call names your own session, unique per task/agent: `BU_NAME=<task>-<purpose> browser-use <<'PY' ... PY`. Never `agent`/`default`, never share a name with a parallel agent.
- Open your tab once with `new_tab(url)` (own headless window, always visible) and reuse it with `switch_tab(<id>)`; no `activate_tab` needed. When done, `close_tab()` your tab — this also stops your daemon. Never close tabs you did not open.
- Screenshots: `screenshot(path)` / `capture_screenshot(path=...)`. Set the viewport in each call if it matters (`cdp("Emulation.setDeviceMetricsOverride", ...)`).
- Odoo 16: use the preloaded helpers instead of hand-rolled `js` + clicks — `odoo_login`, `odoo_open(base, action, id)`, `wait_view`, `fill`, `fill_m2o`, `fill_select`, `line_add`/`line_fill`, `save`, `click_btn(name)`, `odoo_errors`, `dialog_click`, `form_state`, `switch_user(login|"admin")`. Dates are typed `dd/mm/yyyy`. Keep each call under 30 s (split long flows over several calls with the same `BU_NAME`). FarmNet flows (`so`, `framework`, `appendix`, `debt`, `return`, `payment_request`, `disbursement`) are scripted: dispatch the `flow-runner` agent (Haiku, thinking off) with `flow-step` — `skill://orca-pr-ship-loop/references/farmnet.md` (also the manual recipe and approver lookup SQL).
- Verify every key state with BOTH the UI and the DB. UI: open the screenshot you just saved and check what the user sees — stage/status badge, header buttons, field values, dialogs/errors, layout. DB: a read-only SQL on the same record — state/stage, ids, links, amounts. A step passes only when both agree; when they disagree, report the mismatch (the UI is what users act on). SQL alone never proves a UI step, and a screenshot alone never proves stored data.
- Want to watch or log in by hand: `agent-chrome --show`, then `agent-chrome --hide` to go back headless.
